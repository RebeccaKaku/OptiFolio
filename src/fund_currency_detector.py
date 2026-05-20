# src/fund_currency_detector.py
"""
QDII基金币种检测器
专门用于判断QDII基金的交易币种，基于复杂的匹配规则
"""

import re
from typing import Optional, Tuple


class FundCurrencyDetector:
    """QDII基金币种检测器"""
    
    def __init__(self):
        """初始化检测器"""
        # 核心关键词
        self.usd_keywords = ['美元现汇', '美元现钞', '美元汇', '美元']
        self.hkd_keywords = ['港币', '港元']
        
        # 所有关键词，按长度降序排序（优先匹配长关键词）
        self.all_keywords = sorted(
            self.usd_keywords + self.hkd_keywords,
            key=len,
            reverse=True
        )
        
        # 后缀模式
        self.suffix_patterns = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J',
                               'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T',
                               'U', 'V', 'W', 'X', 'Y', 'Z', ')']
        
        # 特定短语 - 需要检测的
        self.special_phrases = ['(美元现汇份额)', '(美元现钞份额)', '(美元份额)']
    
    def detect_currency(self, fund_name: str) -> Tuple[str, str]:
        """
        检测基金币种
        
        Args:
            fund_name: 基金名称
            
        Returns:
            Tuple[currency, reason]: 币种代码和检测原因
        """
        # 首先检查特定短语
        for phrase in self.special_phrases:
            if phrase in fund_name:
                if '美元' in phrase:
                    return 'USD', f'包含特定短语: {phrase}'
        
        # 查找所有关键词出现的位置
        keyword_matches = []
        for keyword in self.all_keywords:
            # 查找所有出现位置
            positions = [(m.start(), m.end()) for m in re.finditer(re.escape(keyword), fund_name)]
            for start, end in positions:
                keyword_matches.append({
                    'keyword': keyword,
                    'start': start,
                    'end': end,
                    'length': len(keyword)
                })
        
        # 如果没有找到关键词，返回CNY
        if not keyword_matches:
            return 'CNY', '未找到美元/港币关键词'
        
        # 对匹配按位置排序
        keyword_matches.sort(key=lambda x: x['start'])
        
        # 检查每个关键词是否匹配过滤模式
        for match in keyword_matches:
            keyword = match['keyword']
            end_pos = match['end']
            
            # 确定币种类型
            currency = 'USD' if any(kw in keyword for kw in ['美元']) else 'HKD'
            
            # 检查模式1: 关键词 + 结尾
            if end_pos == len(fund_name):
                return currency, f'关键词"{keyword}"位于名称末尾'
            
            # 检查后面的字符
            next_char = fund_name[end_pos] if end_pos < len(fund_name) else ''
            
            # 检查模式2: 关键词 + (QDII)
            if fund_name[end_pos:].startswith('(QDII)'):
                return currency, f'关键词"{keyword}"后接(QDII)'
            
            # 检查模式3: 关键词 + 后缀
            if next_char in self.suffix_patterns:
                # 但需要确保不是像"美元债"这样的情况
                # 检查关键词后面的完整单词
                rest_of_name = fund_name[end_pos:]
                
                # 如果是"美元债"、"美元票息"等，应该是CNY
                if rest_of_name.startswith('债') or rest_of_name.startswith('票息'):
                    continue  # 跳过，继续检查其他匹配
                
                return currency, f'关键词"{keyword}"后接后缀"{next_char}"'
            
            # 检查模式4: 关键词 + ) 后面可能有其他字符
            if next_char == ')':
                # 检查是否在括号内
                bracket_content = ''
                bracket_depth = 1
                i = end_pos + 1
                while i < len(fund_name) and bracket_depth > 0:
                    if fund_name[i] == '(':
                        bracket_depth += 1
                    elif fund_name[i] == ')':
                        bracket_depth -= 1
                        if bracket_depth == 0:
                            break
                    bracket_content += fund_name[i]
                    i += 1
                
                # 如果括号内容包含A、C等后缀，匹配
                if any(suffix in bracket_content for suffix in self.suffix_patterns[:10]):  # A-Z
                    return currency, f'关键词"{keyword}"在括号内后接后缀'
        
        # 如果有关键词但没有匹配任何过滤模式，返回CNY
        # 例如"美元债"、"美元票息"等
        return 'CNY', '有关键词但不符合过滤模式(如"美元债"、"美元票息"等)'
    
    def should_filter_out(self, fund_name: str) -> Tuple[bool, str]:
        """
        判断是否应该过滤掉该基金（旧逻辑，保留兼容性）
        
        Args:
            fund_name: 基金名称
            
        Returns:
            Tuple[是否过滤, 原因]
        """
        currency, reason = self.detect_currency(fund_name)
        return currency in ['USD', 'HKD'], f'检测到{currency}币种: {reason}'


# 便捷函数
def detect_fund_currency(fund_name: str) -> str:
    """便捷函数：检测基金币种"""
    detector = FundCurrencyDetector()
    currency, _ = detector.detect_currency(fund_name)
    return currency


def should_filter_fund(fund_name: str) -> Tuple[bool, str]:
    """便捷函数：判断是否应该过滤基金"""
    detector = FundCurrencyDetector()
    return detector.should_filter_out(fund_name)


if __name__ == "__main__":
    # 测试代码
    detector = FundCurrencyDetector()
    
    test_cases = [
        # (基金名称, 预期币种, 说明)
        ("华夏全球股票(QDII)(人民币)", "CNY", "人民币QDII"),
        ("嘉实美国成长股票美元现汇", "USD", "美元现汇"),
        ("嘉实美国成长股票美元现钞", "USD", "美元现钞"),
        ("富国全球科技互联网股票(QDII)A(后端)", "CNY", "人民币A类"),
        ("富国中国中小盘混合(QDII)人民币A(后端)", "CNY", "人民币A类"),
        ("广发亚太中高收益债美元现汇(QDII)A", "USD", "美元现汇带后缀A"),
        ("华夏移动互联混合美元现汇", "USD", "美元现汇"),
        ("华夏移动互联混合美元现钞", "USD", "美元现钞"),
        ("中银美元债债券(QDII)人民币A", "CNY", "美元债是产品类型，不是币种"),
        ("中银美元债债券(QDII)美元", "USD", "美元币种"),
        ("嘉实新兴市场C2(QDII)", "CNY", "C2后缀但无美元关键词"),
        ("工银香港中小盘人民币", "CNY", "人民币"),
        ("工银香港中小盘美元", "USD", "美元"),
        ("易方达原油C类美元汇", "USD", "美元汇"),
        ("易方达全球优质企业混合(QDII)A(美元现汇份额)", "USD", "美元现汇份额"),
        ("富国全球消费精选混合(QDII)美元", "USD", "美元结尾"),
        ("华夏全球股票美元现汇(QDII)", "USD", "美元现汇在(QDII)前"),
    ]
    
    print("=== QDII基金币种检测器测试 ===")
    for fund_name, expected_currency, description in test_cases:
        currency, reason = detector.detect_currency(fund_name)
        status = "✓" if currency == expected_currency else "✗"
        print(f"{status} {description}")
        print(f"  名称: {fund_name}")
        print(f"  预期: {expected_currency}, 实际: {currency} ({reason})")
        print()