"""GPU 训练执行器 —— 统一封装 PyTorch 训练/推理生命周期。

目标：
- 检测 CUDA 可用性（torch.cuda.is_available()）
- 管理 GPU 资源（单卡/多卡、显存监控）
- 执行 PyTorch 训练脚本（subprocess，支持超时）
- 捕获训练日志、提取指标（loss、accuracy、F1 等）
- 保存模型检查点

设计原则：
- 纯本地执行，不依赖外部 API
- GPU 不可用时提供清晰的降级路径（CPU 回退 + 明确日志）
- 与 environment_manager.py 风格保持一致（dataclass + 异常捕获 + logger）
"""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 检查点默认保存目录
CHECKPOINT_BASE_DIR = Path(__file__).parent.parent.parent / "data" / "checkpoints"

# OOM 防护默认阈值（显存使用超过此比例触发预警）
DEFAULT_VRAM_WARN_THRESHOLD = 0.85  # 85%
DEFAULT_VRAM_KILL_THRESHOLD = 0.95  # 95%

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class GPUInfo:
    """单张 GPU 信息。"""

    id: int
    name: str
    total_memory_mb: float
    free_memory_mb: float
    used_memory_mb: float
    utilization_percent: float
    temperature_c: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VRAMMonitorConfig:
    """显存监控配置。"""
    warn_threshold: float = DEFAULT_VRAM_WARN_THRESHOLD
    kill_threshold: float = DEFAULT_VRAM_KILL_THRESHOLD
    check_interval_sec: float = 2.0
    enabled: bool = True


@dataclass
class TrainingMetrics:
    """从训练日志中提取的指标。"""

    loss: Optional[float] = None
    accuracy: Optional[float] = None
    f1: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    epoch: Optional[int] = None
    step: Optional[int] = None
    val_loss: Optional[float] = None
    val_accuracy: Optional[float] = None
    custom: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CheckpointInfo:
    """检查点信息。"""
    path: str
    epoch: int
    step: int
    metric_value: Optional[float] = None
    metric_name: str = ""
    saved_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "epoch": self.epoch,
            "step": self.step,
            "metric_value": self.metric_value,
            "metric_name": self.metric_name,
            "saved_at": self.saved_at,
        }


@dataclass
class TrainingResult:
    """训练执行结果。"""

    success: bool
    stdout: str
    stderr: str
    returncode: int
    metrics: TrainingMetrics
    checkpoint_path: Optional[str] = None
    duration_sec: float = 0.0
    gpu_used: bool = False
    message: str = ""
    checkpoints: List[CheckpointInfo] = field(default_factory=list)
    resumed_from: Optional[str] = None  # 从哪个检查点恢复

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "stdout": self.stdout[:5000] if self.stdout else "",
            "stderr": self.stderr[:3000] if self.stderr else "",
            "returncode": self.returncode,
            "metrics": self.metrics.to_dict(),
            "checkpoint_path": self.checkpoint_path,
            "duration_sec": self.duration_sec,
            "gpu_used": self.gpu_used,
            "message": self.message,
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "resumed_from": self.resumed_from,
        }


@dataclass
class InferenceResult:
    """推理执行结果。"""

    success: bool
    stdout: str
    stderr: str
    returncode: int
    predictions: Optional[List[Any]] = None
    duration_sec: float = 0.0
    gpu_used: bool = False
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# GPU 资源管理
# ---------------------------------------------------------------------------


