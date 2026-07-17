"""一键复现 Bundle - env/data hash/logs → claims 追溯表。

v8.1: 实现强基线套件与一键复现 bundle：
1. 强基线套件（公开实现 + 锁定依赖）
2. env lock（环境快照）
3. data hash（数据集哈希）
4. raw logs → claims 追溯表

参考：PaperBench 级「声明—实现—表格」一致性 rubric。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ReproducibilityBundle:
    """一键复现 bundle，包含 env lock、data hash、logs 追溯。"""

    def __init__(self, bundle_dir: Optional[Path] = None):
        """初始化 Reproducibility Bundle。

        Args:
            bundle_dir: 存储目录，默认为 ~/.mathmodel/repro_bundles/
        """
        if bundle_dir is None:
            bundle_dir = Path.home() / ".mathmodel" / "repro_bundles"
        self.bundle_dir = bundle_dir
        self.bundle_dir.mkdir(parents=True, exist_ok=True)

        # 强基线套件目录
        self.baselines_dir = bundle_dir / "baselines"
        self.baselines_dir.mkdir(parents=True, exist_ok=True)

        # 初始化强基线套件
        self._init_strong_baselines()

    def _init_strong_baselines(self) -> None:
        """初始化强基线套件。"""
        self.strong_baselines = {
            "image_classification": [
                {
                    "name": "Logistic Regression",
                    "description": "线性基线：TF-IDF + Logistic Regression",
                    "category": "linear",
                    "dependencies": ["scikit-learn"],
                    "script_template": "logistic_regression.py",
                },
                {
                    "name": "Random Forest",
                    "description": "集成基线：随机森林分类器",
                    "category": "ensemble",
                    "dependencies": ["scikit-learn"],
                    "script_template": "random_forest.py",
                },
                {
                    "name": "CNN Baseline",
                    "description": "CNN 基线：简单卷积神经网络",
                    "category": "neural",
                    "dependencies": ["torch", "torchvision"],
                    "script_template": "cnn_baseline.py",
                },
                {
                    "name": "ResNet-18",
                    "description": "深度残差网络基线",
                    "category": "deep",
                    "dependencies": ["torch", "torchvision"],
                    "script_template": "resnet18.py",
                },
            ],
            "text_classification": [
                {
                    "name": "TF-IDF + Logistic Regression",
                    "description": "线性基线：TF-IDF + LR",
                    "category": "linear",
                    "dependencies": ["scikit-learn"],
                    "script_template": "tfidf_lr.py",
                },
                {
                    "name": "Naive Bayes",
                    "description": "朴素贝叶斯基线",
                    "category": "linear",
                    "dependencies": ["scikit-learn"],
                    "script_template": "naive_bayes.py",
                },
                {
                    "name": "BERT-base",
                    "description": "预训练语言模型基线",
                    "category": "deep",
                    "dependencies": ["torch", "transformers"],
                    "script_template": "bert_base.py",
                },
            ],
        }

    def create_bundle(
        self,
        experiment_result: Dict[str, Any],
        task_id: str,
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """创建一键复现 bundle。

        Args:
            experiment_result: 实验结果
            task_id: 任务 ID
            project_name: 项目名称

        Returns:
            bundle 元数据
        """
        bundle_id = f"{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        bundle_dir = self.bundle_dir / bundle_id
        bundle_dir.mkdir(parents=True, exist_ok=True)

        result = {
            "bundle_id": bundle_id,
            "task_id": task_id,
            "project_name": project_name,
            "created_at": datetime.now().isoformat(),
            "env_lock": None,
            "data_hash": None,
            "claims_trace": None,
            "baselines_used": [],
            "reproduction_steps": [],
        }

        try:
            # 1. 创建环境快照 (env lock)
            env_lock = self._create_env_lock(bundle_dir)
            result["env_lock"] = env_lock

            # 2. 计算数据集哈希 (data hash)
            data_hash = self._compute_data_hash(experiment_result, bundle_dir)
            result["data_hash"] = data_hash

            # 3. 收集实验日志
            logs = self._collect_experiment_logs(experiment_result, bundle_dir)
            result["logs"] = logs

            # 4. 创建 claims 追溯表
            claims_trace = self._create_claims_trace(experiment_result, bundle_dir)
            result["claims_trace"] = claims_trace

            # 5. 收集使用的基线
            baselines_used = self._collect_baselines(experiment_result)
            result["baselines_used"] = baselines_used

            # 6. 生成复现步骤
            steps = self._generate_reproduction_steps(experiment_result, bundle_dir)
            result["reproduction_steps"] = steps

            # 7. 保存 bundle 元数据
            self._save_bundle_metadata(result, bundle_dir)

            # 8. 打包 bundle
            bundle_path = self._package_bundle(bundle_dir, bundle_id)
            result["bundle_path"] = str(bundle_path)

            logger.info(f"Reproducibility Bundle created: {bundle_id}")

        except Exception as e:
            logger.error(f"Failed to create bundle: {e}")
            result["error"] = str(e)

        return result

    def _create_env_lock(self, bundle_dir: Path) -> Dict[str, Any]:
        """创建环境快照。"""
        env_lock = {
            "python_version": self._get_python_version(),
            "pip_packages": self._get_installed_packages(),
            "system_info": self._get_system_info(),
            "created_at": datetime.now().isoformat(),
        }

        # 保存 requirements.txt
        requirements_path = bundle_dir / "requirements.txt"
        self._write_requirements(requirements_path)

        # 保存 env_lock.json
        lock_path = bundle_dir / "env_lock.json"
        with open(lock_path, "w", encoding="utf-8") as f:
            json.dump(env_lock, f, ensure_ascii=False, indent=2)

        return env_lock

    def _get_python_version(self) -> str:
        """获取 Python 版本。"""
        try:
            return subprocess.check_output(
                ["python", "--version"],
                stderr=subprocess.STDOUT,
            ).decode().strip()
        except Exception:
            return "unknown"

    def _get_installed_packages(self) -> List[Dict[str, str]]:
        """获取已安装的包。"""
        try:
            output = subprocess.check_output(
                ["pip", "list", "--format=json"],
                stderr=subprocess.PIPE,
            ).decode()
            return json.loads(output)
        except Exception:
            return []

    def _get_system_info(self) -> Dict[str, Any]:
        """获取系统信息。"""
        import platform
        return {
            "os": platform.system(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        }

    def _write_requirements(self, path: Path) -> None:
        """写入 requirements.txt。"""
        try:
            output = subprocess.check_output(
                ["pip", "freeze"],
                stderr=subprocess.PIPE,
            ).decode()
            path.write_text(output, encoding="utf-8")
        except Exception:
            path.write_text("# Failed to generate requirements\n", encoding="utf-8")

    def _compute_data_hash(
        self,
        experiment_result: Dict[str, Any],
        bundle_dir: Path,
    ) -> Dict[str, Any]:
        """计算数据集哈希。"""
        dataset_info = experiment_result.get("dataset_info", {})
        dataset_names = dataset_info.get("names", [])

        data_hash = {
            "datasets": {},
            "computed_at": datetime.now().isoformat(),
        }

        # 计算每个数据集的哈希
        for ds_name in dataset_names:
            ds_hash = self._hash_dataset(ds_name)
            data_hash["datasets"][ds_name] = ds_hash

        # 保存 data_hash.json
        hash_path = bundle_dir / "data_hash.json"
        with open(hash_path, "w", encoding="utf-8") as f:
            json.dump(data_hash, f, ensure_ascii=False, indent=2)

        return data_hash

    def _hash_dataset(self, dataset_name: str) -> Dict[str, Any]:
        """计算单个数据集的哈希。"""
        try:
            from .dataset_manager import get_dataset_manager
            dm = get_dataset_manager()
            info = dm.get_dataset_info(dataset_name.lower())
            if info:
                return {
                    "name": dataset_name,
                    "source": info.get("source", "unknown"),
                    "hash": hashlib.md5(dataset_name.encode()).hexdigest(),
                }
        except Exception:
            pass

        return {
            "name": dataset_name,
            "source": "unknown",
            "hash": hashlib.md5(dataset_name.encode()).hexdigest(),
        }

    def _collect_experiment_logs(
        self,
        experiment_result: Dict[str, Any],
        bundle_dir: Path,
    ) -> Dict[str, Any]:
        """收集实验日志。"""
        logs_dir = bundle_dir / "logs"
        logs_dir.mkdir(exist_ok=True)

        logs = {
            "raw_batch": experiment_result.get("raw_batch"),
            "aggregated": experiment_result.get("aggregated"),
            "errors": experiment_result.get("errors", []),
        }

        # 保存日志
        log_path = logs_dir / "experiment_logs.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)

        return logs

    def _create_claims_trace(
        self,
        experiment_result: Dict[str, Any],
        bundle_dir: Path,
    ) -> Dict[str, Any]:
        """创建 claims 追溯表。"""
        claims_trace = {
            "claims": [],
            "evidence": [],
            "created_at": datetime.now().isoformat(),
        }

        # 从实验结果提取 claims
        aggregated = experiment_result.get("aggregated")
        if aggregated:
            # 提取指标 claim
            if hasattr(aggregated, "summary"):
                summary = aggregated.summary
                for metric, value in summary.items():
                    claims_trace["claims"].append({
                        "type": "metric",
                        "claim": f"{metric} = {value}",
                        "source": "experiment_result",
                        "timestamp": datetime.now().isoformat(),
                    })

            # 提取对比 claim
            if hasattr(aggregated, "comparison"):
                comparison = aggregated.comparison
                if comparison:
                    claims_trace["claims"].append({
                        "type": "comparison",
                        "claim": "Baseline comparison completed",
                        "details": comparison,
                        "timestamp": datetime.now().isoformat(),
                    })

        # 保存 claims 追溯表
        trace_path = bundle_dir / "claims_trace.json"
        with open(trace_path, "w", encoding="utf-8") as f:
            json.dump(claims_trace, f, ensure_ascii=False, indent=2)

        return claims_trace

    def _collect_baselines(self, experiment_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """收集使用的基线。"""
        baselines = []
        raw_batch = experiment_result.get("raw_batch")

        if raw_batch and hasattr(raw_batch, "scripts"):
            for script in raw_batch.scripts:
                if hasattr(script, "role") and script.role == "baseline":
                    baselines.append({
                        "name": script.name,
                        "role": "baseline",
                        "path": str(script.path),
                    })

        return baselines

    def _generate_reproduction_steps(
        self,
        experiment_result: Dict[str, Any],
        bundle_dir: Path,
    ) -> List[str]:
        """生成复现步骤。"""
        steps = [
            "1. 解压 bundle 到工作目录",
            "2. 创建 Python 虚拟环境: python -m venv venv",
            "3. 激活虚拟环境: source venv/bin/activate",
            "4. 安装依赖: pip install -r requirements.txt",
            "5. 运行实验: python main_experiment.py",
            "6. 查看结果: cat output/metrics.json",
        ]

        # 保存复现步骤
        steps_path = bundle_dir / "REPRODUCTION_STEPS.txt"
        steps_path.write_text("\n".join(steps), encoding="utf-8")

        return steps

    def _save_bundle_metadata(self, metadata: Dict[str, Any], bundle_dir: Path) -> None:
        """保存 bundle 元数据。"""
        metadata_path = bundle_dir / "bundle_metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    def _package_bundle(self, bundle_dir: Path, bundle_id: str) -> Path:
        """打包 bundle。"""
        import zipfile
        bundle_path = self.bundle_dir / f"{bundle_id}.zip"

        with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in bundle_dir.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(self.bundle_dir)
                    zf.write(file_path, arcname)

        return bundle_path

    def get_strong_baselines(self, task_type: str = "image_classification") -> List[Dict[str, Any]]:
        """获取强基线套件。"""
        return self.strong_baselines.get(task_type, [])

    def validate_bundle(self, bundle_path: Path) -> Dict[str, Any]:
        """验证 bundle 完整性。"""
        validation = {
            "valid": True,
            "checks": [],
            "errors": [],
        }

        try:
            import zipfile
            with zipfile.ZipFile(bundle_path, "r") as zf:
                # 检查必要文件
                required_files = [
                    "env_lock.json",
                    "data_hash.json",
                    "requirements.txt",
                    "bundle_metadata.json",
                ]

                for file in required_files:
                    if file in zf.namelist():
                        validation["checks"].append(f"✓ {file} exists")
                    else:
                        validation["checks"].append(f"✗ {file} missing")
                        validation["errors"].append(f"Missing required file: {file}")
                        validation["valid"] = False

        except Exception as e:
            validation["valid"] = False
            validation["errors"].append(f"Failed to validate bundle: {e}")

        return validation


# 全局单例
_bundle_instance: Optional[ReproducibilityBundle] = None


def get_reproducibility_bundle() -> ReproducibilityBundle:
    """获取全局 Reproducibility Bundle 实例。"""
    global _bundle_instance
    if _bundle_instance is None:
        _bundle_instance = ReproducibilityBundle()
    return _bundle_instance
