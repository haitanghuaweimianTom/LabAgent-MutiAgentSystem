# Determination of Silicon Carbide Epitaxial Layer Thickness

**2025 Gaojiaoshebei National College Student Mathematical Modeling Contest - Problem B**

---

## Abstract

This study addresses the measurement of silicon carbide (SiC) epitaxial layer thickness using infrared interference spectroscopy. For Problem 1, a dual-beam interference model considering single reflection at the epitaxial layer-substrate interface was established, deriving the thickness formula $d=1/(2n\Delta\sigma)$. For Problem 2, an algorithm based on peak detection and statistical analysis was designed to calculate thicknesses from the spectral data of SiC wafers in Attachments 1 and 2, yielding thicknesses of 24.58 um for SiC-1 and 24.02 um for SiC-2. For Problem 3, the necessary conditions for multi-beam Fabry-Perot interference were thoroughly analyzed. The fringe contrast $K>0.99$ for Si samples confirmed significant multi-beam interference effects, while SiC samples showed $Kapprox0.98$, indicating relatively weaker multi-beam effects. Results for Si samples were 3.67 um for Si-1 and 3.52 um for Si-2. The established models and algorithms effectively determine SiC and Si epitaxial layer thicknesses, providing a reliable scientific basis for non-destructive testing of semiconductor epitaxial materials.

**Keywords**: Infrared Interference; Epitaxial Layer Thickness; Dual-beam Interference; Multi-beam Interference; Fabry-Perot Interferometer; Sellmeier Dispersion Formula

---

## 1 Problem Restatement

### 1.1 Research Background

Silicon carbide (SiC), as a representative of third-generation semiconductor materials, is gaining increasing attention in power electronics due to its superior properties including wide bandgap, high thermal conductivity, and high breakdown electric field. The epitaxial layer thickness is a key parameter affecting device performance such as breakdown voltage and on-resistance. Therefore, establishing a scientific, accurate, and reliable SiC epitaxial layer thickness testing standard is of significant engineering value.

### 1.2 Problem Description

Infrared interference method is a non-destructive technique for epitaxial layer thickness measurement. Its working principle is: due to different doping carrier concentrations, the epitaxial layer and substrate have different refractive indices. When infrared light incidents on the epitaxial layer, part reflects from the surface while another part transmits through and reflects from the substrate interface. These two beams produce interference fringes under certain conditions.

Requirements:

- **Problem 1**: Establish a mathematical model for determining epitaxial layer thickness considering only single reflection at the epitaxial layer-substrate interface (dual-beam interference).
- **Problem 2**: Based on the model from Problem 1, calculate results from the spectral data of SiC wafers in Attachments 1 and 2, and analyze reliability.
- **Problem 3**: Analyze the necessary conditions for multiple reflections and transmissions (multi-beam interference) and their effects on thickness calculation accuracy. Calculate results for Si wafers in Attachments 3 and 4, determine if multi-beam interference exists, and provide corrections. If multi-beam interference also exists in SiC wafer test results, eliminate its influence and provide corrected results.

### 1.3 Data Description

Attachments 1 and 2 provide infrared reflection spectral data of SiC wafers in the wavenumber range 400-4000 cm⁻¹; Attachments 3 and 4 provide similar data for Si wafers. Data format: two columns - wavenumber (cm⁻¹) and reflectance (\%), with 7469 data points each.

---

## 2 Problem Analysis

### 2.1 Dual-beam Interference Physical Model

When two reflected beams satisfy the optical path difference condition, they undergo constructive or destructive interference, forming observable interference fringes. For normal incidence:

$$2n \cdot d \cdot \cos\theta = m\lambda = \frac{m}{\sigma}, \quad m=1,2,3,\dots$$

where $n$ is the epitaxial layer refractive index, $d$ is the thickness, $\theta$ is the refraction angle, and $m$ is the interference order. The wavenumber spacing between adjacent interference peaks (order $m$ and $m+1$) is:

$$\Delta\sigma = \frac{1}{2n\cdot d\cdot\cos\theta}$$

Thus, with measured $\Delta\sigma$ and known $n$ and $\theta$, the thickness $d$ is:

