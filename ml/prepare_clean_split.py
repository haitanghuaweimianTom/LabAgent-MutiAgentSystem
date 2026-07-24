"""
构建无数据泄露的干净 train/test 划分
====================================
背景：原有 bug_finder_eval.json 与 bug_finder_train_v7.json 存在大量样本重叠
（约 78% 的评测样本同时出现在训练集），且评测样本内部存在重复，导致指标失真。

本脚本：
1. 汇总 train_v7 + eval_v1 + eval_v5 全部样本
2. 按 instruction 文本去重（保证每个样本唯一）
3. 仅保留 output 为合法 JSON 且 error_type 属于规范标签集的样本
4. 按 error_type 分层抽样，15% 作 test（每类尽量 ≥5），85% 作 train
5. 双重校验：train 与 test 之间零 instruction 重叠

用法：
    python ml/prepare_clean_split.py
输出：
    ml/collected_data/bug_finder_clean_train.json
    ml/collected_data/bug_finder_clean_test.json
"""
from __future__ import annotations

import collections
import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SOURCES = [
    "ml/collected_data/bug_finder_train_v7.json",
    "ml/collected_data/bug_finder_eval.json",      # 80 样本（原报告用）
    "ml/collected_data/bug_finder_eval_v5.json",   # 300 样本
    "ml/collected_data/bug_finder_realtraceback.json",  # 真实执行合成的样本
]

CANONICAL_LABELS = {
    "ValueError", "IndexError", "ZeroDivisionError", "KeyError", "TypeError",
    "AttributeError", "ImportError", "FileNotFoundError", "RuntimeError",
    "SyntaxError", "OOM", "ShapeMismatch", "LogicError", "Timeout",
}

# 同义标签归一化（不同来源写法不一）
SYNONYM_MAP = {
    "ModuleNotFoundError": "ImportError",
    "torch.cuda.OutOfMemoryError": "OOM",
    "cuda.OutOfMemoryError": "OOM",
    "OutOfMemoryError": "OOM",
    "CUDA Out of Memory Error": "OOM",
    "CUDA out of memory": "OOM",
    "RecursionError": "LogicError",
    "NotFittedError": "LogicError",
}

TEST_RATIO = 0.15
SEED = 42


def hash_instr(s: str) -> str:
    return hashlib.md5(s.strip().encode("utf-8")).hexdigest()


def normalize_label(label: str) -> str:
    label = (label or "").strip()
    if label in SYNONYM_MAP:
        label = SYNONYM_MAP[label]
    return label


def load_and_pool() -> list[dict]:
    """汇总所有来源并去重，仅保留标签合法的样本。"""
    seen: set[str] = set()
    pooled: list[dict] = []
    dropped_dup = 0
    dropped_bad = 0
    for src in SOURCES:
        path = ROOT / src
        if not path.exists():
            print(f"[warn] 缺失: {src}")
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for s in data:
            instr = s.get("instruction", "").strip()
            if not instr:
                continue
            h = hash_instr(instr)
            if h in seen:
                dropped_dup += 1
                continue
            # 解析 output 拿到 label
            try:
                out = json.loads(s.get("output", "{}"))
            except Exception:
                dropped_bad += 1
                continue
            label = normalize_label(out.get("error_type", ""))
            if label not in CANONICAL_LABELS:
                dropped_bad += 1
                continue
            seen.add(h)
            rec = dict(s)
            rec["_label"] = label
            # 同步归一化 output 里的 error_type，保证训练标签一致
            out["error_type"] = label
            rec["output"] = json.dumps(out, ensure_ascii=False)
            pooled.append(rec)
    print(f"去重后样本: {len(pooled)}（丢弃重复 {dropped_dup}，丢弃非法标签/输出 {dropped_bad}）")
    return pooled


def stratified_split(pooled: list[dict]) -> tuple[list[dict], list[dict]]:
    rng = random.Random(SEED)
    by_label: dict[str, list[dict]] = collections.defaultdict(list)
    for s in pooled:
        by_label[s["_label"]].append(s)

    train: list[dict] = []
    test: list[dict] = []
    for label, items in sorted(by_label.items()):
        rng.shuffle(items)
        n_test = max(5, int(round(len(items) * TEST_RATIO)))
        n_test = min(n_test, len(items) // 2) if len(items) > 4 else 0
        test.extend(items[:n_test])
        train.extend(items[n_test:])
    rng.shuffle(train)
    rng.shuffle(test)
    return train, test


def verify_no_leakage(train: list[dict], test: list[dict]) -> None:
    th = {hash_instr(s["instruction"]) for s in train}
    eh = {hash_instr(s["instruction"]) for s in test}
    overlap = th & eh
    assert not overlap, f"数据泄露！train/test 重叠 {len(overlap)} 条"
    # test 内部也不应有重复
    assert len(eh) == len(test), "test 内部存在重复样本"


def main():
    pooled = load_and_pool()
    train, test = stratified_split(pooled)
    verify_no_leakage(train, test)

    # 落盘前去掉内部字段
    def clean(items):
        return [{"instruction": s["instruction"], "output": s["output"],
                 "metadata": s.get("metadata", {})} for s in items]

    out_train = ROOT / "ml/collected_data/bug_finder_clean_train.json"
    out_test = ROOT / "ml/collected_data/bug_finder_clean_test.json"
    with open(out_train, "w", encoding="utf-8") as f:
        json.dump(clean(train), f, ensure_ascii=False, indent=2)
    with open(out_test, "w", encoding="utf-8") as f:
        json.dump(clean(test), f, ensure_ascii=False, indent=2)

    # 统计
    tr_dist = collections.Counter(s["_label"] for s in train)
    te_dist = collections.Counter(s["_label"] for s in test)
    print(f"\ntrain: {len(train)} -> {out_train}")
    print(f"test : {len(test)} -> {out_test}")
    print(f"\ntrain 标签分布: {dict(sorted(tr_dist.items(), key=lambda x: -x[1]))}")
    print(f"test  标签分布: {dict(sorted(te_dist.items(), key=lambda x: -x[1]))}")
    print("\n零泄露校验通过 ✓（train/test 间无 instruction 重叠）")


if __name__ == "__main__":
    main()
