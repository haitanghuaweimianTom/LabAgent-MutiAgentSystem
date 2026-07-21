"""演示用的代码模板（仅在 ``BaseAgent._mock_response`` 无 LLM Key 时使用）。

Phase 1D 整改：把原来嵌在 [backend/app/agents/base.py](backend/app/agents/base.py)
的 7 段硬编码字符串（数学建模赛题演示用）抽出到独立模块，让 ``base.py`` 恢复
领域无关。

模板按 **领域关键词** 索引；``_mock_response`` 仍负责匹配，本模块仅提供
字符串素材。新增 / 修改模板不影响 ``base.py`` 任何逻辑。

**重要**：这些模板是 *演示数据*（demo），不影响真实 LLM 推理路径；
当 ``MINIMAX_API_KEY`` 或其他 provider key 配置好后，``_mock_response`` 完全
不会被调用，系统走真实 LLM。
"""
from __future__ import annotations
from typing import Dict

OPTICS_MULTI = r'''import numpy as np
from scipy.optimize import minimize, curve_fit

def airy_formula_reflectance(delta, R1, R2):
    """Airy公式：多光束干涉反射率"""
    r1, r2 = np.sqrt(R1), np.sqrt(R2)
    num = R1 + R2 - 2*r1*r2*np.cos(delta)
    den = 1 + R1*R2 - 2*r1*r2*np.cos(delta)
    return num / den

def compute_phase_delta(wavenumber, thickness, n_eff, angle_rad):
    """计算相位差 δ = 4π·n·d·cosθ/λ = 4π·n·d·cosθ·wavenumber"""
    wavelength = 1e4 / wavenumber
    delta = 4 * np.pi * n_eff * thickness * np.cos(angle_rad) / wavelength
    return delta

def fit_thickness_multi_beam(wavenumber, reflectance, angle_deg, n_eff=2.6, initial_d=5.0):
    angle_rad = np.radians(angle_deg)
    def residual(d):
        delta = 4 * np.pi * n_eff * d * np.cos(angle_rad) * wavenumber * 1e-4
        r1 = (1 - n_eff) / (1 + n_eff)
        r2 = (n_eff - 1) / (n_eff + 1)
        model = (r1**2 + r2**2 - 2*np.abs(r1*r2)*np.cos(delta)) / (1 + r1**2*r2**2 - 2*np.abs(r1*r2)*np.cos(delta))
        return np.sum((model * 100 - reflectance)**2)
    result = minimize(residual, initial_d, method='Nelder-Mead')
    return {"thickness_um": round(result.x[0], 4), "RMSE": round(np.sqrt(result.fun/len(wavenumber)), 4)}

if __name__ == "__main__":
    print("=== 多光束干涉分析（硅晶圆片）===")
'''

