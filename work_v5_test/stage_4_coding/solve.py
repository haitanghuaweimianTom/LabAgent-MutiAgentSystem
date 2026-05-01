import numpy as np
import pandas as pd
import os, json
from math import sqrt, sin, cos, atan2, pi, exp

def missile_pos(t, idx):
    targets = [(20000, 0, 2000), (19000, 600, 2100), (18000, -600, 1900)]
    v = 300.0
    P0 = targets[idx]
    dist0 = sqrt(P0[0]**2 + P0[1]**2 + P0[2]**2)
    dir_vec = (-P0[0]/dist0, -P0[1]/dist0, -P0[2]/dist0)
    return (P0[0] + v*t*dir_vec[0], P0[1] + v*t*dir_vec[1], P0[2] + v*t*dir_vec[2])

def line_cylinder_intersect(p1, p2, c, R, H):
    dx, dy, dz = p2[0]-p1[0], p2[1]-p1[1], p2[2]-p1[2]
    a = dx*dx + dy*dy
    if a < 1e-12: return False
    b = 2*(dx*(p1[0]-c[0]) + dy*(p1[1]-c[1]))
    cc = (p1[0]-c[0])**2 + (p1[1]-c[1])**2 - R*R
    disc = b*b - 4*a*cc
    if disc < 0: return False
    t1 = (-b - sqrt(disc)) / (2*a)
    t2 = (-b + sqrt(disc)) / (2*a)
    t_enter, t_exit = min(t1,t2), max(t1,t2)
    z_enter = p1[2] + t_enter*dz
    z_exit = p1[2] + t_exit*dz
    if t_exit < 0 or t_enter > 1: return False
    t_enter = max(t_enter, 0.0)
    t_exit = min(t_exit, 1.0)
    z_enter = p1[2] + t_enter*dz
    z_exit = p1[2] + t_exit*dz
    if z_enter < 0 and z_exit < 0: return False
    if z_enter > H and z_exit > H: return False
    return True

def check_occlusion(smoke_center, missile_pos, R=7, H=10):
    c = (0.0, 200.0, 0.0)
    if line_cylinder_intersect(smoke_center, missile_pos, c, R, H):
        return True
    return False

def simulate(alpha, t1, fy0, v_fy, dt=0.05):
    v_m = 300.0
    dt_burst = 3.6
    T_smoke = 20.0
    v_sink = 3.0
    r_eff = 10.0
    g = 9.8
    
    t2 = t1 + dt_burst
    fy_dir = (-cos(alpha), -sin(alpha), 0.0)
    
    p_drop = (fy0[0] + v_fy*t1*fy_dir[0], fy0[1] + v_fy*t1*fy_dir[1], fy0[2])
    p_burst = (p_drop[0] + v_fy*dt_burst*fy_dir[0], 
               p_drop[1] + v_fy*dt_burst*fy_dir[1],
               p_drop[2] - 0.5*g*dt_burst**2)
    
    t_start = None
    t_end = None
    
    t = 0.0
    while t <= 80.0:
        pm = missile_pos(t, 0)
        
        if t2 <= t <= t2 + T_smoke:
            h_sink = v_sink * (t - t2)
            p_smoke = (p_burst[0], p_burst[1], p_burst[2] - h_sink)
            d_smoke = sqrt((pm[0]-p_smoke[0])**2 + (pm[1]-p_smoke[1])**2 + (pm[2]-p_smoke[2])**2)
            if d_smoke <= r_eff:
                occluded = check_occlusion(p_smoke, pm)
                if occluded:
                    if t_start is None:
                        t_start = t
                    t_end = t
        
        t += dt
    
    if t_start is None:
        return 0.0, p_drop, p_burst
    return t_end - t_start, p_drop, p_burst

def optimize_single(fy0, v_fy=120.0):
    best_te = 0.0
    best_a, best_t1 = 0.0, 0.0
    best_drop, best_burst = (0,0,0), (0,0,0)
    
    n_alpha = 20
    n_t1 = 10
    
    for i in range(n_alpha):
        alpha = 2*pi * i / n_alpha
        for j in range(n_t1):
            t1 = j * 2.0
            te, pd, pb = simulate(alpha, t1, fy0, v_fy)
            if te > best_te:
                best_te = te
                best_a = alpha
                best_t1 = t1
                best_drop, best_burst = pd, pb
    
    for _ in range(3):
        da = pi / n_alpha
        dt1 = 1.0
        improved = True
        while improved:
            improved = False
            for da_ in [-da, 0, da]:
                for dt1_ in [-dt1, 0, dt1]:
                    if da_ == 0 and dt1_ == 0: continue
                    a2 = best_a + da_
                    t12 = best_t1 + dt1_
                    if t12 < 0: continue
                    te, pd, pb = simulate(a2, t12, fy0, v_fy)
                    if te > best_te:
                        best_te = te
                        best_a, best_t1 = a2, t12
                        best_drop, best_burst = pd, pb
                        improved = True
    
    return best_te, best_a, best_t1, best_drop, best_burst

def solve_all():
    fys = [
        (17800.0, 0.0, 1800.0),
        (12000.0, 1400.0, 1400.0),
        (6000.0, -3000.0, 700.0),
        (11000.0, 2000.0, 1800.0),
        (13000.0, -2000.0, 1300.0)
    ]
    
    results = {}
    for i, fy in enumerate(fys, 1):
        te, a, t1, pd, pb = optimize_single(fy)
        results[f'FY{i}'] = {
            'effective_time': float(te),
            'alpha_deg': float(a * 180 / pi),
            't1': float(t1),
            'drop_point': [float(x) for x in pd],
            'burst_point': [float(x) for x in pb]
        }
    
    missiles = ['M1', 'M2', 'M3']
    for mi, mname in enumerate(missiles):
        best_te, best_fy = 0.0, ''
        for i, fy in enumerate(fys, 1):
            te, a, t1, pd, pb = optimize_single(fy)
            if te > best_te:
                best_te = te
                best_fy = f'FY{i}'
        results[f'best_for_{mname}'] = {
            'fy': best_fy,
            'effective_time': float(best_te)
        }
    
    return results

def main():
    for fname in ['result1.xlsx', 'result2.xlsx', 'result3.xlsx']:
        try:
            df = pd.read_excel(fname)
        except:
            pass
    
    results = solve_all()
    
    output_dir = os.environ.get('OUTPUT_DIR', '.')
    out_path = os.path.join(output_dir, 'execution', 'results.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)

if __name__ == '__main__':
    main()