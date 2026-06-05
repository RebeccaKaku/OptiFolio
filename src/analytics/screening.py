"""Product screening engine — ranks products by explicit criteria.

Design principle: Screening is separate from allocation. The screener
normalizes each metric to 0–1, computes a weighted-sum score, and ranks.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


# ── Dataclasses ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ScreeningCriteria:
    """A single screening dimension.

    Attributes:
        name: Human-readable label (e.g. "7日年化收益率").
        weight: Importance weight in [0, 1].  All weights are renormalised
                to sum to 1 before scoring.
        higher_is_better: True when a larger metric value is desirable.
        field: Key used to look up the raw metric value from each product dict.
    """

    name: str
    weight: float
    higher_is_better: bool
    field: str


@dataclass(frozen=True)
class ScreenedProduct:
    """A ranked screening result for one product.

    Attributes:
        product_id: Unique identifier (e.g. fund code).
        name: Display name.
        product_type: Category string (e.g. "money_market_fund").
        score: Composite score 0–100 (higher is better).
        rank: 1-based rank (1 = best).
        metrics: Raw metric values keyed by field name.
    """

    product_id: str
    name: str
    product_type: str
    score: float
    rank: int
    metrics: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Base screener ────────────────────────────────────────────────────────


class ProductScreener(ABC):
    """Abstract screener that normalises metrics and computes weighted scores.

    Usage: subclass and override ``screen()`` or reuse the default
    implementation with a custom criteria list.
    """

    def screen(
        self,
        products: List[Dict[str, Any]],
        criteria: List[ScreeningCriteria],
    ) -> List[ScreenedProduct]:
        """Score and rank a list of product dicts against screening criteria.

        Steps:
        1. Extract raw metric values for every (product, criterion) pair.
        2. Min-max normalise each metric to [0, 1].
        3. Invert normalised value when *higher_is_better* is False.
        4. Weighted-sum score → scale to 0–100.
        5. Sort descending by score, assign rank.

        Returns an empty list when ``products`` is empty.
        """
        if not products:
            return []

        # ── 1. Extract raw values ──────────────────────────────────────
        raw: List[Dict[str, float]] = []
        for p in products:
            vals: Dict[str, float] = {}
            for c in criteria:
                v = p.get(c.field)
                vals[c.field] = float(v) if v is not None else 0.0
            raw.append(vals)

        # ── 2. Min-max normalise per metric ───────────────────────────
        norm: List[Dict[str, float]] = [{} for _ in products]
        for c in criteria:
            field = c.field
            values = [r[field] for r in raw]
            v_min = min(values)
            v_max = max(values)
            span = v_max - v_min
            if span == 0.0:
                # All identical — every product gets neutral 0.5
                for nd in norm:
                    nd[field] = 0.5
            else:
                for i, r in enumerate(raw):
                    n = (r[field] - v_min) / span
                    norm[i][field] = 1.0 - n if not c.higher_is_better else n

        # ── 3. Normalise weights to sum to 1 ──────────────────────────
        total_w = sum(c.weight for c in criteria)
        if total_w <= 0:
            # All-zero weights → every criterion gets equal weight
            n_criteria = max(len(criteria), 1)
            w_map = {c.field: 1.0 / n_criteria for c in criteria}
        else:
            w_map = {c.field: c.weight / total_w for c in criteria}

        # ── 4. Weighted sum → 0–100 ──────────────────────────────────
        scores: List[float] = []
        for nd in norm:
            s = sum(nd.get(field, 0) * w_map.get(field, 0) for field in w_map)
            scores.append(round(s * 100, 2))

        # ── 5. Rank (descending score) ───────────────────────────────
        indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        rank_by_idx: Dict[int, int] = {}
        prev_score: float | None = None
        prev_rank: int = 0
        for pos, (idx, sc) in enumerate(indexed, start=1):
            if sc != prev_score:
                rank_by_idx[idx] = pos
                prev_rank = pos
            else:
                rank_by_idx[idx] = prev_rank
            prev_score = sc

        # Build results sorted descending by score
        results = [
            ScreenedProduct(
                product_id=str(products[i].get("product_id", i)),
                name=str(products[i].get("name", "")),
                product_type=str(products[i].get("product_type", "")),
                score=scores[i],
                rank=rank_by_idx[i],
                metrics=raw[i],
            )
            for i in range(len(products))
        ]
        results.sort(key=lambda r: r.score, reverse=True)
        return results


# ── Money-market fund screener ──────────────────────────────────────────


class MoneyFundScreener(ProductScreener):
    """Pre-configured screener for money-market funds.

    Criteria (weights sum to 1.0):
      - 7-day annualised yield  (0.40, higher is better)
      - Per-10k-unit yield      (0.20, higher is better)
      - Fund scale (AUM)        (0.15, higher is better)
      - Management fee %        (0.15, lower is better)
      - Redemption speed        (0.10, higher is better)
    """

    DEFAULT_CRITERIA: List[ScreeningCriteria] = [
        ScreeningCriteria(
            name="7日年化收益率",
            weight=0.40,
            higher_is_better=True,
            field="annualized_7d",
        ),
        ScreeningCriteria(
            name="每万份收益",
            weight=0.20,
            higher_is_better=True,
            field="per_10k_yield",
        ),
        ScreeningCriteria(
            name="基金规模",
            weight=0.15,
            higher_is_better=True,
            field="fund_scale",
        ),
        ScreeningCriteria(
            name="管理费率",
            weight=0.15,
            higher_is_better=False,
            field="mgmt_fee",
        ),
        ScreeningCriteria(
            name="赎回到账速度",
            weight=0.10,
            higher_is_better=False,
            field="redemption_days",
        ),
    ]

    def screen_from_fund_data(
        self, funds: List[Dict[str, Any]]
    ) -> List[ScreenedProduct]:
        """Score funds using the default money-market criteria.

        Each fund dict is expected to contain the fields referenced by
        ``DEFAULT_CRITERIA`` plus ``product_id``, ``name``, and
        ``product_type``.

        Args:
            funds: List of fund dicts with raw metrics.

        Returns:
            Ranked list of ``ScreenedProduct``, best first.
        """
        return self.screen(funds, self.DEFAULT_CRITERIA)
