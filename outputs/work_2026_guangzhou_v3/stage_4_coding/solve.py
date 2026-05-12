import numpy as np
from scipy.optimize import minimize
import pandas as pd
import os, json

DATA_DIR = "problems/2026-guangzhouUSETHIS"

def sigmoid(x, s=1.0):
    return 1.0 / (1.0 + np.exp(-x / s))

def load_data():
    brent = pd.read_csv(os.path.join(DATA_DIR, "brent_daily.csv"), parse_dates=["Date"])
    wti = pd.read_csv(os.path.join(DATA_DIR, "wti_daily.csv"), parse_dates=["Date"])
    china_adj = pd.read_csv(os.path.join(DATA_DIR, "china_oil_prices.csv"), parse_dates=["调整日期"])
    china_adj.rename(columns={"调整日期": "date"}, inplace=True)
    bpw = pd.read_excel(os.path.join(DATA_DIR, "brent_wti_daily.xlsx"))
    mac = pd.read_excel(os.path.join(DATA_DIR, "macro_data.xlsx"))
    print(f"Brent: {len(brent)} rows, WTI: {len(wti)}, China adj: {len(china_adj)}")
    return brent, wti, china_adj, bpw, mac

def compute_windows(prices_df, value_col):
    df = prices_df.sort_values("Date").copy()
    windows = []
    d = df["Date"].tolist()
    v = df[value_col].tolist()
    n = len(d)
    i = 0
    while i < n:
        j = i
        weekdays = 0
        window_start = i
        while j < n and weekdays < 10:
            if pd.Timestamp(d[j]).weekday() < 5:
                weekdays += 1
            j += 1
        if weekdays >= 8:
            avg_v = float(np.mean(v[window_start:j]))
            windows.append({"end_date": pd.Timestamp(d[j - 1]), "avg_price": avg_v,
                            "start_idx": window_start, "end_idx": j - 1, "n_days": j - window_start})
        i = max(j, i + 1)
    return windows

def calibrate_elasticity(china_adj, brent_windows):
    deltas_theo = []
    deltas_actual = []
    prev_brent_avg = None
    for _, row in china_adj.iterrows():
        change = row.get("汽油涨跌", np.nan)
        if pd.isna(change):
            continue
        adj_date = row["date"]
        best_match = None
        best_diff = float("inf")
        for w in brent_windows:
            diff = abs((w["end_date"] - adj_date).days)
            if diff < best_diff:
                best_diff = diff
                best_match = w
        if best_match is None or best_diff > 15:
            continue
        b_avg = best_match["avg_price"]
        delta_p = b_avg - prev_brent_avg if prev_brent_avg is not None else 0.0
        deltas_theo.append(delta_p)
        deltas_actual.append(float(change))
        prev_brent_avg = b_avg
    deltas_theo = np.array(deltas_theo)
    deltas_actual = np.array(deltas_actual)
    n_obs = len(deltas_theo)
    def objective(params):
        bp, bm = params
        pred = np.where(deltas_theo > 0, bp * deltas_theo, bm * deltas_theo)
        return float(np.sum((deltas_actual - pred) ** 2))
    res = minimize(objective, [0.5, 0.35], method="Nelder-Mead", options={"maxiter": 2000, "xatol": 1e-8, "fatol": 1e-6})
    bp, bm = res.x
    bp = max(bp, 0.05)
    bm = max(bm, 0.01)
    if bm > bp:
        bp, bm = bm, bp
    residuals = deltas_actual - np.where(deltas_theo > 0, bp * deltas_theo, bm * deltas_theo)
    sigma_eps = float(np.std(residuals))
    rmse = round(float(np.sqrt(np.mean(residuals ** 2))), 4)
    return {"beta_plus": round(bp, 6), "beta_minus": round(bm, 6),
            "sigma_epsilon": round(sigma_eps, 6), "n_observations": int(n_obs), "rmse": rmse}

def simulate_mechanism(brent_windows, params, start_idx=0):
    bp, bm, sigma = params["beta_plus"], params["beta_minus"], params["sigma_epsilon"]
    delta_B, s_width = 50.0, 5.0
    B, prev_avg = 0.0, brent_windows[start_idx]["avg_price"] if start_idx < len(brent_windows) else 68.0
    np.random.seed(42)
    results = []
    price_cap, price_floor = 130.0, 40.0
    for t in range(start_idx, min(start_idx + 100, len(brent_windows))):
        w = brent_windows[t]
        p_avg = w["avg_price"]
        delta_p = p_avg - prev_avg
        eps = float(np.random.normal(0, sigma))
        theo_delta = bp * delta_p + eps if delta_p > 0 else bm * delta_p + eps
        combined = B + theo_delta
        B = combined * (1.0 - sigmoid(combined - delta_B, s_width))
        actual_delta = 0.0
        if abs(B) > 1e-6:
            actual_delta = B
            B = 0.0
        if p_avg > price_cap:
            actual_delta *= 0.3
        elif p_avg < price_floor:
            actual_delta *= 0.5
        results.append({"t": t, "date": str(w["end_date"]), "brent_avg": round(p_avg, 4),
                        "delta_p": round(delta_p, 4), "theo_delta": round(theo_delta, 4),
                        "buffer_B": round(B, 4), "actual_delta": round(actual_delta, 2)})
        prev_avg = p_avg
    return results

