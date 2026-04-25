"""
Computational Solving Module
===========================

Implements algorithms for spectrum analysis and thickness calculation.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from scipy.signal import find_peaks, savgol_filter
from scipy.optimize import curve_fit


@dataclass
class SolveResult:
    """Results from computational solving."""
    sample_name: str
    material: str
    fringe_spacing: float
    thickness: float
    thickness_uncertainty: float
    contrast: float
    multi_beam_corrected: float
    analysis_region: Tuple[float, float]
    peaks: np.ndarray
    valleys: np.ndarray


class SpectrumAnalyzer:
    """
    Analyzes spectral data to extract interference patterns.
    """

    def __init__(self, smoothing_window: int = 31, smoothing_order: int = 3):
        """
        Initialize analyzer.

        Args:
            smoothing_window: Savitzky-Golay window size (must be odd)
            smoothing_order: Polynomial order for smoothing
        """
        self.window = smoothing_window
        self.order = smoothing_order

    def smooth(self, data: np.ndarray) -> np.ndarray:
        """Apply Savitzky-Golay smoothing."""
        if len(data) < self.window:
            return data
        return savgol_filter(data, window_length=self.window, polyorder=self.order)

    def find_peaks(self, signal: np.ndarray,
                   distance: int = 30,
                   prominence: float = 3.0) -> Tuple[np.ndarray, Dict]:
        """
        Find peaks in signal.

        Returns:
            Tuple of (peak_indices, properties)
        """
        return find_peaks(signal, distance=distance, prominence=prominence)

    def find_valleys(self, signal: np.ndarray,
                     distance: int = 20,
                     prominence: float = 1.0) -> Tuple[np.ndarray, Dict]:
        """
        Find valleys (peaks in negative signal).

        Returns:
            Tuple of (valley_indices, properties)
        """
        return find_peaks(-signal, distance=distance, prominence=prominence)

    def compute_contrast(self, signal: np.ndarray) -> float:
        """Compute interference contrast."""
        r_max = np.max(signal)
        r_min = np.min(signal)
        if r_max + r_min == 0:
            return 0.0
        return (r_max - r_min) / (r_max + r_min)


class ThicknessCalculator:
    """
    Calculates epitaxial layer thickness from spectral data.
    """

    # Refractive indices for common materials
    REFRACTIVE_INDICES = {
        'SiC': 2.65,
        'Si': 3.45
    }

    def __init__(self, material: str = 'SiC', refractive_index: Optional[float] = None):
        """
        Initialize calculator.

        Args:
            material: Material type ('SiC' or 'Si')
            refractive_index: Override refractive index
        """
        self.material = material
        self.n = refractive_index or self.REFRACTIVE_INDICES.get(material, 2.65)

    def calculate(self, fringe_spacing: float) -> float:
        """
        Calculate thickness from fringe spacing.

        Args:
            fringe_spacing: Δσ (cm^-1)

        Returns:
            Thickness d (μm)
        """
        if fringe_spacing <= 0:
            raise ValueError("Fringe spacing must be positive")
        return 1e4 / (2 * self.n * fringe_spacing)

    def calculate_with_uncertainty(
        self,
        fringe_spacing: float,
        fringe_spacing_std: float,
        n_uncertainty: float = 0.05
    ) -> Tuple[float, float]:
        """
        Calculate thickness with uncertainty propagation.

        Args:
            fringe_spacing: Measured spacing
            fringe_spacing_std: Standard deviation of spacing
            n_uncertainty: Uncertainty in refractive index

        Returns:
            Tuple of (thickness, uncertainty)
        """
        d = self.calculate(fringe_spacing)

        # Relative uncertainties
        rel_spacing = fringe_spacing_std / fringe_spacing
        rel_n = n_uncertainty / self.n

        # Combined relative uncertainty (RSS)
        rel_total = np.sqrt(rel_spacing**2 + rel_n**2)

        return d, d * rel_total


class EpitaxialLayerSolver:
    """
    Main solver for epitaxial layer thickness measurement problem.
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize solver with configuration.

        Args:
            config: Configuration dictionary
        """
        self.config = config or {}

        # Algorithm parameters
        self.smoothing_window = self.config.get('smoothing_window', 31)
        self.smoothing_order = self.config.get('smoothing_order', 3)
        self.peak_distance = self.config.get('peak_distance', 30)
        self.peak_prominence = self.config.get('peak_prominence', 3.0)

        # Analysis regions
        self.regions = self.config.get('regions', {
            'SiC': (700, 1000),
            'Si_reststrahlen': (400, 700),
            'Si_transparent': (1100, 2000)
        })

        # Refractive indices
        self.refractive_indices = self.config.get('refractive_index', {
            'SiC': 2.65,
            'Si': 3.45
        })

        # Initialize components
        self.analyzer = SpectrumAnalyzer(
            smoothing_window=self.smoothing_window,
            smoothing_order=self.smoothing_order
        )

    def solve_sample(
        self,
        wavenumber: np.ndarray,
        reflectivity: np.ndarray,
        sample_name: str,
        material: str = 'SiC'
    ) -> SolveResult:
        """
        Solve for a single sample.

        Args:
            wavenumber: Wavenumber array (cm^-1)
            reflectivity: Reflectivity array (%)
            sample_name: Name of the sample
            material: Material type

        Returns:
            SolveResult object
        """
        # Determine analysis region
        if material == 'SiC':
            region = self.regions['SiC']
        else:
            region = self.regions['Si_reststrahlen']

        # Extract region
        mask = (wavenumber >= region[0]) & (wavenumber <= region[1])
        wn_region = wavenumber[mask]
        refl_region = reflectivity[mask]

        # Smooth data
        refl_smooth = self.analyzer.smooth(refl_region)

        # Find peaks and valleys
        peak_idx, _ = self.analyzer.find_peaks(
            refl_smooth,
            distance=self.peak_distance,
            prominence=self.peak_prominence
        )
        valley_idx, _ = self.analyzer.find_valleys(refl_smooth)

        # Get wavenumbers
        peaks = wn_region[peak_idx] if len(peak_idx) > 0 else np.array([])
        valleys = wn_region[valley_idx] if len(valley_idx) > 0 else np.array([])

        # Compute contrast
        contrast = self.analyzer.compute_contrast(refl_smooth)

        # Compute fringe spacing
        fringe_spacing = self._compute_fringe_spacing(peaks, valleys)

        # Calculate thickness
        n = self.refractive_indices.get(material, 2.65)
        calculator = ThicknessCalculator(material=material, refractive_index=n)

        if fringe_spacing is not None:
            thickness = calculator.calculate(fringe_spacing)
            # Estimate uncertainty
            spacing_std = self._estimate_spacing_std(peaks, valleys)
            _, thickness_uncertainty = calculator.calculate_with_uncertainty(
                fringe_spacing, spacing_std
            )
        else:
            thickness = np.nan
            thickness_uncertainty = np.nan

        # Multi-beam correction
        multi_beam_corrected = self._apply_multi_beam_correction(
            thickness, contrast
        )

        return SolveResult(
            sample_name=sample_name,
            material=material,
            fringe_spacing=fringe_spacing or np.nan,
            thickness=thickness,
            thickness_uncertainty=thickness_uncertainty,
            contrast=contrast,
            multi_beam_corrected=multi_beam_corrected,
            analysis_region=region,
            peaks=peaks,
            valleys=valleys
        )

    def _compute_fringe_spacing(
        self,
        peaks: np.ndarray,
        valleys: np.ndarray
    ) -> Optional[float]:
        """
        Compute fringe spacing from peaks and valleys.

        Strategy:
        1. If multiple peaks, use peak spacing
        2. If multiple valleys, use valley spacing
        3. If only one extrema, estimate from full spectrum
        """
        all_extrema = np.sort(np.concatenate([peaks, valleys]))

        if len(all_extrema) < 2:
            return None

        spacings = np.diff(all_extrema)

        # Filter out unreasonable spacings
        valid_spacings = spacings[(spacings > 50) & (spacings < 500)]

        if len(valid_spacings) > 0:
            return float(np.mean(valid_spacings))

        return float(np.mean(spacings))

    def _estimate_spacing_std(self, peaks: np.ndarray, valleys: np.ndarray) -> float:
        """Estimate standard deviation of spacing measurement."""
        all_extrema = np.sort(np.concatenate([peaks, valleys]))

        if len(all_extrema) < 3:
            return 5.0  # Default estimate

        spacings = np.diff(all_extrema)
        return float(np.std(spacings))

    def _apply_multi_beam_correction(
        self,
        thickness: float,
        contrast: float
    ) -> Optional[float]:
        """
        Apply multi-beam interference correction.

        Args:
            thickness: Raw thickness
            contrast: Interference contrast

        Returns:
            Corrected thickness or None
        """
        if np.isnan(thickness):
            return None

        # Estimate correction factor from contrast
        # C = 2F/(F+1) => F = C/(2-C)
        if contrast >= 2:
            contrast = 1.99

        F = contrast / (2 - contrast)
        k = F / np.pi

        # Limit correction factor to reasonable range
        k = np.clip(k, 0.95, 1.05)

        return thickness * k

    def solve_all(
        self,
        spectra: Dict[str, Tuple[np.ndarray, np.ndarray]],
        materials: Dict[str, str]
    ) -> List[SolveResult]:
        """
        Solve for all samples.

        Args:
            spectra: Dictionary mapping sample names to (wavenumber, reflectivity)
            materials: Dictionary mapping sample names to material types

        Returns:
            List of SolveResult objects
        """
        results = []

        for name, (wn, refl) in spectra.items():
            material = materials.get(name, 'SiC')
            result = self.solve_sample(wn, refl, name, material)
            results.append(result)

        return results


class ReportGenerator:
    """Generates analysis reports."""

    @staticmethod
    def generate_summary(results: List[SolveResult]) -> str:
        """Generate summary report."""
        lines = ["=" * 70]
        lines.append("EPITAXIAL LAYER THICKNESS MEASUREMENT SUMMARY")
        lines.append("=" * 70)
        lines.append("")

        for r in results:
            lines.append(f"Sample: {r.sample_name}")
            lines.append(f"Material: {r.material}")
            lines.append(f"Analysis Region: {r.analysis_region[0]:.0f}-{r.analysis_region[1]:.0f} cm⁻¹")
            lines.append(f"Fringe Spacing: {r.fringe_spacing:.3f} cm⁻¹")
            lines.append(f"Thickness: {r.thickness:.3f} ± {r.thickness_uncertainty:.3f} μm")
            lines.append(f"Multi-beam Corrected: {r.multi_beam_corrected:.3f} μm" if r.multi_beam_corrected else "Multi-beam Corrected: N/A")
            lines.append(f"Contrast: {r.contrast:.4f}")
            lines.append(f"Peaks: {len(r.peaks)}, Valleys: {len(r.valleys)}")
            lines.append("-" * 40)

        return "\n".join(lines)
