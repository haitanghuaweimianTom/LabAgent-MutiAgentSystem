"""
Prompts Module
==============

Manages system prompts for different agent types and stages.
Allows for flexible prompt engineering and context management.

Template Variables:
- {problem_text}: The problem statement
- {analysis_results}: Results from problem analysis
- {models}: Built mathematical models
- {results}: Computation results
- {context}: General context dictionary
"""

from typing import Dict, Any, List, Optional
from string import Template
from dataclasses import dataclass


@dataclass
class PromptTemplate:
    """A prompt template with variable substitution."""
    name: str
    role: str
    template: str
    description: str = ""
    variables: List[str] = None

    def render(self, **kwargs) -> str:
        """Render template with provided variables."""
        if self.variables:
            # Check all required variables are present
            missing = set(self.variables) - set(kwargs.keys())
            if missing:
                raise ValueError(f"Missing template variables: {missing}")
        return Template(self.template).substitute(**kwargs)


# Problem Analysis Prompts
PROBLEM_ANALYSIS_PROMPTS = {
    "system": PromptTemplate(
        name="problem_analyzer_system",
        role="system",
        template="""You are an expert problem analyst for mathematical modeling competitions.
Your task is to carefully read and analyze the problem statement to identify:
1. The type of problem (optimization, prediction, classification, measurement, etc.)
2. Key variables and parameters
3. Constraints and assumptions
4. Required outputs (papers, figures, numerical results)
5. Connections between sub-problems

Provide structured analysis that will guide the mathematical modeling process.""",
        description="System prompt for problem analyzer"
    ),

    "analyze": PromptTemplate(
        name="analyze_problem",
        role="user",
        template="""Analyze the following mathematical modeling problem:

${problem_text}

${attachments_info}

Please provide:
1. Problem Type: What kind of mathematical problem is this?
2. Key Variables: List all important variables with their meanings
3. Sub-problems: Break down into logical sub-problems
4. Required Outputs: What must be delivered?
5. Data Files: What data is available and how should it be used?
6. Assumptions: What assumptions can be made?

Be specific and thorough in your analysis.""",
        description="Prompt for analyzing a problem",
        variables=["problem_text", "attachments_info"]
    ),

    "extract_requirements": PromptTemplate(
        name="extract_requirements",
        role="user",
        template="""From the following problem statement, extract the specific requirements for each sub-problem:

${problem_text}

For each numbered sub-problem (问题1, 问题2, etc.), provide:
- The objective
- Required inputs
- Expected outputs
- Any specific constraints mentioned""",
        description="Prompt for extracting requirements"
    ),
}


# Mathematical Modeling Prompts
MODEL_BUILDING_PROMPTS = {
    "system": PromptTemplate(
        name="model_builder_system",
        role="system",
        template="""You are an expert mathematical modeler.
Your task is to construct rigorous mathematical models based on:
1. The problem analysis results
2. Physical/physical principles
3. Appropriate simplifying assumptions
4. Clear variable definitions

For each model, provide:
- Model type (e.g., double-beam interference, multi-beam interference)
- Governing equations
- Key assumptions
- Limitations
- Required parameters""",
        description="System prompt for model builder"
    ),

    "build_model": PromptTemplate(
        name="build_model",
        role="user",
        template="""Based on the problem analysis:

${analysis_results}

Build a mathematical model for this measurement/analysis problem.
Consider:
1. What physical principles apply?
2. What simplifications are appropriate?
3. What equations describe the system?
4. What parameters need to be estimated or assumed?

Provide the mathematical formulation with clear notation.""",
        description="Prompt for building a model",
        variables=["analysis_results"]
    ),
}


# Algorithm Design Prompts
ALGORITHM_PROMPTS = {
    "system": PromptTemplate(
        name="solver_system",
        role="system",
        template="""You are an expert algorithm designer and computational scientist.
Your task is to design efficient algorithms for solving mathematical models.

Consider:
1. Algorithm efficiency and numerical stability
2. Error analysis and uncertainty quantification
3. Edge cases and validation
4. Computational complexity

Provide clear, implementable algorithms.""",
        description="System prompt for solver"
    ),

    "design_algorithm": PromptTemplate(
        name="design_algorithm",
        role="user",
        template="""Design an algorithm for the following model:

Model: ${model_description}
Parameters: ${parameters}
Data: ${data_description}

Design an algorithm that:
1. Calculates the desired quantities
2. Handles measurement uncertainty
3. Validates results
4. Provides error estimates""",
        description="Prompt for designing an algorithm",
        variables=["model_description", "parameters", "data_description"]
    ),
}


