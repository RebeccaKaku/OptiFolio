# src/asset_importer.py
"""Asset Importer - Refactored version delegating to PortfolioBookDatabase and FinData."""
import logging, os, re, json, yaml
from typing import Dict, List, Optional, Any
from datetime import datetime
_log = logging.getLogger(__name__)

class AssetDefinition:
    def __init__(self, symbol, asset_type, name=None, currency=None, conflict_id=None, is_conflict=False, **kwargs):
        self.symbol, self.asset_type, self.name = symbol, asset_type, name or symbol
        self.conflict_id, self.is_conflict = conflict_id, is_conflict
        self.currency = currency or self.infer_default_currency()
        self.attributes = kwargs
        self.source, self.last_updated = kwargs.get('source'), kwargs.get('last_updated')
    def get_full_id(self): return self.conflict_id or self.symbol
    def infer_default_currency(self):
        t = self.asset_type.lower()
        if any(x in t for x in ('us_', 'currency', 'forex')): return 'USD'
        return 'HKD' if 'hk_' in t else 'CNY'
    def update_from_api(self, data):
        if data.get('name'): self.name = data['name']
        if data.get('currency'): self.currency = data['currency']
        for k, v in data.items():
            if k not in ('symbol', 'asset_type', 'name', 'currency', 'source', 'last_updated'): self.attributes[k] = v
        self.source, self.last_updated = data.get('source', 'unknown'), datetime.now().isoformat()
    def to_dict(self):
        res = {'symbol': self.symbol, 'asset_type': self.asset_type, 'name': self.name, 'currency': self.currency, 'attributes': self.attributes.copy()}
        if self.conflict_id: res['conflict_id'] = self.conflict_id
        if self.is_conflict: res['is_conflict'] = self.is_conflict
        if self.source: res['source'] = self.source
        if self.last_updated: res['last_updated'] = self.last_updated
        return res
    @classmethod
    def from_dict(cls, d):
        data = d.copy(); s, t = data.pop('symbol'), data.pop('asset_type')
        n, c = data.pop('name', None), data.pop('currency', None)
        cid, isc = data.pop('conflict_id', None), data.pop('is_conflict', False)
        src, upd = data.pop('source', None), data.pop('last_updated', None)
        at = data.pop('attributes', {})
        for k, v in list(data.items()):
            if k not in at and k not in ('symbol', 'asset_type', 'name', 'currency', 'conflict_id', 'is_conflict', 'source', 'last_updated'): at[k] = v
        inst = cls(s, t, n, c, conflict_id=cid, is_conflict=isc, **at); inst.source, inst.last_updated = src, upd
        return inst

