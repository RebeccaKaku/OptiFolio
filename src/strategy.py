# src/strategy.py
import cvxpy as cp
import numpy as np
import pandas as pd

class Strategy:
    def __init__(self, config):
        # 使用 .get() 提供默认值，防止以后忘写参数报错
        self.risk_aversion = config['parameters'].get('risk_aversion', 3.0)
        
        # 允许最大单仓位限制 (例如：单只股票不能超过 40%)
        # 这也是风控的一部分
        self.max_position = 0.4 

    def optimize(self, mu, sigma):
        """
        核心决策函数：使用凸优化求解最优权重
        输入:
            mu: 预期收益向量 (pd.Series)
            sigma: 协方差矩阵 (pd.DataFrame)
        输出:
            optimal_weights: 最优仓位 (pd.Series)
        """
        print(f"    [Strategy] 启动凸优化引擎 (Risk Aversion = {self.risk_aversion})...")
        
        # 1. 准备数学变量
        n_assets = len(mu)
        tickers = mu.index.tolist()
        
        # 定义优化变量：权重 w (维度 N x 1)
        w = cp.Variable(n_assets)
        
        # 2. 定义风险与收益 (数学表达)
        # 组合收益 = w * mu
        port_return = w @ mu.values 
        
        # 组合风险 (方差) = w^T * Sigma * w
        # cp.quad_form 是 cvxpy 专门用来算二次型的函数
        port_risk = cp.quad_form(w, sigma.values)
        
        # 3. 定义目标函数 (Objective)
        # 效用 = 收益 - 风险厌恶 * 风险
        objective = cp.Maximize(port_return - self.risk_aversion * port_risk)
        
        # 4. 定义约束条件 (Constraints)
        constraints = [
            cp.sum(w) == 1,      # 满仓约束 (权重和为1)
            w >= 0,              # 做多约束 (权重非负)
            w <= self.max_position # 分散化约束 (防止押注单只股票)
        ]
        
        # 5. 求解 (Solving)
        prob = cp.Problem(objective, constraints)
        
        try:
            # 使用 OSQP 或 SCS 求解器
            prob.solve() 
        except Exception as e:
            print(f"    [Error] 优化求解失败: {e}")
            # 失败时的兜底策略：等权重
            return pd.Series(np.ones(n_assets)/n_assets, index=tickers)

        # 6. 检查状态
        if prob.status != 'optimal':
            print(f"    [Warning] 求解器未找到最优解 (Status: {prob.status})")
            
        # 7. 格式化输出
        # 小于 0.001% 的仓位直接置 0，保持干净
        clean_weights = pd.Series(w.value, index=tickers)
        clean_weights[clean_weights < 0.0001] = 0
        
        # 归一化 (以防微小的浮点误差)
        clean_weights = clean_weights / clean_weights.sum()
        
        return clean_weights