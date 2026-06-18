"""实验执行器 —— 编排实验全生命周期。

流程：
1. 根据 experimentation_plan 搜索/下载数据集
2. 调用 solver_agent 生成实验代码（train/eval/baseline/ablation）
3. 创建/复用独立实验环境并安装依赖
4. 调用 experiment_runner 执行所有脚本
5. 调用 result_aggregator 整理结果
6. 返回 writer_agent 可用的结构化结果
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.dataset_manager import DatasetManager, ProcessedDataset, get_dataset_manager
from ..core.environment_manager import EnvironmentManager, get_environment_manager
from ..core.paths import get_project_output_dir
from .code_sandbox import CodeSandbox, SandboxConfig
from .experiment_result_aggregator import (
    AggregatedExperimentResult,
    ExperimentResultAggregator,
    get_result_aggregator,
)
from .experiment_runner import ExperimentBatchResult, ExperimentRunner, ExperimentScript

logger = logging.getLogger(__name__)


@dataclass
class ExperimentExecutorResult:
    """实验执行器返回结果。"""

    success: bool
    executed: bool
    aggregated: Optional[AggregatedExperimentResult] = None
    raw_batch: Optional[ExperimentBatchResult] = None
    dataset_info: Optional[Dict[str, Any]] = None
    code_dir: Optional[str] = None
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "executed": self.executed,
            "aggregated": self.aggregated.to_dict() if self.aggregated else None,
            "raw_batch": self.raw_batch.to_dict() if self.raw_batch else None,
            "dataset_info": self.dataset_info,
            "code_dir": self.code_dir,
            "errors": self.errors,
        }


class ExperimentExecutor:
    """实验执行编排器。"""

    def __init__(
        self,
        dataset_manager: Optional[DatasetManager] = None,
        env_manager: Optional[EnvironmentManager] = None,
        runner: Optional[ExperimentRunner] = None,
        aggregator: Optional[ExperimentResultAggregator] = None,
        sandbox: Optional[CodeSandbox] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.dataset_manager = dataset_manager or get_dataset_manager()
        self.env_manager = env_manager or get_environment_manager()
        self.runner = runner or ExperimentRunner()
        self.aggregator = aggregator or get_result_aggregator()
        self.sandbox = sandbox or CodeSandbox(config=SandboxConfig())
        self.config = config or {}

    def execute_experiment_plan(
        self,
        plan: Dict[str, Any],
        modeling_result: Optional[Dict[str, Any]] = None,
        solver_result: Optional[Dict[str, Any]] = None,
        project_name: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> ExperimentExecutorResult:
        """执行一个完整的实验计划。"""
        result = ExperimentExecutorResult(success=False, executed=True)

        try:
            # 1. 确定输出目录
            output_dir = self._get_experiment_output_dir(project_name, task_id)
            output_dir.mkdir(parents=True, exist_ok=True)
            code_dir = output_dir / "code"
            code_dir.mkdir(parents=True, exist_ok=True)
            result.code_dir = str(code_dir)

            # 2. 获取数据集
            datasets_plan = plan.get("datasets", []) or []
            processed_datasets: List[ProcessedDataset] = []
            for ds in datasets_plan:
                ds_name = ds.get("name") if isinstance(ds, dict) else str(ds)
                if not ds_name:
                    continue
                try:
                    pd = self._acquire_dataset(ds_name, output_dir / "datasets")
                    processed_datasets.append(pd)
                except Exception as e:
                    logger.warning(f"[ExperimentExecutor] 数据集 {ds_name} 获取失败: {e}")
                    result.errors.append(f"数据集 {ds_name} 获取失败: {e}")

            if not processed_datasets:
                result.errors.append("未获取到任何可用数据集，跳过实验执行")
                result.executed = False
                return result

            result.dataset_info = {
                "names": [d.name for d in processed_datasets],
                "splits": [self.dataset_manager.get_splits(d) for d in processed_datasets],
            }

            # 3. 生成实验代码（调用 solver_agent 的 experiment 模式，失败降级到模板）
            generated = self._generate_experiment_code(
                plan=plan,
                datasets=processed_datasets,
                modeling_result=modeling_result,
                solver_result=solver_result,
                code_dir=code_dir,
                project_name=project_name,
                task_id=task_id,
            )
            if not generated:
                result.errors.append("实验代码生成失败")
                return result

            # 4. 准备实验环境
            env_name = self._prepare_environment(code_dir, project_name or "experiment", task_id or "default")
            if not env_name:
                result.errors.append("实验环境准备失败")
                return result

            # 5. 执行实验
            batch_result = self.runner.run_experiment(
                main_script=generated["main"],
                baseline_scripts=generated.get("baselines", []),
                ablation_scripts=generated.get("ablations", []),
                output_dir=output_dir / "results",
            )
            result.raw_batch = batch_result
            result.success = batch_result.success

            # 6. 聚合结果
            aggregated = self.aggregator.aggregate(batch_result)
            result.aggregated = aggregated

            # 保存完整结果
            self._save_result(result, output_dir / "experiment_result.json")

        except Exception as e:
            logger.exception("[ExperimentExecutor] 实验执行异常")
            result.errors.append(f"实验执行异常: {e}")

        return result

    # ------------------------------------------------------------------
    # 数据集获取
    # ------------------------------------------------------------------

    def _acquire_dataset(self, name: str, datasets_dir: Path) -> ProcessedDataset:
        """获取并预处理数据集。"""
        datasets_dir.mkdir(parents=True, exist_ok=True)
        # 优先按已知名称精确下载
        known = self.dataset_manager.get_dataset_info(name.lower())
        if known:
            return self.dataset_manager.download_and_preprocess(
                name.lower(),
                source=known["source"],
                config={},
            )

        # 否则尝试按 HuggingFace 数据集名称下载
        try:
            return self.dataset_manager.download_and_preprocess(
                name,
                source="huggingface",
                config={},
            )
        except Exception:
            # 最后尝试 torchvision
            torch_name = name.upper()
            if torch_name in ("MNIST", "CIFAR10", "CIFAR100", "FASHIONMNIST"):
                return self.dataset_manager.download_and_preprocess(
                    name.lower(),
                    source="torchvision",
                    config={},
                )
            raise

    # ------------------------------------------------------------------
    # 代码生成（优先 LLM，降级到模板）
    # ------------------------------------------------------------------

    def _generate_experiment_code(
        self,
        plan: Dict[str, Any],
        datasets: List[ProcessedDataset],
        modeling_result: Optional[Dict[str, Any]],
        solver_result: Optional[Dict[str, Any]],
        code_dir: Path,
        project_name: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """生成实验代码。

        优先调用 solver_agent 的 experiment 模式做 LLM 生成；
        失败时降级到硬编码模板。
        """
        # 1. 尝试 LLM 生成
        llm_generated = self._try_llm_generate(
            plan=plan,
            datasets=datasets,
            modeling_result=modeling_result,
            solver_result=solver_result,
            code_dir=code_dir,
            project_name=project_name,
            task_id=task_id,
        )
        if llm_generated:
            return llm_generated

        # 2. 降级到硬编码模板
        logger.warning("[ExperimentExecutor] LLM 生成失败，降级到硬编码模板")
        return self._generate_template_code(plan, datasets, code_dir)

    def _try_llm_generate(
        self,
        plan: Dict[str, Any],
        datasets: List[ProcessedDataset],
        modeling_result: Optional[Dict[str, Any]],
        solver_result: Optional[Dict[str, Any]],
        code_dir: Path,
        project_name: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """调用 solver_agent 生成实验代码。"""
        try:
            import asyncio
            from ..agents.base import AgentFactory

            solver = AgentFactory.create("solver_agent")
            if solver is None:
                return None

            # 构建数据集路径信息
            dataset_paths = {}
            for ds in datasets:
                splits = self.dataset_manager.get_splits(ds)
                dataset_paths[ds.name] = {
                    "train": splits.get("train"),
                    "val": splits.get("val"),
                    "test": splits.get("test"),
                    "metadata": ds.metadata,
                }

            task_input = {
                "action": "experiment",
                "experiment_plan": plan,
                "dataset_paths": dataset_paths,
                "modeling_result": modeling_result or {},
                "solver_result": solver_result or {},
                "project_name": project_name,
                "task_id": task_id,
            }

            # 运行异步方法
            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(solver.execute(task_input, {}))

            if not result.get("execution_success"):
                logger.warning(f"[ExperimentExecutor] solver_agent experiment 返回失败: {result.get('error')}")
                return None

            # 将 solver_agent 返回的 code_files 转换为 ExperimentScript
            experiment_scripts = result.get("experiment_scripts", {})
            main = experiment_scripts.get("main")
            baselines = experiment_scripts.get("baselines", [])
            ablations = experiment_scripts.get("ablations", [])

            if not main:
                return None

            def _to_script(item: Dict[str, Any], role: str) -> ExperimentScript:
                path = Path(item.get("path", item.get("filename", "script.py")))
                return ExperimentScript(
                    name=path.stem,
                    path=path,
                    role=role,
                    args={"epochs": 2, "batch_size": 32},
                )

            return {
                "main": _to_script(main, "main"),
                "baselines": [_to_script(b, "baseline") for b in baselines],
                "ablations": [_to_script(a, "ablation") for a in ablations],
                "code_dir": result.get("code_dir", str(code_dir)),
                "requirements": result.get("requirements", []),
                "source": "llm",
            }

        except Exception as e:
            logger.warning(f"[ExperimentExecutor] LLM 生成实验代码失败: {e}")
            return None

    def _generate_template_code(
        self,
        plan: Dict[str, Any],
        datasets: List[ProcessedDataset],
        code_dir: Path,
    ) -> Optional[Dict[str, Any]]:
        """硬编码模板代码生成（降级方案）。"""
        dataset = datasets[0]
        splits = self.dataset_manager.get_splits(dataset)
        train_path = splits.get("train", "")
        val_path = splits.get("val") or splits.get("test", "")
        test_path = splits.get("test", "")

        is_image = dataset.metadata.get("source") == "torchvision" or "image_size" in dataset.metadata

        main_script = self._write_main_script(code_dir, dataset, train_path, val_path, test_path, is_image)

        generated = {
            "main": ExperimentScript(
                name="main_experiment",
                path=main_script,
                role="main",
                args={"epochs": 2, "batch_size": 32},
            ),
            "baselines": [],
            "ablations": [],
            "source": "template",
        }

        # baselines
        for baseline in plan.get("baselines", []) or []:
            b_name = baseline.get("name", "baseline") if isinstance(baseline, dict) else str(baseline)
            b_script = self._write_baseline_script(code_dir, b_name, dataset, train_path, val_path, test_path, is_image)
            generated["baselines"].append(
                ExperimentScript(
                    name=b_name,
                    path=b_script,
                    role="baseline",
                    args={"epochs": 2, "batch_size": 32},
                )
            )

        # ablations
        for ablation in plan.get("ablation_plan", []) or []:
            a_name = ablation.get("component", "ablation") if isinstance(ablation, dict) else str(ablation)
            a_script = self._write_ablation_script(code_dir, a_name, dataset, train_path, val_path, test_path, is_image)
            generated["ablations"].append(
                ExperimentScript(
                    name=a_name,
                    path=a_script,
                    role="ablation",
                    args={"epochs": 2, "batch_size": 32},
                )
            )

        return generated

    def _write_main_script(
        self,
        code_dir: Path,
        dataset: ProcessedDataset,
        train_path: str,
        val_path: str,
        test_path: str,
        is_image: bool,
    ) -> Path:
        """写主实验脚本。"""
        script = code_dir / "main_experiment.py"
        if is_image:
            content = self._image_classification_script("Our Method", train_path, val_path, test_path, dataset)
        else:
            content = self._text_classification_script("Our Method", train_path, val_path, test_path, dataset)
        script.write_text(content, encoding="utf-8")
        return script

    def _write_baseline_script(
        self,
        code_dir: Path,
        name: str,
        dataset: ProcessedDataset,
        train_path: str,
        val_path: str,
        test_path: str,
        is_image: bool,
    ) -> Path:
        """写 baseline 脚本。"""
        safe_name = name.lower().replace(" ", "_").replace("-", "_")[:50]
        script = code_dir / f"baseline_{safe_name}.py"
        if is_image:
            content = self._image_baseline_script(name, train_path, val_path, test_path, dataset)
        else:
            content = self._text_baseline_script(name, train_path, val_path, test_path, dataset)
        script.write_text(content, encoding="utf-8")
        return script

    def _write_ablation_script(
        self,
        code_dir: Path,
        name: str,
        dataset: ProcessedDataset,
        train_path: str,
        val_path: str,
        test_path: str,
        is_image: bool,
    ) -> Path:
        """写 ablation 脚本。"""
        safe_name = name.lower().replace(" ", "_").replace("-", "_")[:50]
        script = code_dir / f"ablation_{safe_name}.py"
        if is_image:
            content = self._image_ablation_script(name, train_path, val_path, test_path, dataset)
        else:
            content = self._text_ablation_script(name, train_path, val_path, test_path, dataset)
        script.write_text(content, encoding="utf-8")
        return script

    # ------------------------------------------------------------------
    # 环境准备
    # ------------------------------------------------------------------

    def _prepare_environment(self, code_dir: Path, project_name: str, task_id: str) -> Optional[str]:
        """创建或复用实验环境，安装依赖。"""
        env_name = f"exp_{project_name}_{task_id}"[:50]
        # 复用 venv（若存在）
        envs = self.env_manager.list_environments()
        exists = any(e.name == env_name and e.backend == "venv" for e in envs)
        if not exists:
            ok = self.env_manager.create("venv", env_name)
            if not ok:
                return None

        # 写入 requirements
        requirements = code_dir / "requirements.txt"
        if not requirements.exists():
            requirements.write_text(
                "torch\ntorchvision\ndatasets\ntransformers\nscikit-learn\nnumpy\npandas\nPillow\n",
                encoding="utf-8",
            )

        ok = self.env_manager.install_requirements("venv", env_name, requirements)
        if not ok:
            logger.warning("[ExperimentExecutor] 安装 requirements 失败，尝试继续用已有依赖")

        # 用该环境的 python 更新 runner
        backend = self.env_manager.get_backend("venv")
        if backend:
            env_path = Path(code_dir).parent.parent / "data" / "venvs" / env_name
            python_bin = env_path / "bin" / "python"
            if python_bin.exists():
                self.runner.python_bin = str(python_bin)
        return env_name

    # ------------------------------------------------------------------
    # 输出目录与结果保存
    # ------------------------------------------------------------------

    def _get_experiment_output_dir(self, project_name: Optional[str], task_id: Optional[str]) -> Path:
        base = get_project_output_dir(project_name) if project_name else get_project_output_dir(None)
        return base / "experiments" / (task_id or "default")

    def _save_result(self, result: ExperimentExecutorResult, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # 模板脚本
    # ------------------------------------------------------------------

    def _image_classification_script(
        self, name: str, train_path: str, val_path: str, test_path: str, dataset: ProcessedDataset
    ) -> str:
        return f'''"""{name} - Image Classification Experiment"""
import argparse
import json
import os
import sys

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader
    import torchvision
    import torchvision.transforms as transforms
    HAS_TORCH = True
except ImportError as e:
    print(json.dumps({{"error": f"PyTorch not installed: {{e}}"}}))
    sys.exit(1)

from PIL import Image


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--output_dir", type=str, default="./output")
    parser.add_argument("--gpu_id", type=int, default=-1)
    return parser.parse_args()


def main():
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    device = "cpu"
    if args.gpu_id >= 0 and torch.cuda.is_available():
        device = f"cuda:{{args.gpu_id}}"

    transform = transforms.Compose([
        transforms.Resize((32, 32)),
        transforms.ToTensor(),
        transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)),
    ])

    dataset_name = "{dataset.name}"
    if dataset_name.lower() == "mnist":
        train_ds = torchvision.datasets.MNIST(root="{train_path}", train=True, download=False, transform=transform)
        test_ds = torchvision.datasets.MNIST(root="{train_path}", train=False, download=False, transform=transform)
    elif dataset_name.lower() == "cifar10":
        train_ds = torchvision.datasets.CIFAR10(root="{train_path}", train=True, download=False, transform=transform)
        test_ds = torchvision.datasets.CIFAR10(root="{train_path}", train=False, download=False, transform=transform)
    else:
        train_ds = torchvision.datasets.CIFAR10(root="{train_path}", train=True, download=False, transform=transform)
        test_ds = torchvision.datasets.CIFAR10(root="{train_path}", train=False, download=False, transform=transform)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    test_loader = DataLoader(test_ds, batch_size=args.batch_size, shuffle=False)

    num_classes = {dataset.metadata.get("num_classes", 10)}
    model = nn.Sequential(
        nn.Flatten(),
        nn.Linear(32 * 32 * 3, 128),
        nn.ReLU(),
        nn.Linear(128, num_classes),
    ).to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=args.lr)

    for epoch in range(args.epochs):
        model.train()
        total_loss = 0.0
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        avg_loss = total_loss / len(train_loader)

        model.eval()
        correct = 0
        total = 0
        with torch.no_grad():
            for images, labels in test_loader:
                images, labels = images.to(device), labels.to(device)
                outputs = model(images)
                _, predicted = torch.max(outputs.data, 1)
                total += labels.size(0)
                correct += (predicted == labels).sum().item()
        accuracy = correct / total if total > 0 else 0.0
        print(json.dumps({{"epoch": epoch + 1, "loss": avg_loss, "accuracy": accuracy}}))

    # 保存最终指标
    final_metrics = {{"accuracy": accuracy, "loss": avg_loss}}
    with open(os.path.join(args.output_dir, "metrics.json"), "w") as f:
        json.dump(final_metrics, f)
    print(json.dumps(final_metrics))


if __name__ == "__main__":
    main()
'''

    def _image_baseline_script(
        self, name: str, train_path: str, val_path: str, test_path: str, dataset: ProcessedDataset
    ) -> str:
        return f'''"""Baseline: {name}"""
import argparse
import json
import os
import sys

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader
    import torchvision
    import torchvision.transforms as transforms
except ImportError as e:
    print(json.dumps({{"error": f"PyTorch not installed: {{e}}"}}))
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--output_dir", type=str, default="./output")
    args = parser.parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    transform = transforms.Compose([
        transforms.Resize((32, 32)),
        transforms.ToTensor(),
        transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)),
    ])

    dataset_name = "{dataset.name}"
    if dataset_name.lower() == "mnist":
        train_ds = torchvision.datasets.MNIST(root="{train_path}", train=True, download=False, transform=transform)
        test_ds = torchvision.datasets.MNIST(root="{train_path}", train=False, download=False, transform=transform)
    else:
        train_ds = torchvision.datasets.CIFAR10(root="{train_path}", train=True, download=False, transform=transform)
        test_ds = torchvision.datasets.CIFAR10(root="{train_path}", train=False, download=False, transform=transform)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    test_loader = DataLoader(test_ds, batch_size=args.batch_size, shuffle=False)

    # 更简单的 baseline：单层线性模型
    num_classes = {dataset.metadata.get("num_classes", 10)}
    model = nn.Sequential(nn.Flatten(), nn.Linear(32 * 32 * 3, num_classes))
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.SGD(model.parameters(), lr=0.01)

    for epoch in range(args.epochs):
        model.train()
        total_loss = 0.0
        for images, labels in train_loader:
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        avg_loss = total_loss / len(train_loader)

        model.eval()
        correct = 0
        total = 0
        with torch.no_grad():
            for images, labels in test_loader:
                outputs = model(images)
                _, predicted = torch.max(outputs.data, 1)
                total += labels.size(0)
                correct += (predicted == labels).sum().item()
        accuracy = correct / total if total > 0 else 0.0
        print(json.dumps({{"epoch": epoch + 1, "loss": avg_loss, "accuracy": accuracy}}))

    final_metrics = {{"accuracy": accuracy, "loss": avg_loss}}
    with open(os.path.join(args.output_dir, "metrics.json"), "w") as f:
        json.dump(final_metrics, f)
    print(json.dumps(final_metrics))


if __name__ == "__main__":
    main()
'''

    def _image_ablation_script(
        self, name: str, train_path: str, val_path: str, test_path: str, dataset: ProcessedDataset
    ) -> str:
        return f'''"""Ablation: without {name}"""
import argparse
import json
import os
import sys

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader
    import torchvision
    import torchvision.transforms as transforms
except ImportError as e:
    print(json.dumps({{"error": f"PyTorch not installed: {{e}}"}}))
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--output_dir", type=str, default="./output")
    args = parser.parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    transform = transforms.Compose([
        transforms.Resize((32, 32)),
        transforms.ToTensor(),
    ])

    dataset_name = "{dataset.name}"
    if dataset_name.lower() == "mnist":
        train_ds = torchvision.datasets.MNIST(root="{train_path}", train=True, download=False, transform=transform)
        test_ds = torchvision.datasets.MNIST(root="{train_path}", train=False, download=False, transform=transform)
    else:
        train_ds = torchvision.datasets.CIFAR10(root="{train_path}", train=True, download=False, transform=transform)
        test_ds = torchvision.datasets.CIFAR10(root="{train_path}", train=False, download=False, transform=transform)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    test_loader = DataLoader(test_ds, batch_size=args.batch_size, shuffle=False)

    num_classes = {dataset.metadata.get("num_classes", 10)}
    # 消融：去掉非线性激活
    model = nn.Sequential(nn.Flatten(), nn.Linear(32 * 32 * 3, 128), nn.Linear(128, num_classes))
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)

    for epoch in range(args.epochs):
        model.train()
        total_loss = 0.0
        for images, labels in train_loader:
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        avg_loss = total_loss / len(train_loader)

        model.eval()
        correct = 0
        total = 0
        with torch.no_grad():
            for images, labels in test_loader:
                outputs = model(images)
                _, predicted = torch.max(outputs.data, 1)
                total += labels.size(0)
                correct += (predicted == labels).sum().item()
        accuracy = correct / total if total > 0 else 0.0
        print(json.dumps({{"epoch": epoch + 1, "loss": avg_loss, "accuracy": accuracy}}))

    final_metrics = {{"accuracy": accuracy, "loss": avg_loss}}
    with open(os.path.join(args.output_dir, "metrics.json"), "w") as f:
        json.dump(final_metrics, f)
    print(json.dumps(final_metrics))


if __name__ == "__main__":
    main()
'''

    def _text_classification_script(
        self, name: str, train_path: str, val_path: str, test_path: str, dataset: ProcessedDataset
    ) -> str:
        return f'''"""{name} - Text Classification Experiment"""
import argparse
import json
import os
import sys

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score
    HAS_SKLEARN = True
except ImportError as e:
    print(json.dumps({{"error": f"scikit-learn not installed: {{e}}"}}))
    sys.exit(1)


def load_jsonl(path):
    texts, labels = [], []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            item = json.loads(line)
            texts.append(item.get("text", ""))
            labels.append(int(item.get("label", 0)))
    return texts, labels


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output_dir", type=str, default="./output")
    args = parser.parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    train_texts, train_labels = load_jsonl("{train_path}/data.jsonl")
    test_texts, test_labels = load_jsonl("{test_path}/data.jsonl")

    vectorizer = TfidfVectorizer(max_features=5000)
    X_train = vectorizer.fit_transform(train_texts)
    X_test = vectorizer.transform(test_texts)

    model = LogisticRegression(max_iter=1000)
    model.fit(X_train, train_labels)
    preds = model.predict(X_test)
    accuracy = accuracy_score(test_labels, preds)

    metrics = {{"accuracy": accuracy}}
    with open(os.path.join(args.output_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f)
    print(json.dumps(metrics))


if __name__ == "__main__":
    main()
'''

    def _text_baseline_script(
        self, name: str, train_path: str, val_path: str, test_path: str, dataset: ProcessedDataset
    ) -> str:
        return f'''"""Baseline: {name}"""
import argparse
import json
import os
import sys

try:
    from sklearn.feature_extraction.text import CountVectorizer
    from sklearn.naive_bayes import MultinomialNB
    from sklearn.metrics import accuracy_score
except ImportError as e:
    print(json.dumps({{"error": f"scikit-learn not installed: {{e}}"}}))
    sys.exit(1)


def load_jsonl(path):
    texts, labels = [], []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            item = json.loads(line)
            texts.append(item.get("text", ""))
            labels.append(int(item.get("label", 0)))
    return texts, labels


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output_dir", type=str, default="./output")
    args = parser.parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    train_texts, train_labels = load_jsonl("{train_path}/data.jsonl")
    test_texts, test_labels = load_jsonl("{test_path}/data.jsonl")

    vectorizer = CountVectorizer(max_features=5000)
    X_train = vectorizer.fit_transform(train_texts)
    X_test = vectorizer.transform(test_texts)

    model = MultinomialNB()
    model.fit(X_train, train_labels)
    preds = model.predict(X_test)
    accuracy = accuracy_score(test_labels, preds)

    metrics = {{"accuracy": accuracy}}
    with open(os.path.join(args.output_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f)
    print(json.dumps(metrics))


if __name__ == "__main__":
    main()
'''

    def _text_ablation_script(
        self, name: str, train_path: str, val_path: str, test_path: str, dataset: ProcessedDataset
    ) -> str:
        return f'''"""Ablation: without {name}"""
import argparse
import json
import os
import sys

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import SGDClassifier
    from sklearn.metrics import accuracy_score
except ImportError as e:
    print(json.dumps({{"error": f"scikit-learn not installed: {{e}}"}}))
    sys.exit(1)


def load_jsonl(path):
    texts, labels = [], []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            item = json.loads(line)
            texts.append(item.get("text", ""))
            labels.append(int(item.get("label", 0)))
    return texts, labels


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output_dir", type=str, default="./output")
    args = parser.parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    train_texts, train_labels = load_jsonl("{train_path}/data.jsonl")
    test_texts, test_labels = load_jsonl("{test_path}/data.jsonl")

    # 消融：降低特征维度
    vectorizer = TfidfVectorizer(max_features=500)
    X_train = vectorizer.fit_transform(train_texts)
    X_test = vectorizer.transform(test_texts)

    model = SGDClassifier(max_iter=1000)
    model.fit(X_train, train_labels)
    preds = model.predict(X_test)
    accuracy = accuracy_score(test_labels, preds)

    metrics = {{"accuracy": accuracy}}
    with open(os.path.join(args.output_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f)
    print(json.dumps(metrics))


if __name__ == "__main__":
    main()
'''


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------


def get_experiment_executor(config: Optional[Dict[str, Any]] = None) -> ExperimentExecutor:
    """获取默认实验执行器。"""
    return ExperimentExecutor(config=config)
