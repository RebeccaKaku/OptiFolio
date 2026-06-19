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
        is_critical: If True, missing this metric makes the product incomparable.
    """

    name: str
    weight: float
    higher_is_better: bool
    field: str
    is_critical: bool = False


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
        coverage: Ratio of weights for which metrics were known [0, 1].
        incomparable: True if product was excluded from ranking.
        incomparable_reasons: Why the product is incomparable.
    """

    product_id: str
    name: str
    product_type: str
    score: float
    rank: int
    metrics: Dict[str, float | None] = field(default_factory=dict)
    coverage: float = 1.0
    incomparable: bool = False
    incomparable_reasons: List[str] = field(default_factory=list)

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
        min_coverage: float = 0.8,
    ) -> List[ScreenedProduct]:
        """Score and rank a list of product dicts against screening criteria.

        Steps:
        1. Extract raw metric values, detecting missing data and critical failures.
        2. Filter incomparable products (missing critical fields or low coverage).
        3. Min-max normalise each metric for comparable products.
        4. Weighted-sum score with weight renormalisation for partial data.
        5. Sort by (score DESC, product_id ASC) and assign ranks.

        Returns an empty list when ``products`` is empty.
        """
        if not products:
            return []

        total_weight = sum(c.weight for c in criteria)
        results: List[ScreenedProduct] = []

        # ── 1. Extract values & identify incomparability ──────────────
        for i, p in enumerate(products):
            metrics: Dict[str, float | None] = {}
            reasons: List[str] = []
            known_weight = 0.0

            for c in criteria:
                val = p.get(c.field)
                if val is not None:
                    try:
                        f_val = float(val)
                        metrics[c.field] = f_val
                        known_weight += c.weight
                    except (ValueError, TypeError):
                        metrics[c.field] = None
                else:
                    metrics[c.field] = None

                if metrics[c.field] is None and c.is_critical:
                    reasons.append(f"Missing critical field: {c.field}")

            coverage = known_weight / total_weight if total_weight > 0 else 1.0
            if coverage < min_coverage:
                reasons.append(f"Coverage {coverage:.2f} below threshold {min_coverage}")

            results.append(
                ScreenedProduct(
                    product_id=str(p.get("product_id", i)),
                    name=str(p.get("name", "")),
                    product_type=str(p.get("product_type", "")),
                    score=0.0,
                    rank=0,
                    metrics=metrics,
                    coverage=round(coverage, 4),
                    incomparable=len(reasons) > 0,
                    incomparable_reasons=reasons,
                )
            )

        comparable = [r for r in results if not r.incomparable]

        # ── 2. Normalise metrics for comparable products ──────────────
        if comparable:
            norm_values: List[Dict[str, float]] = [{} for _ in comparable]
            for c in criteria:
                field = c.field
                values = [r.metrics[field] for r in comparable if r.metrics[field] is not None]
                if not values:
                    continue

                v_min = min(values)
                v_max = max(values)
                span = v_max - v_min

                for idx, r in enumerate(comparable):
                    v = r.metrics[field]
                    if v is None:
                        continue

                    if span == 0:
                        n = 0.5
                    else:
                        n = (v - v_min) / span

                    norm_values[idx][field] = 1.0 - n if not c.higher_is_better else n

            # ── 3. Weighted score with weight renormalisation ──────────
            for idx, r in enumerate(comparable):
                active_weights = sum(c.weight for c in criteria if r.metrics[c.field] is not None)
                if active_weights <= 0:
                    r_score = 50.0
                else:
                    s = 0.0
                    for c in criteria:
                        v_norm = norm_values[idx].get(c.field)
                        if v_norm is not None:
                            s += v_norm * (c.weight / active_weights)
                    r_score = round(s * 100, 2)

                # Update in-place in results list via index or just use comparable
                # Since results contains the same objects, we update them
                object.__setattr__(r, "score", r_score)

        # ── 4. Rank comparable products ───────────────────────────────
        # Stable sort: score DESC, then product_id ASC
        comparable.sort(key=lambda x: (-x.score, x.product_id))

        prev_score: float | None = None
        prev_rank: int = 0
        for pos, r in enumerate(comparable, start=1):
            if r.score != prev_score:
                rank = pos
                prev_rank = pos
            else:
                rank = prev_rank

            object.__setattr__(r, "rank", rank)
            prev_score = r.score

        # Final return: comparable (sorted) then incomparable
        incomparable = [r for r in results if r.incomparable]
        return comparable + incomparable


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
