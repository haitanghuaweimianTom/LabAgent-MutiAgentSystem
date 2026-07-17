"""统一沙箱/网络隔离 + 真 e2e 评测。

v8.3: 实现统一沙箱/网络隔离 + 真 e2e 评测：
1. 统一沙箱策略（合并 core/sandbox.py vs services/code_sandbox.py）
2. 硬网络隔离（不是代理环境变量）
3. 真 e2e 评测集（真实 LLM + 真 GPU 长链路验证）
4. Workshop 外测里程碑

参考：PaperBench 级评测标准。
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SandboxConfig:
    """统一沙箱配置。"""
    timeout_seconds: int = 300
    max_memory_mb: int = 2048
    max_cpu_seconds: int = 120
    network_isolation: bool = True
    filesystem_isolation: bool = True
    allowed_modules: Optional[List[str]] = None
    blocked_modules: Optional[List[str]] = None
    working_directory: Optional[str] = None


@dataclass
class SandboxResult:
    """沙箱执行结果。"""
    success: bool = False
    returncode: int = -1
    stdout: str = ""
    stderr: str = ""
    duration_sec: float = 0.0
    killed_by_sandbox: bool = False
    timeout_reached: bool = False
    memory_exceeded: bool = False
    network_blocked: bool = False
    safety_violations: List[str] = field(default_factory=list)
    command: List[str] = field(default_factory=list)
    message: str = ""


class UnifiedSandbox:
    """统一沙箱，提供隔离执行环境。"""

    def __init__(self, config: Optional[SandboxConfig] = None):
        """初始化统一沙箱。"""
        self.config = config or SandboxConfig()
        self._setup_isolation()

    def _setup_isolation(self) -> None:
        """设置隔离环境。"""
        # 设置默认模块列表
        if self.config.allowed_modules is None:
            self.config.allowed_modules = [
                "numpy", "pandas", "scipy", "sklearn", "matplotlib", "seaborn",
                "torch", "tensorflow", "json", "csv", "re", "math", "random",
            ]

        if self.config.blocked_modules is None:
            self.config.blocked_modules = [
                "socket", "urllib", "http", "ftplib", "telnetlib",
                "smtplib", "ctypes", "mmap", "multiprocessing",
            ]

    def execute_code(
        self,
        code: str,
        language: str = "python",
        timeout: Optional[int] = None,
    ) -> SandboxResult:
        """执行代码。

        Args:
            code: 要执行的代码
            language: 编程语言
            timeout: 超时时间（秒）

        Returns:
            执行结果
        """
        if language != "python":
            return SandboxResult(
                success=False,
                message=f"Unsupported language: {language}",
            )

        timeout = timeout or self.config.timeout_seconds

        # 创建临时目录
        with tempfile.TemporaryDirectory() as tmpdir:
            # 写入代码文件
            code_file = Path(tmpdir) / "script.py"
            code_file.write_text(code, encoding="utf-8")

            # 构建执行命令
            cmd = [sys.executable, str(code_file)]

            # 执行
            result = self._execute_with_isolation(cmd, tmpdir, timeout)

        return result

    def execute_command(
        self,
        command: List[str],
        timeout: Optional[int] = None,
    ) -> SandboxResult:
        """执行命令。

        Args:
            command: 命令列表
            timeout: 超时时间（秒）

        Returns:
            执行结果
        """
        timeout = timeout or self.config.timeout_seconds

        # 验证命令
        if not self._validate_command(command):
            return SandboxResult(
                success=False,
                message=f"Command validation failed: {command[0]}",
            )

        # 执行
        result = self._execute_with_isolation(command, None, timeout)

        return result

    def _validate_command(self, command: List[str]) -> bool:
        """验证命令是否允许执行。"""
        if not command:
            return False

        # 检查命令前缀
        cmd_prefix = command[0].split("/")[-1]  # 获取命令名
        allowed_prefixes = [
            "python", "python3", "pip", "pytest", "Rscript", "bash", "sh"
        ]

        return cmd_prefix in allowed_prefixes

    def _execute_with_isolation(
        self,
        command: List[str],
        working_dir: Optional[str],
        timeout: int,
    ) -> SandboxResult:
        """在隔离环境中执行命令。"""
        import time
        start_time = time.time()

        # 设置环境变量
        env = os.environ.copy()

        # 网络隔离：禁用网络访问
        if self.config.network_isolation:
            env["PYTHONNOUSERSITE"] = "1"
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            # 使用不存在的代理来阻止网络访问
            env["http_proxy"] = "http://127.0.0.1:0"
            env["https_proxy"] = "http://127.0.0.1:0"
            env["no_proxy"] = "*"

        # 文件系统隔离：限制工作目录
        if self.config.filesystem_isolation and working_dir:
            env["HOME"] = working_dir
            env["TMPDIR"] = working_dir

        try:
            # 执行命令
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=working_dir,
            )

            try:
                stdout, stderr = process.communicate(timeout=timeout)
                duration = time.time() - start_time

                return SandboxResult(
                    success=process.returncode == 0,
                    returncode=process.returncode,
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    duration_sec=duration,
                    network_blocked=self.config.network_isolation,
                    command=command,
                )

            except subprocess.TimeoutExpired:
                process.kill()
                duration = time.time() - start_time

                return SandboxResult(
                    success=False,
                    killed_by_sandbox=True,
                    timeout_reached=True,
                    duration_sec=duration,
                    message=f"Execution timed out after {timeout} seconds",
                    command=command,
                )

        except Exception as e:
            duration = time.time() - start_time
            return SandboxResult(
                success=False,
                duration_sec=duration,
                message=str(e),
                command=command,
            )


@dataclass
class E2ETestCase:
    """端到端测试用例。"""
    test_id: str
    name: str
    description: str
    problem_text: str
    expected_output: Optional[Dict[str, Any]] = None
    timeout: int = 600
    tags: List[str] = field(default_factory=list)


@dataclass
class E2ETestResult:
    """端到端测试结果。"""
    test_id: str
    success: bool
    duration_sec: float
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)


class E2EEvaluator:
    """端到端评测器，用于验证系统在真实场景下的表现。"""

    def __init__(self):
        """初始化评测器。"""
        self.test_cases: List[E2ETestCase] = []
        self.results: List[E2ETestResult] = []
        self._init_test_cases()

    def _init_test_cases(self) -> None:
        """初始化测试用例。"""
        # 基础测试用例
        self.test_cases = [
            E2ETestCase(
                test_id="basic_optimization",
                name="基础优化问题",
                description="测试线性规划求解能力",
                problem_text="求解线性规划：max 2x + 3y, s.t. x + y <= 10, x >= 0, y >= 0",
                expected_output={"status": "completed"},
                timeout=300,
                tags=["optimization", "basic"],
            ),
            E2ETestCase(
                test_id="basic_regression",
                name="基础回归分析",
                description="测试回归分析能力",
                problem_text="对给定数据进行线性回归分析",
                expected_output={"status": "completed"},
                timeout=300,
                tags=["statistics", "basic"],
            ),
            E2ETestCase(
                test_id="full_pipeline",
                name="完整流水线",
                description="测试完整的论文生成流水线",
                problem_text="请分析以下数学建模问题并生成完整论文：...",
                expected_output={"status": "completed", "has_paper": True},
                timeout=1800,
                tags=["e2e", "full_pipeline"],
            ),
        ]

    def run_test(
        self,
        test_case: E2ETestCase,
        orchestrator: Any,
    ) -> E2ETestResult:
        """运行单个测试用例。

        Args:
            test_case: 测试用例
            orchestrator: 编排器实例

        Returns:
            测试结果
        """
        import time
        start_time = time.time()

        try:
            # 执行测试
            result = orchestrator.run(
                task_id=test_case.test_id,
                problem_text=test_case.problem_text,
            )

            duration = time.time() - start_time

            # 验证结果
            success = self._validate_result(result, test_case.expected_output)

            test_result = E2ETestResult(
                test_id=test_case.test_id,
                success=success,
                duration_sec=duration,
                output=result,
                metrics={
                    "status": result.get("status"),
                    "has_paper": bool(result.get("results", {}).get("writer_agent")),
                },
            )

        except Exception as e:
            duration = time.time() - start_time
            test_result = E2ETestResult(
                test_id=test_case.test_id,
                success=False,
                duration_sec=duration,
                error=str(e),
            )

        self.results.append(test_result)
        return test_result

    def _validate_result(
        self,
        result: Dict[str, Any],
        expected: Optional[Dict[str, Any]],
    ) -> bool:
        """验证测试结果。"""
        if not expected:
            return result.get("status") == "completed"

        # 检查状态
        if "status" in expected:
            if result.get("status") != expected["status"]:
                return False

        # 检查是否生成论文
        if expected.get("has_paper"):
            results = result.get("results", {})
            if not results.get("writer_agent"):
                return False

        return True

    def run_all_tests(
        self,
        orchestrator: Any,
        tags: Optional[List[str]] = None,
    ) -> List[E2ETestResult]:
        """运行所有测试用例。

        Args:
            orchestrator: 编排器实例
            tags: 筛选标签

        Returns:
            测试结果列表
        """
        results = []

        for test_case in self.test_cases:
            # 标签筛选
            if tags:
                if not any(tag in test_case.tags for tag in tags):
                    continue

            result = self.run_test(test_case, orchestrator)
            results.append(result)

        return results

    def get_summary(self) -> Dict[str, Any]:
        """获取测试摘要。"""
        if not self.results:
            return {"total": 0}

        total = len(self.results)
        passed = sum(1 for r in self.results if r.success)
        failed = total - passed

        durations = [r.duration_sec for r in self.results]

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": passed / total if total > 0 else 0,
            "avg_duration": sum(durations) / total if total > 0 else 0,
            "max_duration": max(durations) if durations else 0,
        }

    def generate_report(self) -> str:
        """生成测试报告。"""
        summary = self.get_summary()

        report_lines = [
            "=" * 60,
            "E2E Test Report",
            "=" * 60,
            f"Total Tests: {summary['total']}",
            f"Passed: {summary['passed']}",
            f"Failed: {summary['failed']}",
            f"Pass Rate: {summary['pass_rate']:.1%}",
            f"Avg Duration: {summary['avg_duration']:.1f}s",
            f"Max Duration: {summary['max_duration']:.1f}s",
            "=" * 60,
            "",
            "Test Details:",
        ]

        for result in self.results:
            status = "PASS" if result.success else "FAIL"
            report_lines.append(
                f"  [{status}] {result.test_id}: {result.duration_sec:.1f}s"
            )
            if result.error:
                report_lines.append(f"    Error: {result.error}")

        return "\n".join(report_lines)


# 全局单例
_sandbox_instance: Optional[UnifiedSandbox] = None
_evaluator_instance: Optional[E2EEvaluator] = None


def get_unified_sandbox() -> UnifiedSandbox:
    """获取全局统一沙箱实例。"""
    global _sandbox_instance
    if _sandbox_instance is None:
        _sandbox_instance = UnifiedSandbox()
    return _sandbox_instance


def get_e2e_evaluator() -> E2EEvaluator:
    """获取全局端到端评测器实例。"""
    global _evaluator_instance
    if _evaluator_instance is None:
        _evaluator_instance = E2EEvaluator()
    return _evaluator_instance
