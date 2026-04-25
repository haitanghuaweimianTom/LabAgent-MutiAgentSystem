"""
Solver Agent Module
=================

Implements the TaskSolver agent with self-healing code generation.
Based on LLM-MM-Agent's self-healing loop pattern.

Features:
- Actor-Critic refinement
- Self-healing code generation with retry
- Error diagnosis and fix
- Result interpretation
"""

from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import time
import traceback
from .base import BaseAgent, AgentConfig, AgentRole, register_agent


@dataclass
class CodeAttempt:
    """Record of a code generation attempt."""
    code: str
    error: Optional[str] = None
    success: bool = False
    attempt_number: int = 0
    execution_time: float = 0.0


@dataclass
class SolveResult:
    """Result from solving a task."""
    task_id: str
    code: str
    output: Any
    success: bool
    error: Optional[str] = None
    attempts: int = 0
    execution_time: float = 0.0
    charts_generated: List[str] = field(default_factory=list)


class SelfHealingSolver(BaseAgent):
    """
    Solver agent with self-healing code generation.

    Implements a retry loop:
    1. Generate code
    2. Execute code
    3. If error: diagnose and fix
    4. Repeat up to max_attempts
    """

    def __init__(self, config: AgentConfig):
        """Initialize solver agent."""
        super().__init__(config)
        self.max_attempts = config.max_iterations
        self.debug_rounds = 3

    def analyze(self, input_data: Any) -> Dict[str, Any]:
        """Main analysis entry point."""
        return self.solve_task(input_data)

    def solve_task(self, task_description: Dict[str, Any]) -> SolveResult:
        """
        Solve a task with self-healing.

        Args:
            task_description: Dictionary containing:
                - task_id: Unique identifier
                - problem: Problem description
                - model: Mathematical model to use
                - parameters: Model parameters
                - data: Data to process

        Returns:
            SolveResult with code, output, and status
        """
        task_id = task_description.get('task_id', 'unknown')
        problem = task_description.get('problem', '')
        model = task_description.get('model', {})
        parameters = task_description.get('parameters', {})
        data = task_description.get('data', None)

        print(f"\n{'='*60}")
        print(f"Solving Task: {task_id}")
        print(f"{'='*60}")

        # Initialize
        code = ""
        output = None
        error = None
        success = False
        start_time = time.time()

        # Self-healing loop
        for attempt in range(self.max_attempts):
            print(f"\n--- Attempt {attempt + 1}/{self.max_attempts} ---")

            try:
                # Generate code
                code = self._generate_code(problem, model, parameters, data, attempt)

                # Execute code
                output = self._execute_code(code, data)

                # Validate output
                if self._validate_output(output):
                    success = True
                    print(f"✓ Task solved successfully!")
                    break
                else:
                    error = "Output validation failed"
                    print(f"✗ Output validation failed")
                    code = self._improve_code(code, output, error, attempt)

            except Exception as e:
                error = str(e)
                print(f"✗ Error: {error}")
                code = self._improve_code(code, output, error, attempt)

        execution_time = time.time() - start_time

        return SolveResult(
            task_id=task_id,
            code=code,
            output=output,
            success=success,
            error=error,
            attempts=attempt + 1,
            execution_time=execution_time
        )

    def _generate_code(self, problem: str, model: Dict, parameters: Dict,
                      data: Any, attempt: int) -> str:
        """
        Generate code for solving the task.

        This is a template-based generator. In a full implementation,
        this would use an LLM.
        """
        model_type = model.get('type', 'default')

        if model_type == 'interference':
            return self._generate_interference_code(model, parameters)
        elif model_type == 'regression':
            return self._generate_regression_code(model, parameters)
        else:
            return self._generate_default_code(model, parameters)

    def _generate_interference_code(self, model: Dict, parameters: Dict) -> str:
        """Generate code for interference analysis."""
        n = parameters.get('refractive_index', 2.65)
        region_min = parameters.get('region_min', 700)
        region_max = parameters.get('region_max', 1000)

        code = f'''
import numpy as np
from scipy.signal import savgol_filter, find_peaks

def analyze_interference_spectrum(wavenumber, reflectivity, refractive_index={n}):
    """
    Analyze interference spectrum for epitaxial layer thickness.

    Args:
        wavenumber: Wavenumber array (cm⁻¹)
        reflectivity: Reflectivity array (%)
        refractive_index: Effective refractive index

    Returns:
        Dictionary with analysis results
    """
    # Extract region
    mask = (wavenumber >= {region_min}) & (wavenumber <= {region_max})
    wn_region = wavenumber[mask]
    refl_region = reflectivity[mask]

    # Smooth data
    refl_smooth = savgol_filter(refl_region, window_length=31, polyorder=3)

    # Find peaks
    peaks, _ = find_peaks(refl_smooth, distance=30, prominence=2.0)

    if len(peaks) >= 2:
        # Calculate fringe spacing
        spacing = np.mean(np.diff(wn_region[peaks]))

        # Calculate thickness
        thickness = 1e4 / (2 * refractive_index * spacing)

        # Calculate contrast
        contrast = (refl_smooth.max() - refl_smooth.min()) / (refl_smooth.max() + refl_smooth.min())

        return {{
            'fringe_spacing': spacing,
            'thickness': thickness,
            'contrast': contrast,
            'peaks': wn_region[peaks],
            'success': True
        }}
    else:
        return {{'success': False, 'error': 'Insufficient peaks detected'}}

# Apply analysis
results = analyze_interference_spectrum(wavenumber, reflectivity)
'''
        return code

    def _generate_regression_code(self, model: Dict, parameters: Dict) -> str:
        """Generate code for regression analysis."""
        code = '''
import numpy as np
from scipy.optimize import curve_fit

def linear_model(x, a, b):
    return a * x + b

def fit_regression(x, y):
    """
    Fit data to linear regression model.

    Returns:
        Dictionary with fit parameters and R²
    """
    popt, pcov = curve_fit(linear_model, x, y)
    a, b = popt

    # Calculate R²
    y_pred = linear_model(x, a, b)
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r_squared = 1 - (ss_res / ss_tot)

    return {
        'slope': a,
        'intercept': b,
        'r_squared': r_squared,
        'success': True
    }

results = fit_regression(x_data, y_data)
'''
        return code

    def _generate_default_code(self, model: Dict, parameters: Dict) -> str:
        """Generate default analysis code."""
        return '''
import numpy as np

def analyze_data(data, parameters):
    """
    Default analysis function.

    Args:
        data: Input data
        parameters: Analysis parameters

    Returns:
        Analysis results dictionary
    """
    # Placeholder - implement specific analysis
    return {
        'status': 'placeholder',
        'success': True
    }

results = analyze_data(data, parameters)
'''

    def _execute_code(self, code: str, data: Any) -> Any:
        """
        Execute generated code with data context.

        In a full implementation, this would use a sandboxed executor.
        """
        # Create execution namespace
        namespace = {}

        # Add data to namespace
        if data is not None:
            if isinstance(data, dict):
                for key, value in data.items():
                    namespace[key] = value

        # Execute code
        try:
            exec(code, namespace)
            return namespace.get('results', None)
        except Exception as e:
            raise RuntimeError(f"Code execution failed: {str(e)}")

    def _validate_output(self, output: Any) -> bool:
        """Validate that output is sensible."""
        if output is None:
            return False
        if isinstance(output, dict):
            # Check for success flag
            if 'success' in output:
                return output['success']
            # Check for required fields
            required = ['thickness', 'fringe_spacing']
            if all(k in output for k in required):
                # Validate ranges
                if 0 < output['thickness'] < 1000:  # 0-1000 μm reasonable
                    return True
        return False

    def _improve_code(self, code: str, output: Any, error: str,
                      attempt: int) -> str:
        """
        Improve code based on error or validation failure.

        This is a simplified version. In full implementation,
        this would use an LLM to analyze the error and suggest fixes.
        """
        print(f"Improving code (attempt {attempt + 1})...")

        # Simple heuristics for common errors
        if "find_peaks" in code and "prominence" in str(error):
            # Reduce prominence threshold
            code = code.replace("prominence=2.0", "prominence=1.0")
            print("  → Reduced prominence threshold to 1.0")

        if "Insufficient peaks" in str(output):
            # Try full spectrum analysis
            if "mask = " in code:
                # Remove region mask to use full spectrum
                code = code.replace(
                    "mask = (wavenumber >= region_min) & (wavenumber <= region_max)\n    wn_region = wavenumber[mask]\n    refl_region = reflectivity[mask]",
                    "wn_region = wavenumber\n    refl_region = reflectivity"
                )
                print("  → Using full spectrum instead of region")

        return code


