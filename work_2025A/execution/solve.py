#!/usr/bin/env python3
"""
2025A 烟幕干扰弹投放策略 — 物理精确求解器（向量化加速版）
修正：
1. NumPy 向量化计算覆盖区间
2. 粗网格+局部 Nelder-Mead 细化
3. Q5 采用穷举分配而非贪心
4. multi-decoy 的 last_release 初始值修正为 -1.0
"""
import os
import json
import math
import itertools
import numpy as np
from scipy.optimize import minimize
import pandas as pd

G = 9.8
V_SHELL = 30.0
V_SINK = 3.0
R_EFF = 10.0
T_CLOUD_MAX = 20.0
V_MISSILE = 300.0

P_DECOY = np.array([0.0, 0.0, 0.0])
P_TARGET = np.array([0.0, 200.0, 0.0])

MISSILES = {
    "M1": {"P0": np.array([20000.0, 0.0, 2000.0])},
    "M2": {"P0": np.array([19000.0, 600.0, 2100.0])},
    "M3": {"P0": np.array([18000.0, -600.0, 1900.0])},
}

UAVS = {
    "FY1": {"P0": np.array([17800.0, 0.0, 1800.0]), "v_min": 70.0, "v_max": 140.0},
    "FY2": {"P0": np.array([12000.0, 1400.0, 1400.0]), "v_min": 70.0, "v_max": 140.0},
    "FY3": {"P0": np.array([6000.0, -3000.0, 700.0]), "v_min": 70.0, "v_max": 140.0},
    "FY4": {"P0": np.array([11000.0, 2000.0, 1800.0]), "v_min": 70.0, "v_max": 140.0},
    "FY5": {"P0": np.array([13000.0, -2000.0, 1300.0]), "v_min": 70.0, "v_max": 140.0},
}


_missile_dirs = {}
def missile_dir(missile_name):
    if missile_name not in _missile_dirs:
        d = P_DECOY - MISSILES[missile_name]["P0"]
        _missile_dirs[missile_name] = d / np.linalg.norm(d)
    return _missile_dirs[missile_name]


def missile_pos(missile_name, t):
    return MISSILES[missile_name]["P0"][:, None] + missile_dir(missile_name)[:, None] * V_MISSILE * t


def cloud_centers(uav_name, theta, v, t_release, t_fuse, times):
    P0 = UAVS[uav_name]["P0"]
    d = np.array([math.cos(theta), math.sin(theta), 0.0])
    P_release = P0 + d * v * t_release
    t_burst = t_release + t_fuse
    times = np.asarray(times)

    dt = times - t_release
    dt_shell = t_burst - t_release

    mask_flight = times < t_burst
    mask_sink = ~mask_flight

    centers = np.zeros((3, len(times)))

    if np.any(mask_flight):
        t_f = times[mask_flight]
        dt_f = t_f - t_release
        centers[0, mask_flight] = P_release[0] + d[0] * V_SHELL * dt_f
        centers[1, mask_flight] = P_release[1] + d[1] * V_SHELL * dt_f
        centers[2, mask_flight] = P_release[2] - 0.5 * G * dt_f ** 2

    if np.any(mask_sink):
        P_burst = np.array([
            P_release[0] + d[0] * V_SHELL * dt_shell,
            P_release[1] + d[1] * V_SHELL * dt_shell,
            P_release[2] - 0.5 * G * dt_shell ** 2,
        ])
        dt_s = times[mask_sink] - t_burst
        centers[0, mask_sink] = P_burst[0]
        centers[1, mask_sink] = P_burst[1]
        centers[2, mask_sink] = P_burst[2] - V_SINK * dt_s

    return centers


def dist_point_to_segment_vec(P, A, B):
    AB = (B - A).reshape(3, 1)
    AP = P - A.reshape(3, 1)
    ab2 = np.dot(AB.ravel(), AB.ravel())
    if ab2 < 1e-12:
        return np.linalg.norm(P - A.reshape(3, 1), axis=0)
    t = np.sum(AP * AB, axis=0) / ab2
    t = np.clip(t, 0.0, 1.0)
    closest = A.reshape(3, 1) + t * AB
    return np.linalg.norm(P - closest, axis=0)


