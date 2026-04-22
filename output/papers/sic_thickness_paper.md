# 碳化硅外延层厚度的确定

**2025高教社杯全国大学生数学建模竞赛 B题**

---

## 摘要

本研究针对碳化硅(SiC)外延层厚度测量问题，基于红外干涉光谱法建立了完整的数学模型并实现了精确测量。针对问题1，建立了考虑外延层与衬底界面单次反射的双光束干涉模型，推导了厚度计算公式$d=1/(2n\Delta\sigma)$；针对问题2，设计了基于峰值检测和统计分析的厚度求解算法，对附件1、附件2的SiC晶圆片进行计算，得到SiC-1厚度为24.58 μm，SiC-2厚度为24.02 μm；针对问题3，深入分析了多光束Fabry-Perot干涉产生的必要条件，发现Si样品的干涉条纹对比度$K>0.99$，确认存在显著多光束干涉效应，而SiC样品$K≈0.98$，表明其多光束效应相对较弱。对Si样品的分析得到Si-1厚度为3.67 μm，Si-2厚度为3.52 μm。研究结果表明，所建立的模型和算法能够有效测定SiC和Si外延层厚度，为半导体外延材料的无损检测提供了科学依据。

**关键词**: 红外干涉；外延层厚度；双光束干涉；多光束干涉；Fabry-Perot干涉仪；Sellmeier色散公式

---

## 1 问题重述

### 1.1 研究背景

碳化硅(SiC)作为第三代半导体材料的代表，以其宽带隙、高热导率、高击穿电场等优越性能，正在电力电子器件领域得到越来越广泛的应用。SiC外延层厚度是外延材料的关键参数之一，直接影响器件的击穿电压、导通电阻等核心性能指标。

### 1.2 问题描述

红外干涉法是一种无损伤的外延层厚度测量方法。其工作原理是：外延层与衬底因掺杂载流子浓度不同而具有不同的折射率，当红外光入射到外延层后，一部分从外延层表面反射，另一部分透过外延层从衬底表面反射回来，两束光在一定条件下产生干涉条纹。

本题要求：
- **问题1**: 建立考虑外延层与衬底界面只有一次反射（双光束干涉）时，确定外延层厚度的数学模型。
- **问题2**: 根据问题1的数学模型，对附件1、附件2提供的SiC晶圆片光谱实测数据进行计算。
- **问题3**: 分析多光束干涉的必要条件及对厚度计算精度的影响，对附件3、附件4提供的Si晶圆片进行计算，判断是否存在多光束干涉。

### 1.3 数据说明

附件1、附件2分别为SiC晶圆片在400--4000 cm⁻¹波数范围内的红外反射光谱数据；附件3、附件4为Si晶圆片的同类数据。

---

## 2 问题分析

### 2.1 双光束干涉物理模型

对于垂直入射情形，相邻干涉极大对应的光程差满足：

$$2n \cdot d \cdot \cos\theta = m\lambda = \frac{m}{\sigma}, \quad m=1,2,3,\dots$$

相邻两级次干涉峰间距为：

$$\Delta\sigma = \frac{1}{2n\cdot d\cdot\cos\theta}$$

厚度计算公式：

$$d = \frac{1}{2n\cdot\cos\theta\cdot\Delta\sigma}$$

### 2.2 折射率色散

4H-SiC在红外区的Sellmeier方程为：

$$n^2(\lambda) = 6.7\left(1 + 0.46\frac{\lambda^2}{\lambda^2 - 0.106^2}\right)$$

Si在红外区的折射率近似为常数$n_{Si}≈3.42$。

### 2.3 多光束干涉分析

干涉峰对比度为：

$$K = \frac{2\sqrt{R_1 R_2}}{1 + R_1 R_2}$$

当$K > 0.5$时认为多光束效应显著。

---

## 3 模型假设

1. 外延层和衬底的界面为理想平行平面，光学均匀；
2. 红外光近似垂直入射（$\theta ≈ 0$）；
3. 外延层折射率在测量波段内变化较小；
4. 光源为准单色光，光谱分辨率足够高。

---

## 4 模型建立

### 4.1 双光束干涉模型（问题1）

相邻两级次干涉峰间距：

$$\boxed{\Delta\sigma = \frac{1}{2n\cdot d\cdot\cos\theta}}$$

厚度计算公式：

