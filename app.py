"""
FM Dashboard - 基于Streamlit的可视化界面

功能特性：
1. 资产导入功能（sh000001, AAPL, GBP等）
2. 资产注册表查看
3. 候选资产查看
4. 实际组合查看
5. 资产价格和基本信息展示
6. 回撤、收益率、波动率等指标计算
7. 组合持仓占比可视化
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import sys
import os

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from src.api.enhanced_api_service import get_enhanced_api_service

# 页面配置
st.set_page_config(
    page_title="FM 金融管理仪表板（增强版）",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 初始化增强API服务
@st.cache_resource
def get_api():
    return get_enhanced_api_service()

api_service = get_api()

# 自定义CSS样式
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1E3A8A;
        font-weight: bold;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #3B82F6;
        font-weight: bold;
        margin-top: 1.5rem;
        margin-bottom: 1rem;
    }
    .card {
        background-color: #F8FAFC;
        border-radius: 10px;
        padding: 1.5rem;
        margin-bottom: 1rem;
        border-left: 5px solid #3B82F6;
    }
    .metric-card {
        background-color: #EFF6FF;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
        border: 1px solid #BFDBFE;
    }
    .success-message {
        background-color: #D1FAE5;
        color: #065F46;
        padding: 1rem;
        border-radius: 5px;
        border-left: 5px solid #10B981;
    }
    .error-message {
        background-color: #FEE2E2;
        color: #991B1B;
        padding: 1rem;
        border-radius: 5px;
        border-left: 5px solid #EF4444;
    }
    .warning-message {
        background-color: #FEF3C7;
        color: #92400E;
        padding: 1rem;
        border-radius: 5px;
        border-left: 5px solid #F59E0B;
    }
</style>
""", unsafe_allow_html=True)

