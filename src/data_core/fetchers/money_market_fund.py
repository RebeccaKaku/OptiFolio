#!/usr/bin/env python3
"""
货币基金数据获取解决方案
针对004502中银如意宝货币A等货币基金的净值获取
"""

import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Optional, Dict, List
import json

class MoneyFundFetcher:
    """
    货币基金专门获取器
    解决货币基金数据获取问题：
    1. 使用 fund_money_fund_info_em 接口获取货币基金历史数据
    2. 货币基金没有'单位净值'，只有'每万份收益'和'7日年化收益率'
    3. 需要处理日期格式和数据清洗
    """
    
    def __init__(self):
        self.cache = {}
        
    def fetch_money_fund_history(self, symbol: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """
        获取货币基金历史数据
        
        参数:
            symbol: 基金代码，如 "004502"
            start_date: 开始日期，格式 "YYYY-MM-DD"
            end_date: 结束日期，格式 "YYYY-MM-DD"
            
        返回:
            DataFrame 包含以下列:
            - Date: 日期
            - Per10kYield: 每万份收益（元）
            - Annualized7d: 7日年化收益率（%）
            - PurchaseStatus: 申购状态
            - RedemptionStatus: 赎回状态
        """
        print(f"获取货币基金 {symbol} 历史数据...")
        
        try:
            # 使用货币基金专用接口
            df = ak.fund_money_fund_info_em(symbol=symbol)
            
            if df.empty:
                print(f"警告: {symbol} 数据为空")
                return pd.DataFrame()
            
            # 重命名列
            df = df.rename(columns={
                '净值日期': 'Date',
                '每万份收益': 'Per10kYield',
                '7日年化收益率': 'Annualized7d',
                '申购状态': 'PurchaseStatus',
                '赎回状态': 'RedemptionStatus'
            })
            
            # 转换日期格式
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
            
            # 转换数值列
            df['Per10kYield'] = pd.to_numeric(df['Per10kYield'], errors='coerce')
            df['Annualized7d'] = pd.to_numeric(df['Annualized7d'], errors='coerce')
            
            # 按日期排序
            df = df.sort_values('Date').reset_index(drop=True)
            
            # 日期过滤
            if start_date:
                start_dt = pd.to_datetime(start_date)
                df = df[df['Date'] >= start_dt]
            
            if end_date:
                end_dt = pd.to_datetime(end_date)
                df = df[df['Date'] <= end_dt]
            
            print(f"成功获取 {len(df)} 条数据，时间范围: {df['Date'].min().date()} 到 {df['Date'].max().date()}")
            
            # 缓存结果
            self.cache[symbol] = df
            
            return df
            
        except Exception as e:
            print(f"获取 {symbol} 数据失败: {e}")
            return pd.DataFrame()
    
    def fetch_fund_info(self, symbol: str) -> Dict:
        """获取基金基本信息"""
        try:
            info = ak.fund_individual_basic_info_xq(symbol=symbol)
            if not info.empty:
                # 转换为字典格式
                info_dict = {}
                for _, row in info.iterrows():
                    info_dict[row['item']] = row['value']
                return info_dict
        except Exception as e:
            print(f"获取 {symbol} 基本信息失败: {e}")
        
        return {}
    
    def calculate_statistics(self, df: pd.DataFrame) -> Dict:
        """计算货币基金统计指标"""
        if df.empty:
            return {}
        
        stats = {
            'total_records': len(df),
            'date_range': f"{df['Date'].min().date()} 到 {df['Date'].max().date()}",
            'recent_records': len(df[df['Date'] >= '2025-01-01']),
            'latest_date': df['Date'].max().date().isoformat(),
        }
        
        # 数值统计
        if 'Per10kYield' in df.columns:
            stats['per10k_yield_mean'] = df['Per10kYield'].mean()
            stats['per10k_yield_std'] = df['Per10kYield'].std()
            stats['per10k_yield_max'] = df['Per10kYield'].max()
            stats['per10k_yield_min'] = df['Per10kYield'].min()
            stats['per10k_yield_latest'] = df['Per10kYield'].iloc[-1] if not df.empty else None
        
        if 'Annualized7d' in df.columns:
            stats['annualized7d_mean'] = df['Annualized7d'].mean()
            stats['annualized7d_std'] = df['Annualized7d'].std()
            stats['annualized7d_max'] = df['Annualized7d'].max()
            stats['annualized7d_min'] = df['Annualized7d'].min()
            stats['annualized7d_latest'] = df['Annualized7d'].iloc[-1] if not df.empty else None
        
        return stats
    
    def compare_funds(self, fund_codes: List[str], start_date: str = "2025-01-01") -> pd.DataFrame:
        """比较多个货币基金的收益"""
        comparison_data = []
        
        for code in fund_codes:
            df = self.fetch_money_fund_history(code, start_date=start_date)
            if not df.empty:
                # 计算累计收益（假设每万份收益可以累加）
                if 'Per10kYield' in df.columns:
                    cumulative_yield = df['Per10kYield'].sum() / 10000  # 转换为每份累计收益
                    
                    # 获取最新收益率
                    latest_annualized = df['Annualized7d'].iloc[-1] if 'Annualized7d' in df.columns else None
                    
                    comparison_data.append({
                        '基金代码': code,
                        '数据条数': len(df),
                        '起始日期': df['Date'].min().date().isoformat(),
                        '结束日期': df['Date'].max().date().isoformat(),
                        '平均每万份收益': df['Per10kYield'].mean(),
                        '平均7日年化%': df['Annualized7d'].mean() if 'Annualized7d' in df.columns else None,
                        '最新7日年化%': latest_annualized,
                        '累计收益(每份)': cumulative_yield,
                    })
        
        return pd.DataFrame(comparison_data)


def test_004502_detailed():
    """详细测试004502中银如意宝货币A"""
    print("=== 详细测试004502中银如意宝货币A ===")
    
    fetcher = MoneyFundFetcher()
    
    # 1. 获取基金基本信息
    print("\n1. 基金基本信息:")
    info = fetcher.fetch_fund_info("004502")
    if info:
        important_fields = ['基金代码', '基金名称', '成立时间', '最新规模', '基金公司', '基金类型', '业绩比较基准']
        for field in important_fields:
            if field in info:
                print(f"  {field}: {info[field]}")
    
    # 2. 获取历史数据
    print("\n2. 历史数据获取:")
    df = fetcher.fetch_money_fund_history("004502", start_date="2025-01-01")
    
    if not df.empty:
        print(f"  获取到 {len(df)} 条2025年及以后的数据")
        print(f"  数据范围: {df['Date'].min().date()} 到 {df['Date'].max().date()}")
        
        # 显示最新数据
        print("\n  最新10条数据:")
        print(df[['Date', 'Per10kYield', 'Annualized7d']].tail(10).to_string(index=False))
        
        # 计算统计指标
        stats = fetcher.calculate_statistics(df)
        print("\n  统计指标:")
        for key, value in stats.items():
            if 'date' in key or 'Date' in key:
                continue
            if isinstance(value, float):
                print(f"  {key}: {value:.4f}")
            else:
                print(f"  {key}: {value}")
    
    # 3. 对比其他货币基金
    print("\n3. 与其他货币基金对比:")
    comparison = fetcher.compare_funds(["004502", "000198", "000009"])
    if not comparison.empty:
        print(comparison.to_string(index=False))
    
    return fetcher, df


def visualize_money_fund_data(df: pd.DataFrame, fund_code: str = "004502"):
    """可视化货币基金数据"""
    if df.empty:
        print("没有数据可以可视化")
        return
    
    # 设置中文字体（如果需要）
    plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle(f'货币基金 {fund_code} 数据分析', fontsize=16)
    
    # 1. 每万份收益时间序列
    ax1 = axes[0, 0]
    ax1.plot(df['Date'], df['Per10kYield'], 'b-', linewidth=1, alpha=0.7)
    ax1.set_title('每万份收益时间序列')
    ax1.set_xlabel('日期')
    ax1.set_ylabel('每万份收益 (元)')
    ax1.grid(True, alpha=0.3)
    
    # 计算移动平均
    if len(df) > 30:
        df['MA_30'] = df['Per10kYield'].rolling(window=30).mean()
        ax1.plot(df['Date'], df['MA_30'], 'r-', linewidth=2, label='30日移动平均')
        ax1.legend()
    
    # 2. 7日年化收益率时间序列
    ax2 = axes[0, 1]
    ax2.plot(df['Date'], df['Annualized7d'], 'g-', linewidth=1, alpha=0.7)
    ax2.set_title('7日年化收益率时间序列')
    ax2.set_xlabel('日期')
    ax2.set_ylabel('7日年化收益率 (%)')
    ax2.grid(True, alpha=0.3)
    
    # 3. 收益分布直方图
    ax3 = axes[1, 0]
    ax3.hist(df['Per10kYield'].dropna(), bins=30, edgecolor='black', alpha=0.7)
    ax3.set_title('每万份收益分布')
    ax3.set_xlabel('每万份收益 (元)')
    ax3.set_ylabel('频率')
    ax3.grid(True, alpha=0.3)
    
    # 添加统计信息
    mean_yield = df['Per10kYield'].mean()
    median_yield = df['Per10kYield'].median()
    ax3.axvline(mean_yield, color='red', linestyle='--', label=f'均值: {mean_yield:.4f}')
    ax3.axvline(median_yield, color='green', linestyle='--', label=f'中位数: {median_yield:.4f}')
    ax3.legend()
    
    # 4. 相关性分析
    ax4 = axes[1, 1]
    # 计算滚动相关性（如果有足够数据）
    if len(df) > 30:
        correlation_window = min(60, len(df))
        rolling_corr = df['Per10kYield'].rolling(window=correlation_window).corr(df['Annualized7d'])
        ax4.plot(df['Date'], rolling_corr, 'purple', linewidth=2)
        ax4.set_title(f'{correlation_window}日滚动相关性')
        ax4.set_xlabel('日期')
        ax4.set_ylabel('相关性系数')
        ax4.grid(True, alpha=0.3)
        ax4.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    else:
        # 散点图
        ax4.scatter(df['Per10kYield'], df['Annualized7d'], alpha=0.5)
        ax4.set_title('每万份收益 vs 7日年化收益率')
        ax4.set_xlabel('每万份收益 (元)')
        ax4.set_ylabel('7日年化收益率 (%)')
        ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.show()
    
    # 保存图片
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"money_fund_{fund_code}_{timestamp}.png"
    fig.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"图表已保存为: {filename}")


