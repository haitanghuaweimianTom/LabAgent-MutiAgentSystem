"""代码执行沙箱 —— 在本地 subprocess 上叠加多层安全防护。

设计目标：
- 限制代码只能读写项目输出目录内的文件
- 拦截危险调用（os.system、subprocess、eval、exec 等）
- 设置运行超时和内存上限
- 提供清晰的返回结果（stdout/stderr/returncode/safety_violations）

注意：本项目没有 Docker 基础设施，沙箱依赖操作系统级限制（timeout、rlimit）。
"""
from __future__ import annotations

import logging
import os
import re
import resource
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 默认危险代码模式（简单静态扫描）
DEFAULT_DANGEROUS_PATTERNS: List[Dict[str, Any]] = [
    {"pattern": re.compile(r"\bos\.system\s*\("), "reason": "os.system 调用"},
    {"pattern": re.compile(r"\bos\.popen\s*\("), "reason": "os.popen 调用"},
    {"pattern": re.compile(r"\bsubprocess\.call\s*\("), "reason": "subprocess.call 调用"},
    {"pattern": re.compile(r"\bsubprocess\.run\s*\("), "reason": "subprocess.run 调用"},
    {"pattern": re.compile(r"\bsubprocess\.Popen\s*\("), "reason": "subprocess.Popen 调用"},
    {"pattern": re.compile(r"\beval\s*\("), "reason": "eval 调用"},
    {"pattern": re.compile(r"\bexec\s*\("), "reason": "exec 调用"},
    {"pattern": re.compile(r"\bcompile\s*\("), "reason": "compile 调用"},
    {"pattern": re.compile(r"\b__import__\s*\("), "reason": "__import__ 调用"},
    {"pattern": re.compile(r"\bimportlib"), "reason": "importlib 动态导入"},
    {"pattern": re.compile(r"\bshutil\.rmtree\s*\("), "reason": "shutil.rmtree 递归删除"},
    {"pattern": re.compile(r"\bopen\s*\([^)]*['\"]\s*\+\s*['\"][^)]*\)"), "reason": "可疑字符串拼接路径"},
]

# 默认允许的命令前缀（仅用于 run_command 模式）
DEFAULT_ALLOWED_COMMAND_PREFIXES = [
    "python", "python3", "pytest", "pip", "conda", "Rscript", "bash", "sh"
]


@dataclass
class SandboxResult:
    """沙箱执行结果。"""

    success: bool = False
    returncode: int = -1
    stdout: str = ""
    stderr: str = ""
    safety_violations: List[str] = field(default_factory=list)
    timeout_reached: bool = False
    killed_by_sandbox: bool = False
    duration_sec: float = 0.0
    command: List[str] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "returncode": self.returncode,
            "stdout": self.stdout[:5000] if self.stdout else "",
            "stderr": self.stderr[:5000] if self.stderr else "",
            "safety_violations": self.safety_violations,
            "timeout_reached": self.timeout_reached,
            "killed_by_sandbox": self.killed_by_sandbox,
            "duration_sec": self.duration_sec,
            "command": self.command,
            "message": self.message,
        }


@dataclass
class SandboxConfig:
    """沙箱配置。"""

    max_runtime_seconds: int = 3600
    max_memory_mb: int = 8192
    allowed_paths: List[Path] = field(default_factory=list)
    network_allowed: bool = True
    static_analysis_enabled: bool = True
    allowed_command_prefixes: List[str] = field(default_factory=lambda: DEFAULT_ALLOWED_COMMAND_PREFIXES.copy())

    def __post_init__(self):
        # 统一转为绝对 Path
        self.allowed_paths = [Path(p).expanduser().resolve() for p in self.allowed_paths if p]


