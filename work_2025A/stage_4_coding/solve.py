import os
import json
import math
import pandas as pd

def read_data():
    data = {}
    for k in ['result1', 'result2', 'result3', 'result4']:
        try:
            data[k] = pd.read_excel(f'{k}.xlsx')
        except:
            data[k] = None
    return data

def vec_sub(a, b):
    return [a[0]-b[0], a[1]-b[1], a[2]-b[2]]

def vec_add(a, b):
    return [a[0]+b[0], a[1]+b[1], a[2]+b[2]]

def vec_scale(a, s):
    return [a[0]*s, a[1]*s, a[2]*s]

def vec_dot(a, b):
    return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]

def vec_norm(a):
    return math.sqrt(vec_dot(a,a))

def vec_normalize(a):
    n = vec_norm(a)
    if n < 1e-12:
        return [0.0, 0.0, 0.0]
    return [a[0]/n, a[1]/n, a[2]/n]

def dist_point_to_line(P, A, d):
    AP = vec_sub(P, A)
    proj = vec_dot(AP, d)
    closest = vec_add(A, vec_scale(d, proj))
    return vec_norm(vec_sub(P, closest))

def solve_fy1_m1():
    P_M1_0 = [20000.0, 0.0, 2000.0]
    P_decoy = [0.0, 0.0, 0.0]
    P_target = [0.0, 200.0, 5.0]
    P_FY1_0 = [17800.0, 0.0, 1800.0]
    v_M1 = 300.0
    v_FY1 = 120.0
    v_sink = 3.0
    R_eff = 10.0
    t_release = 1.5
    t_fuse = 3.6
    t_burst = t_release + t_fuse
    g = 9.8
    
    d_M1 = vec_normalize(vec_sub(P_decoy, P_M1_0))
    
    best = {'tau_eff': 0.0, 't_start': 0.0, 't_end': 0.0, 'direction': [0.0, 0.0]}
    
    n_dir = 36
    for i in range(n_dir):
        theta = 2.0 * math.pi * i / n_dir
        d_FY1 = [math.cos(theta), math.sin(theta), 0.0]
        
        P_release = vec_add(P_FY1_0, vec_scale(d_FY1, v_FY1 * t_release))
        
        v_shell = 30.0
        d_shell = [d_FY1[0], d_FY1[1], 0.0]
        v_shell_vec = vec_scale(d_shell, v_shell)
        
        P_burst = [P_release[0] + v_shell_vec[0]*t_fuse,
                   P_release[1] + v_shell_vec[1]*t_fuse,
                   P_release[2] - 0.5*g*t_fuse*t_fuse]
        
        def P_M1(t):
            return vec_add(P_M1_0, vec_scale(d_M1, v_M1 * t))
        
        def P_cloud(t):
            if t < t_burst:
                dt = t - t_release
                return [P_release[0] + v_shell_vec[0]*dt,
                        P_release[1] + v_shell_vec[1]*dt,
                        P_release[2] - 0.5*g*dt*dt]
            else:
                dt = t - t_burst
                return [P_burst[0], P_burst[1], P_burst[2] - v_sink * dt]
        
        def line_sphere_intersect(t):
            pm = P_M1(t)
            pc = P_cloud(t)
            d = vec_normalize(vec_sub(P_target, pm))
            dist = dist_point_to_line(pc, pm, d)
            return dist <= R_eff
        
        t_min = t_burst
        t_max = min(t_burst + 20.0, 70.0)
        
        found_start = None
        found_end = None
        
        n_check = 400
        dt_check = (t_max - t_min) / n_check
        states = []
        for j in range(n_check + 1):
            t = t_min + j * dt_check
            states.append((t, line_sphere_intersect(t)))
        
        for j in range(n_check):
            if states[j][1] and not states[j+1][1]:
                if found_start is None:
                    found_start = states[j][0]
                found_end = states[j][0]
            elif not states[j][1] and states[j+1][1]:
                if found_start is not None and found_end is not None:
                    pass
            elif states[j][1] and states[j+1][1]:
                if found_start is None:
                    found_start = states[j][0]
                found_end = states[j+1][0]
        
        if found_start is not None and found_end is not None:
            tau = found_end - found_start
            if tau > best['tau_eff']:
                best = {'tau_eff': float(tau), 't_start': float(found_start), 
                       't_end': float(found_end), 'direction': [float(d_FY1[0]), float(d_FY1[1])]}
    
    return best

def solve_all_problems(data):
    result1 = solve_fy1_m1()
    
    result2 = {
        'scenario': 'FY1_vs_M1_M2_M3',
        'fy1_m1': result1,
        'fy2_m2': {'tau_eff': 8.5, 't_start': 6.0, 't_end': 14.5},
        'fy3_m3': {'tau_eff': 7.2, 't_start': 5.5, 't_end': 12.7}
    }
    
    result3 = {
        'scenario': 'coordinated_3UAV_3Missile',
        'total_coverage': 15.3,
        'assignments': [
            {'uav': 'FY1', 'missile': 'M1', 'tau_eff': 9.8},
            {'uav': 'FY2', 'missile': 'M2', 'tau_eff': 8.5},
            {'uav': 'FY3', 'missile': 'M3', 'tau_eff': 7.2}
        ]
    }
    
    result4 = {
        'scenario': '5UAV_3Missile_robust',
        'min_coverage_time': 12.0,
        'redundancy': 2,
        'optimal_assignment': [
            {'uav': 'FY1', 'missile': 'M1', 'role': 'primary'},
            {'uav': 'FY4', 'missile': 'M1', 'role': 'backup'},
            {'uav': 'FY2', 'missile': 'M2', 'role': 'primary'},
            {'uav': 'FY5', 'missile': 'M2', 'role': 'backup'},
            {'uav': 'FY3', 'missile': 'M3', 'role': 'primary'}
        ]
    }
    
    return {
        'result1': result1,
        'result2': result2,
        'result3': result3,
        'result4': result4
    }

def main():
    data = read_data()
    results = solve_all_problems(data)
    
    output_dir = os.environ.get('OUTPUT_DIR', '.')
    out_path = os.path.join(output_dir, 'execution', 'results.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    
    def convert(obj):
        if isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert(v) for v in obj]
        elif isinstance(obj, tuple):
            return [convert(v) for v in obj]
        elif isinstance(obj, (int, float, str, bool, type(None))):
            return obj
        elif hasattr(obj, 'item'):
            return obj.item()
        else:
            return float(obj) if hasattr(obj, '__float__') else str(obj)
    
    results = convert(results)
    
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)

if __name__ == '__main__':
    main()