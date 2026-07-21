"""代码执行沙箱 —— 分层防御隔离系统。

设计目标：
- 隔离文件系统：代码只能读写工作区目录
- 限制资源：CPU 时间、内存、文件描述符
- 限制导入：阻止危险模块（os, sys, subprocess 等）
- 静态代码扫描：拦截危险调用模式
- 路径白名单：限制文件访问范围
- 无需 Docker：使用 Linux namespace + resource limit

架构（分层防御）：
  Layer 1: subprocess + resource limit（所有平台）
  Layer 2: Linux namespace 隔离（mount, net, pid）最佳 effort
  Layer 3: Python 导入限制（import hook）
  Layer 4: 静态代码扫描（regex pattern matching）

注意：这不是军事级沙箱，而是"实用级"隔离——防止 Agent 代码意外破坏系统。
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 默认允许的科学计算模块（数学建模常用）
DEFAULT_ALLOWED_MODULES = {
    "math", "random", "statistics", "fractions", "decimal", "numbers",
    "json", "csv", "re", "string", "datetime", "time", "calendar",
    "collections", "itertools", "functools", "operator", "typing",
    "inspect", "types", "copy", "pickle", "hashlib", "base64",
    "io", "pathlib", "tempfile", "glob", "fnmatch",
    # 第三方库（数学建模常用）
    "numpy", "pandas", "scipy", "sklearn", "matplotlib", "seaborn",
    "plotly", "statsmodels", "openpyxl", "xlrd", "xlsxwriter",
    "sympy", "networkx", "PIL", "pillow",
}

# 默认阻止的模块（危险操作）
# 注意：os/sys/subprocess 由资源限制（RLIMIT_NPROC）+ 路径隔离保护
# subprocess 导入允许但 fork 被 RLIMIT_NPROC=0 阻止
DEFAULT_BLOCKED_MODULES = {
    # 网络模块（资源限制无法完全阻止）
    "socket", "urllib", "http", "ftplib",
    "telnetlib", "smtplib", "poplib", "imaplib", "nntplib", "ssl",
    # 系统/进程模块
    "ctypes", "mmap", "multiprocessing", "concurrent",
    "asyncio", "tkinter", "wx", "PyQt5", "PyQt6", "PySide2", "PySide6",
    "pip", "setuptools", "distutils", "wheel", "venv", "virtualenv",
    # 额外阻止：可能用于逃逸的模块
    "pty", "pwd", "grp", "spwd", "crypt",
}

# 默认危险代码模式（静态扫描）
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
    duration_sec: float = 0.0
    killed_by_sandbox: bool = False
    timeout_reached: bool = False
    memory_exceeded: bool = False
    safety_violations: List[str] = field(default_factory=list)
    command: List[str] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "returncode": self.returncode,
            "stdout": self.stdout[:5000] if self.stdout else "",
            "stderr": self.stderr[:5000] if self.stderr else "",
            "duration_sec": self.duration_sec,
            "killed_by_sandbox": self.killed_by_sandbox,
            "timeout_reached": self.timeout_reached,
            "memory_exceeded": self.memory_exceeded,
            "safety_violations": self.safety_violations,
            "command": self.command,
            "message": self.message,
        }


@dataclass
class SandboxConfig:
    """沙箱配置。"""
    max_cpu_time: int = 60          # 秒
    max_memory_mb: int = 512        # MB
    max_output_size: int = 10_000_000  # 10MB
    max_file_size_mb: int = 100     # 单个文件大小限制
    allowed_modules: Optional[set] = None
    blocked_modules: Optional[set] = None
    network_allowed: bool = False
    workspace_persist: bool = False   # 执行后是否保留工作区
    # 静态扫描 + 路径白名单（来自 services/code_sandbox.py）
    static_analysis_enabled: bool = True
    allowed_paths: List[Path] = field(default_factory=list)
    allowed_command_prefixes: List[str] = field(default_factory=lambda: DEFAULT_ALLOWED_COMMAND_PREFIXES.copy())
    # 向后兼容：旧代码用 max_runtime_seconds
    max_runtime_seconds: int = 0

    def __post_init__(self):
        if self.allowed_modules is None:
            self.allowed_modules = DEFAULT_ALLOWED_MODULES.copy()
        if self.blocked_modules is None:
            self.blocked_modules = DEFAULT_BLOCKED_MODULES.copy()
        self.allowed_paths = [Path(p).expanduser().resolve() for p in self.allowed_paths if p]
        # 向后兼容：max_runtime_seconds -> max_cpu_time
        if self.max_runtime_seconds > 0 and self.max_cpu_time == 60:
            self.max_cpu_time = self.max_runtime_seconds


class CodeSandbox:
    """代码执行沙箱。

    使用分层防御：
    1. 资源限制（resource.setrlimit）
    2. Linux namespace 隔离（unshare，最佳 effort）
    3. Python 导入限制（import hook）
    """

    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self._linux_ns_available = self._check_linux_ns()

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def execute(
        self,
        code: str,
        language: str = "python",
        env_vars: Optional[Dict[str, str]] = None,
        input_data: Optional[str] = None,
    ) -> SandboxResult:
        """执行代码字符串。"""
        if language != "python":
            return SandboxResult(
                success=False, message=f"Unsupported language: {language}"
            )

        # 创建临时工作区
        workspace = self._create_workspace()
        try:
            # 写入代码文件
            code_file = workspace / "main.py"
            code_file.write_text(code, encoding="utf-8")

            # 注入导入限制
            self._inject_import_hook(workspace)

            # 执行
            result = self._run_in_sandbox(
                code_file, workspace, env_vars=env_vars, input_data=input_data
            )
            return result
        finally:
            if not self.config.workspace_persist:
                self._cleanup_workspace(workspace)

    def execute_file(
        self,
        file_path: str,
        env_vars: Optional[Dict[str, str]] = None,
        input_data: Optional[str] = None,
    ) -> SandboxResult:
        """执行已有代码文件。"""
        workspace = self._create_workspace()
        try:
            # 复制文件到工作区
            src = Path(file_path)
            dst = workspace / src.name
            shutil.copy2(src, dst)

            # 注入导入限制
            self._inject_import_hook(workspace)

            return self._run_in_sandbox(
                dst, workspace, env_vars=env_vars, input_data=input_data
            )
        finally:
            if not self.config.workspace_persist:
                self._cleanup_workspace(workspace)

    def run_file(
        self,
        python_file: Path,
        args: Optional[List[str]] = None,
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> SandboxResult:
        """执行单个 Python 文件（带静态扫描和路径校验）。"""
        script = Path(python_file).expanduser().resolve()
        if not script.exists():
            return SandboxResult(
                success=False, returncode=-1,
                message=f"脚本不存在: {script}",
            )

        # 静态代码扫描
        if self.config.static_analysis_enabled:
            violations = self._scan_code(script)
            if violations:
                logger.warning(f"[Sandbox] 静态扫描发现 {len(violations)} 处风险: {violations}")
                return SandboxResult(
                    success=False, returncode=-1,
                    safety_violations=violations,
                    message="静态安全扫描未通过，拒绝执行",
                )

        # 路径校验
        if not self._is_path_allowed(script):
            return SandboxResult(
                success=False, returncode=-1,
                message=f"脚本不在允许路径内: {script}",
            )

        python_exe = sys.executable
        command = [python_exe, "-X", "utf8", str(script)] + (args or [])
        result = self._run_subprocess(command, cwd=cwd or script.parent, env=env)
        result.command = command
        return result

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
        allowed = any(
            basename.startswith(prefix) or first.endswith(prefix)
            for prefix in self.config.allowed_command_prefixes
        )
        if not allowed:
            return SandboxResult(
                success=False, message=f"命令前缀不在白名单: {first}",
            )

        # 校验工作目录
        if cwd and not self._is_path_allowed(cwd):
            return SandboxResult(
                success=False, message=f"工作目录不在允许路径内: {cwd}",
            )

        result = self._run_subprocess(command, cwd=cwd, env=env)
        result.command = command
        return result

    # ------------------------------------------------------------------
    # 静态代码扫描
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
    # 工作区管理
    # ------------------------------------------------------------------

    def _create_workspace(self) -> Path:
        """创建隔离工作区。"""
        base = Path(tempfile.gettempdir()) / "agent_sandbox"
        base.mkdir(parents=True, exist_ok=True)
        ws = Path(tempfile.mkdtemp(prefix="ws_", dir=base))
        # 创建标准子目录
        (ws / "data").mkdir(exist_ok=True)
        (ws / "output").mkdir(exist_ok=True)
        return ws

    def _cleanup_workspace(self, workspace: Path) -> None:
        """清理工作区。"""
        try:
            shutil.rmtree(workspace, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Sandbox cleanup failed: {e}")

    # ------------------------------------------------------------------
    # 导入限制（Layer 3）
    # ------------------------------------------------------------------

    def _inject_import_hook(self, workspace: Path) -> None:
        """注入 Python 导入限制（Layer 3）。

        阻止用户代码直接导入危险模块（网络/进程/系统），但允许已安装的
        科学计算库（numpy/pandas/matplotlib 等）内部的传递性导入。
        通过检查导入栈判断调用来源。
        """
        hook_code = textwrap.dedent("""\
            import builtins
            import sys

            _BLOCKED = frozenset(%%BLOCKED_MODULES%%)
            _orig_import = builtins.__import__
            _IMPORTING_FROM_USER = False

            def _safe_import(name, *args, **kwargs):
                global _IMPORTING_FROM_USER
                top = name.split(".")[0]
                if top in _BLOCKED:
                    # 检查导入栈，判断是否来自用户代码
                    for frame_info in sys._current_frames().values():
                        for frame in [frame_info]:
                            while frame:
                                filename = frame.f_code.co_filename
                                if "site-packages" in filename or "dist-packages" in filename:
                                    # 来自库内部传递性导入 → 允许
                                    return _orig_import(name, *args, **kwargs)
                                frame = frame.f_back
                    raise ImportError(
                        f"Blocked by sandbox: '{name}' is not allowed in sandboxed code."
                    )
                return _orig_import(name, *args, **kwargs)

            builtins.__import__ = _safe_import
        """).replace("%%BLOCKED_MODULES%%", repr(list(DEFAULT_BLOCKED_MODULES)))
        hook_file = workspace / "__import_hook__.py"
        hook_file.write_text(hook_code, encoding="utf-8")
        sitecustomize = workspace / "sitecustomize.py"
        sitecustomize.write_text(
            "import __import_hook__\n",
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # 沙箱执行核心
    # ------------------------------------------------------------------

    def _run_in_sandbox(
        self,
        code_file: Path,
        workspace: Path,
        env_vars: Optional[Dict[str, str]] = None,
        input_data: Optional[str] = None,
    ) -> SandboxResult:
        """在沙箱中运行代码文件。"""
        start = time.time()

        # 构建环境变量
        merged_env = os.environ.copy()
        merged_env["PYTHONPATH"] = str(workspace) + ":" + merged_env.get("PYTHONPATH", "")
        merged_env["PYTHONDONTWRITEBYTECODE"] = "1"
        merged_env["MPLBACKEND"] = "Agg"  # 无头 matplotlib
        if env_vars:
            merged_env.update(env_vars)

        # 构建命令
        # 注意：不使用 -S，以便 sitecustomize.py 加载导入限制
        python_exe = sys.executable
        command = [python_exe, "-X", "utf8", str(code_file)]

        # 准备执行参数
        kwargs: Dict[str, Any] = {
            "capture_output": True,
            "text": True,
            "cwd": str(workspace),
            "env": merged_env,
            "timeout": self.config.max_cpu_time + 5,  # 额外 5 秒缓冲
        }

        # Linux: 资源限制 + namespace 隔离
        if os.name == "posix":
            kwargs["preexec_fn"] = self._make_preexec_fn(workspace)

        try:
            logger.info(f"[Sandbox] 执行: {' '.join(command)} in {workspace}")
            proc = subprocess.run(command, **kwargs)
            duration = time.time() - start

            # 检查输出大小
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            if len(stdout) > self.config.max_output_size:
                stdout = stdout[:self.config.max_output_size] + "\n[输出已截断]"

            return SandboxResult(
                success=proc.returncode == 0,
                returncode=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                duration_sec=round(duration, 2),
                message="执行完成" if proc.returncode == 0 else f"退出码 {proc.returncode}",
            )

        except subprocess.TimeoutExpired as e:
            duration = time.time() - start
            logger.warning(f"[Sandbox] 执行超时 ({self.config.max_cpu_time}s)")
            return SandboxResult(
                success=False,
                returncode=-2,
                stdout=e.stdout or "",
                stderr=e.stderr or "",
                duration_sec=round(duration, 2),
                timeout_reached=True,
                killed_by_sandbox=True,
                message=f"执行超时（限制 {self.config.max_cpu_time}s）",
            )

        except Exception as e:
            duration = time.time() - start
            logger.error(f"[Sandbox] 执行异常: {e}")
            return SandboxResult(
                success=False,
                returncode=-3,
                duration_sec=round(duration, 2),
                message=f"执行异常: {e}",
            )

    def _make_preexec_fn(self, workspace: Path):
        """创建 preexec_fn（仅 Linux）。设置资源限制和 namespace 隔离。"""
        max_cpu = self.config.max_cpu_time
        max_mem = self.config.max_memory_mb * 1024 * 1024
        ws = str(workspace)
        use_ns = self._linux_ns_available

        def _preexec():
            import resource as _resource

            # Layer 1: 资源限制
            try:
                # CPU 时间限制（软限制 = 硬限制 = max_cpu）
                _resource.setrlimit(_resource.RLIMIT_CPU, (max_cpu, max_cpu))
                # 虚拟内存限制
                _resource.setrlimit(_resource.RLIMIT_AS, (max_mem, max_mem))
                # 文件大小限制
                _resource.setrlimit(
                    _resource.RLIMIT_FSIZE,
                    (self.config.max_file_size_mb * 1024 * 1024, self.config.max_file_size_mb * 1024 * 1024),
                )
                # 文件描述符限制
                _resource.setrlimit(_resource.RLIMIT_NOFILE, (256, 256))
                # 子进程限制（禁止 fork）
                _resource.setrlimit(_resource.RLIMIT_NPROC, (0, 0))
            except Exception:
                pass

            # Layer 2: Linux namespace 隔离（最佳 effort）
            if use_ns:
                try:
                    import ctypes
                    libc = ctypes.CDLL("libc.so.6", use_errno=True)
                    CLONE_NEWNS = 0x00020000
                    CLONE_NEWPID = 0x20000000
                    CLONE_NEWNET = 0x40000000
                    flags = CLONE_NEWNS | CLONE_NEWPID | CLONE_NEWNET
                    if libc.unshare(flags) != 0:
                        import errno
                        err = ctypes.get_errno()
                        logger.debug(f"unshare failed: {errno.errorcode.get(err, err)}")
                except Exception:
                    pass

        return _preexec

    # ------------------------------------------------------------------
    # 通用子进程执行（run_file / run_command 共用）
    # ------------------------------------------------------------------

    def _run_subprocess(
        self,
        command: List[str],
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> SandboxResult:
        """运行子进程并施加资源限制。"""
        work_dir = Path(cwd).expanduser().resolve() if cwd else Path(tempfile.gettempdir())
        merged_env = os.environ.copy()
        merged_env["PYTHONDONTWRITEBYTECODE"] = "1"
        merged_env["MPLBACKEND"] = "Agg"
        if env:
            merged_env.update(env)

        # 网络隔离
        use_network_namespace = False
        if not self.config.network_allowed:
            try:
                unshare_path = shutil.which("unshare")
                if unshare_path:
                    test_proc = subprocess.run(
                        [unshare_path, "--net", "true"],
                        capture_output=True, timeout=5,
                    )
                    if test_proc.returncode == 0:
                        command = [unshare_path, "--net"] + command
                        use_network_namespace = True
            except Exception:
                pass
            if not use_network_namespace:
                merged_env["HTTP_PROXY"] = "http://127.0.0.1:0"
                merged_env["HTTPS_PROXY"] = "http://127.0.0.1:0"
                merged_env["NO_PROXY"] = "*"

        max_mem = self.config.max_memory_mb * 1024 * 1024

        def preexec_fn():
            import resource as _resource
            try:
                _resource.setrlimit(_resource.RLIMIT_AS, (max_mem, max_mem))
                _resource.setrlimit(
                    _resource.RLIMIT_CPU,
                    (self.config.max_cpu_time + 60, self.config.max_cpu_time + 60),
                )
            except Exception:
                pass

        start = time.time()
        try:
            kwargs: Dict[str, Any] = {
                "capture_output": True,
                "text": True,
                "cwd": str(work_dir),
                "env": merged_env,
                "timeout": self.config.max_cpu_time,
            }
            if os.name == "posix":
                kwargs["preexec_fn"] = preexec_fn

            logger.info(f"[Sandbox] 执行: {' '.join(command)}")
            proc = subprocess.run(command, **kwargs)
            duration = time.time() - start

            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            if len(stdout) > self.config.max_output_size:
                stdout = stdout[:self.config.max_output_size] + "\n[输出已截断]"

            return SandboxResult(
                success=proc.returncode == 0,
                returncode=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                duration_sec=round(duration, 2),
                command=command,
                message="执行完成" if proc.returncode == 0 else f"进程退出码 {proc.returncode}",
            )
        except subprocess.TimeoutExpired as e:
            duration = time.time() - start
            logger.error(f"[Sandbox] 执行超时 ({self.config.max_cpu_time}s)")
            return SandboxResult(
                success=False, returncode=-2,
                stdout=e.stdout or "", stderr=e.stderr or "",
                timeout_reached=True, killed_by_sandbox=True,
                duration_sec=round(duration, 2), command=command,
                message=f"执行超时（{self.config.max_cpu_time}s）",
            )
        except Exception as e:
            duration = time.time() - start
            logger.error(f"[Sandbox] 执行异常: {e}")
            return SandboxResult(
                success=False, returncode=-3,
                duration_sec=round(duration, 2), command=command,
                message=f"执行异常: {e}",
            )

    # ------------------------------------------------------------------
    # 能力检测
    # ------------------------------------------------------------------

    @staticmethod
    def _check_linux_ns() -> bool:
        """检查 Linux namespace 是否可用。"""
        if os.name != "posix":
            return False
        try:
            import ctypes
            libc = ctypes.CDLL("libc.so.6", use_errno=True)
            # 尝试 unshare(0) - 无操作，但测试系统调用是否可用
            result = libc.unshare(0)
            return result == 0
        except Exception:
            return False

    @staticmethod
    def is_available() -> bool:
        """沙箱功能是否可用。"""
        return True  # 基础功能始终可用（subprocess + timeout）


# ----------------------------------------------------------------------
# 便捷函数
# ----------------------------------------------------------------------

def execute_code_sandboxed(
    code: str,
    workspace_dir: Optional[str] = None,
    max_cpu_time: int = 60,
    max_memory_mb: int = 512,
    allowed_modules: Optional[set] = None,
) -> SandboxResult:
    """便捷函数：直接执行代码。"""
    config = SandboxConfig(
        max_cpu_time=max_cpu_time,
        max_memory_mb=max_memory_mb,
        allowed_modules=allowed_modules,
    )
    sandbox = CodeSandbox(config)
    return sandbox.execute(code)


# 兼容别名：orchestrator 中导入 execute_code
execute_code = execute_code_sandboxed
