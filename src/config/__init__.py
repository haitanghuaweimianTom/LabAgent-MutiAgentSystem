"""
Configuration Module
====================

Manages configurations for different problem types and materials.
Supports loading from YAML/JSON and provides default configurations.

Key Features:
- Hierarchical configuration structure
- Environment-specific overrides
- Material/analysis presets
"""

from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field, asdict
from pathlib import Path
import json
import yaml


@dataclass
class MaterialConfig:
    """Configuration for a material type."""
    name: str
    refractive_index: float
    refractive_index_uncertainty: float
    density: Optional[float] = None
    band_gap: Optional[float] = None
    youngs_modulus: Optional[float] = None
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisRegionConfig:
    """Configuration for an analysis spectral region."""
    name: str
    wavenumber_min: float
    wavenumber_max: float
    material: str
    description: str = ""


@dataclass
class AlgorithmConfig:
    """Configuration for algorithms."""
    name: str
    smoothing_window: int = 31
    smoothing_order: int = 3
    peak_distance: int = 30
    peak_prominence: float = 3.0
    valley_prominence: float = 1.0
    fringe_spacing_min: float = 50.0
    fringe_spacing_max: float = 500.0


@dataclass
class VisualizationConfig:
    """Configuration for visualization."""
    figure_width_single: float = 3.5
    figure_width_double: float = 7.0
    figure_dpi: int = 300
    font_family: str = "Arial"
    font_size: int = 10
    color_palette: str = "okabe_ito"  # Colorblind-safe palette


@dataclass
class ProjectConfig:
    """Complete project configuration."""
    project_name: str
    project_description: str
    author: str = "Mathematical Modeling Team"
    materials: Dict[str, MaterialConfig] = field(default_factory=dict)
    analysis_regions: Dict[str, AnalysisRegionConfig] = field(default_factory=dict)
    algorithms: Dict[str, AlgorithmConfig] = field(default_factory=dict)
    visualization: VisualizationConfig = field(default_factory=VisualizationConfig)
    custom_settings: Dict[str, Any] = field(default_factory=dict)