def compute_coverage_union_vec(uav_name, missile_name, decoys, n_check=1200):
    if not decoys:
        return 0.0, []

    dist_to_decoy = np.linalg.norm(MISSILES[missile_name]["P0"] - P_DECOY)
    t_impact = dist_to_decoy / V_MISSILE

    t_min = min(t_release + t_fuse for (_, _, t_release, t_fuse) in decoys)
    t_max = min(
        max(t_release + t_fuse + T_CLOUD_MAX for (_, _, t_release, t_fuse) in decoys),
        t_impact,
    )
    if t_max <= t_min:
        return 0.0, []

    times = np.linspace(t_min, t_max, n_check)
    covered = np.zeros(n_check, dtype=bool)
    pm_all = missile_pos(missile_name, times)

    for theta, v, t_release, t_fuse in decoys:
        pc_all = cloud_centers(uav_name, theta, v, t_release, t_fuse, times)
        d = dist_point_to_segment_vec(pc_all, pm_all[:, 0], P_TARGET)
        covered |= (d <= R_EFF)

    intervals = []
    in_seg = False
    t_start = None
    for i in range(n_check):
        if covered[i] and not in_seg:
            in_seg = True
            t_start = times[i]
        elif not covered[i] and in_seg:
            in_seg = False
            intervals.append((float(t_start), float(times[i - 1])))
    if in_seg:
        intervals.append((float(t_start), float(times[-1])))

    tau = sum(t1 - t0 for t0, t1 in intervals)
    return float(tau), intervals


def coverage_single_vec(uav_name, missile_name, theta, v, t_release, t_fuse, n_check=400):
    tau, _ = compute_coverage_union_vec(uav_name, missile_name, [(theta, v, t_release, t_fuse)], n_check=n_check)
    return tau


# ---------------------------------------------------------------------------
# 两阶段优化
# ---------------------------------------------------------------------------
def optimize_single_decoy(uav_name, missile_name, n_check_coarse=200, n_check_fine=2000):
    best_tau = -1.0
    best_params = None

    thetas = np.linspace(0.0, 2.0 * math.pi, 48)
    vs = np.linspace(UAVS[uav_name]["v_min"], UAVS[uav_name]["v_max"], 6)
    t_releases = np.linspace(0.0, 10.0, 21)
    t_fuses = np.linspace(0.5, 5.0, 10)

    for theta in thetas:
        for v in vs:
            for t_release in t_releases:
                for t_fuse in t_fuses:
                    tau = coverage_single_vec(uav_name, missile_name, theta, v, t_release, t_fuse, n_check_coarse)
                    if tau > best_tau:
                        best_tau = tau
                        best_params = (theta, v, t_release, t_fuse)

    if best_params is None:
        best_params = (math.pi, UAVS[uav_name]["v_max"], 0.0, 3.0)

    def neg_tau(x):
        theta, v, t_release, t_fuse = x
        if v < UAVS[uav_name]["v_min"] or v > UAVS[uav_name]["v_max"] or t_release < 0 or t_fuse < 0.2:
            return 0.0
        return -coverage_single_vec(uav_name, missile_name, theta, v, t_release, t_fuse, n_check_fine)

    result = minimize(
        neg_tau,
        x0=np.array(best_params),
        method="Nelder-Mead",
        options={"maxiter": 300, "xatol": 1e-3, "fatol": 1e-3},
    )

    theta, v, t_release, t_fuse = result.x
    v = float(np.clip(v, UAVS[uav_name]["v_min"], UAVS[uav_name]["v_max"]))
    t_release = max(0.0, float(t_release))
    t_fuse = max(0.2, float(t_fuse))

    tau, intervals = compute_coverage_union_vec(uav_name, missile_name, [(theta, v, t_release, t_fuse)], n_check=n_check_fine)
    return {
        "theta": float(theta), "v": float(v), "t_release": float(t_release), "t_fuse": float(t_fuse),
        "tau_eff": float(tau), "intervals": intervals,
    }


