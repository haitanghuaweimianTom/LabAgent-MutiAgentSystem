"""
Specialized Agents Module
========================

Concrete implementations of agents for specific tasks:
- ProblemAnalyzer: Analyzes and decomposes problems
- MethodRetriever: Retrieves relevant methods from knowledge base
- ModelBuilder: Constructs mathematical models
- ChartCreator: Generates visualizations
- PaperWriter: Compiles scientific papers
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from .base import BaseAgent, AgentConfig, AgentRole
from .coordinator import get_knowledge_base, MethodNode


# Problem Analyzer Agent
class ProblemAnalyzerAgent(BaseAgent):
    """Analyzes mathematical modeling problems."""

    def analyze(self, input_data: Any) -> Dict[str, Any]:
        """
        Analyze a problem statement.

        Args:
            input_data: Dictionary with 'problem_text' and optionally 'attachments'

        Returns:
            Analysis results including sub-problems and requirements
        """
        problem_text = input_data.get('problem_text', '')
        attachments = input_data.get('attachments', [])

        # Identify problem type
        problem_type = self._identify_type(problem_text)

        # Split into sub-problems
        sub_problems = self._decompose(problem_text)

        # Extract requirements
        requirements = self._extract_requirements(problem_text)

        # Identify data requirements
        data_requirements = self._identify_data_requirements(problem_text)

        return {
            'problem_type': problem_type,
            'sub_problems': sub_problems,
            'requirements': requirements,
            'data_requirements': data_requirements,
            'attachments': attachments,
            'problem_text': problem_text
        }

    def _identify_type(self, text: str) -> str:
        """Identify problem type from keywords."""
        text_lower = text.lower()
        if any(kw in text_lower for kw in ['厚度', 'thickness', 'measurement']):
            return 'measurement'
        elif any(kw in text_lower for kw in ['优化', 'optimal', 'minimize', 'maximize']):
            return 'optimization'
        elif any(kw in text_lower for kw in ['预测', 'predict', 'forecast']):
            return 'prediction'
        elif any(kw in text_lower for kw in ['分类', 'classif']):
            return 'classification'
        return 'analysis'

    def _decompose(self, text: str) -> List[Dict[str, Any]]:
        """Decompose problem into sub-problems."""
        import re
        sub_problems = []

        # Match patterns like "问题1", "问题 1", "1."
        pattern = r'(?:问题\s*(\d+)|(\d+)[．.、])[:：]\s*([^\n]+(?:\n(?!\s*(?:问题\s*\d+|附件))[^\n]+)*)'

        matches = re.findall(pattern, text)
        for match in matches:
            num = match[0] or match[1]
            content = match[2].strip()
            sub_problems.append({
                'id': f"task_{num}",
                'number': int(num) if num else len(sub_problems) + 1,
                'description': content[:500],  # Limit length
                'type': self._identify_type(content)
            })

        return sub_problems if sub_problems else [{'id': 'task_1', 'number': 1, 'description': text[:500], 'type': 'analysis'}]

    def _extract_requirements(self, text: str) -> List[str]:
        """Extract requirements from text."""
        requirements = []

        if '论文' in text or 'paper' in text.lower():
            requirements.append('Generate research paper')
        if any(kw in text.lower() for kw in ['图表', 'figure', 'plot']):
            requirements.append('Generate figures')
        if any(kw in text.lower() for kw in ['计算', 'calculat']):
            requirements.append('Numerical calculations')
        if any(kw in text.lower() for kw in ['分析', 'analys']):
            requirements.append('Detailed analysis')

        return requirements

    def _identify_data_requirements(self, text: str) -> Dict[str, Any]:
        """Identify data requirements."""
        return {
            'has_attachments': '附件' in text or 'attachment' in text.lower(),
            'data_format': 'excel' if 'excel' in text.lower() else 'unknown',
            'requires_preprocessing': True
        }


# Method Retriever Agent
class MethodRetrieverAgent(BaseAgent):
    """Retrieves relevant methods from knowledge base."""

    def __init__(self, config: AgentConfig):
        """Initialize with knowledge base."""
        super().__init__(config)
        self.kb = get_knowledge_base()
        self.top_k = 6

    def analyze(self, input_data: Any) -> Dict[str, Any]:
        """
        Retrieve relevant methods for a problem.

        Args:
            input_data: Dictionary with 'problem_description' and optionally 'task_id'

        Returns:
            Retrieved methods with relevance scores
        """
        problem_description = input_data.get('problem_description', '')
        task_id = input_data.get('task_id', 'unknown')

        # Get suggested methods
        suggested = self.kb.suggest_methods(problem_description, top_k=self.top_k)

        # Format results
        methods = []
        for method in suggested:
            methods.append({
                'id': method.id,
                'name': method.name,
                'description': method.description,
                'equations': method.equations,
                'parameters': method.parameters,
                'assumptions': method.assumptions,
                'applications': method.applications,
                'related_methods': method.related_methods
            })

        return {
            'task_id': task_id,
            'methods': methods,
            'method_count': len(methods)
        }


# Model Builder Agent
class ModelBuilderAgent(BaseAgent):
    """Constructs mathematical models."""

    def analyze(self, input_data: Any) -> Dict[str, Any]:
        """
        Build a mathematical model.

        Args:
            input_data: Dictionary with problem analysis and selected methods

        Returns:
            Mathematical model specification
        """
        problem_analysis = input_data.get('problem_analysis', {})
        selected_methods = input_data.get('methods', [])

        # Build model based on problem type
        problem_type = problem_analysis.get('problem_type', 'analysis')

        if problem_type == 'measurement':
            model = self._build_measurement_model(selected_methods)
        elif problem_type == 'optimization':
            model = self._build_optimization_model(selected_methods)
        else:
            model = self._build_analysis_model(selected_methods)

        return {
            'problem_type': problem_type,
            'model': model,
            'variables': model.get('variables', []),
            'equations': model.get('equations', []),
            'parameters': model.get('parameters', []),
            'assumptions': model.get('assumptions', [])
        }

    def _build_measurement_model(self, methods: List[Dict]) -> Dict[str, Any]:
        """Build model for measurement problem."""
        model = {
            'type': 'measurement',
            'variables': [],
            'equations': [],
            'parameters': [],
            'assumptions': []
        }

        # Add variables
        model['variables'] = [
            {'name': 'σ', 'description': 'Wavenumber (cm⁻¹)', 'unit': 'cm⁻¹'},
            {'name': 'Δσ', 'description': 'Fringe spacing', 'unit': 'cm⁻¹'},
            {'name': 'n', 'description': 'Refractive index', 'unit': 'dimensionless'},
            {'name': 'd', 'description': 'Layer thickness', 'unit': 'μm'},
        ]

        # Add equations from methods
        for method in methods:
            if 'equations' in method:
                model['equations'].extend(method['equations'])

        # Add default equation if none found
        if not model['equations']:
            model['equations'] = [
                'Δ = 2nd = mλ (optical path difference)',
                'd = 1/(2nΔσ) × 10⁴ μm (thickness calculation)'
            ]

        # Add parameters
        model['parameters'] = [
            {'name': 'n', 'value': 2.65, 'uncertainty': 0.05, 'description': 'SiC refractive index'}
        ]

        # Add assumptions
        model['assumptions'] = [
            'Perpendicular incidence',
            'No absorption in measurement region',
            'Uniform layer thickness'
        ]

        return model

    def _build_optimization_model(self, methods: List[Dict]) -> Dict[str, Any]:
        """Build model for optimization problem."""
        return {
            'type': 'optimization',
            'variables': [],
            'equations': [],
            'parameters': [],
            'assumptions': [],
            'objective': '',
            'constraints': []
        }

    def _build_analysis_model(self, methods: List[Dict]) -> Dict[str, Any]:
        """Build model for general analysis problem."""
        return {
            'type': 'analysis',
            'variables': [],
            'equations': methods[0].get('equations', []) if methods else [],
            'parameters': [],
            'assumptions': []
        }


# Chart Creator Agent
class ChartCreatorAgent(BaseAgent):
    """Creates visualizations for results."""

    def analyze(self, input_data: Any) -> Dict[str, Any]:
        """
        Create charts for results.

        Args:
            input_data: Dictionary with results and configuration

        Returns:
            Generated chart information
        """
        results = input_data.get('results', {})
        chart_config = input_data.get('chart_config', {})

        num_charts = chart_config.get('num_charts', 3)

        # Define standard charts
        charts = []

        if results.get('spectra'):
            charts.append({
                'type': 'line',
                'title': 'Spectrum Analysis',
                'data': 'spectra',
                'filename': 'chart_spectrum.png'
            })

        if results.get('thickness'):
            charts.append({
                'type': 'bar',
                'title': 'Thickness Results',
                'data': 'thickness',
                'filename': 'chart_thickness.png'
            })

        if results.get('contrast'):
            charts.append({
                'type': 'comparison',
                'title': 'Interference Contrast',
                'data': 'contrast',
                'filename': 'chart_contrast.png'
            })

        return {
            'charts': charts,
            'count': len(charts),
            'output_dir': chart_config.get('output_dir', '.')
        }


# Paper Writer Agent
class PaperWriterAgent(BaseAgent):
    """Writes scientific papers."""

    def analyze(self, input_data: Any) -> Dict[str, Any]:
        """
        Write a scientific paper.

        Args:
            input_data: Dictionary with analysis, models, results, figures

        Returns:
            Generated paper structure
        """
        problem_analysis = input_data.get('problem_analysis', {})
        model = input_data.get('model', {})
        results = input_data.get('results', {})
        figures = input_data.get('figures', [])

        # Build paper sections
        sections = {}

        # Abstract
        sections['abstract'] = self._write_abstract(results)

        # Introduction
        sections['introduction'] = self._write_introduction(problem_analysis)

        # Methods
        sections['methods'] = self._write_methods(model, results)

        # Results
        sections['results'] = self._write_results(results, figures)

        # Discussion
        sections['discussion'] = self._write_discussion(results)

        # Conclusion
        sections['conclusion'] = self._write_conclusion(results)

        return {
            'title': problem_analysis.get('title', 'Mathematical Modeling Analysis'),
            'sections': sections,
            'figures': figures,
            'tables': self._generate_tables(results)
        }

    def _write_abstract(self, results: Dict) -> str:
        """Write abstract section."""
        return f"""