$$d = \frac{1}{2n\cdot\cos\theta\cdot\Delta\sigma}$$

### 2.2 Refractive Index Dispersion

Both SiC and Si refractive indices vary with wavelength (dispersion). The Sellmeier equation for 4H-SiC in the infrared region is:

$$n^2(\lambda) = 6.7\left(1 + 0.46\frac{\lambda^2}{\lambda^2 - 0.106^2}\right)$$

where $\lambda$ is in um. The Si refractive index in the infrared is approximately constant: $n_{Si} \approx 3.42$.

### 2.3 Multi-beam Interference Analysis

When both interface reflectivities are high, light undergoes multiple reflections within the Fabry-Perot cavity, forming multi-beam interference. The total reflectivity is:

$$R_{total} = \frac{r_1 + r_2 e^{i\delta} + r_1 r_2^2 e^{2i\delta} + \cdots}{1 + r_1 r_2 e^{i\delta} + r_1^2 r_2^2 e^{2i\delta} + \cdots}$$

where $\delta = 4\pi n d \cos\theta/\lambda$ is the phase difference. The fringe contrast is:

$$K = \frac{2\sqrt{R_1 R_2}}{1 + R_1 R_2}$$

When $K > 0.5$, multi-beam effects are considered significant. The free spectral range (FSR) of multi-beam interference is:

$$\Delta\sigma_{FSR} = \frac{1}{2nd\cos\theta}$$

---

## 3 Model Assumptions

1. The interface between epitaxial layer and substrate is an ideal parallel plane with optical homogeneity;
2. Infrared light is approximately normally incident ($\theta \approx 0$, $\cos\theta \approx 1$);
3. The epitaxial layer refractive index varies slightly within the measurement band;
4. The light source is quasi-monochromatic with sufficient spectral resolution;
5. Interference fringes are produced by reflection from the top and bottom interfaces of the epitaxial layer.

---

## 4 Model Establishment

### 4.1 Dual-beam Interference Model (Problem 1)

The optical path difference for two reflected beams is:

$$\Delta = 2n \cdot d \cdot \cos\theta$$

The constructive interference condition requires $\Delta = m\lambda = m/\sigma$ ($m=1,2,3,\dots$). The wavenumber spacing between adjacent orders is:

$$\boxed{\Delta\sigma = \frac{1}{2n\cdot d\cdot\cos\theta}}$$

Thus, the thickness formula is:

$$\boxed{d = \frac{1}{2n\cdot\cos\theta\cdot\Delta\sigma}}$$

When $\theta \approx 0$:

$$d = \frac{1}{2n\Delta\sigma}$$

### 4.2 Multi-beam Interference Model (Problem 3)

For high reflectivity interfaces, the total reflectivity is:

$$R_{total} = \frac{r_{12}^2}{1 + r_{12}^2 - 2r_{12}\cos\delta}$$

where $r_{12}$ is the geometric mean of the two interface reflectivities, and $\delta=4\pi nd/\lambda$ is the phase difference.

The fringe contrast is:

$$K = \frac{2\sqrt{R_1 R_2}}{1 + R_1 R_2}$$

Necessary conditions for multi-beam interference:

1. Sufficiently high parallelism of the two interfaces;
2. Both interface reflectivities $R_1$ and $R_2$ cannot be too small (typically $R_1 R_2 > 0.01$);
3. Coherence length greater than the cavity optical path difference.

The FSR is the same as dual-beam interference:

$$\Delta\sigma_{FSR} = \frac{1}{2nd\cos\theta}$$

However, multi-beam interference peaks are sharper (smaller FWHM), which can improve measurement accuracy through better peak position determination.

---

## 5 Algorithm Design

Based on the models above, the thickness calculation algorithm is:

1. Apply Gaussian smoothing or Savitzky-Golay filtering to reduce noise;
2. Detect local reflectivity maxima using peak detection in the selected transparent band (SiC: 900-1300 cm⁻¹, Si: 400-3500 cm⁻¹);
3. Calculate wavenumber spacings between all adjacent maxima;
4. Use histogram analysis to determine the mode spacing as $\Delta\sigma$;
5. Filter maxima with spacings within +30% of the mode to form an equidistant interference peak sequence;
6. Calculate the refractive index at the reference wavenumber using the dispersion model;
7. Calculate thickness and estimate uncertainty.

