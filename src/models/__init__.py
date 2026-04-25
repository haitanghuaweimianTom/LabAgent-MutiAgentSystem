"""
Mathematical Modeling Module
===========================

Implements double-beam and multi-beam interference models for
epitaxial layer thickness measurement.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class ModelParameters:
    """Parameters for interference models."""
    refractive_index: float
    thickness: Optional[float] = None
    fringe_spacing: Optional[float] = None
    contrast: Optional[float] = None
    finesse: Optional[float] = None


class DoubleBeamInterferenceModel:
    """
    Double-beam interference model for epitaxial layer thickness calculation.

    The model is based on the interference of two reflected beams:
    - Beam 1: Reflected from the epitaxial layer surface
    - Beam 2: Transmitted through the epitaxial layer and reflected from substrate

    Key equations:
    - Optical path difference: Δ = 2nd
    - Interference condition: 2ndσ = m
    - Fringe spacing: Δσ = 1/(2nd)
    - Thickness: d = 1/(2nΔσ)
    """

    def __init__(self, refractive_index: float = 2.65):
        """
        Initialize model with refractive index.

        Args:
            refractive_index: Effective refractive index of epitaxial layer
        """
        self.n = refractive_index
        self._parameters = ModelParameters(refractive_index=refractive_index)

    def compute_thickness(self, fringe_spacing: float) -> float:
        """
        Calculate epitaxial layer thickness from fringe spacing.

        Args:
            fringe_spacing: Interference fringe spacing Δσ (cm^-1)

        Returns:
            Thickness d in micrometers
        """
        if fringe_spacing <= 0:
            raise ValueError("Fringe spacing must be positive")

        # d = 1/(2*n*Δσ) * 10^4 μm
        d = 1e4 / (2 * self.n * fringe_spacing)
        self._parameters.thickness = d
        self._parameters.fringe_spacing = fringe_spacing

        return d

    def compute_fringe_spacing_from_thickness(self, thickness: float) -> float:
        """
        Calculate fringe spacing from thickness.

        Args:
            thickness: Layer thickness d (μm)

        Returns:
            Fringe spacing Δσ (cm^-1)
        """
        if thickness <= 0:
            raise ValueError("Thickness must be positive")

        # Δσ = 1/(2nd) * 10^4 cm^-1
        delta_sigma = 1e4 / (2 * self.n * thickness)
        self._parameters.thickness = thickness
        self._parameters.fringe_spacing = delta_sigma

        return delta_sigma

    def compute_contrast(self, r1: float, r2: float, t: float = 1.0) -> float:
        """
        Compute theoretical interference contrast.

        Args:
            r1: Surface reflectance
            r2: Substrate interface reflectance
            t: Transmittance (default 1)

        Returns:
            Contrast C (0-1)
        """
        # C = 2*r1*r2*t^2 / (r1^2 + r2^2*t^2)
        numerator = 2 * r1 * r2 * t**2
        denominator = r1**2 + r2**2 * t**2

        if denominator == 0:
            return 0.0

        return numerator / denominator

    @property
    def parameters(self) -> ModelParameters:
        """Get current model parameters."""
        return self._parameters

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'model_type': 'DoubleBeamInterference',
            'refractive_index': self.n,
            'thickness_um': self._parameters.thickness,
            'fringe_spacing_cm-1': self._parameters.fringe_spacing
        }


class MultiBeamInterferenceModel:
    """
    Multi-beam interference model for enhanced analysis.

    This model accounts for multiple reflections at the epitaxial
    layer-substrate interface, which becomes significant when
    the interface reflectance is high.

    Key equations:
    - Phase difference: δ = 4πnd/λ
    - Intensity: I = I0 * F*sin²(δ/2) / (1 + F*sin²(δ/2))
    - Finesse: F = 4r²/(1-r²)²
    """

    def __init__(self, refractive_index: float = 2.65):
        """
        Initialize multi-beam model.

        Args:
            refractive_index: Effective refractive index
        """
        self.n = refractive_index
        self._parameters = ModelParameters(refractive_index=refractive_index)

    def compute_intensity(self, delta: float, r: float = 0.9) -> float:
        """
        Compute multi-beam interference intensity.

        Args:
            delta: Phase difference δ
            r: Interface reflectance

        Returns:
            Normalized intensity I/I0
        """
        # Finesse
        if r >= 1:
            r = 0.999

        F = 4 * r**2 / (1 - r**2)**2

        # Intensity formula for near-perfect reflector
        sin_sq = np.sin(delta / 2)**2
        intensity = F * sin_sq / (1 + F * sin_sq)

        return intensity

    def compute_correction_factor(self, contrast: float) -> float:
        """
        Compute thickness correction factor based on contrast.

        For high-quality epitaxial layers, the correction is small.
        The correction factor accounts for the difference between the
        double-beam model (which assumes only two reflections) and the
        actual multi-beam interference.

        For most semiconductor layers with R > 0.8, the correction
        is in the range 0.98-1.02.

        Args:
            contrast: Measured interference contrast C

        Returns:
            Correction factor k (typically 0.98 < k < 1.02)
        """
        # Limit contrast to physical range
        if contrast >= 1:
            contrast = 0.999
        if contrast <= 0:
            contrast = 0.001

        # For high contrast (C > 0.85), the correction is small
        # The correction factor k = 1 for ideal two-beam interference
        # For multi-beam with high reflectance, k slightly > 1

        # Empirical formula for semiconductor epitaxial layers
        # Based on: k ≈ 1 + 0.05*(1-C) for C > 0.5
        # This gives k in range 0.98-1.02 for C in 0.85-1.0

        if contrast > 0.5:
            k = 1.0 + 0.05 * (1 - contrast)
        else:
            k = 1.0

        # Limit k to reasonable range
        k = max(0.95, min(1.05, k))

        return k

    def compute_thickness_with_correction(
        self,
        fringe_spacing: float,
        contrast: float
    ) -> Tuple[float, float]:
        """
        Calculate thickness with multi-beam correction.

        Args:
            fringe_spacing: Measured fringe spacing
            contrast: Measured interference contrast

        Returns:
            Tuple of (corrected_thickness, raw_thickness)
        """
        # Raw thickness (double-beam)
        d_raw = 1e4 / (2 * self.n * fringe_spacing)

        # Correction factor
        k = self.compute_correction_factor(contrast)

        # Corrected thickness
        d_corrected = k * d_raw

        return d_corrected, d_raw

    def estimate_finesse(self, contrast: float) -> float:
        """
        Estimate finesse from contrast.

        Args:
            contrast: Measured contrast C

        Returns:
            Finesse F
        """
        if contrast >= 2:
            contrast = 1.99

        return contrast / (2 - contrast)


class SellmeierDispersion:
    """
    Sellmeier dispersion model for wavelength-dependent refractive index.

    n²(λ) = 1 + Σ[Bᵢλ²/(λ² - Cᵢ²)]
    """

    # Material parameters
    MATERIALS = {
        '4H-SiC': {'B': [2.55], 'C': [10.6]},  # μm
        '6H-SiC': {'B': [2.55], 'C': [10.6]},
        'Si': {'B': [1.1, 0.044], 'C': [0.127, 9.79]},  # μm
    }

    def __init__(self, material: str = '4H-SiC'):
        """
        Initialize Sellmeier model.

        Args:
            material: Material name ('4H-SiC', '6H-SiC', 'Si')
        """
        if material not in self.MATERIALS:
            raise ValueError(f"Unknown material: {material}")

        self.material = material
        self.params = self.MATERIALS[material]

    def compute_index(self, wavelength_um: float) -> float:
        """
        Compute refractive index at given wavelength.

        Args:
            wavelength_um: Wavelength in micrometers

        Returns:
            Refractive index n
        """
        wavelength_sq = wavelength_um ** 2
        n_sq = 1.0

        for B, C in zip(self.params['B'], self.params['C']):
            n_sq += B * wavelength_sq / (wavelength_sq - C**2)

        return np.sqrt(n_sq)

    def compute_index_at_wavenumber(self, wavenumber_cm: float) -> float:
        """
        Compute refractive index at given wavenumber.

        Args:
            wavenumber_cm: Wavenumber in cm^-1

        Returns:
            Refractive index n
        """
        wavelength_um = 1e4 / wavenumber_cm  # Convert cm^-1 to μm
        return self.compute_index(wavelength_um)

    def compute_average_index(
        self,
        wn_min: float,
        wn_max: float,
        n_points: int = 100
    ) -> float:
        """
        Compute average refractive index over a wavenumber range.

        Args:
            wn_min, wn_max: Wavenumber range (cm^-1)
            n_points: Number of sample points

        Returns:
            Average refractive index
        """
        wavenumbers = np.linspace(wn_min, wn_max, n_points)
        indices = [self.compute_index_at_wavenumber(wn) for wn in wavenumbers]
        return float(np.mean(indices))


class ModelComparison:
    """Compare different interference models."""

    @staticmethod
    def compare_thickness_results(
        models: List[Tuple[str, DoubleBeamInterferenceModel, float]],
        fringe_spacing: float
    ) -> Dict:
        """
        Compare thickness results from multiple models.

        Args:
            models: List of (name, model, refractive_index) tuples
            fringe_spacing: Measured fringe spacing

        Returns:
            Dictionary of results
        """
        results = {}

        for name, model_class, n in models:
            model = model_class(refractive_index=n)
            thickness = model.compute_thickness(fringe_spacing)
            results[name] = {
                'refractive_index': n,
                'thickness_um': thickness
            }

        return results

    @staticmethod
    def analyze_multi_beam_effect(
        contrast: float,
        raw_thickness: float
    ) -> Dict:
        """
        Analyze the effect of multi-beam interference.

        Args:
            contrast: Measured contrast
            raw_thickness: Thickness from double-beam model

        Returns:
            Analysis results
        """
        # Estimate finesse
        if contrast >= 2:
            contrast = 1.99
        finesse = contrast / (2 - contrast)

        # Correction factor
        k = finesse / np.pi

        return {
            'contrast': contrast,
            'finesse': finesse,
            'correction_factor': k,
            'corrected_thickness': k * raw_thickness,
            'correction_percent': (k - 1) * 100
        }