OPTICS_DOUBLE = r'''import numpy as np
from scipy.optimize import minimize
import pandas as pd

def load_spectrum(file_path):
    df = pd.read_excel(file_path)
    wavenumber = df.iloc[:, 0].values
    reflectance = df.iloc[:, 1].values
    return wavenumber, reflectance

def extract_peaks(wavenumber, reflectance, num_peaks=10):
    from scipy.signal import find_peaks
    spectrum = reflectance - np.mean(reflectance)
    peaks, _ = find_peaks(spectrum, distance=50, height=np.std(spectrum))
    return wavenumber[peaks]

def fft_thickness_estimate(wavenumber, reflectance, n_eff=2.6, angle_deg=10):
    spectrum = reflectance - np.mean(reflectance)
    n = len(wavenumber)
    fft_vals = np.fft.fft(spectrum)
    freqs = np.fft.fftfreq(n, d=wavenumber[1] - wavenumber[0])
    pos_mask = freqs > 0
    pos_freqs = freqs[pos_mask]
    pos_power = np.abs(fft_vals[pos_mask])**2
    peak_idx = np.argmax(pos_power)
    dominant_freq = pos_freqs[peak_idx]
    if dominant_freq > 0:
        delta_nu = 1 / dominant_freq
        angle_rad = np.radians(angle_deg)
        d_estimate = delta_nu * n_eff * np.cos(angle_rad) / 2
    else:
        d_estimate = None
    return d_estimate, dominant_freq

def least_squares_fit_thickness(wavenumber, reflectance, angle_deg, n_eff=2.6, d_init=5.0):
    angle_rad = np.radians(angle_deg)
    def residual(params):
        d, n = params[0], params[1]
        if d <= 0 or n <= 1:
            return 1e20
        delta = 4 * np.pi * n * d * np.cos(angle_rad) / (1e4 / wavenumber)
        r1 = np.abs((1 - n) / (1 + n))
        r2 = np.abs((n - 1) / (n + 1))
        model = r1**2 + r2**2 - 2*r1*r2*np.cos(delta)
        return np.sum((model * 100 - reflectance)**2)
    result = minimize(residual, [d_init, n_eff], method='Nelder-Mead', options={'xatol': 1e-6, 'fatol': 1e-6})
    d_fit, n_fit = result.x
    rmse = np.sqrt(result.fun / len(wavenumber))
    return {"thickness_um": round(d_fit, 4), "n_eff": round(n_fit, 4), "RMSE": round(rmse, 4)}

if __name__ == "__main__":
    print("=== 双光束干涉（FFT 频域法）===")
'''

NEWSVENDOR = r'''import numpy as np
from scipy.stats import norm

def solve_newsvendor(mu, sigma, p, c, o, h):
    """报童模型求解最优订货量"""
    critical_ratio = (p - c + o) / (p - c + h + o)
    q_star = norm.ppf(critical_ratio, loc=mu, scale=sigma)
    return {"optimal_qty": round(q_star, 2), "critical_ratio": round(critical_ratio, 3)}

def monte_carlo_verify(mu, sigma, q_star, p, c, o, h, n=10000):
    demand = np.random.normal(mu, sigma, n)
    revenue = np.minimum(q_star, demand) * p
    costs = c * q_star + h * np.maximum(0, q_star - demand) + o * np.maximum(0, demand - q_star)
    profit = revenue - costs
    return {"mean_profit": round(np.mean(profit), 2), "std_profit": round(np.std(profit), 2), "fill_rate": round(np.mean(demand <= q_star), 3)}

if __name__ == "__main__":
    result = solve_newsvendor(mu=50, sigma=8, p=8, c=3, o=2, h=0.5)
    print(f"最优订货量: {result['optimal_qty']:.1f} kg")
'''

FORECAST = r'''import numpy as np
from statsmodels.tsa.arima.model import ARIMA

def forecast_arima(sales_data, order=(1,1,1), steps=7):
    """ARIMA时间序列预测"""
    model = ARIMA(sales_data, order=order)
    fitted = model.fit()
    forecast = fitted.forecast(steps=steps)
    return {"forecast": list(np.round(forecast, 1)), "summary": str(fitted.summary())}

if __name__ == "__main__":
    data = [45, 52, 48, 55, 50, 47, 53, 49, 51, 46, 54, 50, 48, 56, 52, 49, 55, 51, 47, 53, 50, 48, 55, 52, 49, 54, 51, 48, 56, 50]
    result = forecast_arima(data, order=(1,1,1), steps=7)
    print("未来7天预测销量:", result["forecast"])
'''