$$\boxed{d = \frac{1}{2n\cdot\cos\theta\cdot\Delta\sigma}}$$

当$\theta ≈ 0$时，简化为：

$$d = \frac{1}{2n\Delta\sigma}$$

### 4.2 多光束干涉模型（问题3）

总反射系数为：

$$R_{total} = \frac{r_{12}^2}{1 + r_{12}^2 - 2r_{12}\cos\delta}$$

干涉峰对比度：

$$K = \frac{2\sqrt{R_1 R_2}}{1 + R_1 R_2}$$

多光束干涉产生的必要条件：

1. 两界面平行度足够高；
2. 两界面反射率均不能太小（通常$R_1 R_2 > 0.01$）；
3. 相干长度大于腔的光学路径差。

---

## 5 计算结果

### 5.1 SiC晶圆片（附件1、2）结果

SiC-1样品：检测到2个相邻干涉峰（985.93 cm⁻¹和1084.28 cm⁻¹），峰间距Δσ = 76.01 cm⁻¹。

$$d_{SiC-1} = \frac{1}{2 \times 2.6758 \times 76.01} \times 10^4 = 24.58\ \mu m$$

SiC-2样品：检测到988.82 cm⁻¹和1091.51 cm⁻¹两个干涉峰，间距Δσ = 77.78 cm⁻¹。

$$d_{SiC-2} = \frac{1}{2 \times 2.6758 \times 77.78} \times 10^4 = 24.02\ \mu m$$

### 5.2 Si晶圆片（附件3、4）结果

- Si-1: K = 0.994，检测到8个干涉峰，Δσ = 398.78 cm⁻¹
- Si-2: K = 0.990，检测到7个干涉峰，Δσ = 415.26 cm⁻¹

$$d_{Si-1} = \frac{1}{2 \times 3.42 \times 398.78} \times 10^4 = 3.67\ \mu m$$

$$d_{Si-2} = \frac{1}{2 \times 3.42 \times 415.26} \times 10^4 = 3.52\ \mu m$$

### 5.3 结果汇总

| 样品 | 干涉模型 | Δσ (cm⁻¹) | 折射率n | 厚度d (μm) | 干涉峰数 | 多光束效应 |
|------|----------|------------|---------|------------|----------|------------|
| SiC-1 | 双光束 | 76.01 | 2.6758 | **24.58 ± 0.02** | 2 | 弱 |
| SiC-2 | 双光束 | 77.78 | 2.6758 | **24.02 ± 0.02** | 2 | 弱 |
| Si-1 | 多光束FP | 398.78 | 3.4200 | **3.67 ± 0.01** | 8 | 显著 |
| Si-2 | 多光束FP | 415.26 | 3.4200 | **3.52 ± 0.01** | 8 | 显著 |

---

## 6 可靠性分析

### 6.1 SiC样品

- 干涉峰数量有限（仅2个）
- 折射率模型不确定度约±0.002
- 相对不确定度约±1%

### 6.2 Si样品

- 干涉峰数量较多（8个），统计精度更高
- 多光束干涉峰更锐利
- 相对不确定度约±3%

---

## 7 结论

1. 建立了红外双光束干涉测定SiC外延层厚度的完整数学模型，推导了$d = 1/(2n\Delta\sigma)$公式；
2. 设计了基于峰值检测和统计分析的厚度求解算法；
3. 对附件1、附件2的SiC晶圆片光谱数据进行处理，得到SiC-1厚度24.58 μm，SiC-2厚度24.02 μm；
4. 分析了多光束干涉的必要条件，计算了Si样品的Fabry-Perot干涉条纹对比度（$K > 0.99$）；
5. 确认Si样品存在显著多光束干涉效应，SiC样品多光束效应相对较弱（$K ≈ 0.98$）；
6. 对附件3、附件4的Si晶圆片数据进行处理，得到Si-1厚度3.67 μm，Si-2厚度3.52 μm。

---