class GPUResourceManager:
    """GPU 资源管理：显存监控、利用率查询。"""

    def __init__(self):
        self._torch_available = self._check_torch()

    def _check_torch(self) -> bool:
        try:
            import torch  # noqa: F401
            return True
        except ImportError:
            logger.warning("PyTorch not installed; GPU features disabled.")
            return False

    def is_available(self) -> bool:
        """CUDA 是否可用。"""
        if not self._torch_available:
            return False
        try:
            import torch
            return torch.cuda.is_available()
        except Exception as e:
            logger.warning(f"torch.cuda.is_available() failed: {e}")
            return False

    def get_gpu_info(self) -> List[GPUInfo]:
        """获取所有 GPU 信息。"""
        if not self.is_available():
            return []
        try:
            import torch
            gpus: List[GPUInfo] = []
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                total = props.total_memory / (1024 * 1024)
                reserved = torch.cuda.memory_reserved(i) / (1024 * 1024)
                allocated = torch.cuda.memory_allocated(i) / (1024 * 1024)
                free = total - reserved
                util = self._get_utilization(i)
                temp = self._get_temperature(i)
                gpus.append(
                    GPUInfo(
                        id=i,
                        name=props.name,
                        total_memory_mb=round(total, 2),
                        free_memory_mb=round(free, 2),
                        used_memory_mb=round(allocated, 2),
                        utilization_percent=util,
                        temperature_c=temp,
                    )
                )
            return gpus
        except Exception as e:
            logger.warning(f"Failed to get GPU info: {e}")
            return []

    def _get_utilization(self, gpu_id: int) -> float:
        """通过 nvidia-smi 获取 GPU 利用率。"""
        if not shutil.which("nvidia-smi"):
            return 0.0
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits", "-i", str(gpu_id)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception:
            pass
        return 0.0

    def _get_temperature(self, gpu_id: int) -> Optional[float]:
        """通过 nvidia-smi 获取 GPU 温度。"""
        if not shutil.which("nvidia-smi"):
            return None
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits", "-i", str(gpu_id)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception:
            pass
        return None

    def get_device_name(self, gpu_id: int) -> str:
        """获取指定 GPU 名称。"""
        if not self._torch_available:
            return "cpu"
        try:
            import torch
            if gpu_id < torch.cuda.device_count():
                return torch.cuda.get_device_name(gpu_id)
        except Exception as e:
            logger.warning(f"get_device_name failed: {e}")
        return "cpu"

    def get_best_gpu(self) -> int:
        """返回显存最空闲的 GPU ID；无 GPU 返回 -1。"""
        gpus = self.get_gpu_info()
        if not gpus:
            return -1
        best = max(gpus, key=lambda g: g.free_memory_mb)
        return best.id

    def estimate_max_batch_size(
        self,
        gpu_id: int,
        model_memory_mb: float,
        per_sample_memory_mb: float,
        safety_factor: float = 0.8,
    ) -> int:
        """估算给定 GPU 上可运行的最大 batch size。

        Args:
            gpu_id: GPU ID
            model_memory_mb: 模型本身占用的显存（MB）
            per_sample_memory_mb: 每个样本前向+反向占用的显存（MB）
            safety_factor: 安全因子（留余量防止 OOM）

        Returns:
            建议的最大 batch size
        """
        gpus = self.get_gpu_info()
        gpu = next((g for g in gpus if g.id == gpu_id), None)
        if not gpu:
            return 1  # 无 GPU，回退到 CPU 模式
        available_mb = gpu.free_memory_mb * safety_factor
        # 减去模型本身占用的显存
        available_for_batch = max(0, available_mb - model_memory_mb)
        if available_for_batch <= 0:
            return 1
        max_batch = int(available_for_batch / per_sample_memory_mb)
        return max(1, max_batch)


# ---------------------------------------------------------------------------
# 显存监控器（OOM 防护）
# ---------------------------------------------------------------------------