class ConfigLoader:
    """Loads and manages configurations from files."""

    @staticmethod
    def load_yaml(filepath: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        with open(filepath, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    @staticmethod
    def load_json(filepath: str) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def save_yaml(config: Dict[str, Any], filepath: str) -> None:
        """Save configuration to YAML file."""
        with open(filepath, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

    @staticmethod
    def save_json(config: Dict[str, Any], filepath: str) -> None:
        """Save configuration to JSON file."""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)


# Default material configurations
DEFAULT_MATERIALS = {
    'SiC': MaterialConfig(
        name='Silicon Carbide',
        refractive_index=2.65,
        refractive_index_uncertainty=0.05,
        band_gap=3.26,
        properties={
            'polytype': '4H',
            'thermal_conductivity': 490,  # W/(m·K)
            'breakdown_field': 2.5e6,  # V/cm
        }
    ),
    'Si': MaterialConfig(
        name='Silicon',
        refractive_index=3.45,
        refractive_index_uncertainty=0.02,
        band_gap=1.12,
        properties={
            'crystal_structure': 'diamond_cubic',
            'thermal_conductivity': 150,  # W/(m·K)
        }
    ),
    'GaN': MaterialConfig(
        name='Gallium Nitride',
        refractive_index=2.5,
        refractive_index_uncertainty=0.05,
        band_gap=3.4,
        properties={
            'polytype': 'zincblende',
            'thermal_conductivity': 130,  # W/(m·K)
        }
    ),
}

# Default analysis region configurations
DEFAULT_REGIONS = {
    'SiC_reststrahlen': AnalysisRegionConfig(
        name='SiC Reststrahlen Band',
        wavenumber_min=700,
        wavenumber_max=1000,
        material='SiC',
        description='Strong interference region for SiC epitaxial layers'
    ),
    'Si_reststrahlen': AnalysisRegionConfig(
        name='Si Reststrahlen Band',
        wavenumber_min=400,
        wavenumber_max=700,
        material='Si',
        description='Phonon absorption region for Si'
    ),
    'Si_transparent': AnalysisRegionConfig(
        name='Si Transparent Region',
        wavenumber_min=1100,
        wavenumber_max=2000,
        material='Si',
        description='Transparent region for Si where interference is visible'
    ),
}

# Default algorithm configurations
DEFAULT_ALGORITHMS = {
    'default': AlgorithmConfig(
        name='Default Epitaxial Layer Algorithm',
        smoothing_window=31,
        smoothing_order=3,
        peak_distance=30,
        peak_prominence=2.0,
        valley_prominence=1.0,
        fringe_spacing_min=50.0,
        fringe_spacing_max=500.0
    ),
    'sensitive': AlgorithmConfig(
        name='Sensitive Algorithm',
        smoothing_window=21,
        smoothing_order=2,
        peak_distance=20,
        peak_prominence=1.0,
        valley_prominence=0.5,
        fringe_spacing_min=30.0,
        fringe_spacing_max=600.0
    ),
    'robust': AlgorithmConfig(
        name='Robust Algorithm',
        smoothing_window=51,
        smoothing_order=4,
        peak_distance=50,
        peak_prominence=5.0,
        valley_prominence=2.0,
        fringe_spacing_min=100.0,
        fringe_spacing_max=400.0
    ),
}


class ConfigManager:
    """
    Centralized configuration manager.

    Provides:
    - Default configurations
    - Configuration merging/override
    - Problem-specific presets
    - Easy access to all settings
    """

    def __init__(self):
        """Initialize with defaults."""
        self.config = ProjectConfig(
            project_name="Mathematical Modeling Project",
            project_description="Generic framework for math modeling problems"
        )
        self._load_defaults()

    def _load_defaults(self) -> None:
        """Load default configurations."""
        # Load default materials
        for name, mat in DEFAULT_MATERIALS.items():
            self.config.materials[name] = mat

        # Load default regions
        for name, region in DEFAULT_REGIONS.items():
            self.config.analysis_regions[name] = region

        # Load default algorithms
        for name, algo in DEFAULT_ALGORITHMS.items():
            self.config.algorithms[name] = algo

        # Load default visualization
        self.config.visualization = VisualizationConfig()

    def load_from_file(self, filepath: str) -> None:
        """Load configuration from YAML/JSON file."""
        suffix = Path(filepath).suffix.lower()
        if suffix in ['.yaml', '.yml']:
            data = ConfigLoader.load_yaml(filepath)
        elif suffix == '.json':
            data = ConfigLoader.load_json(filepath)
        else:
            raise ValueError(f"Unsupported config file format: {suffix}")

        self._merge_config(data)

    def save_to_file(self, filepath: str) -> None:
        """Save configuration to YAML/JSON file."""
        suffix = Path(filepath).suffix.lower()
        data = asdict(self.config)
        if suffix in ['.yaml', '.yml']:
            ConfigLoader.save_yaml(data, filepath)
        elif suffix == '.json':
            ConfigLoader.save_json(data, filepath)
        else:
            raise ValueError(f"Unsupported config file format: {suffix}")

    def _merge_config(self, data: Dict[str, Any]) -> None:
        """Merge loaded configuration with defaults."""
        if 'project_name' in data:
            self.config.project_name = data['project_name']
        if 'project_description' in data:
            self.config.project_description = data['project_description']

        # Merge materials
        if 'materials' in data:
            for name, mat_data in data['materials'].items():
                self.config.materials[name] = MaterialConfig(**mat_data)

        # Merge regions
        if 'analysis_regions' in data:
            for name, region_data in data['analysis_regions'].items():
                self.config.analysis_regions[name] = AnalysisRegionConfig(**region_data)

        # Merge algorithms
        if 'algorithms' in data:
            for name, algo_data in data['algorithms'].items():
                self.config.algorithms[name] = AlgorithmConfig(**algo_data)

        # Merge custom settings
        if 'custom_settings' in data:
            self.config.custom_settings.update(data['custom_settings'])

    def get_material(self, name: str) -> Optional[MaterialConfig]:
        """Get material configuration by name."""
        return self.config.materials.get(name)

    def get_region(self, name: str) -> Optional[AnalysisRegionConfig]:
        """Get region configuration by name."""
        return self.config.analysis_regions.get(name)

    def get_algorithm(self, name: str) -> Optional[AlgorithmConfig]:
        """Get algorithm configuration by name."""
        return self.config.algorithms.get(name)

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return asdict(self.config)
