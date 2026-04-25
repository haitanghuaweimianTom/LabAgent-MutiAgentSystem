
## 求解代码


import numpy as np
from scipy.signal import savgol_filter, find_peaks
import pandas as pd

def load_spectrum(filepath):
    # 加载光谱数据
    df = pd.read_excel(filepath)
    return df

def analyze_thickness(wavenumber, reflectivity, refractive_index=2.65,
                      region_min=700, region_max=1000):
    # 分析外延层厚度
    # 区域提取
    mask = (wavenumber >= region_min) & (wavenumber <= region_max)
    wn = wavenumber[mask]
    refl = reflectivity[mask]

    # 平滑
    refl_smooth = savgol_filter(refl, window_length=31, polyorder=3)

    # 峰检测
    peaks, _ = find_peaks(refl_smooth, distance=30, prominence=2.0)

    if len(peaks) >= 2:
        # 条纹间距
        spacing = np.mean(np.diff(wn[peaks]))
        # 厚度
        thickness = 1e4 / (2 * refractive_index * spacing)
        # 对比度
        contrast = (refl_smooth.max() - refl_smooth.min()) / \
                   (refl_smooth.max() + refl_smooth.min())

        return {
            'thickness': thickness,
            'fringe_spacing': spacing,
            'contrast': contrast,
            'success': True
        }
    return {'success': False}

# 主程序
if __name__ == "__main__":
    # 分析SiC样品
    for i in range(1, 3):
        filepath = f"附件{i}.xlsx"
        df = load_spectrum(filepath)
        result = analyze_thickness(
            df['波数'].values,
            df['反射率'].values
        )
        print(f"附件{i}: d = {result.get('thickness', 0):.2f} um")

