"""数据集自动下载与预处理管理器

支持从 HuggingFace Hub、torchvision、自定义 URL 下载数据集，
提供自动预处理、缓存管理和 train/val/test 切分功能。
"""

import hashlib
import json
import logging
import os
import shutil
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


# ===== 数据类定义 =====


@dataclass
class DatasetInfo:
    """数据集元信息"""
    name: str
    source: str  # "huggingface" | "torchvision" | "url" | "local"
    cache_dir: Path
    raw_path: Path
    format: str  # "hf", "torchvision", "csv", "json", "image_folder", "zip", "tar.gz"
    metadata: Dict[str, Any] = field(default_factory=dict)
    downloaded: bool = False
    description: str = ""


@dataclass
class ProcessedDataset:
    """预处理后的数据集"""
    name: str
    base_dir: Path
    train_dir: Optional[Path] = None
    val_dir: Optional[Path] = None
    test_dir: Optional[Path] = None
    vocab_path: Optional[Path] = None
    label_map: Optional[Dict[str, int]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ===== 异常定义 =====


class DatasetDownloadError(Exception):
    """下载失败"""
    pass


class DatasetFormatError(Exception):
    """格式不支持或解析失败"""
    pass


class DatasetPreprocessError(Exception):
    """预处理失败"""
    pass


# ===== 数据集配置 =====


AVAILABLE_DATASETS: List[Dict[str, Any]] = [
    {
        "name": "imdb",
        "source": "huggingface",
        "hf_id": "imdb",
        "description": "IMDB 电影评论情感分类（50K 条）",
        "task": "text_classification",
        "classes": 2,
    },
    {
        "name": "cifar10",
        "source": "torchvision",
        "torch_id": "CIFAR10",
        "description": "CIFAR-10 图像分类（60K 32x32 彩图）",
        "task": "image_classification",
        "classes": 10,
    },
    {
        "name": "mnist",
        "source": "torchvision",
        "torch_id": "MNIST",
        "description": "MNIST 手写数字识别（70K 28x28 灰度图）",
        "task": "image_classification",
        "classes": 10,
    },
    {
        "name": "glue_sst2",
        "source": "huggingface",
        "hf_id": "glue",
        "hf_subset": "sst2",
        "description": "GLUE SST-2 句子情感分类",
        "task": "text_classification",
        "classes": 2,
    },
    {
        "name": "glue_mrpc",
        "source": "huggingface",
        "hf_id": "glue",
        "hf_subset": "mrpc",
        "description": "GLUE MRPC 句子对语义等价判断",
        "task": "text_classification",
        "classes": 2,
    },
    {
        "name": "glue_qnli",
        "source": "huggingface",
        "hf_id": "glue",
        "hf_subset": "qnli",
        "description": "GLUE QNLI 问答自然语言推断",
        "task": "text_classification",
        "classes": 2,
    },
    {
        "name": "custom_csv",
        "source": "local",
        "description": "自定义 CSV 文件（需指定 path）",
        "task": "custom",
    },
]


# ===== 核心类 =====


class DatasetManager:
    """数据集自动下载与预处理管理器

    用法::
        dm = DatasetManager(cache_dir="./datasets")
        info = dm.download("imdb", source="huggingface")
        processed = dm.preprocess(info, {"text_column": "text", "label_column": "label"})
        splits = dm.get_splits(processed)
    """

    def __init__(self, cache_dir: str = "./datasets"):
        self.cache_dir = Path(cache_dir).expanduser().resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_index_file = self.cache_dir / "_cache_index.json"
        self._cache_index: Dict[str, Any] = {}
        self._load_cache_index()

    # ----- 缓存管理 -----

    def _load_cache_index(self) -> None:
        """加载缓存索引"""
        if self._cache_index_file.exists():
            try:
                with open(self._cache_index_file, "r", encoding="utf-8") as f:
                    self._cache_index = json.load(f)
            except Exception as e:
                logger.warning(f"[DatasetManager] 加载缓存索引失败: {e}")
                self._cache_index = {}

    def _save_cache_index(self) -> None:
        """保存缓存索引"""
        try:
            with open(self._cache_index_file, "w", encoding="utf-8") as f:
                json.dump(self._cache_index, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[DatasetManager] 保存缓存索引失败: {e}")

    def _get_cache_key(self, name: str, source: str, **kwargs) -> str:
        """生成缓存键"""
        payload = f"{name}:{source}:{sorted(kwargs.items())}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def _is_cached(self, cache_key: str) -> bool:
        """检查是否已缓存"""
        entry = self._cache_index.get(cache_key)
        if not entry:
            return False
        raw_path = Path(entry.get("raw_path", ""))
        return raw_path.exists()

    def _register_cache(self, cache_key: str, info: DatasetInfo) -> None:
        """注册缓存"""
        self._cache_index[cache_key] = {
            "name": info.name,
            "source": info.source,
            "raw_path": str(info.raw_path),
            "format": info.format,
            "metadata": info.metadata,
        }
        self._save_cache_index()

    def clear_cache(self, name: Optional[str] = None) -> int:
        """清除缓存。name 为 None 时清除全部。返回删除的条目数。"""
        removed = 0
        keys_to_remove = []
        for key, entry in list(self._cache_index.items()):
            if name is None or entry.get("name") == name:
                raw_path = Path(entry.get("raw_path", ""))
                if raw_path.exists():
                    try:
                        if raw_path.is_dir():
                            shutil.rmtree(raw_path)
                        else:
                            raw_path.unlink()
                    except Exception as e:
                        logger.warning(f"[DatasetManager] 删除缓存文件失败: {e}")
                keys_to_remove.append(key)
                removed += 1
        for k in keys_to_remove:
            self._cache_index.pop(k, None)
        self._save_cache_index()
        return removed

    # ----- 下载接口 -----

    def download(self, name: str, source: str = "huggingface", **kwargs) -> DatasetInfo:
        """下载数据集并返回元信息

        Args:
            name: 数据集名称（如 "imdb", "cifar10", "custom_csv"）
            source: 来源类型（"huggingface" | "torchvision" | "url" | "local"）
            **kwargs: 额外参数
                - huggingface: subset, split, revision
                - torchvision: root, download, train
                - url: url, extract
                - local: path

        Returns:
            DatasetInfo 对象
        """
        cache_key = self._get_cache_key(name, source, **kwargs)
        raw_dir = self.cache_dir / "raw" / f"{name}_{cache_key}"
        raw_dir.mkdir(parents=True, exist_ok=True)

        if self._is_cached(cache_key):
            logger.info(f"[DatasetManager] 命中缓存: {name} ({cache_key})")
            entry = self._cache_index[cache_key]
            return DatasetInfo(
                name=name,
                source=source,
                cache_dir=self.cache_dir,
                raw_path=Path(entry["raw_path"]),
                format=entry["format"],
                metadata=entry["metadata"],
                downloaded=True,
            )

        logger.info(f"[DatasetManager] 开始下载: {name} (source={source})")

        try:
            if source == "huggingface":
                info = self._download_huggingface(name, raw_dir, **kwargs)
            elif source == "torchvision":
                info = self._download_torchvision(name, raw_dir, **kwargs)
            elif source == "url":
                info = self._download_url(name, raw_dir, **kwargs)
            elif source == "local":
                info = self._download_local(name, raw_dir, **kwargs)
            else:
                raise DatasetFormatError(f"不支持的 source 类型: {source}")
        except Exception as e:
            logger.error(f"[DatasetManager] 下载 {name} 失败: {e}")
            raise DatasetDownloadError(f"下载 {name} 失败: {e}") from e

        info.downloaded = True
        self._register_cache(cache_key, info)
        logger.info(f"[DatasetManager] 下载完成: {name} -> {info.raw_path}")
        return info

    def _download_huggingface(self, name: str, raw_dir: Path, **kwargs) -> DatasetInfo:
        """从 HuggingFace Hub 下载"""
        try:
            from datasets import load_dataset
        except ImportError as e:
            raise DatasetDownloadError("请安装 datasets 库: pip install datasets") from e

        # 查找配置
        config = next((d for d in AVAILABLE_DATASETS if d["name"] == name), None)
        hf_id = kwargs.get("hf_id") or (config["hf_id"] if config else name)
        subset = kwargs.get("subset") or (config.get("hf_subset") if config else None)
        split = kwargs.get("split", None)
        revision = kwargs.get("revision", None)

        save_path = raw_dir / "hf_dataset"

        try:
            if subset:
                ds = load_dataset(hf_id, subset, split=split, revision=revision)
            else:
                ds = load_dataset(hf_id, split=split, revision=revision)
            ds.save_to_disk(str(save_path))
        except Exception as e:
            raise DatasetDownloadError(f"HuggingFace 加载失败: {e}") from e

        return DatasetInfo(
            name=name,
            source="huggingface",
            cache_dir=self.cache_dir,
            raw_path=save_path,
            format="hf",
            metadata={"hf_id": hf_id, "subset": subset, "split": split},
            description=config.get("description", "") if config else "",
        )

    def _download_torchvision(self, name: str, raw_dir: Path, **kwargs) -> DatasetInfo:
        """从 torchvision 下载标准数据集"""
        try:
            import torchvision.datasets as tv_datasets
            import torchvision.transforms as transforms
        except ImportError as e:
            raise DatasetDownloadError("请安装 torchvision 库: pip install torchvision") from e

        config = next((d for d in AVAILABLE_DATASETS if d["name"] == name), None)
        torch_id = kwargs.get("torch_id") or (config["torch_id"] if config else name.upper())

        # 统一使用标准 transform（ToTensor）
        transform = transforms.ToTensor()
        dataset_root = raw_dir / "torchvision"

        try:
            if torch_id == "MNIST":
                tv_datasets.MNIST(root=str(dataset_root), train=True, download=True, transform=transform)
                tv_datasets.MNIST(root=str(dataset_root), train=False, download=True, transform=transform)
            elif torch_id == "CIFAR10":
                tv_datasets.CIFAR10(root=str(dataset_root), train=True, download=True, transform=transform)
                tv_datasets.CIFAR10(root=str(dataset_root), train=False, download=True, transform=transform)
            elif torch_id == "CIFAR100":
                tv_datasets.CIFAR100(root=str(dataset_root), train=True, download=True, transform=transform)
                tv_datasets.CIFAR100(root=str(dataset_root), train=False, download=True, transform=transform)
            elif torch_id == "FashionMNIST":
                tv_datasets.FashionMNIST(root=str(dataset_root), train=True, download=True, transform=transform)
                tv_datasets.FashionMNIST(root=str(dataset_root), train=False, download=True, transform=transform)
            else:
                # 尝试反射获取
                ds_cls = getattr(tv_datasets, torch_id, None)
                if ds_cls is None:
                    raise DatasetFormatError(f"torchvision 不支持的数据集: {torch_id}")
                ds_cls(root=str(dataset_root), train=True, download=True, transform=transform)
                if hasattr(ds_cls, "train"):
                    ds_cls(root=str(dataset_root), train=False, download=True, transform=transform)
        except Exception as e:
            raise DatasetDownloadError(f"torchvision 下载失败: {e}") from e

        return DatasetInfo(
            name=name,
            source="torchvision",
            cache_dir=self.cache_dir,
            raw_path=dataset_root,
            format="image_folder",
            metadata={"torch_id": torch_id},
            description=config.get("description", "") if config else "",
        )

    def _download_url(self, name: str, raw_dir: Path, **kwargs) -> DatasetInfo:
        """从自定义 URL 下载（支持 zip / tar.gz）"""
        url = kwargs.get("url")
        if not url:
            raise DatasetDownloadError("url 来源必须提供 url 参数")

        extract = kwargs.get("extract", True)
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path) or "download"
        download_path = raw_dir / filename

        # 下载
        try:
            resp = requests.get(url, stream=True, timeout=300)
            resp.raise_for_status()
            with open(download_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
        except Exception as e:
            raise DatasetDownloadError(f"URL 下载失败: {e}") from e

        # 解压
        if extract:
            if filename.endswith(".zip"):
                extract_dir = raw_dir / "extracted"
                try:
                    with zipfile.ZipFile(download_path, "r") as zf:
                        zf.extractall(str(extract_dir))
                except Exception as e:
                    raise DatasetFormatError(f"zip 解压失败: {e}") from e
                return DatasetInfo(
                    name=name,
                    source="url",
                    cache_dir=self.cache_dir,
                    raw_path=extract_dir,
                    format="zip",
                    metadata={"url": url, "original_file": filename},
                )
            elif filename.endswith((".tar.gz", ".tgz")):
                extract_dir = raw_dir / "extracted"
                try:
                    with tarfile.open(download_path, "r:gz") as tf:
                        tf.extractall(str(extract_dir))
                except Exception as e:
                    raise DatasetFormatError(f"tar.gz 解压失败: {e}") from e
                return DatasetInfo(
                    name=name,
                    source="url",
                    cache_dir=self.cache_dir,
                    raw_path=extract_dir,
                    format="tar.gz",
                    metadata={"url": url, "original_file": filename},
                )
            else:
                # 不识别格式，保留原文件
                return DatasetInfo(
                    name=name,
                    source="url",
                    cache_dir=self.cache_dir,
                    raw_path=download_path,
                    format="unknown",
                    metadata={"url": url, "original_file": filename},
                )

        return DatasetInfo(
            name=name,
            source="url",
            cache_dir=self.cache_dir,
            raw_path=download_path,
            format="unknown",
            metadata={"url": url, "original_file": filename},
        )

    def _download_local(self, name: str, raw_dir: Path, **kwargs) -> DatasetInfo:
        """本地文件/目录"""
        path = kwargs.get("path")
        if not path:
            raise DatasetDownloadError("local 来源必须提供 path 参数")

        src = Path(path).expanduser().resolve()
        if not src.exists():
            raise DatasetDownloadError(f"本地路径不存在: {src}")

        # 复制到缓存目录
        dst = raw_dir / "local_copy"
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst / src.name)

        # 推断格式
        if src.is_dir():
            fmt = "image_folder" if any(src.rglob("*.jpg")) or any(src.rglob("*.png")) else "folder"
        else:
            ext = src.suffix.lower()
            fmt = {"csv": "csv", "json": "json", "jsonl": "json", "txt": "text"}.get(ext, "unknown")

        return DatasetInfo(
            name=name,
            source="local",
            cache_dir=self.cache_dir,
            raw_path=dst,
            format=fmt,
            metadata={"original_path": str(src)},
        )

    # ----- 预处理接口 -----

    def preprocess(self, dataset_info: DatasetInfo, config: Dict[str, Any]) -> ProcessedDataset:
        """对数据集进行自动预处理

        Args:
            dataset_info: download() 返回的元信息
            config: 预处理配置
                - text_column: 文本列名（文本任务）
                - label_column: 标签列名
                - image_size: 图像尺寸（图像任务）
                - normalize: 是否标准化（图像任务）
                - split_ratio: [train, val, test] 比例，默认 [0.8, 0.1, 0.1]
                - tokenizer: 分词器类型（"simple" | "bert" | "whitespace"）
                - max_length: 最大序列长度
                - seed: 随机种子

        Returns:
            ProcessedDataset 对象
        """
        if not dataset_info.downloaded or not dataset_info.raw_path.exists():
            raise DatasetPreprocessError("数据集尚未下载或缓存丢失")

        proc_dir = self.cache_dir / "processed" / f"{dataset_info.name}_{dataset_info.raw_path.name}"
        proc_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"[DatasetManager] 开始预处理: {dataset_info.name} (format={dataset_info.format})")

        try:
            if dataset_info.format == "hf":
                processed = self._preprocess_hf(dataset_info, proc_dir, config)
            elif dataset_info.format == "image_folder":
                processed = self._preprocess_image_folder(dataset_info, proc_dir, config)
            elif dataset_info.format == "csv":
                processed = self._preprocess_csv(dataset_info, proc_dir, config)
            elif dataset_info.format == "json":
                processed = self._preprocess_json(dataset_info, proc_dir, config)
            elif dataset_info.format in ("zip", "tar.gz", "folder"):
                # 尝试按图像文件夹处理，否则报错
                processed = self._preprocess_generic_folder(dataset_info, proc_dir, config)
            else:
                raise DatasetFormatError(f"不支持预处理的数据格式: {dataset_info.format}")
        except Exception as e:
            logger.error(f"[DatasetManager] 预处理失败: {e}")
            raise DatasetPreprocessError(f"预处理失败: {e}") from e

        logger.info(f"[DatasetManager] 预处理完成: {dataset_info.name}")
        return processed

    def _preprocess_hf(self, info: DatasetInfo, proc_dir: Path, config: Dict[str, Any]) -> ProcessedDataset:
        """预处理 HuggingFace 数据集"""
        try:
            from datasets import load_from_disk
        except ImportError as e:
            raise DatasetPreprocessError("请安装 datasets 库") from e

        ds = load_from_disk(str(info.raw_path))
        text_col = config.get("text_column", "text")
        label_col = config.get("label_column", "label")
        tokenizer_type = config.get("tokenizer", "simple")
        max_length = config.get("max_length", 512)
        split_ratio = config.get("split_ratio", [0.8, 0.1, 0.1])
        seed = config.get("seed", 42)

        # 确定列名（自动推断）
        if isinstance(ds, dict):
            sample_split = list(ds.keys())[0]
            columns = ds[sample_split].column_names
        else:
            columns = ds.column_names

        if text_col not in columns:
            # 自动推断文本列
            candidates = [c for c in columns if c in ("text", "sentence", "review", "content", "premise")]
            if candidates:
                text_col = candidates[0]
            else:
                text_col = columns[0]

        if label_col not in columns:
            candidates = [c for c in columns if c in ("label", "labels", "target", "class")]
            if candidates:
                label_col = candidates[0]
            else:
                label_col = columns[-1] if len(columns) > 1 else columns[0]

        # 分词
        vocab: Dict[str, int] = {}
        if tokenizer_type == "bert":
            try:
                from transformers import BertTokenizer
                tokenizer = BertTokenizer.from_pretrained("bert-base-uncased")
            except ImportError:
                logger.warning("[DatasetManager] transformers 未安装，回退到 simple 分词")
                tokenizer_type = "simple"

        def tokenize_fn(text: str) -> List[str]:
            if tokenizer_type == "bert" and "tokenizer" in locals():
                return tokenizer.tokenize(text)
            elif tokenizer_type == "whitespace":
                return text.split()
            else:
                # simple: 小写 + 按非字母数字切分
                import re
                return re.findall(r"[a-z0-9]+", text.lower())

        # 处理数据并保存为 jsonl
        def process_split(split_ds, split_name: str) -> Path:
            out_dir = proc_dir / split_name
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / "data.jsonl"

            with open(out_file, "w", encoding="utf-8") as f:
                for item in split_ds:
                    text = str(item.get(text_col, ""))
                    label = item.get(label_col, 0)
                    tokens = tokenize_fn(text)[:max_length]
                    # 构建词汇表
                    for tok in tokens:
                        if tok not in vocab:
                            vocab[tok] = len(vocab) + 1  # 0 留给 padding
                    record = {
                        "text": text,
                        "tokens": tokens,
                        "label": label,
                        "token_ids": [vocab[t] for t in tokens],
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

            return out_dir

        if isinstance(ds, dict):
            # 已有预切分
            train_dir = val_dir = test_dir = None
            for split_name in ds.keys():
                split_dir = process_split(ds[split_name], split_name)
                if "train" in split_name:
                    train_dir = split_dir
                elif "validation" in split_name or "dev" in split_name:
                    val_dir = split_dir
                elif "test" in split_name:
                    test_dir = split_dir
        else:
            # 无预切分，自行切分
            ds = ds.shuffle(seed=seed)
            total = len(ds)
            train_end = int(total * split_ratio[0])
            val_end = train_end + int(total * split_ratio[1])

            train_ds = ds.select(range(0, train_end))
            val_ds = ds.select(range(train_end, val_end)) if split_ratio[1] > 0 else None
            test_ds = ds.select(range(val_end, total)) if split_ratio[2] > 0 else None

            train_dir = process_split(train_ds, "train")
            val_dir = process_split(val_ds, "val") if val_ds else None
            test_dir = process_split(test_ds, "test") if test_ds else None

        # 保存词汇表
        vocab_path = proc_dir / "vocab.json"
        with open(vocab_path, "w", encoding="utf-8") as f:
            json.dump(vocab, f, ensure_ascii=False, indent=2)

        # 构建 label_map
        label_map: Optional[Dict[str, int]] = None
        if isinstance(ds, dict):
            sample_split = list(ds.keys())[0]
            features = ds[sample_split].features
        else:
            features = ds.features

        if label_col in features:
            feat = features[label_col]
            if hasattr(feat, "names"):
                label_map = {name: i for i, name in enumerate(feat.names)}

        return ProcessedDataset(
            name=info.name,
            base_dir=proc_dir,
            train_dir=train_dir,
            val_dir=val_dir,
            test_dir=test_dir,
            vocab_path=vocab_path,
            label_map=label_map,
            metadata={
                "text_column": text_col,
                "label_column": label_col,
                "tokenizer": tokenizer_type,
                "vocab_size": len(vocab),
            },
        )

    def _preprocess_image_folder(self, info: DatasetInfo, proc_dir: Path, config: Dict[str, Any]) -> ProcessedDataset:
        """预处理 torchvision / 图像文件夹数据集"""
        try:
            import torchvision.transforms as transforms
            from PIL import Image
        except ImportError as e:
            raise DatasetPreprocessError("请安装 torchvision 和 Pillow") from e

        image_size = config.get("image_size", 224)
        normalize = config.get("normalize", True)
        split_ratio = config.get("split_ratio", [0.8, 0.1, 0.1])
        seed = config.get("seed", 42)

        # 构建 transform
        tf_list = [transforms.Resize((image_size, image_size)), transforms.ToTensor()]
        if normalize:
            tf_list.append(transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]))
        transform = transforms.Compose(tf_list)

        # 查找所有图像
        raw_path = info.raw_path
        image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}

        # 如果是 torchvision 下载的数据集，结构为 raw_path / MNIST / raw / ...
        # 直接返回原始路径，不做额外复制（torchvision 已处理）
        if info.source == "torchvision":
            return ProcessedDataset(
                name=info.name,
                base_dir=raw_path,
                train_dir=raw_path,  # torchvision 内部管理 train/test
                metadata={"source": "torchvision", "image_size": image_size, "normalize": normalize},
            )

        # 扫描图像文件夹（按子目录作为类别）
        images_by_class: Dict[str, List[Path]] = {}
        for img_path in raw_path.rglob("*"):
            if img_path.suffix.lower() in image_exts and img_path.is_file():
                # 推断类别（父目录名）
                class_name = img_path.parent.name
                images_by_class.setdefault(class_name, []).append(img_path)

        if not images_by_class:
            raise DatasetPreprocessError(f"在 {raw_path} 中未找到图像文件")

        # 构建 label_map
        label_map = {name: i for i, name in enumerate(sorted(images_by_class.keys()))}

        # 切分并保存
        import random
        random.seed(seed)

        def save_split(class_images: Dict[str, List[Path]], split_name: str) -> Path:
            out_dir = proc_dir / split_name
            out_dir.mkdir(parents=True, exist_ok=True)
            for class_name, imgs in class_images.items():
                class_dir = out_dir / class_name
                class_dir.mkdir(parents=True, exist_ok=True)
                for img_path in imgs:
                    try:
                        img = Image.open(img_path).convert("RGB")
                        tensor = transform(img)
                        # 保存为 pt 文件
                        save_name = img_path.stem + ".pt"
                        import torch
                        torch.save({"tensor": tensor, "label": label_map[class_name]}, class_dir / save_name)
                    except Exception as e:
                        logger.warning(f"[DatasetManager] 处理图像失败 {img_path}: {e}")
            return out_dir

        # 按类别切分
        train_images: Dict[str, List[Path]] = {}
        val_images: Dict[str, List[Path]] = {}
        test_images: Dict[str, List[Path]] = {}

        for class_name, imgs in images_by_class.items():
            random.shuffle(imgs)
            total = len(imgs)
            t_end = int(total * split_ratio[0])
            v_end = t_end + int(total * split_ratio[1])
            train_images[class_name] = imgs[:t_end]
            val_images[class_name] = imgs[t_end:v_end] if split_ratio[1] > 0 else []
            test_images[class_name] = imgs[v_end:] if split_ratio[2] > 0 else []

        train_dir = save_split(train_images, "train")
        val_dir = save_split(val_images, "val") if any(val_images.values()) else None
        test_dir = save_split(test_images, "test") if any(test_images.values()) else None

        # 保存 label_map
        label_map_path = proc_dir / "label_map.json"
        with open(label_map_path, "w", encoding="utf-8") as f:
            json.dump(label_map, f, ensure_ascii=False, indent=2)

        return ProcessedDataset(
            name=info.name,
            base_dir=proc_dir,
            train_dir=train_dir,
            val_dir=val_dir,
            test_dir=test_dir,
            label_map=label_map,
            metadata={
                "image_size": image_size,
                "normalize": normalize,
                "num_classes": len(label_map),
                "source": info.source,
            },
        )

    def _preprocess_csv(self, info: DatasetInfo, proc_dir: Path, config: Dict[str, Any]) -> ProcessedDataset:
        """预处理 CSV 数据集"""
        try:
            import csv
        except ImportError:
            raise DatasetPreprocessError("CSV 预处理需要标准库 csv")

        text_col = config.get("text_column", "text")
        label_col = config.get("label_column", "label")
        split_ratio = config.get("split_ratio", [0.8, 0.1, 0.1])
        seed = config.get("seed", 42)
        tokenizer_type = config.get("tokenizer", "simple")
        max_length = config.get("max_length", 512)

        # 查找 CSV 文件
        csv_files = list(info.raw_path.rglob("*.csv"))
        if not csv_files:
            raise DatasetPreprocessError(f"在 {info.raw_path} 中未找到 CSV 文件")

        csv_path = csv_files[0]

        # 读取
        rows: List[Dict[str, Any]] = []
        with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

        if not rows:
            raise DatasetPreprocessError("CSV 文件为空")

        columns = list(rows[0].keys())
        if text_col not in columns:
            candidates = [c for c in columns if c in ("text", "sentence", "review", "content", "premise")]
            text_col = candidates[0] if candidates else columns[0]
        if label_col not in columns:
            candidates = [c for c in columns if c in ("label", "labels", "target", "class")]
            label_col = candidates[0] if candidates else columns[-1]

        # 分词
        import random
        import re
        random.seed(seed)

        vocab: Dict[str, int] = {}

        def tokenize(text: str) -> List[str]:
            if tokenizer_type == "whitespace":
                return text.split()
            else:
                return re.findall(r"[a-z0-9]+", text.lower())

        # 标签映射（字符串标签转整数）
        unique_labels = sorted(set(str(r.get(label_col, "")) for r in rows))
        label_map = {lbl: i for i, lbl in enumerate(unique_labels)}

        # 处理并保存
        random.shuffle(rows)
        total = len(rows)
        t_end = int(total * split_ratio[0])
        v_end = t_end + int(total * split_ratio[1])

        train_rows = rows[:t_end]
        val_rows = rows[t_end:v_end] if split_ratio[1] > 0 else []
        test_rows = rows[v_end:] if split_ratio[2] > 0 else []

        def save_split(data: List[Dict[str, Any]], split_name: str) -> Path:
            out_dir = proc_dir / split_name
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / "data.jsonl"
            with open(out_file, "w", encoding="utf-8") as f:
                for row in data:
                    text = str(row.get(text_col, ""))
                    raw_label = str(row.get(label_col, ""))
                    tokens = tokenize(text)[:max_length]
                    for tok in tokens:
                        if tok not in vocab:
                            vocab[tok] = len(vocab) + 1
                    record = {
                        "text": text,
                        "tokens": tokens,
                        "label": label_map.get(raw_label, 0),
                        "token_ids": [vocab[t] for t in tokens],
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            return out_dir

        train_dir = save_split(train_rows, "train")
        val_dir = save_split(val_rows, "val") if val_rows else None
        test_dir = save_split(test_rows, "test") if test_rows else None

        vocab_path = proc_dir / "vocab.json"
        with open(vocab_path, "w", encoding="utf-8") as f:
            json.dump(vocab, f, ensure_ascii=False, indent=2)

        return ProcessedDataset(
            name=info.name,
            base_dir=proc_dir,
            train_dir=train_dir,
            val_dir=val_dir,
            test_dir=test_dir,
            vocab_path=vocab_path,
            label_map=label_map,
            metadata={
                "text_column": text_col,
                "label_column": label_col,
                "tokenizer": tokenizer_type,
                "vocab_size": len(vocab),
            },
        )

    def _preprocess_json(self, info: DatasetInfo, proc_dir: Path, config: Dict[str, Any]) -> ProcessedDataset:
        """预处理 JSON/JSONL 数据集"""
        text_col = config.get("text_column", "text")
        label_col = config.get("label_column", "label")
        split_ratio = config.get("split_ratio", [0.8, 0.1, 0.1])
        seed = config.get("seed", 42)
        tokenizer_type = config.get("tokenizer", "simple")
        max_length = config.get("max_length", 512)

        json_files = list(info.raw_path.rglob("*.json")) + list(info.raw_path.rglob("*.jsonl"))
        if not json_files:
            raise DatasetPreprocessError(f"在 {info.raw_path} 中未找到 JSON/JSONL 文件")

        data_path = json_files[0]
        rows: List[Dict[str, Any]] = []

        with open(data_path, "r", encoding="utf-8", errors="replace") as f:
            if data_path.suffix == ".jsonl":
                for line in f:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
            else:
                content = json.load(f)
                if isinstance(content, list):
                    rows = content
                else:
                    rows = [content]

        if not rows:
            raise DatasetPreprocessError("JSON 文件为空")

        columns = list(rows[0].keys()) if isinstance(rows[0], dict) else []
        if text_col not in columns:
            candidates = [c for c in columns if c in ("text", "sentence", "review", "content")]
            text_col = candidates[0] if candidates else (columns[0] if columns else "")
        if label_col not in columns:
            candidates = [c for c in columns if c in ("label", "labels", "target", "class")]
            label_col = candidates[0] if candidates else (columns[-1] if columns else "")

        import random
        import re
        random.seed(seed)

        vocab: Dict[str, int] = {}

        def tokenize(text: str) -> List[str]:
            if tokenizer_type == "whitespace":
                return text.split()
            else:
                return re.findall(r"[a-z0-9]+", text.lower())

        unique_labels = sorted(set(str(r.get(label_col, "")) for r in rows if isinstance(r, dict)))
        label_map = {lbl: i for i, lbl in enumerate(unique_labels)} if unique_labels else None

        random.shuffle(rows)
        total = len(rows)
        t_end = int(total * split_ratio[0])
        v_end = t_end + int(total * split_ratio[1])

        train_rows = rows[:t_end]
        val_rows = rows[t_end:v_end] if split_ratio[1] > 0 else []
        test_rows = rows[v_end:] if split_ratio[2] > 0 else []

        def save_split(data: List[Dict[str, Any]], split_name: str) -> Path:
            out_dir = proc_dir / split_name
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / "data.jsonl"
            with open(out_file, "w", encoding="utf-8") as f:
                for row in data:
                    if not isinstance(row, dict):
                        continue
                    text = str(row.get(text_col, ""))
                    raw_label = str(row.get(label_col, ""))
                    tokens = tokenize(text)[:max_length]
                    for tok in tokens:
                        if tok not in vocab:
                            vocab[tok] = len(vocab) + 1
                    record = {
                        "text": text,
                        "tokens": tokens,
                        "label": label_map.get(raw_label, 0) if label_map else 0,
                        "token_ids": [vocab[t] for t in tokens],
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            return out_dir

        train_dir = save_split(train_rows, "train")
        val_dir = save_split(val_rows, "val") if val_rows else None
        test_dir = save_split(test_rows, "test") if test_rows else None

        vocab_path = proc_dir / "vocab.json"
        with open(vocab_path, "w", encoding="utf-8") as f:
            json.dump(vocab, f, ensure_ascii=False, indent=2)

        return ProcessedDataset(
            name=info.name,
            base_dir=proc_dir,
            train_dir=train_dir,
            val_dir=val_dir,
            test_dir=test_dir,
            vocab_path=vocab_path,
            label_map=label_map,
            metadata={
                "text_column": text_col,
                "label_column": label_col,
                "tokenizer": tokenizer_type,
                "vocab_size": len(vocab),
            },
        )

    def _preprocess_generic_folder(self, info: DatasetInfo, proc_dir: Path, config: Dict[str, Any]) -> ProcessedDataset:
        """通用文件夹：先尝试作为图像文件夹处理"""
        image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
        has_images = any(p.suffix.lower() in image_exts for p in info.raw_path.rglob("*") if p.is_file())

        if has_images:
            # 伪装成 image_folder 处理
            info_copy = DatasetInfo(
                name=info.name,
                source=info.source,
                cache_dir=info.cache_dir,
                raw_path=info.raw_path,
                format="image_folder",
                metadata=info.metadata,
                downloaded=True,
            )
            return self._preprocess_image_folder(info_copy, proc_dir, config)

        # 尝试 CSV
        csv_files = list(info.raw_path.rglob("*.csv"))
        if csv_files:
            info_copy = DatasetInfo(
                name=info.name,
                source=info.source,
                cache_dir=info.cache_dir,
                raw_path=info.raw_path,
                format="csv",
                metadata=info.metadata,
                downloaded=True,
            )
            return self._preprocess_csv(info_copy, proc_dir, config)

        # 尝试 JSON
        json_files = list(info.raw_path.rglob("*.json")) + list(info.raw_path.rglob("*.jsonl"))
        if json_files:
            info_copy = DatasetInfo(
                name=info.name,
                source=info.source,
                cache_dir=info.cache_dir,
                raw_path=info.raw_path,
                format="json",
                metadata=info.metadata,
                downloaded=True,
            )
            return self._preprocess_json(info_copy, proc_dir, config)

        raise DatasetFormatError(f"无法识别文件夹内容类型: {info.raw_path}")

    # ----- 获取切分路径 -----

    def get_splits(self, processed: ProcessedDataset) -> Dict[str, Optional[str]]:
        """获取 train/val/test 的数据路径

        Returns:
            {"train": "...", "val": "...", "test": "..."}
            不存在的 split 对应值为 None
        """
        return {
            "train": str(processed.train_dir) if processed.train_dir else None,
            "val": str(processed.val_dir) if processed.val_dir else None,
            "test": str(processed.test_dir) if processed.test_dir else None,
        }

    # ----- 列出可用数据集 -----

    def list_available(self) -> List[Dict[str, Any]]:
        """返回常用数据集列表"""
        return [
            {
                "name": d["name"],
                "source": d["source"],
                "description": d.get("description", ""),
                "task": d.get("task", ""),
                "classes": d.get("classes"),
            }
            for d in AVAILABLE_DATASETS
        ]

    # ----- 便捷方法 -----

    def download_and_preprocess(
        self,
        name: str,
        source: str = "huggingface",
        config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> ProcessedDataset:
        """一键下载+预处理"""
        info = self.download(name, source=source, **kwargs)
        return self.preprocess(info, config or {})

    def get_dataset_info(self, name: str) -> Optional[Dict[str, Any]]:
        """获取数据集配置信息"""
        return next((d for d in AVAILABLE_DATASETS if d["name"] == name), None)


# ===== 全局单例 =====

_dataset_manager: Optional[DatasetManager] = None


def get_dataset_manager(cache_dir: Optional[str] = None) -> DatasetManager:
    """获取数据集管理器单例"""
    global _dataset_manager
    if _dataset_manager is None:
        _dataset_manager = DatasetManager(cache_dir=cache_dir or "./datasets")
    return _dataset_manager
