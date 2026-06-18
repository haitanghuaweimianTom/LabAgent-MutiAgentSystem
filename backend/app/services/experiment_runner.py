"""实验运行器 —— 实际执行主实验、baseline 对比与消融实验。"""
from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .code_sandbox import CodeSandbox, SandboxConfig, SandboxResult

logger = logging.getLogger(__name__)


@dataclass
class ExperimentScript:
    """单个实验脚本描述。"""

    name: str
    path: Path
    args: Dict[str, Any] = field(default_factory=dict)
    role: str = "main"  # main | baseline | ablation
    description: str = ""


@dataclass
class ExperimentRunResult:
    """一次脚本运行的结果。"""

    name: str
    role: str
    success: bool
    metrics: Dict[str, Any] = field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    returncode: int = -1
    duration_sec: float = 0.0
    checkpoint_path: Optional[str] = None
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "success": self.success,
            "metrics": self.metrics,
            "stdout": self.stdout[:2000] if self.stdout else "",
            "stderr": self.stderr[:2000] if self.stderr else "",
            "returncode": self.returncode,
            "duration_sec": self.duration_sec,
            "checkpoint_path": self.checkpoint_path,
            "error": self.error,
        }


@dataclass
class ExperimentBatchResult:
    """一批实验（主实验 + baselines + ablations）的结果。"""

    success: bool
    main: Optional[ExperimentRunResult] = None
    baselines: List[ExperimentRunResult] = field(default_factory=list)
    ablations: List[ExperimentRunResult] = field(default_factory=list)
    figures: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    duration_sec: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "main": self.main.to_dict() if self.main else None,
            "baselines": [r.to_dict() for r in self.baselines],
            "ablations": [r.to_dict() for r in self.ablations],
            "figures": self.figures,
            "errors": self.errors,
            "duration_sec": self.duration_sec,
        }