def optimize_multi_decoy(uav_name, missile_name, n_decoys=3):
    decoys = []
    last_release = -1.0

    for idx in range(n_decoys):
        best_tau = -1.0
        best_params = None

        thetas = np.linspace(0.0, 2.0 * math.pi, 36)
        vs = np.linspace(UAVS[uav_name]["v_min"], UAVS[uav_name]["v_max"], 5)
        t_releases = np.linspace(last_release + 1.0, last_release + 1.0 + 8.0, 17)
        t_fuses = np.linspace(0.5, 5.0, 8)

        current_decoys = decoys.copy()
        for theta in thetas:
            for v in vs:
                for t_release in t_releases:
                    for t_fuse in t_fuses:
                        test_decoys = current_decoys + [(theta, v, t_release, t_fuse)]
                        tau, _ = compute_coverage_union_vec(uav_name, missile_name, test_decoys, n_check=200)
                        if tau > best_tau:
                            best_tau = tau
                            best_params = (theta, v, t_release, t_fuse)

        if best_params is None:
            best_params = (math.pi, UAVS[uav_name]["v_max"], last_release + 1.0, 3.0)

        def neg_tau(x):
            theta, v, t_release, t_fuse = x
            if v < UAVS[uav_name]["v_min"] or v > UAVS[uav_name]["v_max"] or t_release < last_release + 1.0 or t_fuse < 0.2:
                return 0.0
            test_decoys = current_decoys + [(theta, v, t_release, t_fuse)]
            tau, _ = compute_coverage_union_vec(uav_name, missile_name, test_decoys, n_check=800)
            return -tau

        result = minimize(
            neg_tau,
            x0=np.array(best_params),
            method="Nelder-Mead",
            options={"maxiter": 200, "xatol": 1e-3, "fatol": 1e-3},
        )

        theta, v, t_release, t_fuse = result.x
        v = float(np.clip(v, UAVS[uav_name]["v_min"], UAVS[uav_name]["v_max"]))
        t_release = max(last_release + 1.0, float(t_release))
        t_fuse = max(0.2, float(t_fuse))
        last_release = t_release
        decoys.append((theta, v, t_release, t_fuse))

    tau, intervals = compute_coverage_union_vec(uav_name, missile_name, decoys, n_check=2000)
    return {
        "n_decoys": n_decoys,
        "decoys": [
            {"id": i + 1, "theta": float(d[0]), "v": float(d[1]), "t_release": float(d[2]), "t_fuse": float(d[3])}
            for i, d in enumerate(decoys)
        ],
        "tau_eff": float(tau), "intervals": intervals,
    }


def solve_q1():
    theta = math.pi
    v = 120.0
    t_release = 1.5
    t_fuse = 3.6
    tau, intervals = compute_coverage_union_vec("FY1", "M1", [(theta, v, t_release, t_fuse)], n_check=2000)
    return {
        "scenario": "Q1_FY1_fixed_vs_M1",
        "theta": float(theta), "v": float(v), "t_release": float(t_release), "t_fuse": float(t_fuse),
        "tau_eff": float(tau), "intervals": intervals,
    }


def solve_q2():
    return optimize_single_decoy("FY1", "M1")


def solve_q3():
    return optimize_multi_decoy("FY1", "M1", n_decoys=3)


def solve_q4():
    results = {}
    for uav in ["FY1", "FY2", "FY3"]:
        results[uav] = optimize_single_decoy(uav, "M1")
    return results


