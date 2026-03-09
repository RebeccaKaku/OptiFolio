# NeoFM Financial Methodology Review

> This document is intended for financial experts to review the mathematical models, algorithms, and statistical methods used in NeoFM.

## Table of Contents

1. [Data Processing Methodology](#1-data-processing-methodology)
2. [Portfolio Optimization Models](#2-portfolio-optimization-models)
3. [Risk Metrics](#3-risk-metrics)
4. [Statistical Assumptions](#4-statistical-assumptions)
5. [Implementation Details](#5-implementation-details)

---

## 1. Data Processing Methodology

### 1.1 Data Cleaning Pipeline

The data processing follows a sequential pipeline:

```
Raw Data → Missing Value Handler → Outlier Detection → Gap Filling → Validation → Standardization
```

### 1.2 Missing Value Treatment

**Methods Available:**

| Method | Formula | Use Case |
|--------|---------|----------|
| Forward Fill | $x_t = x_{t-1}$ | Short gaps in price data |
| Backward Fill | $x_t = x_{t+1}$ | Initial missing values |
| Linear Interpolation | $x_t = x_{t-k} + \frac{t-k}{j-k}(x_j - x_{t-k})$ | Continuous price series |
| Mean Fill | $x_t = \bar{x}$ | Low volatility periods |
| Drop | Remove row | Large gaps, unreliable data |

**Gap Filling Algorithm:**

```
Algorithm: FillGaps
Input: DataFrame df, max_gap_days
Output: DataFrame with filled gaps

1. Identify consecutive missing sequences
2. For each sequence:
   a. If length > max_gap_days:
      - Mark as unfillable
   b. Else:
      - Apply forward fill
3. Return filled DataFrame
```

### 1.3 Outlier Detection

**IQR Method:**

$$
\text{Lower Bound} = Q_1 - k \times IQR
$$

$$
\text{Upper Bound} = Q_3 + k \times IQR
$$

Where:
- $IQR = Q_3 - Q_1$ (Interquartile Range)
- $k = 1.5$ (typical value, adjustable)

**Z-Score Method:**

$$
z_i = \frac{x_i - \mu}{\sigma}
$$

Values with $|z_i| > \text{threshold}$ are flagged as outliers.

### 1.4 OHLCV Validation Rules

```
Validation Rules:
1. High ≥ Low (always)
2. High ≥ Open, High ≥ Close
3. Low ≤ Open, Low ≤ Close
4. Volume ≥ 0
5. Prices > 0
```

### 1.5 Corporate Action Adjustments

**Stock Split Adjustment:**

For a split ratio $r$ (e.g., 2:1 split → $r = 2$):

$$
P_{\text{adjusted}} = \frac{P_{\text{raw}}}{r}
$$

$$
V_{\text{adjusted}} = V_{\text{raw}} \times r
$$

**Dividend Adjustment:**

For dividend $d$ on ex-date:

$$
P_{\text{adjusted}} = P_{\text{raw}} \times \left(1 - \frac{d}{P_{\text{pre-ex}}}\right)
$$

**Cumulative Adjustment Factor:**

$$
AF_t = \prod_{i=1}^{t} \left( \frac{1}{r_i} \times \left(1 - \frac{d_i}{P_{i-1}}\right) \right)
$$

---

## 2. Portfolio Optimization Models

### 2.1 Mean-Variance Optimization (Markowitz)

**Objective Function:**

Maximize Sharpe Ratio:

$$
\max_w \frac{w^T \mu - r_f}{\sqrt{w^T \Sigma w}}
$$

Subject to:
- $\sum_{i=1}^{n} w_i = 1$ (fully invested)
- $w_i \geq 0$ (long-only, if specified)
- $w_i \leq w_{\max}$ (position limit, if specified)

**Alternative Objectives:**

Minimize Volatility:
$$
\min_w \sqrt{w^T \Sigma w}
$$

Maximize Return (subject to risk constraint):
$$
\max_w w^T \mu \quad \text{s.t.} \quad w^T \Sigma w \leq \sigma_{\max}^2
$$

### 2.2 Expected Returns Estimation

**Mean Historical Return:**

$$
\hat{\mu}_i = \frac{1}{T} \sum_{t=1}^{T} r_{i,t}
$$

**Exponentially Weighted Mean:**

$$
\hat{\mu}_i = \frac{\sum_{t=1}^{T} \lambda^{T-t} r_{i,t}}{\sum_{t=1}^{T} \lambda^{T-t}}
$$

Where $\lambda \in (0,1)$ is the decay factor (typically $\lambda = 0.94$).

**CAPM-Based:**

$$
\mu_i = r_f + \beta_i (E[R_m] - r_f)
$$

Where:
$$
\beta_i = \frac{\text{Cov}(r_i, r_m)}{\text{Var}(r_m)}
$$

### 2.3 Covariance Estimation

**Sample Covariance:**

$$
\hat{\Sigma}_{ij} = \frac{1}{T-1} \sum_{t=1}^{T} (r_{i,t} - \bar{r}_i)(r_{j,t} - \bar{r}_j)
$$

**Ledoit-Wolf Shrinkage:**

$$
\Sigma_{\text{shrunk}} = \delta F + (1-\delta) S
$$

Where:
- $S$ = sample covariance matrix
- $F$ = shrinkage target (typically scaled identity)
- $\delta$ = optimal shrinkage intensity

**Shrinkage Intensity Formula:**

$$
\delta^* = \frac{\kappa T - 2n}{T^2} \cdot \frac{\pi - \rho}{\gamma}
$$

### 2.4 Black-Litterman Model

**Model Foundation:**

The Black-Litterman model combines market equilibrium with investor views using Bayesian inference.

**Step 1: Market Equilibrium Returns**

$$
\Pi = \delta \Sigma w_{\text{mkt}}
$$

Where:
- $\Pi$ = implied equilibrium returns
- $\delta$ = risk aversion coefficient (typically $\delta = 2.5$)
- $\Sigma$ = covariance matrix
- $w_{\text{mkt}}$ = market capitalization weights

**Step 2: Investor Views**

Views are expressed as:

$$
P \mu = Q + \epsilon
$$

Where:
- $P$ = pick matrix (identifies assets in each view)
- $Q$ = view vector (expected returns)
- $\epsilon \sim N(0, \Omega)$ = view uncertainty

**Step 3: Combined Distribution**

Prior: $\mu \sim N(\Pi, \tau \Sigma)$

Posterior:

$$
\mu_{BL} = \left[ (\tau \Sigma)^{-1} + P^T \Omega^{-1} P \right]^{-1} \left[ (\tau \Sigma)^{-1} \Pi + P^T \Omega^{-1} Q \right]
$$

**Step 4: Posterior Covariance**

$$
\Sigma_{BL} = \Sigma + \left[ (\tau \Sigma)^{-1} + P^T \Omega^{-1} P \right]^{-1}
$$

### 2.5 Omega Matrix Construction

**Idzorek's Method (Confidence-Based):**

For view $k$ with confidence $c_k \in [0,1]$:

$$
\omega_k = \frac{1 - c_k}{c_k} \cdot (P_k \Sigma P_k^T)
$$

When $c_k = 1$: $\omega_k = 0$ (absolute certainty)
When $c_k = 0$: $\omega_k \to \infty$ (no confidence)

**Pseudocode:**

```
Algorithm: ConstructOmega
Input: views {symbol: (expected_return, confidence)}, covariance Σ
Output: Omega matrix Ω

1. Initialize Ω as diagonal matrix
2. For each view k:
   a. Extract confidence c_k
   b. Extract pick vector P_k
   c. Compute variance: v_k = P_k Σ P_k^T
   d. Set: Ω[k,k] = (1 - c_k) / c_k * v_k
3. Return Ω
```

---

## 3. Risk Metrics

### 3.1 Value at Risk (VaR)

**Historical VaR:**

$$
\text{VaR}_\alpha = -\text{Percentile}(r, 1-\alpha)
$$

**Parametric VaR (Normal Distribution):**

$$
\text{VaR}_\alpha = -(\mu - \sigma \cdot z_\alpha)
$$

Where $z_\alpha$ is the $\alpha$-quantile of standard normal.

**Cornish-Fisher VaR (Non-Normal):**

$$
\text{VaR}_{CF} = -\left(\mu + \sigma \cdot z_{CF}\right)
$$

Where:
$$
z_{CF} = z_\alpha + \frac{1}{6}(z_\alpha^2 - 1)S + \frac{1}{24}(z_\alpha^3 - 3z_\alpha)(K-3) - \frac{1}{36}(2z_\alpha^3 - 5z_\alpha)S^2
$$

- $S$ = skewness
- $K$ = kurtosis

### 3.2 Conditional VaR (Expected Shortfall)

$$
\text{CVaR}_\alpha = -E[r | r \leq -\text{VaR}_\alpha]
$$

**Numerical Approximation:**

$$
\text{CVaR}_\alpha \approx -\frac{1}{N(1-\alpha)} \sum_{i=1}^{N} r_i \cdot \mathbb{1}_{r_i \leq -\text{VaR}_\alpha}
$$

### 3.3 Sharpe Ratio

$$
\text{Sharpe} = \frac{E[r_p] - r_f}{\sigma_p}
$$

**Annualized:**

$$
\text{Sharpe}_{\text{annual}} = \frac{E[r_p] \times 252 - r_f}{\sigma_p \times \sqrt{252}}
$$

### 3.4 Sortino Ratio

$$
\text{Sortino} = \frac{E[r_p] - r_f}{\sigma_d}
$$

Where downside deviation:
$$
\sigma_d = \sqrt{\frac{1}{T} \sum_{t=1}^{T} \min(r_t - r_f, 0)^2}
$$

### 3.5 Maximum Drawdown

$$
\text{MDD} = \max_{t \in [0,T]} \left( \max_{s \in [0,t]} V_s - V_t \right) / \max_{s \in [0,t]} V_s
$$

**Algorithm:**

```
Algorithm: MaxDrawdown
Input: returns series r
Output: Maximum drawdown

1. Compute cumulative returns: V = cumprod(1 + r)
2. running_max = 0
3. max_dd = 0
4. For each t:
   a. running_max = max(running_max, V[t])
   b. dd = (running_max - V[t]) / running_max
   c. max_dd = max(max_dd, dd)
5. Return max_dd
```

### 3.6 Calmar Ratio

$$
\text{Calmar} = \frac{E[r_p] - r_f}{\text{MDD}}
$$

---

## 4. Statistical Assumptions

### 4.1 Return Distribution Assumptions

| Model | Assumption | Implication |
|-------|------------|-------------|
| Mean-Variance | Normal returns | Symmetric risk, no tail risk |
| Black-Litterman | Normal prior/posterior | Bayesian updating valid |
| VaR (Parametric) | Normal returns | May underestimate tail risk |
| VaR (Historical) | Stationarity | Past represents future |

### 4.2 Time Series Assumptions

1. **Stationarity**: Returns are assumed to be stationary
2. **Independence**: Daily returns are approximately independent
3. **No Serial Correlation**: Returns exhibit minimal autocorrelation

### 4.3 Model Limitations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| Estimation Error | Unstable optimal weights | Shrinkage estimators, resampling |
| Non-Normal Returns | Underestimated tail risk | Cornish-Fisher VaR, CVaR |
| Regime Changes | Historical data may not apply | Rolling windows, regime detection |
| Transaction Costs | Optimal weights not achievable | Turnover constraints |

---

## 5. Implementation Details

### 5.1 Numerical Optimization

**Solver**: Sequential Least Squares Programming (SLSQP)

**Constraints Handling:**
- Equality constraints: $\sum w_i = 1$
- Inequality constraints: $w_i \geq 0$, $w_i \leq w_{\max}$

**Convergence Criteria:**
- Tolerance: $10^{-8}$
- Maximum iterations: 1000

### 5.2 Data Frequency Conversions

| Source Frequency | Target | Method |
|------------------|--------|--------|
| Daily | Weekly | Last observation of week |
| Daily | Monthly | Last observation of month |
| Higher | Lower | Aggregation via resample |

### 5.3 Return Calculation

**Simple Returns:**
$$
r_t = \frac{P_t - P_{t-1}}{P_{t-1}}
$$

**Log Returns:**
$$
r_t = \ln\left(\frac{P_t}{P_{t-1}}\right)
$$

**Annualization:**
$$
\sigma_{\text{annual}} = \sigma_{\text{daily}} \times \sqrt{252}
$$

$$
\mu_{\text{annual}} = \mu_{\text{daily}} \times 252
$$

### 5.4 Edge Case Handling

| Edge Case | Detection | Handling |
|-----------|-----------|----------|
| Singular Covariance | Condition number check | Ledoit-Wolf shrinkage |
| Negative Expected Returns | All $\mu_i < r_f$ | Return warning, use min volatility |
| Insufficient Data | $T < 2n$ | Require minimum 30 observations |
| Zero Variance Asset | $\sigma_i = 0$ | Remove from optimization |

---

## Appendix A: Mathematical Notation

| Symbol | Description |
|--------|-------------|
| $w$ | Weight vector $(n \times 1)$ |
| $\mu$ | Expected return vector $(n \times 1)$ |
| $\Sigma$ | Covariance matrix $(n \times n)$ |
| $r_f$ | Risk-free rate |
| $\lambda$ | Risk aversion parameter |
| $\tau$ | Black-Litterman scaling parameter |
| $\Omega$ | View uncertainty matrix |
| $P$ | Pick matrix for views |
| $Q$ | View vector |
| $\Pi$ | Implied equilibrium returns |

## Appendix B: References

1. Markowitz, H. (1952). Portfolio Selection. *Journal of Finance*, 7(1), 77-91.
2. Black, F., & Litterman, R. (1992). Global Portfolio Optimization. *Financial Analysts Journal*, 48(5), 28-43.
3. Ledoit, O., & Wolf, M. (2004). A Well-Conditioned Estimator for Large-Dimensional Covariance Matrices. *Journal of Multivariate Analysis*, 88(2), 365-411.
4. Idzorek, T. (2007). A Step-by-Step Guide to the Black-Litterman Model. *Incorporating User Views in Asset Allocation*.