class AssetRegistry:
    def __init__(self, config_path="config/asset_registry.yaml"):
        self._config_path, self._db_instance, self.assets, self.conflicts = config_path, None, {}, {}
        self._init_db(); self.load_config()
    @property
    def config_path(self): return self._config_path
    @config_path.setter
    def config_path(self, v):
        if v != self._config_path: self._config_path, self._db_instance = v, None; self._init_db(); self.load_config()
    def _init_db(self):
        from pathlib import Path
        base = Path(self._config_path).stem + ".sqlite"
        local_dir = Path("local")
        local_dir.mkdir(parents=True, exist_ok=True)
        p = local_dir / base
        from src.core.portfolio_book_db import PortfolioBookDatabase
        self._db_instance = PortfolioBookDatabase(p); self._db_instance.initialize()
    def _sync(self):
        self.assets.clear(); self.conflicts.clear()
        for p in self._db_instance.list_products():
            a = self._from_prod(p)
            if a.is_conflict:
                if a.symbol not in self.conflicts: self.conflicts[a.symbol] = []
                self.conflicts[a.symbol].append(a)
            else: self.assets[a.symbol] = a
        for s in self.conflicts: self.conflicts[s].sort(key=lambda x: x.conflict_id or "")
    def load_config(self):
        self._sync()
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    cfg = yaml.safe_load(f)
                    if cfg and 'assets' in cfg:
                        for d in cfg['assets']: self._db_save(AssetDefinition.from_dict(d))
            except: pass
        self._sync()
    def _to_prod(self, a):
        from src.domain.products import ProductDefinition
        m = a.attributes.copy(); m.update({"is_conflict": a.is_conflict, "conflict_id": a.conflict_id, "symbol": a.symbol, "last_updated": a.last_updated, "source": a.source})
        return ProductDefinition(a.get_full_id(), a.name, a.asset_type, currency=a.currency, data_source=a.source or "manual", metadata=m)
    def _from_prod(self, p):
        m = p.metadata.copy(); isc, cid, s = m.pop("is_conflict", False), m.pop("conflict_id", None), m.pop("symbol", p.product_id)
        u, src = m.pop("last_updated", None), m.pop("source", p.data_source)
        return AssetDefinition(s, p.product_type, p.name, p.currency, cid, isc, source=src, last_updated=u, **m)
    def _db_save(self, a):
        p = self._to_prod(a)
        if self._db_instance.get_product(p.product_id): self._db_instance.update_product(p)
        else: self._db_instance.create_product(p)
    def register_asset(self, a, overwrite=False):
        if not a.symbol or not a.asset_type: return False
        if not a.is_conflict and a.symbol in self.assets and not overwrite: return False
        self._db_save(a); self._sync(); return True
    def register_conflict_asset(self, a):
        if not a.symbol or not a.asset_type: return False
        if a.symbol in self.assets:
            ex = self.assets.pop(a.symbol);
            with self._db_instance.connect() as c: c.execute("DELETE FROM products WHERE product_id=?", (ex.symbol,)); c.commit()
            ex.is_conflict, ex.conflict_id = True, f"{a.symbol}_1"; self._db_save(ex)
        self._sync(); cs = self.conflicts.get(a.symbol, [])
        a.is_conflict, a.conflict_id = True, f"{a.symbol}_{len(cs) + 1}"; self._db_save(a); self._sync(); return True
    def get_asset(self, s, cid=None):
        if cid: return next((a for a in self.conflicts.get(s, []) if a.conflict_id == cid), None)
        return self.assets.get(s)
    def remove_asset(self, s, cid=None):
        a = self.get_asset(s, cid)
        if not a: return False
        with self._db_instance.connect() as c: c.execute("DELETE FROM products WHERE product_id=?", (cid or s,)); c.commit()
        if cid:
            self._sync(); cs = self.conflicts.get(s, [])
            if not cs: a.is_conflict, a.conflict_id = False, None; self.register_asset(a, True)
        self._sync(); return True
    def list_all_assets(self):
        res, seen = [], set()
        for a in list(self.assets.values()) + [item for l in self.conflicts.values() for item in l]:
            if a.get_full_id() not in seen: res.append(a); seen.add(a.get_full_id())
        return res
    def find_assets_by_type(self, t): return [a for a in self.list_all_assets() if a.asset_type == t]
    def detect_currency_from_name(self, n):
        if not n: return 'CNY'
        nu = n.upper()
        if any(k in nu for k in ['美元', 'USD']): return 'USD'
        if any(k in nu for k in ['港币', 'HKD', '港元']): return 'HKD'
        return 'EUR' if any(k in nu for k in ['欧元', 'EUR']) else 'CNY'
    def detect_currency(self, n, d='CNY'):
        try:
            from src.fund_currency_detector import FundCurrencyDetector
            c, _ = FundCurrencyDetector().detect_currency(n); return c if c != 'CNY' or d == 'CNY' else d
        except: r = self.detect_currency_from_name(n); return r if r != 'CNY' else d
    def save_config(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f: yaml.dump({'version': '2.0', 'assets': [a.to_dict() for a in self.list_all_assets()]}, f, allow_unicode=True)

class AssetImporter:
    def __init__(self, registry_path="config/asset_registry.yaml", candidates_path="config/candidates.yaml", **kwargs):
        self.registry, self.candidates_path = AssetRegistry(registry_path), candidates_path
        try:
            from findata.adapters import FETCHER_REGISTRY
            self.valid_asset_types = list(FETCHER_REGISTRY.keys())
        except: self.valid_asset_types = ['cn_stock', 'cn_fund', 'us_equity', 'currency', 'cn_stock_sh', 'cn_stock_sz', 'hk_stock', 'us_stock'] + [f'cn_fund_{x}' for x in ['qdii', 'etf', 'open', 'money', 'lof', 'index']]
    def _infer_asset_type(self, s):
        s = str(s).strip().upper()
        if '/' in s or (len(s) == 6 and s.isalpha()): return 'currency'
        return 'us_equity' if s.isalpha() else 'cn_stock' if s.isdigit() and len(s) == 6 else 'cn_fund'
    def _normalize_symbol(self, s, t):
        s = str(s).strip()
        if t == 'cn_stock':
            sl = s.lower()
            if sl.startswith(('sh', 'sz')): return sl
            if s.isdigit() and len(s) == 6:
                if s.startswith(('600', '601', '603', '605', '688')): return f'sh{s}'
                return f'sz{s}' if s.startswith(('000', '001', '002', '003', '300')) else f'sh{s}'
        return s.upper() if t == 'us_equity' else s
    def import_asset(self, symbol, asset_type=None, name=None, currency=None, refresh=False, **kwargs):
        if asset_type and asset_type not in self.valid_asset_types: return None
        t = asset_type or self._infer_asset_type(symbol); ns = self._normalize_symbol(symbol, t)
        a = AssetDefinition(ns if t == 'cn_stock' else symbol, t, name, currency, **kwargs)
        if name: a.name = name
        if currency: a.currency = currency
        if not currency and a.name: a.currency = self.registry.detect_currency(a.name, a.currency)
        if self.registry.register_asset(a, True): self.registry.save_config(); return a
        return None
    def batch_import(self, symbols: List[str], asset_type: Optional[str] = None) -> Dict[str, bool]:
        return {s: self.import_asset(s, asset_type=asset_type) is not None for s in symbols}

def import_asset(s, t, registry_path="config/asset_registry.yaml", **kwargs): return AssetImporter(registry_path).import_asset(s, t, **kwargs)
def get_asset(s, registry_path="config/asset_registry.yaml"):
    reg = AssetRegistry(registry_path); a = reg.get_asset(s)
    if not a:
        for t in reg.list_all_assets():
            if t.symbol == s or t.symbol.endswith(s): return t
    return a