class VRAMMonitor:
    """显存监控线程：定期检查 GPU 显存使用，超过阈值时发出预警或终止训练。"""

    def __init__(
        self,
        gpu_id: int,
        config: Optional[VRAMMonitorConfig] = None,
    ):
        self.gpu_id = gpu_id
        self.config = config or VRAMMonitorConfig()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._peak_usage_mb = 0.0
        self._warned = False
        self._killed = False
        self._kill_reason = ""

    def start(self) -> None:
        """启动监控线程。"""
        if not self.config.enabled:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info(f"[VRAMMonitor] 启动监控 GPU {self.gpu_id} (warn={self.config.warn_threshold:.0%}, kill={self.config.kill_threshold:.0%})")

    def stop(self) -> None:
        """停止监控线程。"""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _monitor_loop(self) -> None:
        """监控循环。"""
        try:
            import torch
        except ImportError:
            return

        while not self._stop_event.is_set():
            try:
                if not torch.cuda.is_available():
                    break

                total = torch.cuda.get_device_properties(self.gpu_id).total_memory / (1024 * 1024)
                allocated = torch.cuda.memory_allocated(self.gpu_id) / (1024 * 1024)
                reserved = torch.cuda.memory_reserved(self.gpu_id) / (1024 * 1024)
                usage_ratio = allocated / total

                self._peak_usage_mb = max(self._peak_usage_mb, allocated)

                # 预警阈值
                if usage_ratio >= self.config.warn_threshold and not self._warned:
                    self._warned = True
                    logger.warning(
                        f"[VRAMMonitor] GPU {self.gpu_id} 显存预警: "
                        f"{allocated:.0f}/{total:.0f} MB ({usage_ratio:.1%})"
                    )

                # 终止阈值
                if usage_ratio >= self.config.kill_threshold and not self._killed:
                    self._killed = True
                    self._kill_reason = (
                        f"GPU {self.gpu_id} 显存超过 {self.config.kill_threshold:.0%} "
                        f"({allocated:.0f}/{total:.0f} MB)"
                    )
                    logger.error(f"[VRAMMonitor] {self._kill_reason}")
                    # 触发 OOM 保护：清空 GPU 缓存
                    torch.cuda.empty_cache()

            except Exception as e:
                logger.debug(f"[VRAMMonitor] 监控异常: {e}")

            self._stop_event.wait(self.config.check_interval_sec)

    @property
    def was_killed(self) -> bool:
        return self._killed

    @property
    def kill_reason(self) -> str:
        return self._kill_reason

    @property
    def peak_usage_mb(self) -> float:
        return self._peak_usage_mb


# ---------------------------------------------------------------------------
# 检查点管理器
# ---------------------------------------------------------------------------


