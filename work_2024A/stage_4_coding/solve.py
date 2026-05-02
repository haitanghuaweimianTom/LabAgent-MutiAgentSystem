import numpy as np
import pandas as pd
import os, json
from math import sin, cos, sqrt, asin, atan2, hypot, pi, exp

p = 0.55
b = p / (2 * pi)
v0 = 1.0
theta0 = 32 * pi
r0 = b * theta0
L_head = 2.86
L_body = 1.65
d_head = L_head - 0.55
d_body = L_body - 0.55
n = 223
dt = 1.0
T_max = 300

def arc_len_diff(theta_a, theta_b):
    return 0.5 * b * (theta_a * sqrt(1 + theta_a**2) - theta_b * sqrt(1 + theta_b**2) + np.arcsinh(theta_a) - np.arcsinh(theta_b))

def s_from_theta(theta):
    return 0.5 * b * (theta0 * sqrt(1 + theta0**2) - theta * sqrt(1 + theta**2) + np.arcsinh(theta0) - np.arcsinh(theta))

def theta_from_s(s_target):
    lo, hi = 0.0, theta0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if s_from_theta(mid) < s_target:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0

def xy(theta):
    return b * theta * cos(theta), b * theta * sin(theta)

def tangent_angle(theta):
    return atan2(sin(theta) + theta * cos(theta), cos(theta) - theta * sin(theta))

def solve_chain(theta1, t):
    thetas = [0.0] * n
    xs = [0.0] * n
    ys = [0.0] * n
    thetas[0] = theta1
    xs[0], ys[0] = xy(theta1)
    for i in range(1, n):
        d = d_head if i == 1 else d_body
        x_prev, y_prev = xs[i-1], ys[i-1]
        theta_prev = thetas[i-1]
        def dist(th):
            x, y = xy(th)
            return hypot(x - x_prev, y - y_prev)
        lo, hi = theta_prev, theta_prev + pi
        if dist(lo) < d - 1e-6:
            thetas[i] = lo
            xs[i], ys[i] = xy(lo)
            continue
        for _ in range(50):
            mid = (lo + hi) / 2.0
            if dist(mid) > d:
                lo = mid
            else:
                hi = mid
        th = (lo + hi) / 2.0
        thetas[i] = th
        xs[i], ys[i] = xy(th)
    return xs, ys, thetas

def velocity(theta, dtheta_dt):
    dx = b * (cos(theta) - theta * sin(theta))
    dy = b * (sin(theta) + theta * cos(theta))
    return dtheta_dt * sqrt(dx**2 + dy**2)

def compute_all():
    times = list(range(0, T_max + 1))
    result = {}
    for t in times:
        s = v0 * t
        th1 = theta_from_s(s)
        xs, ys, ths = solve_chain(th1, t)
        dth = -v0 / (b * sqrt(1 + th1**2))
        v_head = float(v0)
        vs = [v_head]
        for i in range(1, n):
            d = d_head if i == 1 else d_body
            thi = ths[i]
            thim1 = ths[i-1]
            xi, yi = xy(thi)
            xim1, yim1 = xy(thim1)
            dx = xi - xim1
            dy = yi - yim1
            dist = hypot(dx, dy)
            if dist < 1e-10:
                vs.append(0.0)
                continue
            ux, uy = dx / dist, dy / dist
            vim1_x = -v0 * (cos(thim1) - thim1 * sin(thim1)) / sqrt(1 + thim1**2)
            vim1_y = -v0 * (sin(thim1) + thim1 * cos(thim1)) / sqrt(1 + thim1**2)
            vi = vim1_x * ux + vim1_y * uy
            vs.append(float(abs(vi)))
        result[t] = {
            'head_theta': float(th1),
            'head_x': float(xs[0]),
            'head_y': float(ys[0]),
            'positions': [(float(xs[i]), float(ys[i])) for i in range(min(n, 10))],
            'velocities': [float(v) for v in vs[:10]]
        }
    return result

def read_existing_results():
    files = {"result1": "result1.xlsx", "result2": "result2.xlsx", "result4": "result4.xlsx"}
    data = {}
    for key, fname in files.items():
        try:
            df = pd.read_excel(fname)
            data[key] = df.to_dict('records')
        except:
            data[key] = []
    return data

def main():
    existing = read_existing_results()
    computed = compute_all()
    results = {
        'existing_files': existing,
        'computed_spiral': {str(k): v for k, v in computed.items()},
        'summary': {
            'total_segments': n,
            'spiral_pitch': float(p),
            'initial_radius': float(r0),
            'initial_theta': float(theta0),
            'simulation_time': T_max,
            'head_distance_traveled': float(v0 * T_max)
        }
    }
    output_dir = os.environ.get('OUTPUT_DIR', '.')
    out_path = os.path.join(output_dir, 'execution', 'results.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)

if __name__ == '__main__':
    main()