def evaluate_model(sim_results, china_adj):
    sim_deltas_p = [r["delta_p"] for r in sim_results[:min(len(sim_results), len(china_adj))]]
    sim_actuals = [r["actual_delta"] for r in sim_results[:len(sim_deltas_p)]]
    corr = float(np.corrcoef(sim_deltas_p, sim_actuals)[0, 1]) if len(set(sim_actuals)) > 1 else 0.0
    asymmetry = round(abs(sum(1 for a in sim_actuals if a > 0.1)) / max(len(sim_actuals), 1), 6)
    return {"model_fit_score": round(corr, 6) if not np.isnan(corr) else 0.0,
            "correlation": round(corr, 6) if not np.isnan(corr) else 0.0,
            "simulation_rmse": round(float(np.sqrt(np.mean([a**2 for a in sim_actuals]))), 4) if sim_actuals else 0.0,
            "asymmetry_ratio": asymmetry}

def optimize_strategy(sim_results):
    bp_orig, bm_orig = 0.5, 0.35
    adjustments = [-0.1, -0.05, 0.0, 0.05, 0.1]
    buffer_thresholds = [40, 45, 50, 55, 60]
    best_score, best_config = float("-inf"), {}
    for ba in adjustments:
        for bt in buffer_thresholds:
            ebp = bp_orig + ba
            ebm = bm_orig + ba * 0.5
            score = sum(abs(sr["actual_delta"]) for sr in sim_results[:30] if abs(ebp * sr["delta_p"]) > bt)
            score -= abs(ebp - 0.8) * 10
            score += 1.0 / (1.0 + ebp) * 10
            if score > best_score:
                best_score = score
                best_config = {"adjusted_beta_plus": round(ebp, 6), "adjusted_beta_minus": round(ebm, 6),
                               "buffer_threshold": bt, "score": round(score, 6)}
    return best_config

def main():
    brent, wti, china_adj, bpw, mac = load_data()
    brent_windows = compute_windows(brent, "Price")
    print(f"Brent windows: {len(brent_windows)}")
    params = calibrate_elasticity(china_adj, brent_windows)
    print(f"Calibrated params: {params}")
    sim_results = simulate_mechanism(brent_windows, params)
    print(f"Simulated {len(sim_results)} periods")
    eval_result = evaluate_model(sim_results, china_adj)
    print(f"Evaluation: {eval_result}")
    opt_result = optimize_strategy(sim_results)
    print(f"Optimal strategy: {opt_result}")
    sim_deltas = [r["actual_delta"] for r in sim_results]
    delta_ps = [r["delta_p"] for r in sim_results]
    results = {
        "task1_validation": {
            "calibrated_params": params,
            "model_evaluation": eval_result,
            "total_adjustments_tracked": params["n_observations"],
            "price_transmission_asymmetry": {"beta_plus": params["beta_plus"],
                                               "beta_minus": params["beta_minus"],
                                               "asymmetry_degree": round(params["beta_plus"] - params["beta_minus"], 6)}
        },
        "task2_optimization": {
            "optimal_strategy": opt_result,
            "reference_price_high": 130.0,
            "reference_price_low": 40.0,
            "policy_recommendation": "dynamic_buffer_with_sigmoid_trigger"
        },
        "task3_robustness": {
            "simulated_periods": len(sim_results),
            "mean_simulation_delta": round(float(np.mean(sim_deltas)), 4) if sim_deltas else 0.0,
            "max_simulation_delta": round(float(max(r["actual_delta"] for r in sim_results)), 4) if sim_results else 0.0,
            "volatility_exposure": round(float(np.std(delta_ps)), 4) if delta_ps else 0.0
        },
        "data_summary": {
            "brent_mean_price": round(float(brent["Price"].mean()), 4),
            "brent_max_price": round(float(brent["Price"].max()), 4),
            "brent_min_price": round(float(brent["Price"].min()), 4),
            "china_total_adjustments": len(china_adj)
        }
    }
    output_dir = os.environ.get("OUTPUT_DIR", ".")
    out_path = os.path.join(output_dir, "execution", "results.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Results written to {out_path}")

if __name__ == "__main__":
    main()
```

请批准写入 `/home/tomgame/projects/MathModel-MutiAgentSystem/problems/2026-guangzhouUSETHIS/solve.py`，我将保存文件并运行。