This paper presents a comprehensive analysis of {results.get('problem_type', 'the given problem')}.
The methodology involves {' and '.join(results.get('methods', ['standard techniques']))}.
Results indicate {'thickness measurements of ' + str(results.get('thickness', 'N/A')) if 'thickness' in results else 'satisfactory agreement with expected values'}.
The approach provides a non-destructive, accurate method suitable for {'production quality control' if 'thickness' in results else 'scientific analysis'}.
"""

    def _write_introduction(self, problem_analysis: Dict) -> str:
        """Write introduction section."""
        return f"""
The problem addressed in this study involves {problem_analysis.get('problem_type', 'mathematical modeling')} of {problem_analysis.get('description', 'the given system')}.
This type of analysis is important for understanding the underlying mechanisms and predicting future behavior.

The objective of this paper is to establish a rigorous mathematical model and develop efficient algorithms
for solving the problem. We approach this by first analyzing the problem structure, then constructing
appropriate mathematical models, and finally implementing computational solutions.
"""

    def _write_methods(self, model: Dict, results: Dict) -> str:
        """Write methods section."""
        equations = '\n'.join([f"- {eq}" for eq in model.get('equations', [])])
        return f"""
## Mathematical Model

The mathematical model is based on the following key equations:

{equations}

### Parameters