# 侧边栏导航
with st.sidebar:
    st.markdown("## 📊 FM 金融管理")
    st.markdown("---")
    
    # 导航菜单
    page = st.radio(
        "导航菜单",
        ["🏠 仪表板", "📈 资产导入", "🏦 资产管理", "📊 组合管理", "📉 分析工具", "⚙️ 系统设置"]
    )
    
    st.markdown("---")
    
    # 系统状态
    st.markdown("### 系统状态")
    
    # 获取系统状态
    with st.spinner("检查系统状态..."):
        system_status = api_service.get_system_status()
    
    if system_status.get("success"):
        status_data = system_status.get("data", {})
        
        # 总体状态
        overall_status = status_data.get("overall_status", "UNKNOWN")
        status_color = "🟢" if overall_status == "OK" else "🟡" if overall_status in ["DEGRADED", "WARNING"] else "🔴"
        st.markdown(f"**总体状态:** {status_color} {overall_status}")
        
        # 资产系统
        asset_system = status_data.get("asset_system", {})
        asset_status = asset_system.get("status", "UNKNOWN")
        asset_count = asset_system.get("total_assets", 0)
        st.markdown(f"**资产系统:** {'🟢' if asset_status == 'OK' else '🔴'} {asset_count}个资产")
        
        # 组合系统
        portfolio_system = status_data.get("portfolio_system", {})
        portfolio_status = portfolio_system.get("status", "UNKNOWN")
        portfolio_value = portfolio_system.get("total_value", 0)
        st.markdown(f"**组合系统:** {'🟢' if portfolio_status == 'OK' else '🔴'} ¥{portfolio_value:,.2f}")
        
        # 数据库信息（如果存在）
        if "database" in status_data:
            db_info = status_data["database"]
            db_status = db_info.get("status", "UNKNOWN")
            st.markdown(f"**数据库:** {'🟢' if db_status == 'OK' else '🔴'} 已连接")
    else:
        error_msg = system_status.get("error", "未知错误")
        st.markdown(f'<div class="error-message">系统状态检查失败: {error_msg}</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 快速操作
    st.markdown("### 快速操作")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔄 刷新缓存", use_container_width=True):
            with st.spinner("清理缓存中..."):
                result = api_service.clear_cache()
                if result["success"]:
                    st.success("缓存清理完成")
                else:
                    st.error("缓存清理失败")
    
    with col2:
        if st.button("📊 更新价格", use_container_width=True):
            with st.spinner("更新资产价格中..."):
                result = api_service.update_asset_prices()
                if result["success"]:
                    st.success(f"价格更新完成: {result['data']['updated']}个资产已更新")
                else:
                    st.error("价格更新失败")

# ==================== 仪表板页面 ====================
if page == "🏠 仪表板":
    st.markdown('<div class="main-header">🏠 FM 金融管理仪表板</div>', unsafe_allow_html=True)
    
    # 快速统计行
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        with st.spinner("获取资产统计..."):
            asset_overview = api_service.get_asset_overview()
            if asset_overview["success"]:
                # 从概览数据中提取资产总数
                overview_data = asset_overview["data"]
                total_assets = overview_data.get("total_assets", 0)
                st.metric("总资产数", f"{total_assets:,}")
    
    with col2:
        with st.spinner("获取组合价值..."):
            portfolio_value = api_service.get_portfolio_value()
            if portfolio_value["success"]:
                total_value = portfolio_value["data"]["total_value"]
                st.metric("组合总价值", f"¥{total_value:,.2f}")
    
    with col3:
        with st.spinner("获取持仓统计..."):
            position_summary = api_service.portfolio_api.get_position_summary()
            if position_summary["success"]:
                positions_count = position_summary["data"]["total_positions"]
                st.metric("持仓数量", f"{positions_count}")
    
    with col4:
        with st.spinner("获取现金余额..."):
            cash_balances = api_service.get_cash_balances()
            if cash_balances["success"]:
                total_cash = cash_balances["data"]["total"]
                st.metric("现金余额", f"¥{total_cash:,.2f}")
    
    st.markdown("---")
    
    # 图表行
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown('<div class="sub-header">📈 资产类型分布</div>', unsafe_allow_html=True)
        
        with st.spinner("获取资产分布..."):
            distribution = api_service.get_asset_type_distribution()
            if isinstance(distribution, dict) and distribution.get("success"):
                dist_data = distribution["data"]
                
                # 饼图数据
                if dist_data.get("by_asset_type"):
                    asset_types = list(dist_data["by_asset_type"].keys())
                    asset_values = [data["value"] for data in dist_data["by_asset_type"].values()]
                    
                    fig = px.pie(
                        values=asset_values,
                        names=asset_types,
                        title="资产类型分布",
                        hole=0.3,
                        color_discrete_sequence=px.colors.qualitative.Set3
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("暂无资产类型分布数据")
            else:
                st.error("获取资产分布失败")
    
    with col2:
        st.markdown('<div class="sub-header">💼 现金与投资比例</div>', unsafe_allow_html=True)
        
        with st.spinner("获取现金投资比例..."):
            if isinstance(distribution, dict) and distribution.get("success"):
                dist_data = distribution["data"]
                
                if dist_data.get("cash_vs_invested"):
                    cash_data = dist_data["cash_vs_invested"]
                    labels = ["现金", "投资"]
                    values = [cash_data["cash"], cash_data["invested"]]
                    
                    fig = go.Figure(data=[go.Pie(
                        labels=labels,
                        values=values,
                        hole=0.3,
                        marker_colors=['#FF6B6B', '#4ECDC4']
                    )])
                    fig.update_layout(title="现金 vs 投资比例")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("暂无现金投资比例数据")
            else:
                st.error("获取现金投资比例失败")
    
    st.markdown("---")
    
    # 再平衡建议
    st.markdown('<div class="sub-header">⚖️ 再平衡建议</div>', unsafe_allow_html=True)
    
    with st.spinner("获取再平衡建议..."):
        recommendations = api_service.get_rebalance_recommendations()
        if isinstance(recommendations, dict) and recommendations.get("success"):
            rec_data = recommendations["data"]["recommendations"]
            
            if rec_data:
                # 转换为DataFrame
                df_rec = pd.DataFrame(rec_data)
                
                # 按优先级分组显示
                tabs = st.tabs(["高优先级", "中优先级", "低优先级"])
                
                for i, priority in enumerate(["high", "medium", "low"]):
                    with tabs[i]:
                        priority_df = df_rec[df_rec["priority"] == priority]
                        if not priority_df.empty:
                            st.dataframe(
                                priority_df[["symbol", "action", "current_weight", "target_weight", "weight_delta", "value_delta"]],
                                use_container_width=True
                            )
                        else:
                            st.info(f"暂无{['高', '中', '低'][i]}优先级建议")
            else:
                st.success("🎉 组合已经平衡，无需调整")
        else:
            st.error("获取再平衡建议失败")

# ==================== 资产导入页面 ====================
elif page == "📈 资产导入":
    st.markdown('<div class="main-header">📈 资产导入</div>', unsafe_allow_html=True)
    
    # 单资产导入
    st.markdown('<div class="sub-header">单资产导入</div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        symbol = st.text_input("资产代码", placeholder="例如: sh000001, AAPL, EUR/USD")
    
    with col2:
        asset_type = st.selectbox(
            "资产类型",
            ["自动识别", "cn_stock", "cn_fund", "us_equity", "currency", "bond", "commodity"]
        )
    
    with col3:
        refresh = st.checkbox("刷新数据")
    
    if st.button("🚀 导入资产", type="primary", use_container_width=True):
        if symbol:
            with st.spinner(f"正在导入资产 {symbol}..."):
                # 处理资产类型
                actual_type = None if asset_type == "自动识别" else asset_type
                
                result = api_service.import_asset(symbol, actual_type, refresh)
                
                if result["success"]:
                    st.markdown(f'<div class="success-message">{result["message"]}</div>', unsafe_allow_html=True)
                    
                    # 显示资产信息
                    asset_info = result["data"]
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("资产名称", asset_info.get("name", "N/A"))
                    with col2:
                        st.metric("资产类型", asset_info.get("asset_type", "N/A"))
                    with col3:
                        st.metric("货币", asset_info.get("currency", "N/A"))
                else:
                    st.markdown(f'<div class="error-message">{result["error"]}</div>', unsafe_allow_html=True)
        else:
            st.warning("请输入资产代码")
    
    st.markdown("---")
    
    # 批量导入
    st.markdown('<div class="sub-header">批量导入</div>', unsafe_allow_html=True)
    
    batch_input = st.text_area(
        "批量资产代码（每行一个）",
        placeholder="sh000001\nAAPL\nEUR/USD\nGBP/JPY",
        height=100
    )
    
    col1, col2 = st.columns(2)
    
    with col1:
        batch_asset_type = st.selectbox(
            "批量资产类型",
            ["自动识别", "cn_stock", "cn_fund", "us_equity", "currency"],
            key="batch_type"
        )
    
    with col2:
        batch_delay = st.slider("导入延迟（秒）", 0.1, 2.0, 0.5, 0.1)
    
    if st.button("🚀 批量导入", type="primary", use_container_width=True):
        if batch_input:
            symbols = [s.strip() for s in batch_input.split("\n") if s.strip()]
            
            with st.spinner(f"正在批量导入 {len(symbols)} 个资产..."):
                # 处理资产类型
                actual_type = None if batch_asset_type == "自动识别" else batch_asset_type
                asset_types = [actual_type] * len(symbols) if actual_type else None
                
                result = api_service.batch_import_assets(symbols, asset_types)
                
                if result["success"]:
                    st.markdown(f'<div class="success-message">{result["message"]}</div>', unsafe_allow_html=True)
                    
                    # 显示批量导入结果
                    summary = result["data"]["summary"]
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("总数", summary["total"])
                    with col2:
                        st.metric("成功", summary["success"], delta=f"{summary['success_rate']:.1%}")
                    with col3:
                        st.metric("失败", summary["failed"])
                    
                    # 显示详细结果
                    with st.expander("查看详细结果"):
                        results_data = result["data"]["results"]
                        for symbol, import_result in results_data.items():
                            status = "✅" if import_result.get("success") else "❌"
                            message = import_result.get("message") or import_result.get("error", "未知错误")
                            st.write(f"{status} {symbol}: {message}")
                else:
                    st.markdown(f'<div class="error-message">{result["error"]}</div>', unsafe_allow_html=True)
        else:
            st.warning("请输入批量资产代码")
    
    st.markdown("---")
    
    # 示例资产
    st.markdown('<div class="sub-header">示例资产</div>', unsafe_allow_html=True)
    
    example_cols = st.columns(5)
    examples = [
        ("sh000001", "上证指数"),
        ("AAPL", "苹果公司"),
        ("EUR/USD", "欧元/美元"),
        ("000001", "华夏成长基金"),
        ("600519", "贵州茅台")
    ]
    
    for i, (symbol, name) in enumerate(examples):
        with example_cols[i]:
            if st.button(f"{symbol}\n{name}", use_container_width=True):
                with st.spinner(f"导入 {symbol}..."):
                    result = api_service.import_asset(symbol, refresh=True)
                    if result["success"]:
                        st.success(f"导入成功: {result['data'].get('name', symbol)}")
                    else:
                        st.error(f"导入失败: {result.get('error', '未知错误')}")

# ==================== 资产管理页面 ====================
elif page == "🏦 资产管理":
    st.markdown('<div class="main-header">🏦 资产管理</div>', unsafe_allow_html=True)
    
    # 搜索和过滤
    col1, col2, col3 = st.columns([3, 2, 1])
    
    with col1:
        search_query = st.text_input("🔍 搜索资产", placeholder="输入代码、名称或类型...")
    
    with col2:
        filter_type = st.selectbox(
            "过滤类型",
            ["全部", "cn_stock", "cn_fund", "us_equity", "currency", "bond", "commodity"]
        )
    
    with col3:
        page_size = st.selectbox("每页数量", [10, 25, 50, 100], index=1)
    
    # 获取资产列表
    with st.spinner("加载资产列表中..."):
        if search_query:
            search_result = api_service.search_assets(search_query, limit=100)
            if search_result["success"]:
                assets = search_result["data"]["assets"]
            else:
                assets = []
                st.error("搜索失败")
        else:
            actual_filter = None if filter_type == "全部" else filter_type
            list_result = api_service.list_assets(actual_filter, page=1, page_size=page_size)
            if list_result["success"]:
                assets = list_result["data"]["assets"]
            else:
                assets = []
                st.error("获取资产列表失败")
    
    # 显示资产表格
    if assets:
        # 转换为DataFrame
        df_assets = pd.DataFrame(assets)
        
        # 选择显示的列
        display_columns = ["symbol", "name", "asset_type", "currency"]
        if "price_info" in df_assets.columns and df_assets["price_info"].notna().any():
            display_columns.append("price_info")
        
        # 创建显示表格
        display_df = df_assets[display_columns].copy()
        
        # 处理价格信息
        if "price_info" in display_df.columns:
            display_df["最新价格"] = display_df["price_info"].apply(
                lambda x: f"{x['latest']:.2f}" if x and 'latest' in x else "N/A"
            )
            display_df["更新日期"] = display_df["price_info"].apply(
                lambda x: x.get('date', 'N/A') if x else "N/A"
            )
            display_df = display_df.drop(columns=["price_info"])
        
        # 重命名列
        display_df = display_df.rename(columns={
            "symbol": "代码",
            "name": "名称",
            "asset_type": "类型",
            "currency": "货币"
        })
        
        # 显示表格
        st.dataframe(
            display_df,
            use_container_width=True,
            column_config={
                "代码": st.column_config.TextColumn(width="small"),
                "名称": st.column_config.TextColumn(width="medium"),
                "类型": st.column_config.TextColumn(width="small"),
                "货币": st.column_config.TextColumn(width="small"),
                "最新价格": st.column_config.TextColumn(width="small"),
                "更新日期": st.column_config.TextColumn(width="small")
            }
        )
        
        # 资产统计
        st.markdown('<div class="sub-header">📊 资产统计</div>', unsafe_allow_html=True)
        
        with st.spinner("获取资产统计..."):
            asset_overview = api_service.get_asset_overview()
            if asset_overview["success"]:
                overview_data = asset_overview["data"]
                
                # 按类型统计 - 使用by_asset_type或by_type
                if overview_data.get("by_asset_type"):
                    type_stats = overview_data["by_asset_type"]
                elif overview_data.get("by_type"):
                    type_stats = overview_data["by_type"]
                else:
                    type_stats = {}
                
                if type_stats:
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("##### 按类型统计")
                        for asset_type, type_data in type_stats.items():
                            if isinstance(type_data, dict):
                                count = type_data.get("count", 0)
                                value = type_data.get("value", 0)
                                percentage = type_data.get("percentage", 0)
                                st.write(f"**{asset_type}:** {count}个 (价值: ¥{value:,.2f}, {percentage:.1%})")
                            else:
                                # 如果只是数值
                                count = type_data
                                st.write(f"**{asset_type}:** {count}个")
                    
                    with col2:
                        # 类型分布饼图
                        types = list(type_stats.keys())
                        counts = []
                        for type_data in type_stats.values():
                            if isinstance(type_data, dict):
                                counts.append(type_data.get("count", 0))
                            else:
                                counts.append(type_data)
                        
                        if any(counts):
                            fig = px.pie(
                                values=counts,
                                names=types,
                                title="资产类型分布",
                                hole=0.3
                            )
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.info("暂无类型分布数据")
                else:
                    st.info("暂无资产类型统计数据")
            else:
                st.error("获取资产概览失败")
    else:
        st.info("暂无资产数据")
    
    st.markdown("---")
    
    # 资产分析工具
    st.markdown('<div class="sub-header">📈 资产分析工具</div>', unsafe_allow_html=True)
    
    analysis_col1, analysis_col2 = st.columns(2)
    
    with analysis_col1:
        analysis_symbol = st.text_input("分析资产代码", placeholder="输入资产代码进行分析")
        analysis_period = st.selectbox(
            "分析周期",
            ["1y", "3m", "6m", "2y", "5y", "10y"],
            index=0
        )
    
    with analysis_col2:
        if analysis_symbol and st.button("开始分析", use_container_width=True):
            with st.spinner(f"分析 {analysis_symbol} 中..."):
                analysis_result = api_service.analyze_asset(analysis_symbol, analysis_period)
                
                if analysis_result["success"]:
                    analysis_data = analysis_result["data"]
                    
                    # 显示基本信息
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("资产名称", analysis_data.get("name", "N/A"))
                    with col2:
                        st.metric("资产类型", analysis_data.get("asset_type", "N/A"))
                    with col3:
                        st.metric("货币", analysis_data.get("currency", "N/A"))
                    
                    # 显示价格信息
                    if analysis_data.get("price_info"):
                        price_info = analysis_data["price_info"]
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("最新价格", f"{price_info.get('latest', 0):.2f}")
                        with col2:
                            st.metric("30日收益", f"{price_info.get('returns_30d', 0):.2%}" if price_info.get('returns_30d') else "N/A")
                        with col3:
                            st.metric("30日波动", f"{price_info.get('volatility_30d', 0):.2%}" if price_info.get('volatility_30d') else "N/A")
                    
                    # 显示性能指标
                    if analysis_data.get("performance"):
                        perf_data = analysis_data["performance"]
                        
                        st.markdown("##### 性能指标")
                        perf_cols = st.columns(4)
                        metrics = [
                            ("年化收益", "annual_return", ".2%"),
                            ("最大回撤", "max_drawdown", ".2%"),
                            ("夏普比率", "sharpe_ratio", ".2f"),
                            ("索提诺比率", "sortino_ratio", ".2f")
                        ]
                        
                        for i, (label, key, fmt) in enumerate(metrics):
                            with perf_cols[i]:
                                value = perf_data.get(key, 0)
                                st.metric(label, format(value, fmt) if value else "N/A")
                else:
                    st.error(f"分析失败: {analysis_result.get('error', '未知错误')}")
    
    st.markdown("---")
    
    # 增强功能：关注列表和价格曲线分析
    st.markdown('<div class="sub-header">🚀 增强功能</div>', unsafe_allow_html=True)
    
    # 关注功能
    st.markdown("##### 📌 关注功能")
    
    col1, col2 = st.columns(2)
    
    with col1:
        watchlist_symbol = st.text_input("资产代码", placeholder="输入资产代码添加到关注列表", key="watchlist_symbol")
        watchlist_notes = st.text_area("备注（可选）", placeholder="添加备注", height=60, key="watchlist_notes")
    
    with col2:
        user_id = st.text_input("用户ID", value="default", key="user_id")
        watchlist_action = st.radio("操作", ["添加关注", "移除关注"], horizontal=True, key="watchlist_action")
    
    if st.button("执行关注操作", type="primary", use_container_width=True):
        if watchlist_symbol:
            with st.spinner(f"{'添加关注' if watchlist_action == '添加关注' else '移除关注'} {watchlist_symbol}..."):
                if watchlist_action == "添加关注":
                    result = api_service.add_to_watchlist(watchlist_symbol, user_id, watchlist_notes)
                else:
                    result = api_service.remove_from_watchlist(watchlist_symbol, user_id)
                
                if result["success"]:
                    st.success(result["message"])
                    
                    if watchlist_action == "添加关注":
                        # 显示添加成功后的信息
                        watchlist_data = result["data"]
                        if isinstance(watchlist_data, dict) and "asset_info" in watchlist_data:
                            asset_info = watchlist_data["asset_info"]
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("资产名称", asset_info.get("name", "N/A"))
                            with col2:
                                st.metric("资产类型", asset_info.get("asset_type", "N/A"))
                            with col3:
                                st.metric("关注状态", "✅ 已关注")
                else:
                    st.error(f"操作失败: {result.get('error', '未知错误')}")
        else:
            st.warning("请输入资产代码")
    
    st.markdown("---")
    
    # 关注列表查看
    if st.button("查看我的关注列表", type="secondary", use_container_width=True):
        with st.spinner("加载关注列表中..."):
            watchlist_result = api_service.get_watchlist(user_id)
            
            if watchlist_result["success"]:
                watchlist_data = watchlist_result["data"]["watchlist"]
                
                if watchlist_data:
                    st.markdown(f"##### 📋 {user_id}的关注列表 ({len(watchlist_data)}个资产)")
                    
                    # 转换为DataFrame显示
                    df_watchlist = pd.DataFrame(watchlist_data)
                    
                    if not df_watchlist.empty:
                        # 选择要显示的列
                        display_cols = ["symbol", "name", "asset_type", "currency", "latest_price", "volatility_30d"]
                        available_cols = [col for col in display_cols if col in df_watchlist.columns]
                        
                        display_df = df_watchlist[available_cols].copy()
                        
                        # 重命名列
                        column_rename = {
                            "symbol": "代码",
                            "name": "名称",
                            "asset_type": "类型",
                            "currency": "货币",
                            "latest_price": "最新价格",
                            "volatility_30d": "30日波动率"
                        }
                        
                        display_df = display_df.rename(columns={k: v for k, v in column_rename.items() if k in display_df.columns})
                        
                        # 格式化数值列
                        if "最新价格" in display_df.columns:
                            display_df["最新价格"] = display_df["最新价格"].apply(lambda x: f"{x:.2f}" if isinstance(x, (int, float)) else x)
                        if "30日波动率" in display_df.columns:
                            display_df["30日波动率"] = display_df["30日波动率"].apply(lambda x: f"{x:.2%}" if isinstance(x, (int, float)) else x)
                        
                        st.dataframe(display_df, use_container_width=True)
                        
                        # 快速操作按钮
                        st.markdown("##### ⚡ 快速操作")
                        watchlist_symbols = list(df_watchlist["symbol"])
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            if st.button("更新所有资产价格", use_container_width=True):
                                with st.spinner(f"更新 {len(watchlist_symbols)} 个资产价格中..."):
                                    update_result = api_service.update_asset_prices(watchlist_symbols)
                                    if update_result["success"]:
                                        st.success(f"价格更新完成: {update_result['data'].get('updated', 0)}个资产已更新")
                                    else:
                                        st.error("价格更新失败")
                        
                            with col2:
                                if st.button("导出关注列表", use_container_width=True):
                                    # 简单导出功能
                                    import io
                                    csv_buffer = io.StringIO()
                                    df_watchlist.to_csv(csv_buffer, index=False)
                                    csv_string = csv_buffer.getvalue()
                                    
                                    st.download_button(
                                        label="下载CSV文件",
                                        data=csv_string,
                                        file_name=f"watchlist_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                        mime="text/csv"
                                    )
                else:
                    st.info(f"{user_id}的关注列表为空")
            else:
                st.error(f"获取关注列表失败: {watchlist_result.get('error', '未知错误')}")
    
    st.markdown("---")
    
    # 价格曲线分析
    st.markdown("##### 📊 价格曲线分析")
    
    price_analysis_symbol = st.text_input("分析资产代码", placeholder="输入资产代码进行价格曲线分析", key="price_analysis_symbol")
    analysis_days = st.slider("分析天数", 30, 365, 90, 30, key="analysis_days")
    
    if st.button("获取价格曲线分析", type="primary", use_container_width=True):
        if price_analysis_symbol:
            with st.spinner(f"获取 {price_analysis_symbol} 价格曲线分析中..."):
                price_result = api_service.get_price_history_with_analysis(price_analysis_symbol, analysis_days)
                
                if price_result["success"]:
                    price_data = price_result["data"]
                    
                    # 显示基本信息
                    if isinstance(price_data, dict) and "asset_info" in price_data:
                        asset_info = price_data["asset_info"]
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("资产名称", asset_info.get("name", "N/A"))
                        with col2:
                            st.metric("资产类型", asset_info.get("asset_type", "N/A"))
                        with col3:
                            st.metric("分析天数", analysis_days)
                    
                    # 显示价格曲线
                    if "price_history" in price_data:
                        price_history = price_data["price_history"]
                        
                        if isinstance(price_history, dict) and "data" in price_history:
                            df_prices = pd.DataFrame(price_history["data"])
                            
                            if not df_prices.empty and "date" in df_prices.columns and "price" in df_prices.columns:
                                fig = px.line(
                                    df_prices,
                                    x="date",
                                    y="price",
                                    title=f"{price_analysis_symbol} 价格走势 ({analysis_days}天)",
                                    labels={"date": "日期", "price": "价格"}
                                )
                                st.plotly_chart(fig, use_container_width=True)
                    
                    # 显示技术指标
                    if "technical_indicators" in price_data:
                        tech_indicators = price_data["technical_indicators"]
                        
                        st.markdown("##### 📈 技术指标")
                        
                        if isinstance(tech_indicators, dict):
                            tech_cols = st.columns(3)
                            indicator_groups = [
                                ["ma_short", "ma_medium", "ma_long"],
                                ["rsi", "macd", "bollinger_upper"],
                                ["bollinger_lower", "volume_avg", "atr"]
                            ]
                            
                            for i, group in enumerate(indicator_groups):
                                with tech_cols[i]:
                                    for indicator in group:
                                        if indicator in tech_indicators:
                                            value = tech_indicators[indicator]
                                            display_name = {
                                                "ma_short": "短期均线",
                                                "ma_medium": "中期均线",
                                                "ma_long": "长期均线",
                                                "rsi": "RSI指标",
                                                "macd": "MACD",
                                                "bollinger_upper": "布林上轨",
                                                "bollinger_lower": "布林下轨",
                                                "volume_avg": "平均成交量",
                                                "atr": "ATR波动率"
                                            }.get(indicator, indicator)
                                            
                                            if isinstance(value, (int, float)):
                                                if indicator == "rsi":
                                                    st.metric(display_name, f"{value:.2f}")
                                                else:
                                                    st.metric(display_name, f"{value:.4f}")
                    
                    # 显示波动率分析
                    if "volatility_analysis" in price_data:
                        vol_analysis = price_data["volatility_analysis"]
                        
                        st.markdown("##### 📉 波动率分析")
                        
                        if isinstance(vol_analysis, dict):
                            vol_cols = st.columns(4)
                            vol_metrics = [
                                ("daily_volatility", "日波动率", ".2%"),
                                ("annual_volatility", "年化波动率", ".2%"),
                                ("max_daily_change", "最大单日变动", ".2%"),
                                ("volatility_regime", "波动率区间", None)
                            ]
                            
                            for i, (key, label, fmt) in enumerate(vol_metrics):
                                with vol_cols[i]:
                                    if key in vol_analysis:
                                        value = vol_analysis[key]
                                        if fmt:
                                            st.metric(label, format(value, fmt) if isinstance(value, (int, float)) else str(value))
                                        else:
                                            st.metric(label, str(value))
                else:
                    st.error(f"获取价格曲线分析失败: {price_result.get('error', '未知错误')}")
        else:
            st.warning("请输入资产代码")
    
    st.markdown("---")
    
    # 资产指标仪表板
    st.markdown("##### 📋 资产指标仪表板")
    
    dashboard_symbol = st.text_input("资产代码（指标仪表板）", placeholder="输入资产代码获取完整指标", key="dashboard_symbol")
    
    if st.button("获取资产指标仪表板", type="primary", use_container_width=True):
        if dashboard_symbol:
            with st.spinner(f"获取 {dashboard_symbol} 指标仪表板中..."):
                dashboard_result = api_service.get_asset_metrics_dashboard(dashboard_symbol)
                
                if dashboard_result["success"]:
                    dashboard_data = dashboard_result["data"]
                    
                    # 显示完整仪表板
                    if isinstance(dashboard_data, dict):
                        # 基本信息卡片
                        st.markdown("###### 🏷️ 基本信息")
                        if "asset_info" in dashboard_data:
                            asset_info = dashboard_data["asset_info"]
                            info_cols = st.columns(4)
                            with info_cols[0]:
                                st.metric("资产名称", asset_info.get("name", "N/A"))
                            with info_cols[1]:
                                st.metric("资产类型", asset_info.get("asset_type", "N/A"))
                            with info_cols[2]:
                                st.metric("货币", asset_info.get("currency", "N/A"))
                            with info_cols[3]:
                                st.metric("数据源", asset_info.get("source", "N/A"))
                        
                        # 价格信息卡片
                        st.markdown("###### 💰 价格信息")
                        if "price_info" in dashboard_data:
                            price_info = dashboard_data["price_info"]
                            price_cols = st.columns(4)
                            with price_cols[0]:
                                st.metric("最新价格", f"{price_info.get('latest', 0):.2f}" if price_info.get('latest') else "N/A")
                            with price_cols[1]:
                                st.metric("今日变动", f"{price_info.get('daily_change', 0):.2%}" if price_info.get('daily_change') else "N/A")
                            with price_cols[2]:
                                st.metric("30日收益", f"{price_info.get('returns_30d', 0):.2%}" if price_info.get('returns_30d') else "N/A")
                            with price_cols[3]:
                                st.metric("30日波动", f"{price_info.get('volatility_30d', 0):.2%}" if price_info.get('volatility_30d') else "N/A")
                        
                        # 风险评估卡片
                        st.markdown("###### ⚠️ 风险评估")
                        if "risk_metrics" in dashboard_data:
                            risk_metrics = dashboard_data["risk_metrics"]
                            risk_cols = st.columns(3)
                            with risk_cols[0]:
                                st.metric("VaR (95%)", f"{risk_metrics.get('var_95', 0):.2%}" if risk_metrics.get('var_95') else "N/A")
                            with risk_cols[1]:
                                st.metric("CVaR (95%)", f"{risk_metrics.get('cvar_95', 0):.2%}" if risk_metrics.get('cvar_95') else "N/A")
                            with risk_cols[2]:
                                st.metric("最大回撤", f"{risk_metrics.get('max_drawdown', 0):.2%}" if risk_metrics.get('max_drawdown') else "N/A")
                        
                        # 投资建议卡片
                        st.markdown("###### 💡 投资建议")
                        if "investment_advice" in dashboard_data:
                            advice = dashboard_data["investment_advice"]
                            
                            if isinstance(advice, dict):
                                advice_cols = st.columns(2)
                                with advice_cols[0]:
                                    st.metric("建议评级", advice.get("rating", "N/A"))
                                with advice_cols[1]:
                                    st.metric("风险等级", advice.get("risk_level", "N/A"))
                            
                            st.markdown(f"**理由:** {advice.get('reason', '无')}")
                            
                            if "recommendations" in advice and isinstance(advice["recommendations"], list):
                                st.markdown("**具体建议:**")
                                for rec in advice["recommendations"]:
                                    st.write(f"- {rec}")
                else:
                    st.error(f"获取资产指标仪表板失败: {dashboard_result.get('error', '未知错误')}")
        else:
            st.warning("请输入资产代码")

# ==================== 组合管理页面 ====================
elif page == "📊 组合管理":
    st.markdown('<div class="main-header">📊 组合管理</div>', unsafe_allow_html=True)
    
    # 组合概览
    st.markdown('<div class="sub-header">📈 组合概览</div>', unsafe_allow_html=True)
    
    with st.spinner("获取组合信息..."):
        portfolio_snapshot = api_service.get_portfolio_snapshot()
        
        if isinstance(portfolio_snapshot, dict) and portfolio_snapshot.get("success"):
            snapshot_data = portfolio_snapshot["data"]
            portfolio_value = snapshot_data["portfolio_value"]
            position_summary = snapshot_data["position_summary"]
            
            # 关键指标
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("组合总价值", f"¥{portfolio_value['total_value']:,.2f}")
            
            with col2:
                st.metric("持仓价值", f"¥{portfolio_value['portfolio_value']:,.2f}")
            
            with col3:
                st.metric("现金价值", f"¥{portfolio_value['cash_value']:,.2f}")
            
            with col4:
                cash_percentage = portfolio_value['cash_value'] / portfolio_value['total_value'] if portfolio_value['total_value'] > 0 else 0
                st.metric("现金比例", f"{cash_percentage:.1%}")
            
            st.markdown("---")
            
            # 持仓详情
            st.markdown('<div class="sub-header">💼 当前持仓</div>', unsafe_allow_html=True)
            
            if position_summary.get("positions"):
                positions = position_summary["positions"]
                
                # 转换为DataFrame
                df_positions = pd.DataFrame(positions)
                
                if not df_positions.empty:
                    # 选择显示的列
                    display_df = df_positions[["symbol", "shares", "price", "currency", "value", "weight"]].copy()
                    
                    # 格式化
                    display_df["价格"] = display_df["price"].apply(lambda x: f"{x:,.2f}")
                    display_df["价值"] = display_df["value"].apply(lambda x: f"¥{x:,.2f}")
                    display_df["权重"] = display_df["weight"].apply(lambda x: f"{x:.2%}")
                    display_df["股数"] = display_df["shares"].apply(lambda x: f"{x:,.0f}")
                    
                    # 重命名列
                    display_df = display_df.rename(columns={
                        "symbol": "代码",
                        "currency": "货币"
                    })
                    
                    # 显示表格
                    st.dataframe(
                        display_df[["代码", "股数", "价格", "货币", "价值", "权重"]],
                        use_container_width=True,
                        column_config={
                            "代码": st.column_config.TextColumn(width="small"),
                            "股数": st.column_config.TextColumn(width="medium"),
                            "价格": st.column_config.TextColumn(width="small"),
                            "货币": st.column_config.TextColumn(width="small"),
                            "价值": st.column_config.TextColumn(width="medium"),
                            "权重": st.column_config.TextColumn(width="small")
                        }
                    )
                    
                    # 持仓分布图
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # 按资产类型分布
                        if position_summary.get("by_type"):
                            type_data = position_summary["by_type"]
                            types = list(type_data.keys())
                            values = [data["value"] for data in type_data.values()]
                            
                            fig = px.pie(
                                values=values,
                                names=types,
                                title="按资产类型分布",
                                hole=0.3
                            )
                            st.plotly_chart(fig, use_container_width=True)
                    
                    with col2:
                        # 按货币分布
                        if position_summary.get("by_currency"):
                            currency_data = position_summary["by_currency"]
                            currencies = list(currency_data.keys())
                            values = [data["value"] for data in currency_data.values()]
                            
                            fig = px.pie(
                                values=values,
                                names=currencies,
                                title="按货币分布",
                                hole=0.3
                            )
                            st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("暂无持仓数据")
            else:
                st.info("暂无持仓数据")
        else:
            st.error("获取组合信息失败")
    
    st.markdown("---")
    
    # 持仓操作
    st.markdown('<div class="sub-header">⚙️ 持仓操作</div>', unsafe_allow_html=True)
    
    op_tabs = st.tabs(["添加持仓", "移除持仓", "更新现金"])
    
    with op_tabs[0]:
        col1, col2 = st.columns(2)
        
        with col1:
            add_symbol = st.text_input("资产代码", key="add_symbol")
        
        with col2:
            add_shares = st.number_input("股份数量", min_value=0.0, value=100.0, step=10.0)
        
        if st.button("添加持仓", type="primary", use_container_width=True):
            if add_symbol:
                with st.spinner(f"添加持仓 {add_symbol}..."):
                    result = api_service.add_position(add_symbol, add_shares)
                    if result["success"]:
                        st.success(result["message"])
                    else:
                        st.error(result["error"])
            else:
                st.warning("请输入资产代码")
    
    with op_tabs[1]:
        # 获取当前持仓
        with st.spinner("获取持仓列表..."):
            holdings_result = api_service.get_current_holdings()
            if holdings_result["success"]:
                holdings = holdings_result["data"]["holdings"]
                
                if holdings:
                    remove_symbol = st.selectbox("选择持仓", list(holdings.keys()))
                    
                    if st.button("移除持仓", type="primary", use_container_width=True):
                        with st.spinner(f"移除持仓 {remove_symbol}..."):
                            result = api_service.remove_position(remove_symbol)
                            if result["success"]:
                                st.success(result["message"])
                            else:
                                st.error(result["error"])
                else:
                    st.info("暂无持仓可移除")
            else:
                st.error("获取持仓列表失败")
    
    with op_tabs[2]:
        col1, col2 = st.columns(2)
        
        with col1:
            update_currency = st.text_input("货币代码", value="CNY", key="update_currency")
        
        with col2:
            update_amount = st.number_input("金额", min_value=0.0, value=0.0, step=1000.0)
        
        if st.button("更新现金", type="primary", use_container_width=True):
            if update_currency:
                with st.spinner(f"更新现金 {update_currency}..."):
                    result = api_service.update_cash(update_currency, update_amount)
                    if result["success"]:
                        st.success(result["message"])
                    else:
                        st.error(result["error"])
            else:
                st.warning("请输入货币代码")

# ==================== 分析工具页面 ====================
elif page == "📉 分析工具":
    st.markdown('<div class="main-header">📉 分析工具</div>', unsafe_allow_html=True)
    
    # 性能分析
    st.markdown('<div class="sub-header">📊 性能分析</div>', unsafe_allow_html=True)
    
    with st.spinner("获取性能数据..."):
        performance_data = api_service.get_performance_chart_data(365)
        
        if performance_data["success"]:
            perf_data = performance_data["data"]
            
            # 累计收益图表
            fig = go.Figure()
            
            # 累计收益线
            fig.add_trace(go.Scatter(
                x=perf_data["dates"],
                y=perf_data["cumulative_returns"],
                mode='lines',
                name='累计收益',
                line=dict(color='#3B82F6', width=2)
            ))
            
            # 运行最大值线
            fig.add_trace(go.Scatter(
                x=perf_data["dates"],
                y=perf_data["running_max"],
                mode='lines',
                name='运行最大值',
                line=dict(color='#10B981', width=1, dash='dash')
            ))
            
            fig.update_layout(
                title=f"累计收益走势 ({perf_data['period']})",
                xaxis_title="日期",
                yaxis_title="累计收益",
                hovermode='x unified',
                template='plotly_white'
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # 回撤图表
            fig2 = go.Figure()
            
            fig2.add_trace(go.Scatter(
                x=perf_data["dates"],
                y=perf_data["drawdown"],
                mode='lines',
                name='回撤',
                fill='tozeroy',
                fillcolor='rgba(239, 68, 68, 0.3)',
                line=dict(color='#EF4444', width=2)
            ))
            
            fig2.update_layout(
                title="回撤走势",
                xaxis_title="日期",
                yaxis_title="回撤",
                hovermode='x unified',
                template='plotly_white'
            )
            
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.error("获取性能数据失败")
    
    st.markdown("---")
    
    # 风险分析
    st.markdown('<div class="sub-header">⚠️ 风险分析</div>', unsafe_allow_html=True)
    
    with st.spinner("获取风险指标..."):
        risk_data = api_service.get_risk_metrics_data()
        
        if isinstance(risk_data, dict) and risk_data.get("success"):
            risk_metrics = risk_data["data"]
            
            # 风险指标卡片
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                volatility = risk_metrics["portfolio_metrics"].get("volatility", 0)
                st.metric("年化波动率", f"{volatility:.2%}")
            
            with col2:
                max_drawdown = risk_metrics["portfolio_metrics"].get("max_drawdown", 0)
                st.metric("最大回撤", f"{max_drawdown:.2%}")
            
            with col3:
                sharpe = risk_metrics["portfolio_metrics"].get("sharpe_ratio", 0)
                st.metric("夏普比率", f"{sharpe:.2f}")
            
            with col4:
                sortino = risk_metrics["portfolio_metrics"].get("sortino_ratio", 0)
                st.metric("索提诺比率", f"{sortino:.2f}")
            
            # VaR分析
            if risk_metrics.get("portfolio_risk"):
                portfolio_risk = risk_metrics["portfolio_risk"]
                
                st.markdown("##### VaR分析")
                
                var_cols = st.columns(3)
                
                with var_cols[0]:
                    var_historical = portfolio_risk.get("var_historical", 0)
                    st.metric("历史VaR (95%)", f"{var_historical:.2%}")
                
                with var_cols[1]:
                    cvar_historical = portfolio_risk.get("cvar_historical", 0)
                    st.metric("历史CVaR (95%)", f"{cvar_historical:.2%}")
                
                with var_cols[2]:
                    var_parametric = portfolio_risk.get("var_parametric", 0)
                    st.metric("参数VaR (95%)", f"{var_parametric:.2%}")
            
            # 压力测试
            if risk_metrics.get("stress_tests"):
                stress_tests = risk_metrics["stress_tests"]
                
                st.markdown("##### 压力测试")
                
                # 历史情景
                st.markdown("**历史情景:**")
                for scenario in stress_tests.get("historical_scenarios", []):
                    st.write(f"- {scenario['name']}: {scenario['impact']} (恢复时间: {scenario['recovery_months']}个月)")
                
                # 假设情景
                st.markdown("**假设情景:**")
                for scenario in stress_tests.get("hypothetical_scenarios", []):
                    st.write(f"- {scenario['name']}: {scenario['impact']}")
        else:
            st.error("获取风险指标失败")
    
    st.markdown("---")
    
    # 资产比较
    st.markdown('<div class="sub-header">📊 资产比较</div>', unsafe_allow_html=True)
    
    compare_symbols = st.text_input(
        "比较资产（逗号分隔）",
        placeholder="例如: sh000001,AAPL,EUR/USD"
    )
    
    if compare_symbols:
        symbols = [s.strip() for s in compare_symbols.split(",") if s.strip()]
        
        if len(symbols) >= 2:
            if st.button("开始比较", type="primary", use_container_width=True):
                with st.spinner("比较资产中..."):
                    compare_result = api_service.compare_assets(symbols)
                    
                    if compare_result["success"]:
                        compare_data = compare_result["data"]["comparison"]
                        
                        # 转换为DataFrame
                        df_compare = pd.DataFrame(compare_data)
                        
                        if not df_compare.empty:
                            # 显示比较表格
                            st.dataframe(
                                df_compare,
                                use_container_width=True
                            )
                            
                            # 可视化比较
                            if "return" in df_compare.columns and "volatility" in df_compare.columns:
                                fig = px.scatter(
                                    df_compare,
                                    x="volatility",
                                    y="return",
                                    text="symbol",
                                    title="收益-风险散点图",
                                    labels={
                                        "volatility": "波动率",
                                        "return": "收益率"
                                    }
                                )
                                fig.update_traces(textposition='top center')
                                st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.error(f"比较失败: {compare_result.get('error', '未知错误')}")
        else:
            st.warning("至少需要2个资产进行比较")

# ==================== 系统设置页面 ====================
elif page == "⚙️ 系统设置":
    st.markdown('<div class="main-header">⚙️ 系统设置</div>', unsafe_allow_html=True)
    
    # 缓存管理
    st.markdown('<div class="sub-header">🗑️ 缓存管理</div>', unsafe_allow_html=True)
    
    cache_type = st.radio(
        "选择缓存类型",
        ["全部缓存", "资产缓存", "组合缓存", "仪表板缓存"],
        horizontal=True
    )
    
    cache_type_map = {
        "全部缓存": "all",
        "资产缓存": "asset",
        "组合缓存": "portfolio",
        "仪表板缓存": "dashboard"
    }
    
    if st.button("清理缓存", type="primary", use_container_width=True):
        with st.spinner("清理缓存中..."):
            result = api_service.clear_cache(cache_type_map[cache_type])
            if result["success"]:
                st.success(result["message"])
                
                # 显示缓存统计
                cache_stats = result["data"]["cache_stats"]
                st.markdown("##### 缓存统计")
                st.json(cache_stats)
            else:
                st.error(result["error"])
    
    st.markdown("---")
    
    # 数据导出
    st.markdown('<div class="sub-header">💾 数据导出</div>', unsafe_allow_html=True)
    
    export_format = st.selectbox("导出格式", ["json", "csv"])
    
    if st.button("导出系统数据", type="primary", use_container_width=True):
        with st.spinner("导出数据中..."):
            result = api_service.export_system_data(export_format)
            if result["success"]:
                st.success(result["message"])
                
                export_data = result["data"]
                
                # 显示导出信息
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("导出格式", export_data["format"].upper())
                with col2:
                    st.metric("文件大小", f"{export_data['size_bytes']:,} 字节")
                
                # 显示导出内容
                with st.expander("查看导出内容"):
                    st.code(export_data["content"], language=export_format)
                
                # 下载按钮
                st.download_button(
                    label="下载导出文件",
                    data=export_data["content"],
                    file_name=f"fm_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{export_format}",
                    mime="application/json" if export_format == "json" else "text/csv"
                )
            else:
                st.error(result["error"])
    
    st.markdown("---")
    
    # 系统信息
    st.markdown('<div class="sub-header">ℹ️ 系统信息</div>', unsafe_allow_html=True)
    
    with st.spinner("获取系统信息..."):
        system_status = api_service.get_system_status()
        
        if system_status["success"]:
            status_data = system_status["data"]
            
            info_cols = st.columns(2)
            
            with info_cols[0]:
                st.markdown("##### 系统状态")
                st.write(f"**版本:** {status_data['version']}")
                st.write(f"**总体状态:** {status_data['overall_status']}")
                st.write(f"**更新时间:** {status_data['timestamp']}")
            
            with info_cols[1]:
                st.markdown("##### 组件状态")
                for component, info in status_data.items():
                    if component.endswith("_system"):
                        component_name = component.replace("_system", "").capitalize()
                        status = info["status"]
                        status_icon = "✅" if status == "OK" else "⚠️" if status == "DEGRADED" else "❌"
                        st.write(f"**{component_name}:** {status_icon} {status}")
        else:
            st.error("获取系统信息失败")
    
    st.markdown("---")
    
    # 网络接口测试
    st.markdown('<div class="sub-header">🌐 网络接口测试</div>', unsafe_allow_html=True)
    
    # 网络状态概览
    with st.spinner("获取网络状态..."):
        try:
            network_status = api_service.dashboard_api.get_network_status()
            if network_status["success"]:
                status_data = network_status["data"]
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    overall_status = status_data["overall_status"]
                    status_color = "🟢" if overall_status == "good" else "🟡" if overall_status == "warning" else "🔴"
                    st.metric("网络状态", f"{status_color} {overall_status}")
                with col2:
                    st.metric("成功率", f"{status_data['success_rate']:.1f}%")
                with col3:
                    st.metric("平均响应时间", f"{status_data['avg_response_time']:.2f}s")
            else:
                st.warning("无法获取网络状态")
        except Exception as e:
            st.error(f"获取网络状态失败: {e}")
    
    # 网络测试控制
    col1, col2 = st.columns([2, 1])
    
    with col1:
        test_mode = st.radio(
            "测试模式",
            ["快速测试", "完整测试"],
            horizontal=True,
            help="快速测试使用缓存结果，完整测试重新运行所有接口"
        )
    
    with col2:
        if st.button("🚀 开始网络测试", type="primary", use_container_width=True):
            with st.spinner("正在测试网络接口..."):
                try:
                    # 运行网络测试
                    if test_mode == "快速测试":
                        network_report = api_service.dashboard_api.test_network_apis(async_mode=False)
                    else:
                        network_report = api_service.dashboard_api.test_network_apis(async_mode=True)
                    
                    if network_report["success"]:
                        report_data = network_report["data"]
                        
                        # 显示测试摘要
                        st.success("网络测试完成！")
                        
                        summary = report_data["summary"]
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("总测试数", summary["total_tests"])
                        with col2:
                            st.metric("成功数", summary["success_count"])
                        with col3:
                            st.metric("失败数", summary["failed_count"])
                        with col4:
                            st.metric("成功率", f"{summary['success_rate']:.1f}%")
                        
                        # 显示详细结果
                        with st.expander("查看详细测试结果"):
                            details = report_data["details"]
                            
                            # 按类型分组显示
                            for api_type in ["akshare_function", "yfinance_function", "http", "symbol_test"]:
                                type_results = [r for r in details if r["type"] == api_type]
                                if type_results:
                                    st.markdown(f"##### {api_type.replace('_', ' ').title()}")
                                    
                                    for result in type_results:
                                        status_icon = "✅" if result["status"] == "success" else "❌"
                                        st.write(f"{status_icon} **{result['name']}**")
                                        st.write(f"  响应时间: {result['response_time'] or 'N/A'}秒")
                                        if result["error"]:
                                            st.write(f"  错误: {result['error']}")
                            
                        # 显示失败的API
                        failed_apis = [r for r in details if r["status"] != "success"]
                        if failed_apis:
                            with st.expander("查看失败的API"):
                                for api in failed_apis:
                                    st.error(f"**{api['name']}**: {api.get('error', '未知错误')}")
                        
                        # 导出功能
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("📊 导出为CSV"):
                                try:
                                    export_result = api_service.dashboard_api.export_network_test()
                                    if export_result["success"]:
                                        csv_data = export_result["data"]["csv_data"]
                                        filename = export_result["data"]["filename"]
                                        
                                        st.download_button(
                                            label="下载CSV文件",
                                            data=csv_data,
                                            file_name=filename,
                                            mime="text/csv"
                                        )
                                    else:
                                        st.error("导出失败")
                                except Exception as e:
                                    st.error(f"导出失败: {e}")
                        
                        with col2:
                            if st.button("🔄 重新测试"):
                                st.rerun()
                    else:
                        st.error(f"网络测试失败: {network_report.get('error', '未知错误')}")
                        
                except Exception as e:
                    st.error(f"网络测试出错: {e}")
    
    # 网络监控建议
    with st.expander("网络监控建议"):
        st.markdown("""
        ### 最佳实践
        
        1. **定期监控**: 建议每小时运行一次快速测试
        2. **阈值设置**: 成功率低于80%时发出警告
        3. **故障处理**: 
           - AkShare接口失败: 检查网络连接和akshare版本
           - yfinance接口失败: 确认能访问Yahoo Finance
           - HTTP接口失败: 检查防火墙和代理设置
        4. **备用方案**: 准备多个数据源作为备份
        
        ### 常见问题
        
        - **超时错误**: 增加超时时间或检查网络速度
        - **证书错误**: 更新SSL证书或检查系统时间
        - **频率限制**: 避免过于频繁的测试请求
        """)

# 页脚
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #6B7280; font-size: 0.9rem;">
        FM 金融管理系统 | 版本 1.0.0 | © 2025 版权所有
    </div>
    """,
    unsafe_allow_html=True
)