class ActorCriticAgent(BaseAgent):
    """
    Agent implementing Actor-Critic refinement pattern.

    Pattern:
    1. Actor generates initial response
    2. Critic evaluates and identifies issues
    3. Improver refines based on critique
    4. Repeat for specified rounds
    """

    def __init__(self, config: AgentConfig):
        """Initialize actor-critic agent."""
        super().__init__(config)
        self.rounds = config.max_iterations

    def analyze(self, input_data: Any) -> Dict[str, Any]:
        """Run actor-critic analysis."""
        problem = input_data.get('problem', '')

        # Initial generation (Actor)
        response = self._actor_generate(problem)

        # Refinement loop
        for round_num in range(self.rounds):
            # Critic evaluation
            critique = self._critic_evaluate(problem, response)

            # Check if good enough
            if self._is_acceptable(critique):
                print(f"  ✓ Acceptable after {round_num + 1} rounds")
                break

            # Improvement (Actor again)
            response = self._improver_refine(problem, response, critique)
            print(f"  → Round {round_num + 1}: refined based on critique")

        return {
            'response': response,
            'critique': critique if 'critique' in dir() else None,
            'rounds': self.rounds
        }

    def _actor_generate(self, problem: str) -> str:
        """Actor generates initial response."""
        # Placeholder - in full implementation, use LLM
        return f"Analysis of: {problem[:100]}..."

    def _critic_evaluate(self, problem: str, response: str) -> str:
        """Critic evaluates response."""
        # Placeholder - in full implementation, use LLM
        return "Analysis complete. No major issues identified."

    def _improver_refine(self, problem: str, response: str, critique: str) -> str:
        """Improve response based on critique."""
        # Placeholder - in full implementation, use LLM
        return response + "\n[Refined based on critique]"

    def _is_acceptable(self, critique: str) -> bool:
        """Check if critique indicates acceptable quality."""
        negative_keywords = ['error', 'incorrect', 'missing', 'incomplete', 'failed']
        return not any(kw in critique.lower() for kw in negative_keywords)