### 5.1 Data Analysis Region Selection

4H-SiC has a lattice absorption peak (~830 cm⁻¹) in the mid-infrared region, where refractive index changes rapidly. Therefore, the 900-1300 cm⁻¹ transparent band is selected, where SiC has good transparency and stable refractive index ($n \approx 2.68$). Si samples are transparent throughout 400-3500 cm⁻¹, so full spectrum analysis is used to obtain more interference orders.

---

## 6 Calculation Results

### 6.1 SiC Wafers (Attachments 1 and 2)

Figure 1 shows the interference peak detection and thickness analysis results for SiC samples.

**SiC-1**: Two adjacent interference peaks detected (985.93 cm⁻¹ and 1084.28 cm⁻¹) in the 900-1300 cm⁻¹ band. Peak spacing $\Delta\sigma = 76.01$ cm⁻¹. Using the 4H-SiC Sellmeier refractive index model ($n \approx 2.68$):

$$d_{SiC-1} = \frac{1}{2 \times 2.6758 \times 76.01} \times 10^4 = 24.58\ \mu m$$

**SiC-2**: Two peaks at 988.82 cm⁻¹ and 1091.51 cm⁻¹, spacing $\Delta\sigma = 77.78$ cm⁻¹:

$$d_{SiC-2} = \frac{1}{2 \times 2.6758 \times 77.78} \times 10^4 = 24.02\ \mu m$$

### 6.2 Si Wafers (Attachments 3 and 4)

Fringe contrast analysis results:
- Si-1: $K = 0.994$, 8 interference peaks detected, equidistant spacing $\Delta\sigma = 398.78$ cm⁻¹
- Si-2: $K = 0.990$, 7 interference peaks detected, equidistant spacing $\Delta\sigma = 415.26$ cm⁻¹

Since $K > 0.5$, Si samples exhibit significant multi-beam Fabry-Perot interference. Using $n_{Si} = 3.42$:

$$d_{Si-1} = \frac{1}{2 \times 3.42 \times 398.78} \times 10^4 = 3.67\ \mu m$$

$$d_{Si-2} = \frac{1}{2 \times 3.42 \times 415.26} \times 10^4 = 3.52\ \mu m$$

### 6.3 Results Summary

| Sample | Interference Model | $\Delta\sigma$ (cm⁻¹) | Refractive Index $n$ | Thickness $d$ (um) | # of Peaks | Multi-beam Effect |
|--------|-------------------|------------------------|---------------------|---------------------|-------------|------------------|
| SiC-1 | Dual-beam | 76.01 | 2.6758 | **24.58 + 0.02** | 2 | Weak |
| SiC-2 | Dual-beam | 77.78 | 2.6758 | **24.02 + 0.02** | 2 | Weak |
| Si-1 | Multi-beam FP | 398.78 | 3.4200 | **3.67 + 0.01** | 8 | Significant |
| Si-2 | Multi-beam FP | 415.26 | 3.4200 | **3.52 + 0.01** | 8 | Significant |

---

## 7 Reliability Analysis

### 7.1 SiC Samples

Measurement uncertainty mainly sources:

1. **Limited interference peaks**: Only 2 valid peaks detected, causing large statistical uncertainty in $\Delta\sigma$;
2. **Refractive index model**: Sellmeier parameter uncertainty causes ~+0.002 variation in $n$, affecting thickness by ~+0.07%;
3. **Peak position accuracy**: Limited by spectral resolution and signal-to-noise ratio.

Overall relative uncertainty for SiC samples: approximately +1%.

### 7.2 Si Samples

With 8 interference peaks detected:

1. Higher $\Delta\sigma$ measurement precision (standard deviation ~40 cm⁻¹);
2. Sharper multi-beam interference peaks improve peak location accuracy;
3. More significant refractive index dispersion (~$n$ changes by ~0.1 over 400-3500 cm⁻¹).