def solve_q5():
    """Q5: 穷举所有 UAV-导弹分配方案（每枚导弹分配一架不同 UAV），取总覆盖最大"""
    # 先计算每个配对的单枚最优覆盖
    pair_coverage = {}
    for uav_name in UAVS:
        for missile_name in MISSILES:
            key = (uav_name, missile_name)
            print(f"    [Q5-pair] {uav_name} vs {missile_name} ...")
            pair_coverage[key] = optimize_single_decoy(uav_name, missile_name)

    # 穷举所有 3-导弹到 3-UAV 的分配（从 5 架 UAV 中选 3 架排列，共 60 种）
    missiles_list = ["M1", "M2", "M3"]
    best_assignment = None
    best_total = -1.0

    for uavs_perm in itertools.permutations(UAVS.keys(), 3):
        total = sum(pair_coverage[(uav, m)]["tau_eff"] for uav, m in zip(uavs_perm, missiles_list))
        if total > best_total:
            best_total = total
            best_assignment = list(zip(uavs_perm, missiles_list))

    assignments = []
    for uav_name, missile_name in best_assignment:
        assignments.append({
            "uav": uav_name, "missile": missile_name,
            "tau_eff": pair_coverage[(uav_name, missile_name)]["tau_eff"],
            "params": pair_coverage[(uav_name, missile_name)],
        })

    total_coverage = sum(a["tau_eff"] for a in assignments)

    print("    [Q5-multi] Optimizing multi-decoy for assigned pairs...")
    multi_results = {}
    for a in assignments:
        uav, missile = a["uav"], a["missile"]
        multi_results[f"{uav}_{missile}"] = optimize_multi_decoy(uav, missile, n_decoys=3)

    total_multi = sum(r["tau_eff"] for r in multi_results.values())

    return {
        "single_pair": {f"{k[0]}_{k[1]}": v for k, v in pair_coverage.items()},
        "assignments": assignments,
        "total_coverage_single": float(total_coverage),
        "multi_pair": multi_results,
        "total_coverage_multi": float(total_multi),
    }


def solve_robust():
    """Result4: 鲁棒配置 — 为每枚导弹选主/备"""
    pair = {}
    for uav in UAVS:
        for m in MISSILES:
            print(f"    [Robust] {uav} vs {m} ...")
            pair[(uav, m)] = optimize_single_decoy(uav, m)

    robust = {}
    for m in MISSILES:
        candidates = [(uav, pair[(uav, m)]["tau_eff"]) for uav in UAVS]
        candidates.sort(key=lambda x: x[1], reverse=True)
        primary = candidates[0]
        backup = candidates[1] if len(candidates) > 1 else (None, 0.0)
        robust[m] = {
            "primary": {"uav": primary[0], "tau_eff": float(primary[1])},
            "backup": {"uav": backup[0], "tau_eff": float(backup[1])},
        }

    min_cov = min(robust[m]["primary"]["tau_eff"] for m in MISSILES)
    redundancy = sum(1 for m in MISSILES if robust[m]["backup"]["tau_eff"] > 0.5)

    optimal_assignment = []
    for m in MISSILES:
        optimal_assignment.append({"uav": robust[m]["primary"]["uav"], "missile": m, "role": "primary"})
        if robust[m]["backup"]["uav"]:
            optimal_assignment.append({"uav": robust[m]["backup"]["uav"], "missile": m, "role": "backup"})

    return {
        "scenario": "5UAV_3Missile_robust",
        "min_coverage_time": float(min_cov),
        "redundancy": int(redundancy),
        "optimal_assignment": optimal_assignment,
        "details": {m: robust[m] for m in MISSILES},
    }


