import pandas as pd
import numpy as np
import os, json

def load_data(filepath):
    df = pd.read_excel(filepath)
    cols = df.columns.tolist()
    wave_col = [c for c in cols if '波' in str(c) or 'wave' in str(c).lower() or '波长' in str(c) or 'Wavelength' in str(c)][0]
    refl_col = [c for c in cols if '反射' in str(c) or 'reflect' in str(c).lower() or 'R' in str(c)][0]
    return df[wave_col].values.astype(float), df[refl_col].values.astype(float)

def sellmeier_sic(lam_um, nd=1e16):
    lam = lam_um
    n2 = 1 + 2.5534 * lam**2 / (lam**2 - 0.0363656) + 1.4105 * lam**2 / (lam**2 - 47.5149)
    n = np.sqrt(n2)
    return n

def two_beam_model(lam, d, n1, n2, theta0=0):
    k = 2 * np.pi / lam
    if theta0 == 0:
        cos1 = 1.0
        r01 = (1 - n1) / (1 + n1)
        r12 = (n1 - n2) / (n1 + n2)
    else:
        s0 = np.sin(theta0)
        c1 = np.sqrt(1 - (s0/n1)**2)
        cos1 = c1
        r01 = (np.cos(theta0) - n1*c1) / (np.cos(theta0) + n1*c1)
        r12 = (n1*c1 - n2*np.sqrt(1-(s0/n2)**2)) / (n1*c1 + n2*np.sqrt(1-(s0/n2)**2))
    beta = k * n1 * d * cos1
    r01r12 = r01 * r12
    R = (r01**2 + r12**2 + 2*r01r12*np.cos(2*beta)) / (1 + r01**2*r12**2 + 2*r01r12*np.cos(2*beta))
    return R

def extract_period(lam, R):
    idx = np.argsort(lam)
    lam, R = lam[idx], R[idx]
    R = (R - np.min(R)) / (np.max(R) - np.min(R) + 1e-10)
    peaks = []
    for i in range(1, len(R)-1):
        if R[i] > R[i-1] and R[i] > R[i+1] and R[i] > 0.3:
            peaks.append(i)
    if len(peaks) < 2:
        return None
    periods = []
    for i in range(1, len(peaks)):
        dl = lam[peaks[i]] - lam[peaks[i-1]]
        if dl > 0:
            periods.append(dl)
    if len(periods) == 0:
        return None
    return np.median(periods)

def thickness_from_period(period, n_avg, theta0=0):
    cos1 = 1.0 if theta0 == 0 else np.cos(np.arcsin(np.sin(theta0)/n_avg))
    return 1e4 / (2 * n_avg * cos1 * (1.0/period))

def refine_thickness(lam, R_meas, d0, n1_func, n2_func, theta0=0, n_grid=101):
    d_min, d_max = max(0.1, d0*0.7), d0*1.3
    ds = np.linspace(d_min, d_max, n_grid)
    best_d, best_err = d0, 1e10
    for d in ds:
        n1s = n1_func(lam)
        n2s = n2_func(lam)
        R_sim = two_beam_model(lam, d, n1s, n2s, theta0)
        err = np.mean((R_sim - R_meas)**2)
        if err < best_err:
            best_err = err
            best_d = d
    return float(best_d), float(best_err)

def n_substrate(lam):
    return sellmeier_sic(lam, nd=1e18)

def process_file(filepath, theta0=0):
    lam, R = load_data(filepath)
    lam = np.array(lam)
    R = np.array(R)
    R = (R - np.min(R)) / (np.max(R) - np.min(R) + 1e-10)
    period = extract_period(lam, R)
    n_avg = np.mean(sellmeier_sic(lam))
    if period is not None:
        d0 = thickness_from_period(period, n_avg, theta0)
    else:
        d0 = 10.0
    d, err = refine_thickness(lam, R, d0, sellmeier_sic, n_substrate, theta0)
    return d, err, lam.tolist(), R.tolist()

def main():
    files = {
        '附件1': '附件1.xlsx',
        '附件2': '附件2.xlsx',
        '附件3': '附件3.xlsx',
        '附件4': '附件4.xlsx'
    }
    results = {}
    for name, fpath in files.items():
        if os.path.exists(fpath):
            d, err, lam_list, r_list = process_file(fpath)
            results[name] = {
                'thickness_um': d,
                'fitting_error': err,
                'wavelength_range': [min(lam_list), max(lam_list)],
                'num_points': len(lam_list)
            }
        else:
            results[name] = {'error': 'file not found'}
    output_dir = os.environ.get('OUTPUT_DIR', '.')
    out_path = os.path.join(output_dir, 'execution', 'results.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)

if __name__ == '__main__':
    main()