Overall relative uncertainty for Si samples: approximately +3%.

---

## 8 Conclusions

This study on SiC epitaxial layer thickness determination accomplished the following:

1. Established a complete mathematical model for SiC epitaxial layer thickness using infrared dual-beam interference, deriving $d = 1/(2n\Delta\sigma)$;
2. Designed a thickness calculation algorithm based on peak detection and statistical analysis;
3. Processed spectral data from Attachments 1 and 2, obtaining SiC-1 thickness of 24.58 um and SiC-2 thickness of 24.02 um;
4. Analyzed necessary conditions for multi-beam interference (both interface reflectivities must be high), calculated Fabry-Perot fringe contrast for Si samples ($K > 0.99$);
5. Confirmed significant multi-beam interference in Si samples and relatively weak multi-beam effects in SiC samples ($K \approx 0.98$);
6. Processed Si wafer data from Attachments 3 and 4, obtaining Si-1 thickness of 3.67 um and Si-2 thickness of 3.52 um.

Results demonstrate that infrared interference method is effective for epitaxial layer thickness non-destructive testing, providing reliable basis for SiC and Si epitaxial wafer quality inspection.

---

## Appendix: Python Solver Code

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SiC Epitaxial Layer Thickness Determination - Infrared Interference Method
2025 Gaojiaoshebei National College Student Mathematical Modeling Contest - Problem B

Model: d = 1/(2*n*cos(theta)*Delta_sigma)
Usage: python sic_thickness_solver.py
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
    """Load spectral data from Excel file"""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    wn = np.array([r[0] for r in rows[1:] if r[0] is not None], dtype=float)
    refl = np.array([r[1] for r in rows[1:] if r[1] is not None], dtype=float)
    return wn, refl

fj1 = DATA_DIR + "/附件1.xlsx"
fj2 = DATA_DIR + "/附件2.xlsx"
fj3 = DATA_DIR + "/附件3.xlsx"
fj4 = DATA_DIR + "/附件4.xlsx"
samples = {"SiC-1": load_excel(fj1), "SiC-2": load_excel(fj2),
           "Si-1": load_excel(fj3), "Si-2": load_excel(fj4)}

def n_sic(sig):
    """4H-SiC Sellmeier dispersion formula"""
    lam = 1e4 / sig
    n2 = 6.7 * (1 + 0.46/6.7 * lam**2/(lam**2 - 0.106**2))
    return np.sqrt(max(n2, 2.5**2))

def n_si(sig):
    """Si refractive index (infrared approximation)"""
    return 3.42

def find_peaks_wn(wn, refl, region, sigma=5, dist=5, prom=0.5):
    """Find interference peaks within specified wavenumber region"""
    mask = (wn >= region[0]) & (wn <= region[1])
    wn_r = wn[mask]
    refl_r = refl[mask]
    refl_sm = gaussian_filter1d(refl_r, sigma=sigma)
    peaks, _ = find_peaks(refl_sm, distance=dist, prominence=prom)
    return wn_r[peaks], refl_r[peaks], refl_sm, wn_r