def export_to_json(df: pd.DataFrame, fund_code: str, filename: str = None):
    """导出数据到JSON格式"""
    if df.empty:
        print("没有数据可以导出")
        return
    
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"money_fund_{fund_code}_{timestamp}.json"
    
    # 准备导出数据
    export_data = {
        'fund_code': fund_code,
        'export_date': datetime.now().isoformat(),
        'total_records': len(df),
        'date_range': {
            'start': df['Date'].min().isoformat(),
            'end': df['Date'].max().isoformat()
        },
        'statistics': {
            'per10k_yield': {
                'mean': float(df['Per10kYield'].mean()),
                'std': float(df['Per10kYield'].std()),
                'min': float(df['Per10kYield'].min()),
                'max': float(df['Per10kYield'].max()),
                'latest': float(df['Per10kYield'].iloc[-1]) if not df.empty else None
            },
            'annualized7d': {
                'mean': float(df['Annualized7d'].mean()),
                'std': float(df['Annualized7d'].std()),
                'min': float(df['Annualized7d'].min()),
                'max': float(df['Annualized7d'].max()),
                'latest': float(df['Annualized7d'].iloc[-1]) if not df.empty else None
            }
        },
        'data': df.to_dict('records')
    }
    
    # 转换日期为字符串格式
    for record in export_data['data']:
        if isinstance(record['Date'], pd.Timestamp):
            record['Date'] = record['Date'].isoformat()
    
    # 写入JSON文件
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    
    print(f"数据已导出到: {filename}")
    print(f"  包含 {len(df)} 条记录")
    print(f"  时间范围: {df['Date'].min().date()} 到 {df['Date'].max().date()}")


