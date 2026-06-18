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
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 检查点默认保存目录
CHECKPOINT_BASE_DIR = Path(__file__).parent.parent.parent / "data" / "checkpoints"

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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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

    def execute_training(self, script_path: str, args: Dict[str, Any]) -> TrainingResult:
        """执行训练脚本。

        Args:
            script_path: 训练脚本路径（.py 文件）。
            args: 脚本参数字典，如 {"epochs": 10, "batch_size": 32}。
                  自动注入 ``--gpu_id`` 和 ``--output_dir``。

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

        # 构建命令
        cmd = [sys.executable, str(script)]
        merged_args = dict(args)
        merged_args.setdefault("gpu_id", self.gpu_id if self.is_available() else -1)
        merged_args.setdefault("output_dir", str(output_dir))
        for key, val in merged_args.items():
            cmd.append(f"--{key}")
            cmd.append(str(val))

        env = os.environ.copy()
        if self.is_available():
            env["CUDA_VISIBLE_DEVICES"] = str(self.gpu_id)
        else:
            env["CUDA_VISIBLE_DEVICES"] = ""

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
            metrics = self.parser.parse(result.stdout + "\n" + result.stderr)

            # 查找检查点
            checkpoint_path = self._find_checkpoint(output_dir)

            success = result.returncode == 0
            message = "Training completed successfully." if success else f"Training failed with code {result.returncode}."
            if not self.is_available():
                message += " (CPU fallback mode)"

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
            )
        except subprocess.TimeoutExpired:
            duration = time.time() - start
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
