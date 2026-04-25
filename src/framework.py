"""
Main Framework Module
====================

Generic mathematical modeling framework entry point.
Coordinates the multi-stage workflow across all agents.

Based on LLM-MM-Agent's architecture:
- Stage 1: Problem Analysis
- Stage 2: Mathematical Modeling
- Stage 3: Computational Solving
- Stage 4: Visualization
- Stage 5: Report Generation
"""

from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from pathlib import Path
import time
import json

from agents import (
    BaseAgent, AgentConfig, AgentRole,
    ProblemAnalyzerAgent, MethodRetrieverAgent,
    ModelBuilderAgent, ChartCreatorAgent, PaperWriterAgent
)
from workflows import (
    BaseWorkflow, WorkflowStage, WorkflowEngine,
    MathModelingWorkflow, StageResult
)
from config import ConfigManager
from prompts import PromptManager
from agents.coordinator import get_knowledge_base


@dataclass
class FrameworkConfig:
    """Configuration for the framework."""
    project_name: str = "Mathematical Modeling Project"
    output_dir: str = "output"
    num_figures: int = 3
    problem_analysis_rounds: int = 3
    task_solving_attempts: int = 5
    enable_rag: bool = True


class MathModelingFramework:
    """
    Main framework class for mathematical modeling problem solving.

    Coordinates all agents and workflows to solve problems
    and generate comprehensive reports.

    Usage:
        framework = MathModelingFramework(config)
        results = framework.solve(problem_text, attachments)
        framework.generate_report(output_file)
    """

    def __init__(self, config: Optional[FrameworkConfig] = None):
        """
        Initialize the framework.

        Args:
            config: Framework configuration
        """
        self.config = config or FrameworkConfig()

        # Initialize components
        self.config_manager = ConfigManager()
        self.prompt_manager = PromptManager()
        self.workflow_engine = WorkflowEngine()

        # Initialize agents
        self._init_agents()

        # Results storage
        self.results: Dict[str, Any] = {}
        self.artifacts: Dict[str, Any] = {}

    def _init_agents(self) -> None:
        """Initialize all agents."""
        # Problem Analyzer
        analyzer_config = AgentConfig(
            name="problem_analyzer",
            role=AgentRole.PROBLEM_ANALYZER,
            description="Analyzes problem statements"
        )
        self.problem_analyzer = ProblemAnalyzerAgent(analyzer_config)

        # Method Retriever
        retriever_config = AgentConfig(
            name="method_retriever",
            role=AgentRole.DATA_PROCESSOR,
            description="Retrieves relevant methods"
        )
        self.method_retriever = MethodRetrieverAgent(retriever_config)

        # Model Builder
        builder_config = AgentConfig(
            name="model_builder",
            role=AgentRole.MODEL_BUILDER,
            description="Builds mathematical models"
        )
        self.model_builder = ModelBuilderAgent(builder_config)

        # Chart Creator
        chart_config = AgentConfig(
            name="chart_creator",
            role=AgentRole.VISUALIZER,
            description="Creates visualizations"
        )
        self.chart_creator = ChartCreatorAgent(chart_config)

        # Paper Writer
        writer_config = AgentConfig(
            name="paper_writer",
            role=AgentRole.REPORTER,
            description="Writes scientific papers"
        )
        self.paper_writer = PaperWriterAgent(writer_config)

    def solve(self, problem_text: str,
              attachments: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Solve a mathematical modeling problem.

        Args:
            problem_text: The problem statement text
            attachments: Optional list of data file paths

        Returns:
            Complete results dictionary
        """
        print("\n" + "="*70)
        print("MATHEMATICAL MODELING FRAMEWORK")
        print("="*70)
        print(f"Project: {self.config.project_name}")
        print("="*70)

        start_time = time.time()

        # Stage 1: Problem Analysis
        print("\n" + "-"*50)
        print("STAGE 1: PROBLEM ANALYSIS")
        print("-"*50)

        problem_analysis = self.problem_analyzer.analyze({
            'problem_text': problem_text,
            'attachments': attachments or []
        })

        print(f"Problem type: {problem_analysis['problem_type']}")
        print(f"Sub-problems identified: {len(problem_analysis['sub_problems'])}")
        for sp in problem_analysis['sub_problems']:
            print(f"  - {sp['id']}: {sp['description'][:60]}...")

        self.results['problem_analysis'] = problem_analysis

        # Stage 2: Mathematical Modeling
        print("\n" + "-"*50)
        print("STAGE 2: MATHEMATICAL MODELING")
        print("-"*50)

        # Retrieve relevant methods
        method_results = self.method_retriever.analyze({
            'problem_description': problem_text,
            'task_id': 'main'
        })

        print(f"Retrieved {method_results['method_count']} relevant methods:")
        for method in method_results['methods']:
            print(f"  - {method['name']}")

        # Build model
        model_results = self.model_builder.analyze({
            'problem_analysis': problem_analysis,
            'methods': method_results['methods']
        })

        print(f"\nBuilt model type: {model_results['model']['type']}")
        print(f"Variables: {len(model_results['variables'])}")
        print(f"Equations: {len(model_results['equations'])}")

        self.results['methods'] = method_results['methods']
        self.results['model'] = model_results

        # Stage 3: Computational Solving
        print("\n" + "-"*50)
        print("STAGE 3: COMPUTATIONAL SOLVING")
        print("-"*50)

        # This would invoke the solver agent
        # For now, mark as complete
        self.results['solving'] = {
            'status': 'ready',
            'model': model_results['model']
        }

        print("Solver ready. Implement data loading and execution in solver_agent.py")

        # Stage 4: Visualization
        print("\n" + "-"*50)
        print("STAGE 4: VISUALIZATION")
        print("-"*50)

        chart_results = self.chart_creator.analyze({
            'results': self.results,
            'chart_config': {
                'num_charts': self.config.num_figures,
                'output_dir': self.config.output_dir
            }
        })

        print(f"Generated {chart_results['count']} charts:")
        for chart in chart_results['charts']:
            print(f"  - {chart['filename']}: {chart['type']}")

        self.artifacts['charts'] = chart_results['charts']

        # Stage 5: Report Generation
        print("\n" + "-"*50)
        print("STAGE 5: REPORT GENERATION")
        print("-"*50)

        paper_results = self.paper_writer.analyze({
            'problem_analysis': problem_analysis,
            'model': model_results['model'],
            'results': self.results,
            'figures': chart_results['charts']
        })

        print(f"Paper title: {paper_results['title']}")
        print(f"Sections: {', '.join(paper_results['sections'].keys())}")
        print(f"Tables: {len(paper_results['tables'])}")

        self.artifacts['paper'] = paper_results

        # Summary
        elapsed = time.time() - start_time
        print("\n" + "="*70)
        print("ANALYSIS COMPLETE")
        print(f"Total time: {elapsed:.2f}s")
        print("="*70)

        return self.results

    def generate_report(self, output_file: str = "report.md") -> None:
        """
        Generate a complete report.

        Args:
            output_file: Output file path
        """
        paper = self.artifacts.get('paper', {})
        sections = paper.get('sections', {})

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"# {paper.get('title', 'Mathematical Modeling Report')}\n\n")

            for section_name, section_content in sections.items():
                f.write(f"## {section_name.upper()}\n\n")
                f.write(section_content)
                f.write("\n\n")

        print(f"\nReport saved to: {output_file}")

    def save_results(self, output_file: str = "results.json") -> None:
        """
        Save results to JSON file.

        Args:
            output_file: Output file path
        """
        # Convert results to JSON-serializable format
        serializable_results = self._make_serializable(self.results)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(serializable_results, f, ensure_ascii=False, indent=2)

        print(f"\nResults saved to: {output_file}")

    def _make_serializable(self, obj: Any) -> Any:
        """Convert objects to JSON-serializable format."""
        if isinstance(obj, dict):
            return {k: self._make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._make_serializable(item) for item in obj]
        elif hasattr(obj, '__dict__'):
            return str(obj)
        else:
            return obj


def create_framework(config: Optional[FrameworkConfig] = None) -> MathModelingFramework:
    """
    Factory function to create framework instance.

    Args:
        config: Optional framework configuration

    Returns:
        Configured MathModelingFramework instance
    """
    return MathModelingFramework(config)


# Main entry point
def main():
    """Main entry point for running the framework."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Generic Mathematical Modeling Framework'
    )
    parser.add_argument('--problem', '-p', type=str,
                       help='Path to problem text file')
    parser.add_argument('--attachments', '-a', nargs='*',
                       help='Paths to attachment files')
    parser.add_argument('--output', '-o', type=str, default='output',
                       help='Output directory')
    parser.add_argument('--config', '-c', type=str,
                       help='Path to configuration file')

    args = parser.parse_args()

    # Load problem
    if args.problem:
        with open(args.problem, 'r', encoding='utf-8') as f:
            problem_text = f.read()
    else:
        problem_text = """
请阅读以下问题并进行数学建模：

[Problem description not provided - use --problem argument]
        """

    # Create framework
    framework_config = FrameworkConfig(
        project_name="Mathematical Modeling Project",
        output_dir=args.output
    )

    framework = create_framework(framework_config)

    # Solve problem
    results = framework.solve(problem_text, args.attachments)

    # Generate outputs
    Path(args.output).mkdir(exist_ok=True)

    framework.generate_report(f"{args.output}/report.md")
    framework.save_results(f"{args.output}/results.json")

    print("\nFramework execution complete!")


if __name__ == '__main__':
    main()