class ExperimentRunner:
    """实验运行器。

    负责：
    - 在指定环境中运行主实验脚本
    - 批量运行 baseline 脚本
    - 批量运行 ablation 变体脚本
    - 提取指标和检查点路径
    """

    def __init__(
        self,
        sandbox: Optional[CodeSandbox] = None,
        python_bin: Optional[str] = None,
        max_runtime_seconds: int = 3600,
        max_memory_mb: int = 8192,
    ):
        self.sandbox = sandbox or CodeSandbox(
            config=SandboxConfig(max_runtime_seconds=max_runtime_seconds, max_memory_mb=max_memory_mb)
        )
        self.python_bin = python_bin or (shutil.which("python3") or shutil.which("python") or "python")
        self.max_runtime_seconds = max_runtime_seconds

    # ------------------------------------------------------------------
    # 批量执行
    # ------------------------------------------------------------------

    def run_experiment(
        self,
        main_script: ExperimentScript,
        baseline_scripts: Optional[List[ExperimentScript]] = None,
        ablation_scripts: Optional[List[ExperimentScript]] = None,
        output_dir: Optional[Path] = None,
    ) -> ExperimentBatchResult:
        """运行完整实验批次。"""
        start = time.time()
        result = ExperimentBatchResult(success=True)

        # 主实验
        logger.info(f"[ExperimentRunner] 运行主实验: {main_script.name}")
        result.main = self._run_single(main_script, output_dir)
        if not result.main.success:
            result.success = False
            result.errors.append(f"主实验失败: {result.main.error}")

        # baselines
        for script in baseline_scripts or []:
            logger.info(f"[ExperimentRunner] 运行 baseline: {script.name}")
            run_result = self._run_single(script, output_dir)
            result.baselines.append(run_result)
            if not run_result.success:
                result.success = False
                result.errors.append(f"baseline {script.name} 失败: {run_result.error}")

        # ablations
        for script in ablation_scripts or []:
            logger.info(f"[ExperimentRunner] 运行 ablation: {script.name}")
            run_result = self._run_single(script, output_dir)
            result.ablations.append(run_result)
            if not run_result.success:
                result.success = False
                result.errors.append(f"ablation {script.name} 失败: {run_result.error}")

        result.duration_sec = round(time.time() - start, 2)

        # 扫描输出目录中的图表
        if output_dir and output_dir.exists():
            for ext in ("*.png", "*.pdf", "*.jpg"):
                result.figures.extend(str(p) for p in sorted(output_dir.rglob(ext)))

        return result

    # ------------------------------------------------------------------
    # 单脚本执行
    # ------------------------------------------------------------------

    def _run_single(self, script: ExperimentScript, output_dir: Optional[Path]) -> ExperimentRunResult:
        if not script.path.exists():
            return ExperimentRunResult(
                name=script.name,
                role=script.role,
                success=False,
                error=f"脚本不存在: {script.path}",
            )

        # 构建命令
        cmd = [self.python_bin, "-X", "utf8", str(script.path)]
        args = dict(script.args)
        if output_dir:
            args.setdefault("output_dir", str(output_dir / script.role / script.name.replace(" ", "_")))
        for key, val in args.items():
            cmd.append(f"--{key}")
            cmd.append(str(val))

        # 执行
        sandbox_result = self.sandbox.run_command(cmd, cwd=script.path.parent)

        # 提取指标
        metrics = self._extract_metrics(sandbox_result)

        # 查找检查点
        checkpoint_path = None
        if output_dir:
            role_dir = output_dir / script.role / script.name.replace(" ", "_")
            checkpoint_path = self._find_checkpoint(role_dir)

        return ExperimentRunResult(
            name=script.name,
            role=script.role,
            success=sandbox_result.success,
            metrics=metrics,
            stdout=sandbox_result.stdout,
            stderr=sandbox_result.stderr,
            returncode=sandbox_result.returncode,
            duration_sec=sandbox_result.duration_sec,
            checkpoint_path=str(checkpoint_path) if checkpoint_path else None,
            error=sandbox_result.message if not sandbox_result.success else "",
        )

    # ------------------------------------------------------------------
    # 指标提取
    # ------------------------------------------------------------------

    def _extract_metrics(self, result: SandboxResult) -> Dict[str, Any]:
        """从 stdout/stderr 中提取指标。"""
        text = (result.stdout or "") + "\n" + (result.stderr or "")
        metrics: Dict[str, Any] = {}

        # 优先解析 JSON 行 {"metric": value, ...}
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    data = json.loads(line)
                    for k, v in data.items():
                        if isinstance(v, (int, float, str, bool)):
                            metrics[k] = v
                except json.JSONDecodeError:
                    continue

        # 如果没有 JSON 指标，回退到正则提取
        if not metrics:
            patterns = {
                "loss": re.compile(r"loss[\s:=]+([\d.]+(?:e[+-]?\d+)?)", re.IGNORECASE),
                "val_loss": re.compile(r"val(?:idation)?[\s_]?loss[\s:=]+([\d.]+(?:e[+-]?\d+)?)", re.IGNORECASE),
                "accuracy": re.compile(r"acc(?:uracy)?[\s:=]+([\d.]+)", re.IGNORECASE),
                "val_accuracy": re.compile(r"val(?:idation)?[\s_]?acc(?:uracy)?[\s:=]+([\d.]+)", re.IGNORECASE),
                "f1": re.compile(r"f1[\s_-]?score?[\s:=]+([\d.]+)", re.IGNORECASE),
                "precision": re.compile(r"precision[\s:=]+([\d.]+)", re.IGNORECASE),
                "recall": re.compile(r"recall[\s:=]+([\d.]+)", re.IGNORECASE),
            }
            for key, pattern in patterns.items():
                matches = pattern.findall(text)
                if matches:
                    try:
                        metrics[key] = float(matches[-1])
                    except ValueError:
                        continue

        return metrics

    def _find_checkpoint(self, output_dir: Path) -> Optional[Path]:
        """查找最新的检查点文件。"""
        if not output_dir.exists():
            return None
        candidates = list(output_dir.rglob("*.pt")) + list(output_dir.rglob("*.pth")) + list(output_dir.rglob("*.ckpt"))
        if not candidates:
            return None
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------


def get_experiment_runner(
    python_bin: Optional[str] = None,
    max_runtime_seconds: int = 3600,
    max_memory_mb: int = 8192,
) -> ExperimentRunner:
    """获取默认实验运行器。"""
    return ExperimentRunner(
        python_bin=python_bin,
        max_runtime_seconds=max_runtime_seconds,
        max_memory_mb=max_memory_mb,
    )