class CheckpointManager:
    """训练检查点管理：保存、恢复、自动清理。"""

    def __init__(self, output_dir: Path, max_keep: int = 3):
        self.output_dir = output_dir
        self.max_keep = max_keep
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint_meta(self, checkpoints: List[CheckpointInfo]) -> None:
        """保存检查点索引文件。"""
        meta_path = self.output_dir / "checkpoints.json"
        meta_path.write_text(
            json.dumps([c.to_dict() for c in checkpoints], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def load_checkpoint_meta(self) -> List[CheckpointInfo]:
        """加载检查点索引。"""
        meta_path = self.output_dir / "checkpoints.json"
        if not meta_path.exists():
            return []
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            return [
                CheckpointInfo(
                    path=c["path"],
                    epoch=c.get("epoch", 0),
                    step=c.get("step", 0),
                    metric_value=c.get("metric_value"),
                    metric_name=c.get("metric_name", ""),
                    saved_at=c.get("saved_at", ""),
                )
                for c in data
            ]
        except Exception as e:
            logger.warning(f"[CheckpointManager] 加载检查点索引失败: {e}")
            return []

    def find_latest_checkpoint(self) -> Optional[CheckpointInfo]:
        """找到最新的检查点。"""
        checkpoints = self.load_checkpoint_meta()
        if not checkpoints:
            # 回退到文件扫描
            candidates = (
                list(self.output_dir.rglob("*.pt"))
                + list(self.output_dir.rglob("*.pth"))
                + list(self.output_dir.rglob("*.ckpt"))
            )
            if not candidates:
                return None
            candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            latest = candidates[0]
            return CheckpointInfo(
                path=str(latest),
                epoch=0,
                step=0,
                saved_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            )
        # 按 epoch 排序取最新
        checkpoints.sort(key=lambda c: (c.epoch, c.step), reverse=True)
        return checkpoints[0]

    def cleanup_old_checkpoints(self) -> None:
        """清理旧检查点，只保留最新的 max_keep 个。"""
        checkpoints = self.load_checkpoint_meta()
        if len(checkpoints) <= self.max_keep:
            return
        checkpoints.sort(key=lambda c: (c.epoch, c.step), reverse=True)
        to_remove = checkpoints[self.max_keep:]
        for ckpt in to_remove:
            try:
                Path(ckpt.path).unlink(missing_ok=True)
                logger.info(f"[CheckpointManager] 清理旧检查点: {ckpt.path}")
            except Exception as e:
                logger.warning(f"[CheckpointManager] 清理检查点失败: {e}")
        # 更新索引
        self.save_checkpoint_meta(checkpoints[:self.max_keep])


# ---------------------------------------------------------------------------
# 日志解析器
# ---------------------------------------------------------------------------


class TrainingLogParser:
    """从训练 stdout/stderr 中提取指标。"""

    # 常见指标正则
    PATTERNS = {
        "loss": re.compile(r"loss[:\s=]+([\d.]+(?:e[+-]?\d+)?)", re.IGNORECASE),
        "val_loss": re.compile(r"val(?:idation)?[_\s]?loss[:\s=]+([\d.]+(?:e[+-]?\d+)?)", re.IGNORECASE),
        "accuracy": re.compile(r"acc(?:uracy)?[:\s=]+([\d.]+)", re.IGNORECASE),
        "val_accuracy": re.compile(r"val(?:idation)?[_\s]?acc(?:uracy)?[:\s=]+([\d.]+)", re.IGNORECASE),
        "f1": re.compile(r"f1[_\s-]?(?:score)?[:\s=]+([\d.]+)", re.IGNORECASE),
        "precision": re.compile(r"precision[:\s=]+([\d.]+)", re.IGNORECASE),
        "recall": re.compile(r"recall[:\s=]+([\d.]+)", re.IGNORECASE),
        "epoch": re.compile(r"epoch[:\s=]+(\d+)", re.IGNORECASE),
        "step": re.compile(r"step[:\s=]+(\d+)", re.IGNORECASE),
    }

    @classmethod
    def parse(cls, text: str) -> TrainingMetrics:
        metrics = TrainingMetrics()
        for key, pattern in cls.PATTERNS.items():
            matches = pattern.findall(text)
            if matches:
                try:
                    val = float(matches[-1]) if key not in ("epoch", "step") else int(matches[-1])
                    setattr(metrics, key, val)
                except ValueError:
                    continue
        # 尝试解析 JSON 行（如 {"loss": 0.3, "accuracy": 0.95}）
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    data = json.loads(line)
                    for k, v in data.items():
                        if k in ("loss", "accuracy", "f1", "precision", "recall", "epoch", "step", "val_loss", "val_accuracy"):
                            if isinstance(v, (int, float)):
                                setattr(metrics, k, v)
                        else:
                            metrics.custom[k] = v
                except json.JSONDecodeError:
                    continue
        return metrics

    @classmethod
    def parse_checkpoints(cls, text: str) -> List[CheckpointInfo]:
        """从训练日志中解析检查点保存信息。"""
        checkpoints = []
        # 匹配格式: CHECKPOINT Saved epoch=5 step=1000 path=/path/to/ckpt.pt
        pattern = re.compile(
            r"CHECKPOINT\s+Saved\s+epoch=(\d+)\s+step=(\d+)\s+path=(\S+)"
            r"(?:\s+metric=(\S+):([\d.]+))?",
            re.IGNORECASE,
        )
        for match in pattern.finditer(text):
            checkpoints.append(
                CheckpointInfo(
                    path=match.group(3),
                    epoch=int(match.group(1)),
                    step=int(match.group(2)),
                    metric_name=match.group(4) or "",
                    metric_value=float(match.group(5)) if match.group(5) else None,
                    saved_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                )
            )
        return checkpoints


# ---------------------------------------------------------------------------
# GPU 执行器
# ---------------------------------------------------------------------------


class GPUExecutor:
    """GPU 训练/推理执行器。

    降级路径：
    - CUDA 不可用时自动回退 CPU，并在日志中明确标注 ``gpu_used=False``。
    - 脚本中可通过环境变量 ``CUDA_VISIBLE_DEVICES`` 控制可见 GPU。
    """

    def __init__(self, gpu_id: int = 0, timeout: int = 3600):
        self.gpu_id = gpu_id
        self.timeout = timeout
        self.resource_manager = GPUResourceManager()
        self.parser = TrainingLogParser()
        self._check_cuda()

    def _check_cuda(self) -> None:
        if not self.resource_manager.is_available():
            logger.warning(
                f"CUDA not available (requested gpu_id={self.gpu_id}). "
                "All training will fall back to CPU."
            )

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """CUDA 是否可用。"""
        return self.resource_manager.is_available()

    def get_gpu_info(self) -> Dict[str, Any]:
        """获取 GPU 信息字典。"""
        gpus = self.resource_manager.get_gpu_info()
        if not gpus:
            return {
                "cuda_available": False,
                "requested_gpu_id": self.gpu_id,
                "gpus": [],
                "message": "No CUDA-capable GPU detected; will use CPU.",
            }
        return {
            "cuda_available": True,
            "requested_gpu_id": self.gpu_id,
            "device_count": len(gpus),
            "gpus": [g.to_dict() for g in gpus],
        }

    def execute_training(
        self,
        script_path: str,
        args: Dict[str, Any],
        resume_from: Optional[str] = None,
        vram_monitor_config: Optional[VRAMMonitorConfig] = None,
    ) -> TrainingResult:
        """执行训练脚本，支持检查点恢复和显存监控。

        Args:
            script_path: 训练脚本路径（.py 文件）。
            args: 脚本参数字典，如 {"epochs": 10, "batch_size": 32}。
                  自动注入 ``--gpu_id`` 和 ``--output_dir``。
            resume_from: 从指定检查点路径恢复训练（可选）。
            vram_monitor_config: 显存监控配置（可选）。

        Returns:
            TrainingResult: 包含 stdout、stderr、提取的指标、检查点路径等。
        """
        script = Path(script_path)
        if not script.exists():
            return TrainingResult(
                success=False,
                stdout="",
                stderr="",
                returncode=-1,
                metrics=TrainingMetrics(),
                message=f"Script not found: {script_path}",
            )

        # 准备输出目录
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_dir = CHECKPOINT_BASE_DIR / f"train_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)

        # 检查点管理器
        ckpt_manager = CheckpointManager(output_dir, max_keep=3)

        # 如果指定了 resume_from，验证检查点存在
        resumed_from = None
        if resume_from:
            resume_path = Path(resume_from)
            if resume_path.exists():
                resumed_from = str(resume_path)
                logger.info(f"[GPUExecutor] 将从检查点恢复: {resume_from}")
            else:
                logger.warning(f"[GPUExecutor] 指定的检查点不存在: {resume_from}")

        # 构建命令
        cmd = [sys.executable, str(script)]
        merged_args = dict(args)
        merged_args.setdefault("gpu_id", self.gpu_id if self.is_available() else -1)
        merged_args.setdefault("output_dir", str(output_dir))
        if resumed_from:
            merged_args["resume_from"] = resumed_from
        for key, val in merged_args.items():
            cmd.append(f"--{key}")
            cmd.append(str(val))

        env = os.environ.copy()
        if self.is_available():
            env["CUDA_VISIBLE_DEVICES"] = str(self.gpu_id)
        else:
            env["CUDA_VISIBLE_DEVICES"] = ""

        # 启动显存监控
        vram_monitor = None
        if self.is_available() and (vram_monitor_config is None or vram_monitor_config.enabled):
            vram_monitor = VRAMMonitor(
                gpu_id=self.gpu_id,
                config=vram_monitor_config or VRAMMonitorConfig(),
            )
            vram_monitor.start()

        logger.info(f"Starting training: {' '.join(cmd)}")
        start = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(script.parent),
                env=env,
                timeout=self.timeout,
            )
            duration = time.time() - start

            # 停止显存监控
            if vram_monitor:
                vram_monitor.stop()

            # 解析指标和检查点
            full_output = result.stdout + "\n" + result.stderr
            metrics = self.parser.parse(full_output)
            checkpoints = self.parser.parse_checkpoints(full_output)

            # 查找检查点（回退到文件扫描）
            checkpoint_path = self._find_checkpoint(output_dir)
            if not checkpoints and checkpoint_path:
                checkpoints = [CheckpointInfo(
                    path=str(checkpoint_path),
                    epoch=0,
                    step=0,
                    saved_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                )]

            # 保存检查点索引
            if checkpoints:
                ckpt_manager.save_checkpoint_meta(checkpoints)
                ckpt_manager.cleanup_old_checkpoints()

            success = result.returncode == 0
            message = "Training completed successfully." if success else f"Training failed with code {result.returncode}."
            if not self.is_available():
                message += " (CPU fallback mode)"
            if vram_monitor and vram_monitor.was_killed:
                message += f" [VRAM ALERT: {vram_monitor.kill_reason}]"
                success = False  # 显存超限视为失败

            return TrainingResult(
                success=success,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
                metrics=metrics,
                checkpoint_path=str(checkpoint_path) if checkpoint_path else None,
                duration_sec=round(duration, 2),
                gpu_used=self.is_available(),
                message=message,
                checkpoints=checkpoints,
                resumed_from=resumed_from,
            )
        except subprocess.TimeoutExpired:
            duration = time.time() - start
            if vram_monitor:
                vram_monitor.stop()
            logger.error(f"Training timed out after {self.timeout}s")
            return TrainingResult(
                success=False,
                stdout="",
                stderr=f"Timeout after {self.timeout} seconds",
                returncode=-2,
                metrics=TrainingMetrics(),
                duration_sec=round(duration, 2),
                gpu_used=self.is_available(),
                message=f"Training timed out after {self.timeout}s",
            )
        except Exception as e:
            duration = time.time() - start
            if vram_monitor:
                vram_monitor.stop()
            logger.error(f"Training execution error: {e}")
            return TrainingResult(
                success=False,
                stdout="",
                stderr=str(e),
                returncode=-3,
                metrics=TrainingMetrics(),
                duration_sec=round(duration, 2),
                gpu_used=self.is_available(),
                message=f"Training execution error: {e}",
            )

    def resume_training(self, script_path: str, args: Dict[str, Any], output_dir: Optional[str] = None) -> TrainingResult:
        """从最新的检查点恢复训练。

        Args:
            script_path: 训练脚本路径。
            args: 脚本参数。
            output_dir: 之前的输出目录（包含检查点）。如果为 None，则尝试从 args 中的 output_dir 获取。

        Returns:
            TrainingResult: 恢复后的训练结果。
        """
        # 确定输出目录
        if output_dir is None:
            output_dir = args.get("output_dir")
        if not output_dir:
            return TrainingResult(
                success=False,
                stdout="",
                stderr="",
                returncode=-1,
                metrics=TrainingMetrics(),
                message="无法恢复训练：未指定 output_dir",
            )

        # 查找最新检查点
        ckpt_manager = CheckpointManager(Path(output_dir))
        latest_ckpt = ckpt_manager.find_latest_checkpoint()
        if not latest_ckpt:
            logger.warning(f"[GPUExecutor] 未找到检查点，将从头开始训练: {output_dir}")
            return self.execute_training(script_path, args)

        logger.info(f"[GPUExecutor] 恢复训练: epoch={latest_ckpt.epoch}, path={latest_ckpt.path}")
        return self.execute_training(
            script_path=script_path,
            args=args,
            resume_from=latest_ckpt.path,
        )

    def get_recommended_batch_size(
        self,
        model_memory_mb: float = 500.0,
        per_sample_memory_mb: float = 10.0,
    ) -> int:
        """根据当前 GPU 显存推荐 batch size。

        Args:
            model_memory_mb: 模型预估显存占用（MB）
            per_sample_memory_mb: 每个样本预估显存占用（MB）

        Returns:
            推荐 batch size
        """
        return self.resource_manager.estimate_max_batch_size(
            gpu_id=self.gpu_id,
            model_memory_mb=model_memory_mb,
            per_sample_memory_mb=per_sample_memory_mb,
        )
    def execute_inference(self, model_path: str, data_path: str, extra_args: Optional[Dict[str, Any]] = None) -> InferenceResult:
        """执行推理脚本。

        若项目未提供独立推理脚本，本方法会生成一个最小临时脚本并执行。

        Args:
            model_path: 模型检查点路径。
            data_path: 输入数据路径。
            extra_args: 额外参数。

        Returns:
            InferenceResult: 包含 stdout、stderr、预测结果等。
        """
        model = Path(model_path)
        data = Path(data_path)
        if not model.exists():
            return InferenceResult(
                success=False,
                stdout="",
                stderr="",
                returncode=-1,
                message=f"Model not found: {model_path}",
            )
        if not data.exists():
            return InferenceResult(
                success=False,
                stdout="",
                stderr="",
                returncode=-1,
                message=f"Data not found: {data_path}",
            )

        # 生成最小推理脚本
        script_content = self._generate_inference_script()
        tmp_script = Path(__file__).parent / "_tmp_inference.py"
        tmp_script.write_text(script_content, encoding="utf-8")

        args = dict(extra_args or {})
        args["model_path"] = str(model)
        args["data_path"] = str(data)
        args["gpu_id"] = self.gpu_id if self.is_available() else -1

        cmd = [sys.executable, str(tmp_script)]
        for key, val in args.items():
            cmd.append(f"--{key}")
            cmd.append(str(val))

        env = os.environ.copy()
        if self.is_available():
            env["CUDA_VISIBLE_DEVICES"] = str(self.gpu_id)
        else:
            env["CUDA_VISIBLE_DEVICES"] = ""

        logger.info(f"Starting inference: {' '.join(cmd)}")
        start = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(model.parent),
                env=env,
                timeout=self.timeout,
            )
            duration = time.time() - start

            # 尝试解析 stdout 中的 JSON 预测结果
            predictions = self._extract_predictions(result.stdout)

            success = result.returncode == 0
            message = "Inference completed successfully." if success else f"Inference failed with code {result.returncode}."
            if not self.is_available():
                message += " (CPU fallback mode)"

            return InferenceResult(
                success=success,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
                predictions=predictions,
                duration_sec=round(duration, 2),
                gpu_used=self.is_available(),
                message=message,
            )
        except subprocess.TimeoutExpired:
            duration = time.time() - start
            return InferenceResult(
                success=False,
                stdout="",
                stderr=f"Timeout after {self.timeout} seconds",
                returncode=-2,
                duration_sec=round(duration, 2),
                gpu_used=self.is_available(),
                message=f"Inference timed out after {self.timeout}s",
            )
        except Exception as e:
            duration = time.time() - start
            return InferenceResult(
                success=False,
                stdout="",
                stderr=str(e),
                returncode=-3,
                duration_sec=round(duration, 2),
                gpu_used=self.is_available(),
                message=f"Inference execution error: {e}",
            )
        finally:
            # 清理临时脚本
            if tmp_script.exists():
                tmp_script.unlink()

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _find_checkpoint(self, output_dir: Path) -> Optional[Path]:
        """在输出目录中查找最新的检查点文件。"""
        if not output_dir.exists():
            return None
        candidates = list(output_dir.rglob("*.pt")) + list(output_dir.rglob("*.pth")) + list(output_dir.rglob("*.ckpt"))
        if not candidates:
            return None
        # 按修改时间排序，取最新
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]

    def _extract_predictions(self, stdout: str) -> Optional[List[Any]]:
        """尝试从 stdout 中提取 JSON 预测结果。"""
        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
            if line.startswith("{") and line.endswith("}"):
                try:
                    data = json.loads(line)
                    if "predictions" in data:
                        return data["predictions"]
                except json.JSONDecodeError:
                    continue
        return None

    def _generate_inference_script(self) -> str:
        """生成最小推理脚本内容。"""
        return '''\
"""Auto-generated minimal inference script."""
import argparse
import json
import sys
import os

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", required=True)
    parser.add_argument("--data_path", required=True)
    parser.add_argument("--gpu_id", type=int, default=-1)
    parser.add_argument("--batch_size", type=int, default=32)
    args = parser.parse_args()

    device = "cpu"
    if HAS_TORCH and args.gpu_id >= 0 and torch.cuda.is_available():
        if args.gpu_id < torch.cuda.device_count():
            device = f"cuda:{args.gpu_id}"

    print(f"{{\"device\": \"{device}\", \"model\": \"{args.model_path}\"}}")
    # 这里仅做占位；实际推理逻辑应由业务脚本提供
    print("[]")

if __name__ == "__main__":
    main()
'''

    def save_checkpoint(self, source_path: str, checkpoint_name: Optional[str] = None) -> str:
        """将外部检查点保存到统一目录。

        Args:
            source_path: 源检查点文件路径。
            checkpoint_name: 目标名称；为空则使用时间戳。

        Returns:
            str: 保存后的绝对路径。
        """
        src = Path(source_path)
        if not src.exists():
            raise FileNotFoundError(f"Checkpoint source not found: {source_path}")
        name = checkpoint_name or f"ckpt_{time.strftime('%Y%m%d_%H%M%S')}{src.suffix}"
        dest_dir = CHECKPOINT_BASE_DIR / "saved"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / name
        shutil.copy2(str(src), str(dest))
        logger.info(f"Checkpoint saved: {dest}")
        return str(dest.resolve())


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

_gpu_executor: Optional[GPUExecutor] = None


def get_gpu_executor(gpu_id: int = 0, timeout: int = 3600) -> GPUExecutor:
    """获取全局 GPUExecutor 单例。"""
    global _gpu_executor
    if _gpu_executor is None:
        _gpu_executor = GPUExecutor(gpu_id=gpu_id, timeout=timeout)
    return _gpu_executor
