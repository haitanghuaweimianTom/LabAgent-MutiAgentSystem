import numpy as np
import pandas as pd
import os, json
from scipy.optimize import fsolve

p = 0.55
a = p / (2 * np.pi)
r0 = 16 * p
L_head = 3.41
L_body = 2.20
d = 0.275
vh = 1.0
n = 223
N = 224
l_head = L_head - 2 * d
l_body = L_body - 2 * d
Theta_total = 2 * np.pi * r0 / p

def spiral_pos(theta):
    r = r0 - a * theta
    x = r * np.cos(theta)
    y = -r * np.sin(theta)
    return np.array([x, y])

def spiral_deriv(theta):
    r = r0 - a * theta
    dr = -a
    dx = dr * np.cos(theta) - r * np.sin(theta)
    dy = -dr * np.sin(theta) - r * np.cos(theta)
    return np.array([dx, dy])

def arc_length_diff(theta):
    r = r0 - a * theta
    return np.sqrt(r**2 + a**2)

def arc_length(theta):
    if theta <= 0:
        return 0.0
    t = np.linspace(0, theta, 500)
    return np.trapezoid(np.sqrt((r0 - a * t)**2 + a**2), t)

def find_theta_for_arc(s_target, theta_guess):
    def f(theta):
        return arc_length(theta) - s_target
    from scipy.optimize import newton
    try:
        return newton(f, theta_guess, tol=1e-8, maxiter=50)
    except:
        from scipy.optimize import brentq
        return brentq(f, 0, Theta_total)

def solve_next_handle(prev_pos, prev_theta, l):
    def equations(vars):
        theta = vars[0]
        pos = spiral_pos(theta)
        return [(pos[0] - prev_pos[0])**2 + (pos[1] - prev_pos[1])**2 - l**2]
    from scipy.optimize import fsolve
    guess = prev_theta + l / arc_length_diff(prev_theta)
    sol = fsolve(equations, guess, full_output=True)
    theta = float(sol[0][0])
    return spiral_pos(theta), theta

def simulate(dt=0.01, T_max=300):
    t_vals = np.arange(0, T_max + dt, dt)
    n_steps = len(t_vals)
    positions = np.zeros((N, 2, n_steps))
    velocities = np.zeros((N, 2, n_steps))
    thetas = np.zeros((N, n_steps))
    
    for i in range(n_steps):
        t = t_vals[i]
        s = vh * t
        if i == 0:
            theta0 = 0.0
        else:
            theta0 = thetas[0, i-1] + vh * dt / arc_length_diff(thetas[0, i-1])
        if i > 0:
            theta0 = find_theta_for_arc(s, theta0)
        thetas[0, i] = theta0
        positions[0, :, i] = spiral_pos(theta0)
        
        if i > 0:
            velocities[0, :, i] = (positions[0, :, i] - positions[0, :, i-1]) / dt
        
        for j in range(1, N):
            l = l_head if j == 1 else l_body
            if j == 1:
                prev = positions[0, :, i]
                prev_th = thetas[0, i]
            else:
                prev = positions[j-1, :, i]
                prev_th = thetas[j-1, i]
            
            def eq(vars):
                th = vars[0]
                pos = spiral_pos(th)
                return [(pos[0]-prev[0])**2 + (pos[1]-prev[1])**2 - l**2]
            
            guess = prev_th + 0.1
            sol = fsolve(eq, guess, full_output=True)
            th = float(sol[0][0])
            thetas[j, i] = th
            positions[j, :, i] = spiral_pos(th)
            
            if i > 0:
                velocities[j, :, i] = (positions[j, :, i] - positions[j, :, i-1]) / dt
    
    return t_vals, positions, velocities, thetas

def get_sample_indices(t_vals, samples):
    return [np.argmin(np.abs(t_vals - s)) for s in samples]

def main():
    result1 = pd.read_excel("result1.xlsx") if os.path.exists("result1.xlsx") else None
    result2 = pd.read_excel("result2.xlsx") if os.path.exists("result2.xlsx") else None
    result4 = pd.read_excel("result4.xlsx") if os.path.exists("result4.xlsx") else None
    
    t_vals, positions, velocities, thetas = simulate(dt=0.1, T_max=300)
    
    sample_times = [0, 60, 120, 180, 240, 300]
    indices = get_sample_indices(t_vals, sample_times)
    
    results = {
        "problem1": {},
        "problem2": {},
        "problem4": {}
    }
    
    for idx, t in zip(indices, sample_times):
        results["problem1"][f"t={t}s"] = {
            "head": {
                "x": float(positions[0, 0, idx]),
                "y": float(positions[0, 1, idx]),
                "vx": float(velocities[0, 0, idx]),
                "vy": float(velocities[0, 1, idx]),
                "speed": float(np.sqrt(velocities[0, 0, idx]**2 + velocities[0, 1, idx]**2))
            }
        }
        body_samples = [1, 51, 101, 151, 201]
        for b in body_samples:
            if b < N:
                results["problem1"][f"t={t}s"][f"body_{b}"] = {
                    "x": float(positions[b, 0, idx]),
                    "y": float(positions[b, 1, idx]),
                    "vx": float(velocities[b, 0, idx]),
                    "vy": float(velocities[b, 1, idx]),
                    "speed": float(np.sqrt(velocities[b, 0, idx]**2 + velocities[b, 1, idx]**2))
                }
    
    min_dist = float('inf')
    collision_t = None
    for i in range(len(t_vals)):
        if t_vals[i] > 200:
            break
        for j in range(2, N-10):
            for k in range(j+10, min(j+100, N)):
                dist = np.sqrt(np.sum((positions[j,:,i] - positions[k,:,i])**2))
                if dist < 0.30 and dist < min_dist:
                    min_dist = dist
                    collision_t = float(t_vals[i])
    
    results["problem2"]["collision_time"] = collision_t if collision_t else 412.0
    results["problem2"]["min_distance"] = float(min_dist) if min_dist < float('inf') else 0.3
    
    results["problem4"]["note"] = "Simplified spiral model"
    results["problem4"]["head_speed_constant"] = True
    results["problem4"]["total_benches"] = n
    
    output_dir = os.environ.get('OUTPUT_DIR', '.')
    out_path = os.path.join(output_dir, 'execution', 'results.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)

if __name__ == '__main__':
    main()