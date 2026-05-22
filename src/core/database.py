"""
数据库模块 - 使用SQLite存储资产、价格和用户关注数据

设计目标：
1. 替代现有的文件存储，提供结构化数据管理
2. 支持"关注即导入"的自动化流程
3. 存储历史价格数据和计算指标
4. 提供高效查询接口
"""

import sqlite3
import json
import shutil
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
from pathlib import Path
from .paths import get_database_path, get_legacy_database_candidates

class DatabaseManager:
    """
    数据库管理器 - 处理所有数据库操作
    
    数据库设计：
    1. assets - 资产基本信息表
    2. price_history - 历史价格数据表
    3. user_watchlist - 用户关注列表表
    4. calculated_metrics - 计算指标表
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        初始化数据库管理器
        
        Args:
            db_path: SQLite数据库文件路径
        """
        self.db_path = Path(db_path) if db_path is not None else get_database_path()
        self.db_path.parent.mkdir(exist_ok=True)
        self._migrate_legacy_database_file()
        self.conn = None
        self._init_database()

    def _migrate_legacy_database_file(self) -> None:
        """Copy the old FM database file to the OptiFolio path once, if needed."""
        if self.db_path.exists():
            return

        same_dir_legacy = self.db_path.parent / "fm_database.db"
        candidates = [same_dir_legacy, *get_legacy_database_candidates()]
        for legacy_path in candidates:
            if legacy_path == self.db_path:
                continue
            if legacy_path.exists():
                shutil.copy2(legacy_path, self.db_path)
                return
    
    def _init_database(self) -> None:
        """初始化数据库表结构"""
        self._connect()
        
        # 创建资产表
        self._execute("""
            CREATE TABLE IF NOT EXISTS assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT UNIQUE NOT NULL,
                name TEXT,
                asset_type TEXT,
                currency TEXT,
                source TEXT,
                last_updated TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                attributes TEXT  -- JSON格式的扩展属性
            )
        """)
        
        # 创建历史价格表
        self._execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER NOT NULL,
                date DATE NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (asset_id) REFERENCES assets (id),
                UNIQUE(asset_id, date)
            )
        """)
        
        # 创建用户关注表
        self._execute("""
            CREATE TABLE IF NOT EXISTS user_watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER NOT NULL,
                user_id TEXT DEFAULT 'default',  -- 支持多用户扩展
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                notes TEXT,
                FOREIGN KEY (asset_id) REFERENCES assets (id),
                UNIQUE(asset_id, user_id)
            )
        """)
        
        # 创建计算指标表
        self._execute("""
            CREATE TABLE IF NOT EXISTS calculated_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER NOT NULL,
                metric_name TEXT NOT NULL,
                period_days INTEGER,
                value REAL,
                calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (asset_id) REFERENCES assets (id),
                UNIQUE(asset_id, metric_name, period_days)
            )
        """)
        
        # 创建价格索引以提高查询性能
        self._execute("CREATE INDEX IF NOT EXISTS idx_price_asset_date ON price_history (asset_id, date DESC)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_assets_symbol ON assets (symbol)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_watchlist_user_asset ON user_watchlist (user_id, asset_id)")
        
        self._commit()
        
    def _connect(self) -> None:
        """连接到数据库"""
        if self.conn is None:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
    
    def _execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """执行SQL查询"""
        self._connect()
        return self.conn.execute(query, params)
    
    def _executemany(self, query: str, params_list: list) -> None:
        """批量执行SQL查询"""
        self._connect()
        self.conn.executemany(query, params_list)
    
    def _commit(self) -> None:
        """提交事务"""
        if self.conn:
            self.conn.commit()
    
    def close(self) -> None:
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    # ==================== 资产相关操作 ====================
    
    def add_or_update_asset(self, asset_data: Dict[str, Any]) -> int:
        """
        添加或更新资产
        
        Args:
            asset_data: 资产数据字典，必须包含symbol
            
        Returns:
            资产ID
        """
        symbol = asset_data['symbol']
        
        # 检查资产是否已存在
        cursor = self._execute("SELECT id FROM assets WHERE symbol = ?", (symbol,))
        existing = cursor.fetchone()
        
        # 准备数据
        attributes = json.dumps(asset_data.get('attributes', {}), ensure_ascii=False)
        
        if existing:
            # 更新现有资产
            asset_id = existing['id']
            self._execute("""
                UPDATE assets SET 
                    name = ?, asset_type = ?, currency = ?, 
                    source = ?, last_updated = ?, attributes = ?, is_active = 1
                WHERE id = ?
            """, (
                asset_data.get('name', ''),
                asset_data.get('asset_type', ''),
                asset_data.get('currency', ''),
                asset_data.get('source', ''),
                datetime.now().isoformat(),
                attributes,
                asset_id
            ))
        else:
            # 插入新资产
            cursor = self._execute("""
                INSERT INTO assets 
                (symbol, name, asset_type, currency, source, last_updated, attributes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol,
                asset_data.get('name', ''),
                asset_data.get('asset_type', ''),
                asset_data.get('currency', ''),
                asset_data.get('source', ''),
                datetime.now().isoformat(),
                attributes
            ))
            asset_id = cursor.lastrowid
        
        self._commit()
        return asset_id
    
    def get_asset(self, symbol: str) -> Optional[Dict[str, Any]]:
        """根据符号获取资产信息"""
        cursor = self._execute("""
            SELECT * FROM assets WHERE symbol = ? AND is_active = 1
        """, (symbol,))
        row = cursor.fetchone()
        
        if row:
            return self._row_to_dict(row)
        return None
    
    def get_asset_by_id(self, asset_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取资产信息"""
        cursor = self._execute("SELECT * FROM assets WHERE id = ?", (asset_id,))
        row = cursor.fetchone()
        
        if row:
            return self._row_to_dict(row)
        return None
    
    def list_assets(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """列出所有资产"""
        cursor = self._execute("""
            SELECT * FROM assets 
            WHERE is_active = 1 
            ORDER BY symbol
            LIMIT ? OFFSET ?
        """, (limit, offset))
        
        return [self._row_to_dict(row) for row in cursor.fetchall()]
    
    def search_assets(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """搜索资产（按代码或名称）"""
        cursor = self._execute("""
            SELECT * FROM assets 
            WHERE is_active = 1 
            AND (symbol LIKE ? OR name LIKE ?)
            ORDER BY symbol
            LIMIT ?
        """, (f"%{query}%", f"%{query}%", limit))
        
        return [self._row_to_dict(row) for row in cursor.fetchall()]
    
    def deactivate_asset(self, symbol: str) -> bool:
        """停用资产（软删除）"""
        cursor = self._execute(
            "UPDATE assets SET is_active = 0 WHERE symbol = ?", 
            (symbol,)
        )
        self._commit()
        return cursor.rowcount > 0
    
    # ==================== 价格数据操作 ====================
    
    def add_price_data(self, symbol: str, price_data: Dict[str, Any]) -> int:
        """
        添加价格数据
        
        Args:
            symbol: 资产代码
            price_data: 价格数据，必须包含date
        
        Returns:
            添加的记录数
        """
        # 获取资产ID
        asset = self.get_asset(symbol)
        if not asset:
            raise ValueError(f"资产 {symbol} 不存在")
        
        asset_id = asset['id']
        date = price_data['date']
        
        # 检查是否已存在该日期的数据
        cursor = self._execute("""
            SELECT id FROM price_history 
            WHERE asset_id = ? AND date = ?
        """, (asset_id, date))
        
        if cursor.fetchone():
            # 更新现有数据
            self._execute("""
                UPDATE price_history SET 
                    open = ?, high = ?, low = ?, close = ?, volume = ?, source = ?
                WHERE asset_id = ? AND date = ?
            """, (
                price_data.get('open'),
                price_data.get('high'),
                price_data.get('low'),
                price_data.get('close'),
                price_data.get('volume'),
                price_data.get('source', ''),
                asset_id,
                date
            ))
        else:
            # 插入新数据
            self._execute("""
                INSERT INTO price_history 
                (asset_id, date, open, high, low, close, volume, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                asset_id,
                date,
                price_data.get('open'),
                price_data.get('high'),
                price_data.get('low'),
                price_data.get('close'),
                price_data.get('volume'),
                price_data.get('source', '')
            ))
        
        self._commit()
        return 1
    
    def add_price_history(self, symbol: str, df: pd.DataFrame) -> int:
        """
        批量添加历史价格数据
        
        Args:
            symbol: 资产代码
            df: 包含日期索引的DataFrame，列包括open, high, low, close, volume
        
        Returns:
            添加的记录数
        """
        asset = self.get_asset(symbol)
        if not asset:
            raise ValueError(f"资产 {symbol} 不存在")
        
        asset_id = asset['id']
        added_count = 0
        
        # 准备批量插入数据
        data_to_insert = []
        for idx, row in df.iterrows():
            date_str = idx.strftime('%Y-%m-%d') if hasattr(idx, 'strftime') else str(idx)
            
            data_to_insert.append((
                asset_id,
                date_str,
                float(row.get('open', row.get('Close'))),
                float(row.get('high', row.get('Close'))),
                float(row.get('low', row.get('Close'))),
                float(row.get('close', row.get('Close'))),
                float(row.get('volume', 0)),
                'fetcher'
            ))
        
        # 批量插入，忽略重复
        try:
            self._executemany("""
                INSERT OR IGNORE INTO price_history 
                (asset_id, date, open, high, low, close, volume, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, data_to_insert)
            self._commit()
            added_count = len(data_to_insert)
        except Exception as e:
            print(f"[Database] 批量插入价格数据失败: {e}")
            # 回退到逐条插入
            for data in data_to_insert:
                try:
                    self._execute("""
                        INSERT OR IGNORE INTO price_history 
                        (asset_id, date, open, high, low, close, volume, source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, data)
                    added_count += 1
                except:
                    pass
            self._commit()
        
        return added_count
    
    def get_price_history(self, symbol: str, days: int = 30) -> pd.DataFrame:
        """
        获取历史价格数据
        
        Args:
            symbol: 资产代码
            days: 天数（从今天往前推）
            
        Returns:
            DataFrame，索引为日期
        """
        asset = self.get_asset(symbol)
        if not asset:
            return pd.DataFrame()
        
        asset_id = asset['id']
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        cursor = self._execute("""
            SELECT date, open, high, low, close, volume 
            FROM price_history 
            WHERE asset_id = ? AND date >= ? 
            ORDER BY date
        """, (asset_id, start_date.strftime('%Y-%m-%d')))
        
        rows = cursor.fetchall()
        if not rows:
            return pd.DataFrame()
        
        data = []
        for row in rows:
            data.append({
                'Date': row['date'],
                'Open': row['open'],
                'High': row['high'],
                'Low': row['low'],
                'Close': row['close'],
                'Volume': row['volume']
            })
        
        df = pd.DataFrame(data)
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.set_index('Date')
        return df
    
    def get_latest_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取最新价格"""
        asset = self.get_asset(symbol)
        if not asset:
            return None
        
        cursor = self._execute("""
            SELECT date, open, high, low, close, volume 
            FROM price_history 
            WHERE asset_id = ? 
            ORDER BY date DESC 
            LIMIT 1
        """, (asset['id'],))
        
        row = cursor.fetchone()
        if row:
            return {
                'date': row['date'],
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row['volume']
            }
        return None
    
    # ==================== 用户关注操作 ====================
    
    def add_to_watchlist(self, symbol: str, user_id: str = 'default', 
                        notes: str = '') -> bool:
        """
        添加资产到用户关注列表
        
        Args:
            symbol: 资产代码
            user_id: 用户ID（默认为'default'）
            notes: 备注信息
            
        Returns:
            是否成功添加
        """
        # 首先确保资产存在
        asset = self.get_asset(symbol)
        if not asset:
            # 资产不存在，需要先导入
            # 这里应该调用AssetImporter，但先返回False
            return False
        
        try:
            self._execute("""
                INSERT OR REPLACE INTO user_watchlist 
                (asset_id, user_id, notes, is_active)
                VALUES (?, ?, ?, 1)
            """, (asset['id'], user_id, notes))
            self._commit()
            return True
        except Exception as e:
            print(f"[Database] 添加到关注列表失败: {e}")
            return False
    
    def remove_from_watchlist(self, symbol: str, user_id: str = 'default') -> bool:
        """从关注列表中移除资产"""
        asset = self.get_asset(symbol)
        if not asset:
            return False
        
        cursor = self._execute("""
            DELETE FROM user_watchlist 
            WHERE asset_id = ? AND user_id = ?
        """, (asset['id'], user_id))
        self._commit()
        
        return cursor.rowcount > 0
    
    def get_watchlist(self, user_id: str = 'default') -> List[Dict[str, Any]]:
        """获取用户的关注列表"""
        cursor = self._execute("""
            SELECT a.*, w.added_at, w.notes
            FROM assets a
            JOIN user_watchlist w ON a.id = w.asset_id
            WHERE w.user_id = ? AND w.is_active = 1 AND a.is_active = 1
            ORDER BY w.added_at DESC
        """, (user_id,))
        
        return [self._row_to_dict(row) for row in cursor.fetchall()]
    
    def is_in_watchlist(self, symbol: str, user_id: str = 'default') -> bool:
        """检查资产是否在用户关注列表中"""
        asset = self.get_asset(symbol)
        if not asset:
            return False
        
        cursor = self._execute("""
            SELECT 1 FROM user_watchlist 
            WHERE asset_id = ? AND user_id = ? AND is_active = 1
        """, (asset['id'], user_id))
        
        return cursor.fetchone() is not None
    
    # ==================== 指标计算操作 ====================
    
    def save_metric(self, symbol: str, metric_name: str, value: float, 
                   period_days: int = 0) -> bool:
        """保存计算指标"""
        asset = self.get_asset(symbol)
        if not asset:
            return False
        
        try:
            self._execute("""
                INSERT OR REPLACE INTO calculated_metrics 
                (asset_id, metric_name, period_days, value)
                VALUES (?, ?, ?, ?)
            """, (asset['id'], metric_name, period_days, value))
            self._commit()
            return True
        except Exception as e:
            print(f"[Database] 保存指标失败: {e}")
            return False
    
    def get_metric(self, symbol: str, metric_name: str, 
                  period_days: int = 0) -> Optional[float]:
        """获取计算指标"""
        asset = self.get_asset(symbol)
        if not asset:
            return None
        
        cursor = self._execute("""
            SELECT value FROM calculated_metrics 
            WHERE asset_id = ? AND metric_name = ? AND period_days = ?
            ORDER BY calculated_at DESC 
            LIMIT 1
        """, (asset['id'], metric_name, period_days))
        
        row = cursor.fetchone()
        return row['value'] if row else None
    
    def calculate_and_save_volatility(self, symbol: str, days: int = 30) -> Optional[float]:
        """
        计算并保存波动率
        
        Args:
            symbol: 资产代码
            days: 计算天数
            
        Returns:
            波动率值，如果计算失败返回None
        """
        try:
            # 获取价格历史
            df = self.get_price_history(symbol, days + 5)  # 多取几天数据
            
            if df.empty or len(df) < 2:
                return None
            
            # 计算日收益率
            returns = df['Close'].pct_change().dropna()
            
            # 计算年化波动率（假设252个交易日）
            volatility = returns.std() * (252 ** 0.5)
            
            # 保存到数据库
            self.save_metric(symbol, 'volatility', float(volatility), days)
            
            return float(volatility)
        except Exception as e:
            print(f"[Database] 计算波动率失败: {e}")
            return None
    
    def get_recent_volatility(self, symbol: str, days: int = 30) -> Optional[float]:
        """获取最近计算的波动率"""
        return self.get_metric(symbol, 'volatility', days)
    
    # ==================== 统计和报表 ====================
    
    def get_database_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        stats = {}
        
        # 资产统计
        cursor = self._execute("SELECT COUNT(*) as count FROM assets WHERE is_active = 1")
        total_assets = cursor.fetchone()['count']
        stats['total_assets'] = total_assets
        stats['assets_count'] = total_assets  # 兼容性键名
        
        cursor = self._execute("SELECT COUNT(*) as count FROM user_watchlist WHERE is_active = 1")
        total_watchlist = cursor.fetchone()['count']
        stats['total_watchlist'] = total_watchlist
        stats['watchlist_count'] = total_watchlist  # 兼容性键名
        
        cursor = self._execute("SELECT COUNT(*) as count FROM price_history")
        total_price_records = cursor.fetchone()['count']
        stats['total_price_records'] = total_price_records
        stats['price_history_count'] = total_price_records  # 兼容性键名
        
        # 用户统计
        cursor = self._execute("SELECT COUNT(DISTINCT user_id) as count FROM user_watchlist WHERE is_active = 1")
        total_users = cursor.fetchone()['count']
        stats['users_count'] = total_users
        
        # 按类型统计资产
        cursor = self._execute("""
            SELECT asset_type, COUNT(*) as count 
            FROM assets 
            WHERE is_active = 1 
            GROUP BY asset_type
        """)
        stats['assets_by_type'] = {row['asset_type']: row['count'] for row in cursor.fetchall()}
        
        # 最近更新的资产
        cursor = self._execute("""
            SELECT symbol, name, last_updated 
            FROM assets 
            WHERE is_active = 1 
            ORDER BY last_updated DESC 
            LIMIT 5
        """)
        stats['recently_updated'] = [self._row_to_dict(row) for row in cursor.fetchall()]
        
        # 数据库文件信息
        if self.db_path.exists():
            db_file_size = self.db_path.stat().st_size / (1024 * 1024)
            stats['db_file_size_mb'] = db_file_size
            stats['database_file'] = str(self.db_path)
        else:
            stats['database_file'] = str(self.db_path)
            stats['db_file_size_mb'] = 0
        
        return stats
    
    # ==================== 辅助方法 ====================
    
    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """将数据库行转换为字典"""
        result = {}
        for key in row.keys():
            value = row[key]
            
            # 处理JSON字段
            if key == 'attributes' and value:
                try:
                    result[key] = json.loads(value)
                except:
                    result[key] = {}
            elif isinstance(value, str) and key.endswith('_at'):
                # 时间戳字段
                result[key] = value
            else:
                result[key] = value
        
        return result
    
    def migrate_from_file_system(self) -> int:
        """
        从文件系统迁移数据到数据库
        
        Returns:
            迁移的资产数量
        """
        import yaml
        from pathlib import Path
        
        migrated_count = 0
        
        try:
            # 迁移资产注册表
            registry_path = Path("config/asset_registry.yaml")
            if registry_path.exists():
                with open(registry_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                
                if config and 'assets' in config:
                    for asset_data in config['assets']:
                        symbol = asset_data.get('symbol')
                        if symbol and self.get_asset(symbol):
                            continue
                        self.add_or_update_asset(asset_data)
                        migrated_count += 1
            
            # TODO: 迁移价格数据（从data/raw目录）
            # 这需要更复杂的逻辑，因为需要解析CSV/Parquet文件
            
            print(f"[Database] 从文件系统迁移了 {migrated_count} 个资产")
            
        except Exception as e:
            print(f"[Database] 迁移数据失败: {e}")
        
        return migrated_count


# 全局数据库管理器实例
_database_instance = None

def get_database() -> DatabaseManager:
    """
    获取全局数据库管理器实例（单例模式）
    
    Returns:
        DatabaseManager实例
    """
    global _database_instance
    if _database_instance is None:
        _database_instance = DatabaseManager()
    return _database_instance

def close_database() -> None:
    """关闭全局数据库连接"""
    global _database_instance
    if _database_instance:
        _database_instance.close()
        _database_instance = None