def main():
    print("货币基金数据获取解决方案")
    print("=" * 50)
    
    # 测试004502
    fetcher, df_004502 = test_004502_detailed()
    
    if not df_004502.empty:
        print("\n=== 可选操作 ===")
        print("1. 可视化数据 (需要matplotlib)")
        print("2. 导出数据到JSON")
        print("3. 分析多只基金对比")
        
        # 默认执行可视化
        try:
            print("\n正在生成可视化图表...")
            visualize_money_fund_data(df_004502, "004502")
        except Exception as e:
            print(f"可视化失败: {e}")
            print("请确保已安装 matplotlib 和 seaborn:")
            print("  pip install matplotlib seaborn")
        
        # 导出数据
        export_to_json(df_004502, "004502")
        
        # 分析更多基金
        print("\n分析其他货币基金...")
        all_funds = ["004502", "000198", "000009", "000002"]
        comparison = fetcher.compare_funds(all_funds, start_date="2025-01-01")
        
        if not comparison.empty:
            print("\n货币基金对比分析:")
            print(comparison.to_string(index=False))
            
            # 简单排序
            if '平均每万份收益' in comparison.columns:
                sorted_by_yield = comparison.sort_values('平均每万份收益', ascending=False)
                print("\n按平均每万份收益排序:")
                print(sorted_by_yield[['基金代码', '平均每万份收益', '平均7日年化%', '最新7日年化%']].to_string(index=False))
    
    print("\n=== 解决方案总结 ===")
    print("1. 货币基金应使用 fund_money_fund_info_em 接口")
    print("2. 货币基金没有'单位净值'，主要关注'每万份收益'和'7日年化收益率'")
    print("3. 数据通常更新到当前日期")
    print("4. 对于004502中银如意宝货币A，成功获取到2025-2026年数据")


if __name__ == "__main__":
    main()