class CodeSandbox:
    """轻量级本地代码执行沙箱。

    两种使用模式：
    1. ``run_file(python_file, args)``: 执行单个 Python 脚本。
    2. ``run_command(command, cwd)``: 执行外部命令（会做前缀白名单校验）。
    """

    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def run_file(
        self,
        python_file: Path,
        args: Optional[List[str]] = None,
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> SandboxResult:
        """执行单个 Python 文件。"""
        script = Path(python_file).expanduser().resolve()
        if not script.exists():
            return SandboxResult(
                success=False,
                returncode=-1,
                message=f"脚本不存在: {script}",
            )

        # 静态代码扫描
        violations: List[str] = []
        if self.config.static_analysis_enabled:
            violations = self._scan_code(script)
            if violations:
                logger.warning(f"[CodeSandbox] 静态扫描发现 {len(violations)} 处风险: {violations}")
                # 有安全违规时直接拒绝，不执行
                return SandboxResult(
                    success=False,
                    returncode=-1,
                    safety_violations=violations,
                    message="静态安全扫描未通过，拒绝执行",
                )

        # 校验脚本路径是否在允许范围内
        if not self._is_path_allowed(script):
            return SandboxResult(
                success=False,
                returncode=-1,
                message=f"脚本不在允许路径内: {script}",
            )

        python_exe = shutil.which("python3") or shutil.which("python") or "python"
        command = [python_exe, "-X", "utf8", str(script)] + (args or [])
        return self._run_subprocess(command, cwd=cwd or script.parent, env=env)

    def run_command(
        self,
        command: List[str],
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> SandboxResult:
        """执行外部命令（仅允许白名单前缀）。"""
        if not command:
            return SandboxResult(success=False, message="命令为空")

        # 命令前缀校验
        first = command[0]
        basename = os.path.basename(first)
        allowed = any(basename.startswith(prefix) or first.endswith(prefix) for prefix in self.config.allowed_command_prefixes)
        if not allowed:
            return SandboxResult(
                success=False,
                message=f"命令前缀不在白名单: {first}",
            )

        # 校验工作目录
        if cwd and not self._is_path_allowed(cwd):
            return SandboxResult(
                success=False,
                message=f"工作目录不在允许路径内: {cwd}",
            )

        return self._run_subprocess(command, cwd=cwd, env=env)

    # ------------------------------------------------------------------
    # 安全扫描
    # ------------------------------------------------------------------

    @classmethod
    def scan_code_text(cls, code: str, extra_patterns: Optional[List[Dict[str, Any]]] = None) -> List[str]:
        """扫描代码文本，返回违规说明列表。"""
        patterns = DEFAULT_DANGEROUS_PATTERNS + (extra_patterns or [])
        violations: List[str] = []
        for i, line in enumerate(code.splitlines(), 1):
            for item in patterns:
                if item["pattern"].search(line):
                    violations.append(f"第 {i} 行: {item['reason']}")
                    break
        return violations

    def _scan_code(self, script: Path) -> List[str]:
        """扫描脚本文件。"""
        try:
            code = script.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return [f"无法读取脚本进行安全扫描: {e}"]
        return self.scan_code_text(code)

    # ------------------------------------------------------------------
    # 路径控制
    # ------------------------------------------------------------------

    def _is_path_allowed(self, path: Path) -> bool:
        """检查路径是否在白名单内。"""
        if not self.config.allowed_paths:
            return True
        target = Path(path).expanduser().resolve()
        for allowed in self.config.allowed_paths:
            try:
                target.relative_to(allowed)
                return True
            except ValueError:
                continue
        return False

    # ------------------------------------------------------------------
    # 执行核心
    # ------------------------------------------------------------------

    def _run_subprocess(
        self,
        command: List[str],
        cwd: Optional[Path],
        env: Optional[Dict[str, str]],
    ) -> SandboxResult:
        """运行子进程并施加资源限制。"""
        work_dir = Path(cwd).expanduser().resolve() if cwd else Path(tempfile.gettempdir())
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        # 若不允许多网络，可设置 HTTP_PROXY 等（此处仅作占位，实际阻断需 iptables/nftables）
        if not self.config.network_allowed:
            merged_env["HTTP_PROXY"] = "http://127.0.0.1:0"
            merged_env["HTTPS_PROXY"] = "http://127.0.0.1:0"

        max_bytes = self.config.max_memory_mb * 1024 * 1024

        def preexec_fn():
            """子进程启动前设置资源限制（仅 POSIX）。"""
            try:
                # 虚拟内存上限
                resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))
                # CPU 时间上限（留一定余量，超时由 subprocess 控制）
                resource.setrlimit(
                    resource.RLIMIT_CPU,
                    (self.config.max_runtime_seconds + 60, self.config.max_runtime_seconds + 60),
                )
            except Exception:
                pass

        start = os.times()[0]
        try:
            kwargs = {
                "capture_output": True,
                "text": True,
                "cwd": str(work_dir),
                "env": merged_env,
                "timeout": self.config.max_runtime_seconds,
            }
            if os.name == "posix":
                kwargs["preexec_fn"] = preexec_fn

            logger.info(f"[CodeSandbox] 执行: {' '.join(command)}")
            proc = subprocess.run(command, **kwargs)
            duration = os.times()[0] - start

            return SandboxResult(
                success=proc.returncode == 0,
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                duration_sec=round(duration, 2),
                command=command,
                message="执行完成" if proc.returncode == 0 else f"进程退出码 {proc.returncode}",
            )
        except subprocess.TimeoutExpired as e:
            duration = os.times()[0] - start
            logger.error(f"[CodeSandbox] 执行超时 ({self.config.max_runtime_seconds}s)")
            return SandboxResult(
                success=False,
                returncode=-2,
                stdout=e.stdout or "",
                stderr=e.stderr or "",
                timeout_reached=True,
                killed_by_sandbox=True,
                duration_sec=round(duration, 2),
                command=command,
                message=f"执行超时（{self.config.max_runtime_seconds}s）",
            )
        except Exception as e:
            duration = os.times()[0] - start
            logger.error(f"[CodeSandbox] 执行异常: {e}")
            return SandboxResult(
                success=False,
                returncode=-3,
                duration_sec=round(duration, 2),
                command=command,
                message=f"执行异常: {e}",
            )


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------


def get_code_sandbox(
    allowed_paths: Optional[List[Path]] = None,
    max_runtime_seconds: int = 3600,
    max_memory_mb: int = 8192,
) -> CodeSandbox:
    """获取一个配置好的沙箱实例。"""
    config = SandboxConfig(
        allowed_paths=allowed_paths or [],
        max_runtime_seconds=max_runtime_seconds,
        max_memory_mb=max_memory_mb,
    )
    return CodeSandbox(config=config)
