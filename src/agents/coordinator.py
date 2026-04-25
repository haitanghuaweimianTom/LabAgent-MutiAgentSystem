"""
Hierarchical Method Knowledge Base
================================

Similar to LLM-MM-Agent's HMML (Hierarchical Mathematical Modeling Library),
this module provides a structured knowledge base of mathematical methods
organized by domain and subdomain.

The knowledge base is used for:
- Method retrieval based on problem characteristics
- RAG-based scoring using embeddings
- Hierarchical traversal for method suggestions
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json


class MethodDomain(Enum):
    """High-level method domains."""
    SPECTROSCOPY = "spectroscopy"
    INTERFERENCE = "interference"
    THIN_FILMS = "thin_films"
    SEMICONDUCTOR = "semiconductor"
    OPTIMIZATION = "optimization"
    REGRESSION = "regression"
    CLASSIFICATION = "classification"
    TIME_SERIES = "time_series"
    IMAGE_PROCESSING = "image_processing"
    SIGNAL_PROCESSING = "signal_processing"


class MethodSubdomain(Enum):
    """Method subdomains."""
    FTIR_SPECTROSCOPY = "ftir_spectroscopy"
    RAMAN_SPECTROSCOPY = "raman_spectroscopy"
    INTERFERENCE_SPECTROSCOPY = "interference_spectroscopy"
    MULTI_BEAM_INTERFERENCE = "multi_beam_interference"
    OPTICAL_THICKNESS = "optical_thickness"
    MATERIAL_CHARACTERIZATION = "material_characterization"
    LINEAR_PROGRAMMING = "linear_programming"
    NONLINEAR_PROGRAMMING = "nonlinear_programming"
    CURVE_FITTING = "curve_fitting"
    FOURIER_ANALYSIS = "fourier_analysis"


@dataclass
class MethodNode:
    """A node in the method knowledge tree."""
    id: str
    name: str
    domain: str
    subdomain: str
    description: str
    equations: List[str] = field(default_factory=list)
    parameters: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    applications: List[str] = field(default_factory=list)
    related_methods: List[str] = field(default_factory=list)
    code_template: str = ""
    references: List[str] = field(default_factory=list)


class MethodKnowledgeBase:
    """
    Hierarchical mathematical modeling method knowledge base.

    Structure:
    - Domain (e.g., Spectroscopy, Optimization)
      - Subdomain (e.g., FTIR Spectroscopy, Interference)
        - Method (e.g., Double-beam Interference Model)
    """

    def __init__(self):
        """Initialize with default methods."""
        self.methods: Dict[str, MethodNode] = {}
        self.domain_to_subdomains: Dict[str, List[str]] = {}
        self.subdomain_to_methods: Dict[str, List[str]] = {}
        self._load_default_methods()

    def _load_default_methods(self) -> None:
        """Load default spectroscopy and interference methods."""
        # Double-beam interference method
        self.add_method(MethodNode(
            id="double_beam_interference",
            name="Double-beam Interference Model",
            domain="spectroscopy",
            subdomain="interference_spectroscopy",
            description="Two-beam interference model for thin film thickness measurement",
            equations=[
                "Δ = 2nd = mλ (optical path difference)",
                "d = 1/(2nΔσ) × 10⁴ μm (thickness calculation)"
            ],
            parameters=["n (refractive index)", "Δσ (fringe spacing)"],
            assumptions=[
                "Perpendicular incidence",
                "Single reflection at each interface",
                "No absorption in layer"
            ],
            applications=["Epitaxial layer thickness", "Thin film measurement"],
            related_methods=["multi_beam_interference", "sellmeier_dispersion"]
        ))

        # Multi-beam interference method
        self.add_method(MethodNode(
            id="multi_beam_interference",
            name="Multi-beam Interference Model",
            domain="spectroscopy",
            subdomain="multi_beam_interference",
            description="Enhanced model accounting for multiple reflections at interface",
            equations=[
                "I/I₀ = F·sin²(δ/2) / (1 + F·sin²(δ/2))",
                "F = 4r²/(1-r²)² (finesse factor)",
                "C = F/(F+1) (contrast)"
            ],
            parameters=["r (interface reflectance)", "F (finesse)", "C (contrast)"],
            assumptions=[
                "High interface reflectance",
                "Multiple internal reflections"
            ],
            applications=["High-precision thickness", "Semiconductor quality control"],
            related_methods=["double_beam_interference"]
        ))

        # Sellmeier dispersion model
        self.add_method(MethodNode(
            id="sellmeier_dispersion",
            name="Sellmeier Dispersion Model",
            domain="spectroscopy",
            subdomain="material_characterization",
            description="Wavelength-dependent refractive index model",
            equations=[
                "n²(λ) = 1 + Σ[Bᵢλ²/(λ² - Cᵢ²)]"
            ],
            parameters=["Bᵢ, Cᵢ (Sellmeier coefficients)"],
            assumptions=["Normal dispersion region"],
            applications=["Refractive index calculation", "Dispersion correction"],
            related_methods=["double_beam_interference"]
        ))

        # Savitzky-Golay smoothing
        self.add_method(MethodNode(
            id="savgol_filter",
            name="Savitzky-Golay Smoothing",
            domain="signal_processing",
            subdomain="spectral_smoothing",
            description="Polynomial smoothing filter preserving peak shapes",
            equations=[
                "Window size: odd integer",
                "Polynomial order: typically 2-4"
            ],
            parameters=["window_length", "polyorder"],
            assumptions=["Smooth underlying signal"],
            applications=["Noise reduction", "Spectral preprocessing"],
            related_methods=["moving_average", "gaussian_smoothing"]
        ))

        # Peak detection
        self.add_method(MethodNode(
            id="peak_detection",
            name="Interference Peak Detection",
            domain="signal_processing",
            subdomain="spectral_analysis",
            description="Detection of peaks and valleys in spectral data",
            equations=[
                "Prominence: vertical distance to lowest contour line",
                "Distance: minimum horizontal separation between peaks"
            ],
            parameters=["prominence", "distance", "height"],
            assumptions=["Clear signal peaks"],
            applications=["Fringe spacing measurement", "Spectral analysis"],
            related_methods=["savgol_filter", "fourier_analysis"]
        ))

        # Fourier analysis
        self.add_method(MethodNode(
            id="fourier_analysis",
            name="Fourier Transform Analysis",
            domain="signal_processing",
            subdomain="fourier_analysis",
            description="Frequency domain analysis for periodic patterns",
            equations=[
                "F(ν) = ∫f(t)e^(-i2πνt)dt",
                "Period = 1/frequency"
            ],
            parameters=["frequency resolution", "window function"],
            assumptions=["Stationary signals"],
            applications=["Frequency identification", "Period estimation"],
            related_methods=["peak_detection"]
        ))

        # Linear regression
        self.add_method(MethodNode(
            id="linear_regression",
            name="Linear Regression",
            domain="regression",
            subdomain="curve_fitting",
            description="Fitting data to linear models",
            equations=[
                "y = ax + b",
                "a = Σ(x-x̄)(y-ȳ) / Σ(x-x̄)²"
            ],
            parameters=["slope", "intercept", "R²"],
            assumptions=["Linear relationship", "Gaussian errors"],
            applications=["Calibration", "Parameter estimation"],
            related_methods=["nonlinear_regression", "polynomial_fitting"]
        ))

        # Uncertainty propagation
        self.add_method(MethodNode(
            id="uncertainty_propagation",
            name="Uncertainty Propagation",
            domain="statistics",
            subdomain="error_analysis",
            description="Propagation of measurement uncertainties",
            equations=[
                "σ_f² = Σ(∂f/∂xᵢ)²σᵢ² (independent)",
                "σ_f² = Σ(∂f/∂x)²σᵢ² + 2Σ(∂f/∂xᵢ)(∂f/∂xⱼ)COV(xᵢ,xⱼ)"
            ],
            parameters=["standard deviations", "correlation coefficients"],
            assumptions=["Gaussian distributions"],
            applications=["Error estimation", "Sensitivity analysis"],
            related_methods=["monte_carlo"]
        ))

    def add_method(self, method: MethodNode) -> None:
        """Add a method to the knowledge base."""
        self.methods[method.id] = method

        # Update domain/subdomain mappings
        if method.domain not in self.domain_to_subdomains:
            self.domain_to_subdomains[method.domain] = []
        if method.subdomain not in self.domain_to_subdomains[method.domain]:
            self.domain_to_subdomains[method.domain].append(method.subdomain)

        if method.subdomain not in self.subdomain_to_methods:
            self.subdomain_to_methods[method.subdomain] = []
        self.subdomain_to_methods[method.subdomain].append(method.id)

    def get_method(self, method_id: str) -> Optional[MethodNode]:
        """Get a method by ID."""
        return self.methods.get(method_id)

    def get_methods_by_subdomain(self, subdomain: str) -> List[MethodNode]:
        """Get all methods in a subdomain."""
        method_ids = self.subdomain_to_methods.get(subdomain, [])
        return [self.methods[mid] for mid in method_ids if mid in self.methods]

    def get_methods_by_domain(self, domain: str) -> List[MethodNode]:
        """Get all methods in a domain."""
        subdomains = self.domain_to_subdomains.get(domain, [])
        methods = []
        for sd in subdomains:
            methods.extend(self.get_methods_by_subdomain(sd))
        return methods

    def search_methods(self, query: str) -> List[Tuple[MethodNode, float]]:
        """
        Simple keyword-based method search.

        Returns methods matching the query, sorted by relevance.

        Args:
            query: Search query (keywords)

        Returns:
            List of (method, score) tuples
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scores = []
        for method in self.methods.values():
            # Count keyword matches
            text = f"{method.name} {method.description} {' '.join(method.applications)}".lower()
            word_matches = sum(1 for word in query_words if word in text)

            # Bonus for exact name match
            name_match = 1.0 if query_lower in method.name.lower() else 0.0

            # Calculate score
            score = word_matches + name_match
            if score > 0:
                scores.append((method, score))

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

    def suggest_methods(self, problem_description: str, top_k: int = 3) -> List[MethodNode]:
        """
        Suggest relevant methods based on problem description.

        Args:
            problem_description: Description of the problem
            top_k: Number of methods to return

        Returns:
            List of suggested method nodes
        """
        results = self.search_methods(problem_description)
        return [method for method, score in results[:top_k]]

    def get_method_chain(self, method_id: str) -> List[MethodNode]:
        """
        Get a chain of related methods starting from a given method.

        Args:
            method_id: Starting method ID

        Returns:
            List of methods in the chain
        """
        chain = []
        visited = set()

        def traverse(mid: str):
            if mid in visited or mid not in self.methods:
                return
            visited.add(mid)
            chain.append(self.methods[mid])
            method = self.methods[mid]
            for related_id in method.related_methods:
                traverse(related_id)

        traverse(method_id)
        return chain

    def to_json(self) -> Dict[str, Any]:
        """Export knowledge base to JSON-serializable dict."""
        return {
            "methods": {
                k: {
                    "id": v.id,
                    "name": v.name,
                    "domain": v.domain,
                    "subdomain": v.subdomain,
                    "description": v.description,
                    "equations": v.equations,
                    "parameters": v.parameters,
                    "assumptions": v.assumptions,
                    "applications": v.applications,
                    "related_methods": v.related_methods,
                    "references": v.references
                }
                for k, v in self.methods.items()
            },
            "domain_to_subdomains": self.domain_to_subdomains,
            "subdomain_to_methods": {
                k: list(v) for k, v in self.subdomain_to_methods.items()
            }
        }

    def save(self, filepath: str) -> None:
        """Save knowledge base to JSON file."""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_json(), f, ensure_ascii=False, indent=2)

    def load(self, filepath: str) -> None:
        """Load knowledge base from JSON file."""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.methods = {}
        self.domain_to_subdomains = {}
        self.subdomain_to_methods = {}

        for method_id, method_data in data.get("methods", {}).items():
            self.add_method(MethodNode(**method_data))

    def print_tree(self) -> None:
        """Print the method hierarchy tree."""
        for domain, subdomains in self.domain_to_subdomains.items():
            print(f"\n{domain.upper().replace('_', ' ')}:")
            for subdomain in subdomains:
                methods = self.subdomain_to_methods.get(subdomain, [])
                print(f"  └── {subdomain}:")
                for mid in methods:
                    if mid in self.methods:
                        print(f"      └── {self.methods[mid].name} ({mid})")


# Global knowledge base instance
_method_knowledge_base = None

def get_knowledge_base() -> MethodKnowledgeBase:
    """Get the global knowledge base instance."""
    global _method_knowledge_base
    if _method_knowledge_base is None:
        _method_knowledge_base = MethodKnowledgeBase()
    return _method_knowledge_base