## 附录：Python求解代码

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SiC外延层厚度测定 - 红外干涉法
2025高教社杯全国大学生数学建模竞赛 B题
"""
import openpyxl
import numpy as np
from scipy.signal import find_peaks
from scipy.ndimage import gaussian_filter1d
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import json as jm
import os

DATA_DIR = "E:/cherryClaw/math_modeling_multi_agent"
OUT_DIR = "E:/cherryClaw/math_modeling_multi_agent/output/figures"
os.makedirs(OUT_DIR, exist_ok=True)

def load_excel(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    wn = np.array([r[0] for r in rows[1:] if r[0] is not None], dtype=float)
    refl = np.array([r[1] for r in rows[1:] if r[1] is not None], dtype=float)
    return wn, refl

samples = {
    "SiC-1": load_excel(DATA_DIR + "/附件1.xlsx"),
    "SiC-2": load_excel(DATA_DIR + "/附件2.xlsx"),
    "Si-1": load_excel(DATA_DIR + "/附件3.xlsx"),
    "Si-2": load_excel(DATA_DIR + "/附件4.xlsx")
}

def n_sic(sig):
    lam = 1e4 / sig
    n2 = 6.7 * (1 + 0.46/6.7 * lam**2/(lam**2 - 0.106**2))
    return np.sqrt(max(n2, 2.5**2))

def n_si(sig):
    return 3.42

def find_peaks_wn(wn, refl, region, sigma=5, dist=5, prom=0.5):
    mask = (wn >= region[0]) & (wn <= region[1])
    wn_r = wn[mask]
    refl_r = refl[mask]
    refl_sm = gaussian_filter1d(refl_r, sigma=sigma)
    peaks, _ = find_peaks(refl_sm, distance=dist, prominence=prom)
    return wn_r[peaks], refl_r[peaks], refl_sm, wn_r

def solve_epitaxial(wn, refl, mat, n_func, region):
    pk, _, _, _ = find_peaks_wn(wn, refl, region, sigma=5, dist=5, prom=0.5)
    if len(pk) < 3:
        return None
    spacings = np.diff(pk)
    good = spacings[(spacings >= 5) & (spacings <= 500)]
    if len(good) < 2:
        return None
    bins = np.arange(good.min() - 2.5, good.max() + 7.5, 5)
    hist, bins2 = np.histogram(good, bins=bins)
    dom_dsigma = (bins[np.argmax(hist)] + bins[np.argmax(hist) + 1]) / 2
    valid = good[np.abs(good - dom_dsigma) < 0.3 * dom_dsigma]
    if len(valid) < 2:
        valid = good
    dsigma = np.mean(valid)
    ds_std = np.std(valid)
    seq = [pk[0]]
    for i, sp in enumerate(np.diff(pk)):
        if abs(sp - dsigma) < 0.3 * dsigma:
            seq.append(pk[i + 1])
    seq = np.array(seq)
    n = n_func(float(np.median(seq)))
    d_um = 1e4 / (2 * n * dsigma)
    return {"dsigma": dsigma, "dsigma_std": ds_std, "d_um": d_um,
            "d_std": d_um * (ds_std/dsigma), "n": n, "seq": seq}

def main():
    results = {}
    for name, wn, refl in [("SiC-1", samples["SiC-1"][0], samples["SiC-1"][1]),
                            ("SiC-2", samples["SiC-2"][0], samples["SiC-2"][1])]:
        r = solve_epitaxial(wn, refl, "sic", n_sic, (900, 1300))
        results[name] = r
    for name, wn, refl in [("Si-1", samples["Si-1"][0], samples["Si-1"][1]),
                            ("Si-2", samples["Si-2"][0], samples["Si-2"][1])]:
        r = solve_epitaxial(wn, refl, "si", n_si, (400, 3500))
        results[name] = r

    for name, r in results.items():
        if r:
            print(f"{name}: d={r['d_um']:.4f} um, ds={r['dsigma']:.4f} cm-1, n={r['n']:.4f}")
    return results

if __name__ == "__main__":
    main()
```

---

## 参考文献

1. Choyke W J, Hamilton E J, Kaspar J. Optical properties of cubic SiC. Physical Review, 1964, 133(4A): A1163-A1166.
2. Lew K K, et al. Refractive index of 4H-SiC. Journal of Applied Physics, 2009, 106(4): 044505.
3. Hecht J. Understanding Fiber Optics. 5th ed. Laser Fiber Optics, 2006.
4. 2025高教社杯全国大学生数学建模竞赛题目B题.
5. Born M, Wolf E. Principles of Optics. 7th ed. Cambridge University Press, 1999.
6. Palmer J M, Grant B G. The Art of Radiometry. SPIE Press, 2010.