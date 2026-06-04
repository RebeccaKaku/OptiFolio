# src/api/network_tester.py
"""
网络接口测试模块
用于测试各种金融数据API的连通性和响应状态
"""
import asyncio
import aiohttp
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
import logging

# 设置基础日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class NetworkTester:
    """网络接口测试器"""
    
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.test_results = []
        
        # 定义要测试的API接口 - 按金融产品类型分类
        self.api_endpoints = {
            # =============== 中国股票 ===============
            'akshare_stock_zh_a_spot_em': {
                'name': 'AkShare A股实时行情',
                'type': 'akshare_function',
                'function': 'stock_zh_a_spot_em',
                'description': '东方财富A股实时行情 - 中国股票核心接口'
            },
            'akshare_stock_zh_a_hist': {
                'name': 'AkShare A股历史行情', 
                'type': 'akshare_function',
                'function': 'stock_zh_a_hist',
                'description': '东方财富A股历史行情 - 中国股票历史数据'
            },
            'akshare_stock_info_a_code_name': {
                'name': 'AkShare A股代码名称对照',
                'type': 'akshare_function',
                'function': 'stock_info_a_code_name',
                'description': 'A股股票代码与名称对照表'
            },
            
            # =============== 中国基金 ===============
            'akshare_fund_em': {
                'name': 'AkShare 基金数据',
                'type': 'akshare_function', 
                'function': 'fund_em',
                'description': '天天基金网数据 - 基金基础信息'
            },
            'akshare_fund_money_rate_em': {
                'name': 'AkShare 货币基金数据',
                'type': 'akshare_function',
                'function': 'fund_money_rate_em',
                'description': '天天基金网货币基金数据 - 货币基金利率'
            },
            'akshare_fund_individual_basic_info_xq': {
                'name': 'AkShare 基金详细信息(雪球)',
                'type': 'akshare_function',
                'function': 'fund_individual_basic_info_xq',
                'description': '雪球基金详细信息 - QDII基金识别'
            },
            
            # =============== 美股 ===============
            'yfinance_stock_info': {
                'name': 'yfinance 股票信息',
                'type': 'yfinance_function',
                'function': 'Ticker',
                'description': 'Yahoo Finance股票信息 - 美股基础信息'
            },
            'yfinance_stock_history': {
                'name': 'yfinance 股票历史数据',
                'type': 'yfinance_function',
                'function': 'download',
                'description': 'Yahoo Finance股票历史数据 - 美股历史行情'
            },
            
            # =============== 外汇/货币 ===============
            'yfinance_fx_usdcny': {
                'name': 'yfinance 美元兑人民币',
                'type': 'yfinance_function',
                'function': 'Ticker',
                'description': 'USD/CNY汇率 - 主要外汇对'
            },
            'yfinance_fx_eurusd': {
                'name': 'yfinance 欧元兑美元',
                'type': 'yfinance_function',
                'function': 'Ticker',
                'description': 'EUR/USD汇率 - 主要外汇对'
            },
            'yfinance_fx_gbpusd': {
                'name': 'yfinance 英镑兑美元',
                'type': 'yfinance_function',
                'function': 'Ticker',
                'description': 'GBP/USD汇率 - 主要外汇对'
            },
            'yfinance_fx_usdjpy': {
                'name': 'yfinance 美元兑日元',
                'type': 'yfinance_function',
                'function': 'Ticker',
                'description': 'USD/JPY汇率 - 主要外汇对'
            },
            
            # =============== 外部财经网站 ===============
            'sina_finance': {
                'name': '新浪财经',
                'type': 'http',
                'url': 'https://finance.sina.com.cn',
                'description': '新浪财经首页 - 综合财经资讯'
            },
            'eastmoney': {
                'name': '东方财富',
                'type': 'http',
                'url': 'https://www.eastmoney.com',
                'description': '东方财富网 - 综合财经数据'
            },
            'tencent_finance': {
                'name': '腾讯财经',
                'type': 'http',
                'url': 'https://finance.qq.com',
                'description': '腾讯财经 - 财经新闻和数据'
            },
            'yahoo_finance': {
                'name': 'Yahoo Finance',
                'type': 'http',
                'url': 'https://finance.yahoo.com',
                'description': 'Yahoo Finance - 国际财经数据'
            },
            
            # =============== 测试用的代表性股票代码 ===============
            # 中国A股 - 不同行业和交易所的代表
            'test_cn_blue_chips': {
                'name': '测试中国蓝筹股',
                'type': 'symbol_test',
                'symbols': ['sh600519', 'sz000858', 'sh600036', 'sz000002'],  # 茅台、五粮液、招行、万科
                'description': '测试中国A股蓝筹股代码的可用性 - 消费、金融、地产'
            },
            'test_cn_tech_stocks': {
                'name': '测试中国科技股',
                'type': 'symbol_test',
                'symbols': ['sz300750', 'sz002415', 'sh688111', 'sz002230'],  # 宁德时代、海康威视、金山办公、科大讯飞
                'description': '测试中国科技股代码的可用性 - 新能源、安防、软件、AI'
            },
            'test_cn_etf_funds': {
                'name': '测试中国ETF基金',
                'type': 'symbol_test',
                'symbols': ['510300', '510500', '159915', '510050'],  # 沪深300、中证500、创业板、上证50
                'description': '测试中国主要ETF基金代码的可用性 - 宽基指数ETF'
            },
            
            # 美股 - 不同行业的代表
            'test_us_tech_giants': {
                'name': '测试美股科技巨头',
                'type': 'symbol_test',
                'symbols': ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'META'],  # 苹果、谷歌、微软、亚马逊、Meta
                'description': '测试美股科技巨头代码的可用性 - FAANG等'
            },
            'test_us_financials': {
                'name': '测试美股金融股',
                'type': 'symbol_test',
                'symbols': ['JPM', 'BAC', 'WFC', 'GS'],  # 摩根大通、美国银行、富国银行、高盛
                'description': '测试美股金融股代码的可用性 - 主要银行'
            },
            'test_us_consumer': {
                'name': '测试美股消费股',
                'type': 'symbol_test',
                'symbols': ['KO', 'PEP', 'PG', 'WMT'],  # 可口可乐、百事、宝洁、沃尔玛
                'description': '测试美股消费股代码的可用性 - 日常消费品'
            },
            
            # 基金 - 不同类型基金的代表
            'test_cn_active_funds': {
                'name': '测试中国主动管理基金',
                'type': 'symbol_test',
                'symbols': ['005827', '002892', '163402', '110011'],  # 易方达蓝筹、华夏移动互联、兴全趋势、易方达中小盘
                'description': '测试中国主动管理基金代码的可用性 - 明星基金经理产品'
            },
            'test_cn_money_funds': {
                'name': '测试中国货币基金',
                'type': 'symbol_test',
                'symbols': ['000198', '004502', '000009', '000700'],  # 天弘余额宝、中银如意宝、易方达天天理财、招商招利宝
                'description': '测试中国货币基金代码的可用性 - 主要货币基金'
            },
            'test_cn_qdii_funds': {
                'name': '测试中国QDII基金',
                'type': 'symbol_test',
                'symbols': ['002892', '000071', '270023', '513100'],  # 华夏移动互联、华夏恒生ETF、广发全球精选、纳指ETF
                'description': '测试中国QDII基金代码的可用性 - 海外投资QDII'
            },
            
            # 外汇 - 主要货币对
            'test_major_fx_pairs': {
                'name': '测试主要外汇对',
                'type': 'symbol_test',
                'symbols': ['USDCNY=X', 'EURUSD=X', 'GBPUSD=X', 'USDJPY=X'],  # 主要货币对
                'description': '测试主要外汇对代码的可用性 - 主要货币对'
            },
            'test_cross_fx_pairs': {
                'name': '测试交叉外汇对',
                'type': 'symbol_test',
                'symbols': ['EURJPY=X', 'GBPJPY=X', 'EURGBP=X'],  # 交叉货币对
                'description': '测试交叉外汇对代码的可用性 - 非美元货币对'
            }
        }
    
    async def test_all_apis(self) -> Dict:
        """测试所有API接口"""
        logger.info("开始测试所有API接口...")
        start_time = time.time()
        
        # 清空之前的结果
        self.test_results = []
        
        # 并行测试所有接口
        tasks = []
        for api_id, api_config in self.api_endpoints.items():
            task = asyncio.create_task(self._test_single_api(api_id, api_config))
            tasks.append(task)
        
        # 等待所有测试完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"测试过程中出现异常: {result}")
            else:
                self.test_results.append(result)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # 生成测试报告
        report = self._generate_report(total_time)
        
        logger.info(f"API接口测试完成，耗时: {total_time:.2f}秒")
        return report
    
    async def _test_single_api(self, api_id: str, api_config: dict) -> Dict:
        """测试单个API接口"""
        logger.info(f"正在测试: {api_config['name']}")
        
        result = {
            'id': api_id,
            'name': api_config['name'],
            'description': api_config['description'],
            'type': api_config['type'],
            'status': 'unknown',
            'response_time': None,
            'error': None,
            'tested_at': datetime.now().isoformat()
        }
        
        try:
            start_time = time.time()
            
            if api_config['type'] == 'http':
                status = await self._test_http_api(api_config['url'])
                result['status'] = 'success' if status else 'failed'
                
            elif api_config['type'] == 'akshare_function':
                status = await self._test_akshare_function(api_config['function'])
                result['status'] = 'success' if status else 'failed'
                
            elif api_config['type'] == 'yfinance_function':
                status = await self._test_yfinance_function(api_config['function'])
                result['status'] = 'success' if status else 'failed'
                
            elif api_config['type'] == 'symbol_test':
                status = await self._test_symbols(api_config['symbols'])
                result['status'] = 'success' if status else 'failed'
            
            end_time = time.time()
            result['response_time'] = round(end_time - start_time, 3)
            
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
            logger.error(f"测试 {api_config['name']} 时出错: {e}")
        
        return result
    
    async def _test_http_api(self, url: str) -> bool:
        """测试HTTP API"""
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    return response.status == 200
        except Exception:
            return False
    
    async def _test_akshare_function(self, function_name: str) -> bool:
        """测试AkShare函数"""
        try:
            # 动态导入akshare函数
            import akshare as ak
            
            if hasattr(ak, function_name):
                func = getattr(ak, function_name)
                
                # 根据函数类型测试不同的参数
                if function_name == 'stock_zh_a_spot_em':
                    # 测试获取A股实时行情
                    df = func()
                    return not df.empty
                elif function_name == 'stock_zh_a_hist':
                    # 测试获取历史行情
                    df = func(
                        symbol="600519",
                        period="daily", 
                        start_date="20240101",
                        end_date="20240102"
                    )
                    return not df.empty
                elif function_name == 'fund_em':
                    # 测试基金数据
                    df = func()
                    return not df.empty
                else:
                    # 通用测试：尝试调用函数
                    try:
                        result = func()
                        return result is not None
                    except:
                        return False
            else:
                return False
                
        except Exception as e:
            logger.error(f"AkShare函数 {function_name} 测试失败: {e}")
            return False
    
    async def _test_yfinance_function(self, function_name: str) -> bool:
        """测试yfinance函数"""
        try:
            import yfinance as yf
            
            if function_name == 'Ticker':
                # 测试股票信息获取
                ticker = yf.Ticker("AAPL")
                info = ticker.info
                return bool(info) and len(info) > 0
                
            elif function_name == 'download':
                # 测试历史数据下载
                data = yf.download("AAPL", start="2024-01-01", end="2024-01-02", progress=False)
                return not data.empty
                
            else:
                # 通用测试
                return True
                
        except Exception as e:
            logger.error(f"yfinance函数 {function_name} 测试失败: {e}")
            return False
    
    async def _test_symbols(self, symbols: List[str]) -> bool:
        """测试股票代码的可用性"""
        try:
            # 根据符号类型选择不同的测试方法
            if any(symbol.startswith(('sh', 'sz')) for symbol in symbols):
                # 中国股票
                return await self._test_cn_symbols(symbols)
            elif any(symbol.isalpha() and len(symbol) <= 5 for symbol in symbols):
                # 美股
                return await self._test_us_symbols(symbols)
            else:
                # 通用测试
                return await self._test_generic_symbols(symbols)
                
        except Exception as e:
            logger.error(f"股票代码测试失败: {e}")
            return False
    
    async def _test_cn_symbols(self, symbols: List[str]) -> bool:
        """测试中国股票代码的可用性"""
        try:
            import akshare as ak
            
            # 获取实时行情数据
            df = ak.stock_zh_a_spot_em()
            if df.empty:
                return False
            
            success_count = 0
            for symbol in symbols:
                # 提取纯数字代码
                code = symbol[2:] if symbol.startswith(('sh', 'sz')) else symbol
                
                # 检查代码是否存在于数据中
                if not df[df['代码'] == code].empty:
                    success_count += 1
            
            # 至少70%的代码可用即认为成功
            return success_count >= len(symbols) * 0.7
            
        except Exception as e:
            logger.error(f"中国股票代码测试失败: {e}")
            return False
    
    async def _test_us_symbols(self, symbols: List[str]) -> bool:
        """测试美股代码的可用性"""
        try:
            import yfinance as yf
            
            def check_symbol(symbol: str) -> bool:
                """同步函数：检查单个美股代码"""
                try:
                    # 尝试获取股票信息
                    ticker = yf.Ticker(symbol)
                    info = ticker.info
                    return bool(info and len(info) > 0)
                except:
                    return False

            # 使用 asyncio.to_thread 在线程池中并发执行同步的 yfinance 请求
            tasks = [asyncio.to_thread(check_symbol, symbol) for symbol in symbols]
            results = await asyncio.gather(*tasks)
            success_count = sum(results)
            
            # 至少70%的代码可用即认为成功
            return success_count >= len(symbols) * 0.7
            
        except Exception as e:
            logger.error(f"美股代码测试失败: {e}")
            return False
    
    async def _test_generic_symbols(self, symbols: List[str]) -> bool:
        """测试通用基金代码的可用性"""
        try:
            import akshare as ak
            
            # 获取基金数据
            try:
                df = ak.fund_name_em()
                if df.empty:
                    return False
                
                success_count = 0
                for symbol in symbols:
                    if not df[df['基金代码'] == symbol].empty:
                        success_count += 1
                
                return success_count >= len(symbols) * 0.7
                
            except:
                # 如果基金数据获取失败，尝试其他方法
                return await self._test_cn_symbols(symbols)
                
        except Exception as e:
            logger.error(f"通用代码测试失败: {e}")
            return False
    
    def _generate_report(self, total_time: float) -> Dict:
        """生成测试报告"""
        if not self.test_results:
            return {'error': '没有测试结果被记录'}
        
        # 统计结果
        total_tests = len(self.test_results)
        success_count = sum(1 for r in self.test_results if r['status'] == 'success')
        failed_count = sum(1 for r in self.test_results if r['status'] == 'failed')
        error_count = sum(1 for r in self.test_results if r['status'] == 'error')
        
        # 计算平均响应时间
        response_times = [r['response_time'] for r in self.test_results if r['response_time'] is not None]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        # 按类型分组
        by_type = {}
        for result in self.test_results:
            api_type = result['type']
            if api_type not in by_type:
                by_type[api_type] = {'success': 0, 'failed': 0, 'error': 0, 'total': 0}
            
            by_type[api_type]['total'] += 1
            if result['status'] == 'success':
                by_type[api_type]['success'] += 1
            elif result['status'] == 'failed':
                by_type[api_type]['failed'] += 1
            else:
                by_type[api_type]['error'] += 1
        
        report = {
            'summary': {
                'total_tests': total_tests,
                'success_count': success_count,
                'failed_count': failed_count,
                'error_count': error_count,
                'success_rate': round(success_count / total_tests * 100, 1) if total_tests > 0 else 0,
                'total_time': round(total_time, 2),
                'avg_response_time': round(avg_response_time, 3)
            },
            'by_type': by_type,
            'details': self.test_results,
            'tested_at': datetime.now().isoformat()
        }
        
        return report
    
    def get_failed_apis(self) -> List[Dict]:
        """获取失败的API列表"""
        return [r for r in self.test_results if r['status'] != 'success']
    
    def export_to_dataframe(self) -> pd.DataFrame:
        """将测试结果导出为DataFrame"""
        if not self.test_results:
            return pd.DataFrame()
        
        df = pd.DataFrame(self.test_results)
        
        # 添加状态描述
        status_map = {
            'success': '成功',
            'failed': '失败', 
            'error': '错误',
            'unknown': '未知'
        }
        df['status_desc'] = df['status'].map(status_map)
        
        # 重新排列列顺序
        columns = ['name', 'type', 'status_desc', 'response_time', 'error', 'description']
        df = df[columns]
        df.columns = ['接口名称', '类型', '状态', '响应时间(秒)', '错误信息', '描述']
        
        return df


# 便捷函数
async def test_all_apis() -> Dict:
    """测试所有API接口的便捷函数"""
    tester = NetworkTester()
    return await tester.test_all_apis()


def run_network_test() -> Dict:
    """同步版本的API测试函数"""
    try:
        return asyncio.run(test_all_apis())
    except Exception as e:
        logger.error(f"网络测试失败: {e}")
        return {'error': str(e)}


if __name__ == "__main__":
    # 测试运行
    report = run_network_test()
    print("API接口测试报告:")
    print(f"总测试数: {report['summary']['total_tests']}")
    print(f"成功数: {report['summary']['success_count']}")
    print(f"失败数: {report['summary']['failed_count']}")
    print(f"成功率: {report['summary']['success_rate']}%")
    print(f"总耗时: {report['summary']['total_time']}秒")