The following parameters were used in the analysis:
{self._format_parameters(model.get('parameters', []))}

### Assumptions

The analysis is based on the following assumptions:
{self._format_list(model.get('assumptions', []))}
"""

    def _write_results(self, results: Dict, figures: List) -> str:
        """Write results section."""
        figure_refs = '\n'.join([f"Figure {i+1}: {f.get('title', 'Untitled')}" for i, f in enumerate(figures)])
        return f"""
## Results

The analysis yielded the following results:

### Key Findings

{self._format_results(results)}

### Figures

{figure_refs if figure_refs else 'No figures generated.'}
"""

    def _write_discussion(self, results: Dict) -> str:
        """Write discussion section."""
        return f"""
## Discussion

The results demonstrate the effectiveness of the proposed approach.
The {'thickness measurements show good agreement with expected values' if 'thickness' in results else 'analysis provides valuable insights into the problem structure'}.

### Limitations

The current analysis makes certain assumptions that may limit the generalizability:
{self._format_list(results.get('limitations', ['Analysis limited to specified parameter ranges']))}

### Future Work

Future work could explore:
- Extended parameter ranges
- Additional validation studies
- Optimization for production use
"""

    def _write_conclusion(self, results: Dict) -> str:
        """Write conclusion section."""
        return f"""
## Conclusion

This study has successfully established a mathematical model for {'epitaxial layer thickness measurement' if 'thickness' in results else 'the given problem'}.
The computational approach provides {'accurate results' if results.get('success') else 'preliminary insights'} suitable for practical applications.
The method is {'non-destructive and suitable for production quality control' if 'thickness' in results else 'general-purpose and adaptable'}.
"""

    def _format_parameters(self, parameters: List[Dict]) -> str:
        """Format parameters list."""
        if not parameters:
            return "- No parameters specified"
        return '\n'.join([f"- {p.get('name', 'unknown')}: {p.get('value', 'N/A')} ({p.get('description', '')})" for p in parameters])

    def _format_list(self, items: List[str]) -> str:
        """Format list items."""
        if not items:
            return "- None specified"
        return '\n'.join([f"- {item}" for item in items])

    def _format_results(self, results: Dict) -> str:
        """Format results summary."""
        lines = []
        for key, value in results.items():
            if key not in ['success', 'methods', 'limitations']:
                lines.append(f"- **{key}**: {value}")
        return '\n'.join(lines) if lines else "- Results pending"

    def _generate_tables(self, results: Dict) -> List[Dict]:
        """Generate result tables."""
        tables = []

        if 'thickness' in results:
            tables.append({
                'title': 'Thickness Measurement Results',
                'headers': ['Sample', 'Thickness (μm)', 'Uncertainty (μm)'],
                'rows': results.get('thickness_table', [])
            })

        return tables
