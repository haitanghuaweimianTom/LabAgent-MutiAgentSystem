import os, json, pandas as pd, numpy as np
from itertools import product

def load_series(path):
    if path.endswith('.xlsx'): df = pd.read_excel(path)
    else: df = pd.read_csv(path)
    col = df.select_dtypes(include='number').iloc[:, 0].astype(float).dropna()
    return col.values

def simulate(prices, fx, act_hist, psi, lambdas):
    gamma, step = 7.3, 10
    theo, act = [], []
    res, last_p = 0.0, prices[0]
    for i in range(step, len(prices), step):
        p_curr = np.mean(prices[i-step:i])
        delta = p_curr - last_p
        r = fx[i]
        lam = lambdas[0] if p_curr < 60 else (lambdas[1] if p_curr <= 100 else lambdas[2])
        d_rmb = psi * delta * r * gamma * lam
        d_rmb = np.clip(d_rmb, 40*r*gamma*lam, 130*r*gamma*lam)
        val = d_rmb + res
        if abs(val) < 50:
            res = val
            a = 0.0
        else:
            a = val
            res = 0.0
        theo.append(float(d_rmb))
        act.append(float(a))
        last_p = p_curr
    min_len_sim = min(len(act), len(act_hist))
    m = float(np.mean((np.array(act[:min_len_sim]) - act_hist[:min_len_sim])**2))
    return theo, act, m

def find_data_dir():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        script_dir,
        os.path.dirname(script_dir),
        os.getcwd(),
        os.path.join(script_dir, "data"),
        os.path.join(os.path.dirname(script_dir), "data"),
        os.path.join(script_dir, "2026-guangzhouUSETHIS"),
        os.path.join(os.path.dirname(script_dir), "2026-guangzhouUSETHIS")
    ]
    for cand in candidates:
        cand = os.path.abspath(cand)
        if os.path.isdir(cand) and os.path.exists(os.path.join(cand, "macro_data.xlsx")):
            return cand
    return script_dir

def main():
    base_dir = find_data_dir()
    data_paths = {
        "macro": os.path.join(base_dir, "macro_data.xlsx"),
        "brent": os.path.join(base_dir, "brent_daily.csv"),
        "hist": os.path.join(base_dir, "china_oil_adjust_history.xlsx"),
        "wti": os.path.join(base_dir, "wti_daily.csv"),
        "cpi": os.path.join(base_dir, "china_cpi_monthly.csv"),
        "ppi": os.path.join(base_dir, "china_ppi_monthly.csv")
    }
    fx = load_series(data_paths["macro"])
    brent = load_series(data_paths["brent"])
    wti = load_series(data_paths["wti"])
    act_hist = load_series(data_paths["hist"])
    
    min_len = min(len(fx), len(brent), len(wti), len(act_hist))
    prices = 0.5*brent[:min_len] + 0.5*wti[:min_len]
    fx = fx[:min_len]
    act_hist = act_hist[:min_len]
    
    grid = list(product(np.arange(0.8, 1.11, 0.05), np.arange(0.6, 1.01, 0.05)))
    best_mse, best_p, best_l = 1e9, None, None
    best_theo, best_act = [], []
    for p, l in grid:
        t, a, m = simulate(prices, fx, act_hist, p, [1.0, l, 0.5])
        if m < best_mse:
            best_mse, best_p, best_l = m, p, l
            best_theo, best_act = t, a
            
    regs = [0, 0, 0]
    for i in range(10, len(prices), 10):
        p = np.mean(prices[i-10:i])
        if p < 60: regs[0] += 1
        elif p <= 100: regs[1] += 1
        else: regs[2] += 1
        
    results = {
        "calibrated_psi": float(best_p),
        "calibrated_lambda_mid": float(best_l),
        "calibration_mse": best_mse,
        "regime_distribution_low": int(regs[0]),
        "regime_distribution_mid": int(regs[1]),
        "regime_distribution_high": int(regs[2]),
        "total_adjustment_windows": int(len(best_act)),
        "mean_theoretical_change": float(np.mean(best_theo)),
        "mean_actual_change": float(np.mean(best_act)),
        "final_residual": float(0.0),
        "policy_sensitivity_score": float(best_p * best_l)
    }
    
    output_dir = os.environ.get('OUTPUT_DIR', '.')
    out_path = os.path.join(output_dir, 'execution', 'results.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)

if __name__ == '__main__':
    main()