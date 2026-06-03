# Legacy CLI entrypoint. DEPRECATED — use tools/start_app.py for FastAPI
# or tools/ingest_portfolio_prices.py for data ingestion.

import pandas as pd
from src.utils import load_config_with_deep_merge, update_asset_names_in_config
from src.data_loader import DataLoader
from src.math_engine import MathEngine
from src.strategy import Strategy
from src.execution import Execution

def load_config():
    """
    加载并深度合并配置，确保包含 universe.assets
    """
    config = load_config_with_deep_merge()
    
    # 如果配置中没有 universe.assets，尝试从 candidates.yaml 加载
    if 'universe' not in config or 'assets' not in config['universe']:
        import os
        import yaml
        
        candidates_path = "config/candidates.yaml"
        if os.path.exists(candidates_path):
            try:
                with open(candidates_path, 'r', encoding='utf-8') as f:
                    candidates_data = yaml.safe_load(f)
                
                if 'candidates' in candidates_data and 'assets' in candidates_data['candidates']:
                    # 构建 universe 结构
                    config['universe'] = {
                        'assets': candidates_data['candidates']['assets']
                    }
                    print(f">>> [Config] 从 {candidates_path} 加载了 {len(config['universe']['assets'])} 个资产")
                else:
                    print(f">>> [Warning] {candidates_path} 中没有找到 assets 数据")
            except Exception as e:
                print(f">>> [Warning] 加载 {candidates_path} 失败: {e}")
        else:
            print(f">>> [Warning] 未找到 {candidates_path}")
    
    return config

def run():
    print(">>> [System] OptiFolio 初始化...")
    print(">>> [Version] 2.0 - 增强工厂模式 + 多货币支持")
    
    # 1. 加载配置 (The Law) - 使用深度合并
    config = load_config()
    
    # 更新资产名称信息
    config = update_asset_names_in_config(config)
    
    # 解析资产列表：从对象列表中提取 ticker
    asset_list = config['universe']['assets']
    tickers = [item['symbol'] for item in asset_list]
    names = [item['name'] for item in asset_list]
    
    print(f">>> [Config] 目标资产池 ({len(tickers)}):")
    for i, (symbol, name) in enumerate(zip(tickers, names)):
        print(f"    {i+1:2d}. {symbol} - {name}")
    
    print(f">>> [Params] 时间范围: {config['parameters']['start_date']} 至 {config['parameters']['end_date']}")
    print(f">>> [Params] 风险偏好: {config['parameters']['risk_aversion']}, 无风险利率: {config['parameters']['risk_free_rate']}")

    # 2. 感知层 (Data Layer) - 使用增强的DataLoader
    loader = DataLoader(config, processor_strategy="common_start")
    prices = loader.fetch_all_data() 
    
    if prices.empty:
        print(">>> [Error] 获取数据失败，程序退出")
        return
    
    print("\n>>> [Data] 资产价格矩阵预览 (最后5行):")
    print(prices.tail())
    
    print("\n>>> [Data] 资产价格矩阵统计:")
    print(f"    形状: {prices.shape} (天数 × 资产数)")
    print(f"    日期范围: {prices.index.min().date()} 至 {prices.index.max().date()}")

    # 3. 数理层 (Math Layer)
    # 计算统计量
    returns = prices.pct_change().dropna()
    stats = MathEngine.get_stats(returns) 
    print(">>> [Math] 统计量计算完成")
    print(f"    有效天数: {len(returns)}")
    print(f"    年化收益范围: {stats['mu'].min():.2%} 至 {stats['mu'].max():.2%}")

    # 4. 决策层 (Strategy Layer)
    strat_engine = Strategy(config)
    target_weights = strat_engine.optimize(stats['mu'], stats['sigma'])
    
    print("\n>>> [Strategy] 最优仓位建议:")
    # 创建格式化的权重表格
    weight_df = pd.DataFrame({
        '资产': [asset['name'] for asset in config['universe']['assets'] if asset['symbol'] in target_weights.index],
        '代码': target_weights.index,
        '权重': target_weights.values * 100
    })
    weight_df = weight_df.sort_values('权重', ascending=False)
    
    # 显示前10个资产
    pd.set_option('display.max_rows', None)
    pd.set_option('display.width', 1000)
    for _, row in weight_df.iterrows():
        print(f"    {row['代码']:10s} ({row['资产']:20s}): {row['权重']:6.2f}%")
    
    print(f"    总计: {target_weights.sum()*100:.2f}%")

    # 5. 执行层 (Execution Layer)
    if config['system']['mode'] != 'backtest':
        print("\n>>> [Execution] 生成交易建议...")
        executor = Execution(config)
        executor.generate_orders(target_weights)
    else:
        print("\n>>> [Execution] 回测模式 - 跳过订单生成")

if __name__ == "__main__":
    run()
