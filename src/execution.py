class Execution:
    def __init__(self, config):
        self.mode = config['system']['mode']

    def generate_orders(self, target_weights):
        print(f">>> [Execution] 正在生成交易指令 (模式: {self.mode})...")
        # 暂时只打印
        for asset, weight in target_weights.items():
            print(f"    买入/持有 {asset}: {weight:.2%}")