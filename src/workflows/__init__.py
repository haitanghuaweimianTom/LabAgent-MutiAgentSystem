"""
Workflow System Module
=====================

Manages multi-agent collaboration workflows for problem solving.
Based on LLM-MM-Agent's four-stage workflow design.

Stages:
1. Problem Analysis - Understand and deconstruct the problem
2. Model Building - Construct mathematical models
3. Computational Solving - Implement algorithms
4. Report Generation - Produce results and papers
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import time
from collections import defaultdict


class WorkflowStage(Enum):
    """Standard workflow stages."""
    PROBLEM_ANALYSIS = "problem_analysis"
    MODEL_BUILDING = "model_building"
    COMPUTATIONAL_SOLVING = "solving"
    VISUALIZATION = "visualization"
    REPORT_GENERATION = "report_generation"
    FINAL_REVIEW = "final_review"


@dataclass
class StageResult:
    """Result from a workflow stage."""
    stage: WorkflowStage
    status: str  # "success", "failed", "partial"
    output: Any
    artifacts: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    duration: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowConfig:
    """Configuration for a workflow."""
    name: str
    description: str
    stages: List[WorkflowStage]
    max_retries: int = 3
    timeout_per_stage: int = 600
    parallel_stages: bool = False


class BaseWorkflow(ABC):
    """
    Abstract base class for workflows.

    A workflow defines the sequence of stages and manages
    the flow of data between them.
    """

    def __init__(self, config: WorkflowConfig):
        """
        Initialize workflow.

        Args:
            config: WorkflowConfig defining workflow properties
        """
        self.config = config
        self.name = config.name
        self.description = config.description
        self.stages = config.stages
        self.results: Dict[WorkflowStage, StageResult] = {}
        self.current_stage: Optional[WorkflowStage] = None

    @abstractmethod
    def execute_stage(self, stage: WorkflowStage, input_data: Any) -> StageResult:
        """
        Execute a single stage - must be implemented by subclasses.

        Args:
            stage: The stage to execute
            input_data: Input data for the stage

        Returns:
            StageResult containing stage output
        """
        pass

    def execute(self, input_data: Any) -> Dict[WorkflowStage, StageResult]:
        """
        Execute the complete workflow.

        Args:
            input_data: Initial input data

        Returns:
            Dictionary of stage results
        """
        data = input_data

        for stage in self.stages:
            self.current_stage = stage
            start_time = time.time()

            result = self.execute_stage(stage, data)
            result.duration = time.time() - start_time

            self.results[stage] = result

            if result.status == "failed":
                print(f"Stage {stage.value} failed: {result.errors}")
                break

            # Pass output to next stage
            data = result.output

        return self.results

    def get_result(self, stage: WorkflowStage) -> Optional[StageResult]:
        """Get result for a specific stage."""
        return self.results.get(stage)

    def get_all_artifacts(self) -> Dict[str, Any]:
        """Collect all artifacts from all stages."""
        artifacts = {}
        for stage, result in self.results.items():
            artifacts.update(result.artifacts)
        return artifacts


class SequentialWorkflow(BaseWorkflow):
    """Workflow that executes stages sequentially."""

    def execute_stage(self, stage: WorkflowStage, input_data: Any) -> StageResult:
        """Execute a single stage sequentially."""
        print(f"\n{'='*60}")
        print(f"Executing stage: {stage.value}")
        print(f"{'='*60}")

        try:
            output = self._process_stage(stage, input_data)
            return StageResult(
                stage=stage,
                status="success",
                output=output
            )
        except Exception as e:
            return StageResult(
                stage=stage,
                status="failed",
                output=None,
                errors=[str(e)]
            )

    @abstractmethod
    def _process_stage(self, stage: WorkflowStage, input_data: Any) -> Any:
        """Internal method to process a stage."""
        pass


class MathModelingWorkflow(SequentialWorkflow):
    """
    Standard workflow for mathematical modeling problems.

    Follows the four-stage model:
    1. Problem Analysis - Read and understand the problem
    2. Model Building - Develop mathematical models
    3. Computational Solving - Implement algorithms
    4. Report Generation - Write the paper
    """

    def __init__(self):
        """Initialize with standard stages."""
        config = WorkflowConfig(
            name="Mathematical Modeling Workflow",
            description="Standard 4-stage workflow for math modeling competitions",
            stages=[
                WorkflowStage.PROBLEM_ANALYSIS,
                WorkflowStage.MODEL_BUILDING,
                WorkflowStage.COMPUTATIONAL_SOLVING,
                WorkflowStage.VISUALIZATION,
                WorkflowStage.REPORT_GENERATION,
                WorkflowStage.FINAL_REVIEW
            ]
        )
        super().__init__(config)
        self.context: Dict[str, Any] = {}

    def _process_stage(self, stage: WorkflowStage, input_data: Any) -> Any:
        """Process each stage."""
        if stage == WorkflowStage.PROBLEM_ANALYSIS:
            return self._analyze_problem(input_data)
        elif stage == WorkflowStage.MODEL_BUILDING:
            return self._build_models(input_data)
        elif stage == WorkflowStage.COMPUTATIONAL_SOLVING:
            return self._solve(input_data)
        elif stage == WorkflowStage.VISUALIZATION:
            return self._visualize(input_data)
        elif stage == WorkflowStage.REPORT_GENERATION:
            return self._generate_report(input_data)
        elif stage == WorkflowStage.FINAL_REVIEW:
            return self._final_review(input_data)
        return input_data

    def _analyze_problem(self, input_data: Any) -> Dict[str, Any]:
        """Stage 1: Problem Analysis."""
        # Extract key requirements
        self.context['problem_text'] = input_data.get('problem_text', '')
        self.context['attachments'] = input_data.get('attachments', [])

        # Identify problem type and requirements
        analysis = {
            'problem_type': self._identify_problem_type(input_data.get('problem_text', '')),
            'requirements': self._extract_requirements(input_data.get('problem_text', '')),
            'sub_problems': self._split_into_subproblems(input_data.get('problem_text', '')),
            'data_files': input_data.get('attachments', []),
            'expected_outputs': self._identify_outputs(input_data.get('problem_text', ''))
        }

        self.context['analysis'] = analysis
        return analysis

    def _build_models(self, input_data: Any) -> Dict[str, Any]:
        """Stage 2: Mathematical Modeling."""
        analysis = input_data
        models = {}

        # Build model for each sub-problem
        for sub_prob in analysis.get('sub_problems', []):
            models[sub_prob['id']] = {
                'type': sub_prob['type'],
                'variables': sub_prob.get('variables', []),
                'equations': sub_prob.get('equations', []),
                'assumptions': sub_prob.get('assumptions', [])
            }

        self.context['models'] = models
        return models

    def _solve(self, input_data: Any) -> Dict[str, Any]:
        """Stage 3: Computational Solving."""
        # This would be replaced with actual solver implementation
        return {"status": "solved", "results": {}}

    def _visualize(self, input_data: Any) -> Dict[str, Any]:
        """Stage 4: Visualization."""
        return {"figures": []}

    def _generate_report(self, input_data: Any) -> Dict[str, Any]:
        """Stage 5: Report Generation."""
        return {"paper": "", "figures": []}

    def _final_review(self, input_data: Any) -> Dict[str, Any]:
        """Stage 6: Final Review."""
        return {"status": "complete"}

    def _identify_problem_type(self, text: str) -> str:
        """Identify the type of mathematical problem."""
        text_lower = text.lower()
        if '优化' in text or 'optimal' in text_lower:
            return "optimization"
        elif '预测' in text or 'forecast' in text_lower:
            return "prediction"
        elif '分类' in text or 'classif' in text_lower:
            return "classification"
        elif '拟合' in text or 'fitting' in text_lower:
            return "curve_fitting"
        elif '测量' in text or 'measurement' in text_lower:
            return "measurement"
        else:
            return "analysis"

    def _extract_requirements(self, text: str) -> List[str]:
        """Extract problem requirements."""
        requirements = []
        if '问题1' in text:
            requirements.append("Problem 1 analysis required")
        if '问题2' in text:
            requirements.append("Problem 2 analysis required")
        if '问题3' in text:
            requirements.append("Problem 3 analysis required")
        if '问题4' in text:
            requirements.append("Problem 4 analysis required")
        return requirements

    def _split_into_subproblems(self, text: str) -> List[Dict[str, Any]]:
        """Split problem text into sub-problems."""
        sub_problems = []

        # Simple splitting by "问题X" markers
        import re
        pattern = r'问题\s*(\d+)[：:]\s*([^\n]+(?:\n(?!\s*问题\s*\d)[^\n]+)*)'

        matches = re.findall(pattern, text)
        for i, (num, content) in enumerate(matches):
            sub_problems.append({
                'id': f"problem_{num}",
                'number': int(num),
                'description': content.strip()[:200],
                'type': 'analysis'  # Default type
            })

        return sub_problems

    def _identify_outputs(self, text: str) -> List[str]:
        """Identify expected outputs."""
        outputs = []
        if '论文' in text or 'paper' in text.lower():
            outputs.append("Research paper")
        if '图表' in text or 'figure' in text.lower():
            outputs.append("Figures and tables")
        if '数据' in text or 'result' in text.lower():
            outputs.append("Numerical results")
        return outputs


class WorkflowEngine:
    """Engine for managing and executing workflows."""

    def __init__(self):
        """Initialize workflow engine."""
        self.workflows: Dict[str, BaseWorkflow] = {}
        self.active_workflow: Optional[BaseWorkflow] = None

    def register_workflow(self, name: str, workflow: BaseWorkflow) -> None:
        """Register a workflow."""
        self.workflows[name] = workflow

    def execute_workflow(self, name: str, input_data: Any) -> Dict[WorkflowStage, StageResult]:
        """Execute a registered workflow."""
        if name not in self.workflows:
            raise ValueError(f"Workflow '{name}' not found")

        workflow = self.workflows[name]
        self.active_workflow = workflow
        return workflow.execute(input_data)

    def get_workflow(self, name: str) -> Optional[BaseWorkflow]:
        """Get a workflow by name."""
        return self.workflows.get(name)