def main():
    print("[Solver] Solving Q1...")
    q1 = solve_q1()
    print(f"  Q1 tau_eff = {q1['tau_eff']:.3f}s")

    print("[Solver] Solving Q2...")
    q2 = solve_q2()
    print(f"  Q2 tau_eff = {q2['tau_eff']:.3f}s")

    print("[Solver] Solving Q3...")
    q3 = solve_q3()
    print(f"  Q3 tau_eff = {q3['tau_eff']:.3f}s")

    print("[Solver] Solving Q4...")
    q4 = solve_q4()
    for k, v in q4.items():
        print(f"  Q4 {k} tau_eff = {v['tau_eff']:.3f}s")

    print("[Solver] Solving Q5...")
    q5 = solve_q5()
    print(f"  Q5 total single = {q5['total_coverage_single']:.3f}s")
    print(f"  Q5 total multi  = {q5['total_coverage_multi']:.3f}s")
    for a in q5["assignments"]:
        print(f"    {a['uav']} -> {a['missile']}: {a['tau_eff']:.3f}s")

    print("[Solver] Solving robust...")
    r4 = solve_robust()
    print(f"  Robust min_cov = {r4['min_coverage_time']:.3f}s, redundancy = {r4['redundancy']}")

    results = {
        "result1": q1,
        "result2": {
            "scenario": "FY1_FY2_FY3_vs_M1",
            **{k.lower(): v for k, v in q4.items()},
        },
        "result3": {
            "scenario": "coordinated_3UAV_3Missile",
            "total_coverage": float(q5["total_coverage_single"]),
            "assignments": [
                {"uav": a["uav"], "missile": a["missile"], "tau_eff": a["tau_eff"]}
                for a in q5["assignments"]
            ],
        },
        "result4": r4,
        "detailed": {"q1": q1, "q2": q2, "q3": q3, "q4": q4, "q5": q5},
    }

    # 修正输出路径：直接写到当前目录（脚本已在 execution/ 内）
    out_path = "results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=float)
    print(f"[Solver] Saved {out_path}")

    # 生成 xlsx
    df1 = pd.DataFrame([
        {
            "decoy_id": d["id"],
            "theta_rad": d["theta"],
            "v_mps": d["v"],
            "t_release_s": d["t_release"],
            "t_fuse_s": d["t_fuse"],
            "P_release_x": UAVS["FY1"]["P0"][0] + math.cos(d["theta"]) * d["v"] * d["t_release"],
            "P_release_y": UAVS["FY1"]["P0"][1] + math.sin(d["theta"]) * d["v"] * d["t_release"],
            "P_release_z": UAVS["FY1"]["P0"][2],
        }
        for d in q3["decoys"]
    ])
    df1.to_excel("result1.xlsx", index=False)

    rows = []
    for uav_name, data in q4.items():
        theta = data["theta"]
        v = data["v"]
        t_release = data["t_release"]
        P0 = UAVS[uav_name]["P0"]
        rows.append({
            "uav": uav_name,
            "theta_rad": theta,
            "v_mps": v,
            "t_release_s": t_release,
            "t_fuse_s": data["t_fuse"],
            "tau_eff_s": data["tau_eff"],
            "P_release_x": P0[0] + math.cos(theta) * v * t_release,
            "P_release_y": P0[1] + math.sin(theta) * v * t_release,
            "P_release_z": P0[2],
        })
    df2 = pd.DataFrame(rows)
    df2.to_excel("result2.xlsx", index=False)

    rows = []
    for a in q5["assignments"]:
        p = a["params"]
        theta = p["theta"]
        v = p["v"]
        t_release = p["t_release"]
        P0 = UAVS[a["uav"]]["P0"]
        rows.append({
            "uav": a["uav"],
            "missile": a["missile"],
            "theta_rad": theta,
            "v_mps": v,
            "t_release_s": t_release,
            "t_fuse_s": p["t_fuse"],
            "tau_eff_s": a["tau_eff"],
            "P_release_x": P0[0] + math.cos(theta) * v * t_release,
            "P_release_y": P0[1] + math.sin(theta) * v * t_release,
            "P_release_z": P0[2],
        })
    df3 = pd.DataFrame(rows)
    df3.to_excel("result3.xlsx", index=False)

    print("[Solver] Saved result1.xlsx, result2.xlsx, result3.xlsx")


if __name__ == "__main__":
    main()