SENSITIVITY = r'''import numpy as np
import matplotlib.pyplot as plt

def sensitivity_analysis(base_params, param_ranges):
    """One-at-a-Time sensitivity analysis"""
    results = {}
    for param_name, perturbed in param_ranges.items():
        outputs = []
        for val in perturbed:
            params = dict(base_params)
            params[param_name] = val
            profit = params['price'] * params['demand'] - params['cost'] * val
            outputs.append(profit)
        results[param_name] = {
            "perturbed_values": perturbed,
            "outputs": outputs,
            "sensitivity": (max(outputs) - min(outputs)) / (max(perturbed) - min(perturbed) + 1e-9)
        }
    return results

if __name__ == "__main__":
    params = {'price': 8, 'cost': 3, 'demand': 50, 'holding_cost': 0.5, 'stockout_cost': 2}
    ranges = {
        'demand': np.linspace(40, 60, 11),
        'holding_cost': np.linspace(0.2, 0.8, 7),
        'stockout_cost': np.linspace(1.0, 3.0, 9),
    }
    sa_results = sensitivity_analysis(params, ranges)
    for k, v in sa_results.items():
        print(f"{k}: sensitivity={v['sensitivity']:.4f}")
'''

TOPSIS = r'''import numpy as np

def topsis_evaluate(decision_matrix, weights, beneficial_indices):
    norm_matrix = decision_matrix / np.sqrt((decision_matrix ** 2).sum(axis=0))
    weighted = norm_matrix * weights
    ideal_pos = weighted.max(axis=0)
    ideal_neg = weighted.min(axis=0)
    for idx in beneficial_indices:
        ideal_pos[idx], ideal_neg[idx] = ideal_neg[idx], ideal_pos[idx]
    d_pos = np.sqrt(((weighted - ideal_pos) ** 2).sum(axis=1))
    d_neg = np.sqrt(((weighted - ideal_neg) ** 2).sum(axis=1))
    closeness = d_neg / (d_pos + d_neg)
    rankings = np.argsort(closeness)[::-1] + 1
    return {"rankings": rankings.tolist(), "closeness": closeness.tolist(), "best": rankings[0]}

if __name__ == "__main__":
    data = np.array([[50, 0.1, 0.95, 1000], [45, 0.08, 0.92, 950], [55, 0.12, 0.98, 1200], [48, 0.09, 0.94, 980], [52, 0.11, 0.96, 1100]])
    weights = np.array([0.3, 0.2, 0.3, 0.2])
    result = topsis_evaluate(data, weights, beneficial_indices=[0, 2, 3])
    print("排名:", result["rankings"])
'''

LP_FALLBACK = r'''import numpy as np
from scipy.optimize import linprog

def solve_lp(c, A_ub=None, b_ub=None, bounds=None):
    result = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds)
    if result.success:
        return {"optimal_value": round(result.fun, 4), "optimal_solution": [round(x, 4) for x in result.x], "status": "最优解"}
    return {"status": f"求解失败: {result.message}"}

if __name__ == "__main__":
    c = [1, 2, 3]
    result = solve_lp(c)
    print(result)
'''


# 字典：领域 → 模板字符串。``_mock_response`` 按关键词匹配后取用。
DEMO_CODE_TEMPLATES: Dict[str, str] = {
    "optics_multi": OPTICS_MULTI,
    "optics_double": OPTICS_DOUBLE,
    "newsvendor": NEWSVENDOR,
    "forecast": FORECAST,
    "sensitivity": SENSITIVITY,
    "topsis": TOPSIS,
    "lp_fallback": LP_FALLBACK,
}


# 关键词 → 模板 ID 的映射（``_mock_response`` 直接 import 使用）
DEMO_KEYWORD_TO_TEMPLATE = {
    "optics_multi": ("optics_multi", ["多光束", "多次反射", "airy", "多束", "硅晶圆"]),
    "optics_double": ("optics_double", ["干涉", "外延", "厚度", "折射率", "光程差", "双光束", "SiC", "碳化硅", "红外", "波数", "反射率", "菲涅尔", "薄膜", "膜厚"]),
    "newsvendor": ("newsvendor", ["订货", "库存", "报童", "随机"]),
    "forecast": ("forecast", ["预测", "时序", "arima", "需求"]),
    "sensitivity": ("sensitivity", ["灵敏度", "稳健性", "参数"]),
    "topsis": ("topsis", ["评价", "topsis", "综合", "品类", "ahp"]),
}
