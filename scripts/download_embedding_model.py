#!/usr/bin/env python3
"""预下载 Sentence-Transformers 嵌入模型（v5.3.0）。

为什么需要：
- KnowledgeManager 用 sentence-transformers 做向量化
- 第一次启动会触发 sentence-transformers 库去 HuggingFace 下载模型
- 模型 ~400MB，下载慢且可能因网络抖动失败
- 提前下载到本地缓存，启动时不再阻塞

用法：
    python scripts/download_embedding_model.py

模型选择：
- paraphrase-multilingual-MiniLM-L12-v2
- 支持 50+ 语言（含中英文），体积小（~470MB），速度快，质量好
- 维度 384（适合中小规模 KB）

失败回退：
- 如果下载/加载失败，KnowledgeManager 自动 fallback 到 TF-IDF
- 不影响系统运行，只是检索质量差一点
"""
import os
import sys
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
CACHE_DIR = PROJECT_ROOT / "data" / "models" / "embedding"
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

# 确保依赖可导入
sys.path.insert(0, str(PROJECT_ROOT / "backend"))


def main() -> int:
    print(f"[download_embedding_model] model={MODEL_NAME}")
    print(f"[download_embedding_model] cache={CACHE_DIR}")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(CACHE_DIR))
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(CACHE_DIR))

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print(
            "[download_embedding_model] ERROR: sentence-transformers 未安装。\n"
            "请先 pip install sentence-transformers\n"
            "或运行：pip install -r backend/requirements.txt"
        )
        return 1

    try:
        print(f"[download_embedding_model] 正在下载 {MODEL_NAME} ...")
        model = SentenceTransformer(MODEL_NAME, cache_folder=str(CACHE_DIR))
        # 测试一次 encode 确认模型可用
        embedding = model.encode(["测试一下模型可用性"], normalize_embeddings=True)
        print(
            f"[download_embedding_model] ✓ 下载完成！"
            f"\n  - 嵌入维度: {embedding.shape[1]}"
            f"\n  - 模型缓存: {CACHE_DIR}"
        )
        return 0
    except Exception as e:
        print(
            f"[download_embedding_model] ✗ 下载/加载失败: {e}\n"
            f"\n"
            f"知识库会自动 fallback 到 TF-IDF（无嵌入模型）。\n"
            f"网络问题常见原因：\n"
            f"  - HuggingFace 访问受限（国内网络）\n"
            f"  - 防火墙拦截 huggingface.co\n"
            f"解决：\n"
            f"  1. 重试：python scripts/download_embedding_model.py\n"
            f"  2. 手动从镜像下载到 data/models/embedding/\n"
            f"  3. 使用 HF 镜像：export HF_ENDPOINT=https://hf-mirror.com\n"
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