# Visualization Prompts
VISUALIZATION_PROMPTS = {
    "system": PromptTemplate(
        name="visualizer_system",
        role="system",
        template="""You are an expert in scientific visualization.
Your task is to create clear, publication-quality figures that:
1. Follow scientific visualization best practices
2. Are colorblind-friendly (use Okabe-Ito palette)
3. Have proper labeling with units
4. Are suitable for journal publication

Consider:
- Multi-panel layouts for comparison
- Appropriate color scales
- Clear legends and annotations
- Consistent styling""",
        description="System prompt for visualizer"
    ),

    "design_figures": PromptTemplate(
        name="design_figures",
        role="user",
        template="""Design figures for presenting the following results:

Results: ${results_summary}

Design ${num_figures} figures that:
1. Clearly communicate the key findings
2. Support the paper narrative
3. Are suitable for journal publication
4. Follow colorblind-friendly guidelines

For each figure, describe:
- The type (line plot, bar chart, heatmap, etc.)
- What data to plot
- Key annotations and labels
- How it contributes to the paper""",
        description="Prompt for designing figures",
        variables=["results_summary", "num_figures"]
    ),
}


# Report Generation Prompts
REPORT_GENERATION_PROMPTS = {
    "system": PromptTemplate(
        name="reporter_system",
        role="system",
        template="""You are an expert scientific writer.
Your task is to produce clear, well-structured scientific papers following IMRAD format:
- Introduction: Establish context and objectives
- Methods: Describe approaches in detail
- Results: Present findings objectively
- Discussion: Interpret results and acknowledge limitations

Write in flowing paragraphs, not bullet points.
Use proper scientific notation and units.
Ensure logical flow and proper citations.""",
        description="System prompt for reporter"
    ),

    "write_paper": PromptTemplate(
        name="write_paper",
        role="user",
        template="""Write a complete scientific paper for the following mathematical modeling project:

Title: ${title}

Problem: ${problem_summary}

Analysis: ${analysis_results}

Model: ${model_description}

Results: ${results_summary}
${figures_info}

The paper should:
1. Be 18-35 pages in length
2. Follow IMRAD structure
3. Include all necessary mathematical derivations
4. Present clear results with uncertainty estimates
5. Discuss limitations and assumptions
6. Include high-quality figures

Write the complete paper in markdown format.""",
        description="Prompt for writing a paper",
        variables=["title", "problem_summary", "analysis_results", "model_description", "results_summary", "figures_info"]
    ),

    "write_section": PromptTemplate(
        name="write_section",
        role="user",
        template="""Write the ${section_name} section of a scientific paper.

Context:
${context}

Requirements:
${requirements}

Write in flowing paragraphs, maintaining scientific rigor and clarity.""",
        description="Prompt for writing a specific section",
        variables=["section_name", "context", "requirements"]
    ),
}


class PromptManager:
    """
    Centralized prompt management.

    Provides:
    - Template rendering with variables
    - Prompt categories
    - Easy access to prompts by name
    """

    def __init__(self):
        """Initialize with all prompt templates."""
        self.prompts: Dict[str, PromptTemplate] = {}
        self._load_prompts()

    def _load_prompts(self) -> None:
        """Load all prompts into the registry."""
        prompt_collections = [
            PROBLEM_ANALYSIS_PROMPTS,
            MODEL_BUILDING_PROMPTS,
            ALGORITHM_PROMPTS,
            VISUALIZATION_PROMPTS,
            REPORT_GENERATION_PROMPTS,
        ]

        for collection in prompt_collections:
            for name, template in collection.items():
                self.prompts[name] = template

    def get_prompt(self, name: str) -> Optional[PromptTemplate]:
        """Get a prompt template by name."""
        return self.prompts.get(name)

    def render(self, name: str, **kwargs) -> str:
        """
        Get and render a prompt template.

        Args:
            name: Name of the prompt
            **kwargs: Template variables

        Returns:
            Rendered prompt string
        """
        template = self.get_prompt(name)
        if template is None:
            raise ValueError(f"Unknown prompt: {name}")
        return template.render(**kwargs)

    def list_prompts(self, category: str = None) -> List[str]:
        """
        List available prompts.

        Args:
            category: Optional category filter

        Returns:
            List of prompt names
        """
        if category:
            # Filter by category prefix
            return [k for k in self.prompts.keys() if k.startswith(f"{category}_")]
        return list(self.prompts.keys())

    def add_prompt(self, name: str, template: PromptTemplate) -> None:
        """Add a custom prompt template."""
        self.prompts[name] = template

    def create_prompt(self, name: str, role: str, template: str,
                     description: str = "") -> PromptTemplate:
        """Create and add a new prompt template."""
        # Extract variables from template
        import re
        variables = re.findall(r'\$\{([^}]+)\}', template)

        prompt = PromptTemplate(
            name=name,
            role=role,
            template=template,
            description=description,
            variables=variables
        )
        self.prompts[name] = prompt
        return prompt