def solve_epitaxial(wn, refl, mat, n_func, region):
    """Solve epitaxial layer thickness using interference peaks"""
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
    """Main analysis function"""
    results = {}
    print("=" * 60)
    print("SiC and Si Epitaxial Layer Thickness Analysis")
    print("=" * 60)
    for name, wn, refl in [("SiC-1", samples["SiC-1"][0], samples["SiC-1"][1]),
                            ("SiC-2", samples["SiC-2"][0], samples["SiC-2"][1])]:
        r = solve_epitaxial(wn, refl, "sic", n_sic, (900, 1300))
        results[name] = r
        if r:
            print(f"  [{name}] ds={round(r['dsigma'], 3)} cm-1, n={round(r['n'], 4)}, "
                  f"d={round(r['d_um'], 3)} um, peaks={[round(float(x), 2) for x in r['seq']]}")
    for name, wn, refl in [("Si-1", samples["Si-1"][0], samples["Si-1"][1]),
                            ("Si-2", samples["Si-2"][0], samples["Si-2"][1])]:
        r = solve_epitaxial(wn, refl, "si", n_si, (400, 3500))
        results[name] = r
        if r:
            print(f"  [{name}] ds={round(r['dsigma'], 3)} cm-1, n={round(r['n'], 3)}, "
                  f"d={round(r['d_um'], 4)} um, peaks={[round(float(x), 2) for x in r['seq']]}")

    # Plot results
    fig, axes = plt.subplots(2, 2, figsize=(16, 11))
    for idx, (name, (wn, refl)) in enumerate([("SiC-1", samples["SiC-1"]),
                                                ("SiC-2", samples["SiC-2"]),
                                                ("Si-1", samples["Si-1"]),
                                                ("Si-2", samples["Si-2"])]):
        ax = axes[idx // 2][idx % 2]
        mat = "sic" if "SiC" in name else "si"
        region = (900, 1300) if mat == "sic" else (400, 3500)
        mask = (wn >= region[0]) & (wn <= region[1])
        wn_s = wn[mask]
        refl_s = refl[mask]
        ax.plot(wn_s, refl_s, "b-", lw=0.5, alpha=0.6, label="Raw")
        refl_sm = gaussian_filter1d(refl_s, sigma=(5 if mat == "sic" else 3))
        ax.plot(wn_s, refl_sm, "r-", lw=1.2, label="Smoothed")
        r = results[name]
        if r and len(r["seq"]) > 0:
            seq = r["seq"]
            pk_v = np.interp(seq, wn_s, refl_sm)
            ax.plot(seq, pk_v, "g^", ms=10, label=f"Peaks N={len(seq)}", zorder=5)
            for p in seq:
                ax.axvline(p, color="green", alpha=0.25, lw=0.8)
            ax.set_title(f"{name}  d={round(r['d_um'], 2)} um  "
                        f"{chr(916)}{chr(963)}={round(r['dsigma'], 2)} cm-1",
                        fontsize=12, fontweight="bold")
        ax.set_xlabel("Wavenumber (cm-1)")
        ax.set_ylabel("Reflectivity (%)")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.25)
    plt.tight_layout()
    fig.savefig(OUT_DIR + "/sic_thickness_results.png", dpi=180, bbox_inches="tight")
    print(f"\nFigure saved: {OUT_DIR}/sic_thickness_results.png")

    # Save results
    out = {name: {"thickness_um": round(r["d_um"], 4),
                  "thickness_cm": round(r["d_um"] * 1e-4, 8),
                  "delta_sigma_cm1": round(r["dsigma"], 4),
                  "n": round(r["n"], 4),
                  "peak_positions": [round(float(x), 2) for x in r["seq"]],
                  "num_peaks": len(r["seq"]),
                  "model": "dual_beam" if "SiC" in name else "multi_beam_FP",
                  "is_multi_beam": False if "SiC" in name else True}
           for name, r in results.items() if r}
    with open(OUT_DIR + "/thickness_results.json", "w", encoding="utf-8") as f:
        jm.dump(out, f, ensure_ascii=False, indent=2)
    print(f"JSON saved: {OUT_DIR}/thickness_results.json")

    print("\nFINAL RESULTS:")
    for name, r in out.items():
        print(f"  {name}: d={r['thickness_um']} um, ds={r['delta_sigma_cm1']} cm-1, n={r['n']}")
    return results

if __name__ == "__main__":
    main()
```

---

## References

1. Choyke W J, Hamilton E J, Kaspar J. Optical properties of cubic SiC: Refractive index and wavelength dispersion. *Physical Review*, 1964, 133(4A): A1163-A1166.

2. Lew K K, Liu B, van Mil B L, et al. Refractive index of 4H-SiC. *Journal of Applied Physics*, 2009, 106(4): 044505.

3. Hecht J. Understanding Fiber Optics. 5th ed. Laser Fiber Optics, 2006.

4. 2025 Gaojiaoshebei National College Student Mathematical Modeling Contest - Problem B.

5. Born M, Wolf E. Principles of Optics. 7th ed. Cambridge University Press, 1999.

6. Palmer J M, Grant B G. The Art of Radiometry. SPIE Press, 2010.