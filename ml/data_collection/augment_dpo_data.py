"""
DPO 数据增强脚本
================

从系统运行的论文输出中生成 preference pairs（好 vs 差）。

增强方法：
1. 删除关键公式推导段落
2. 注入错误数字（0.85 → 0.95）
3. 打乱章节顺序
4. 删除实验对比表格
5. 用模糊语言替换精确描述
6. 删除参考文献

20 篇 × 4 个降质版本 = 80 pairs
加上 20 篇中质量差异的自然 pairs ≈ 100~150 pairs
增强后 ~500 个训练样本
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


# 降质策略
DEGRADATION_METHODS = [
    "delete_formula_derivation",
    "inject_wrong_numbers",
    "shuffle_sections",
    "delete_experiment_table",
    "vague_language",
    "delete_references",
]

# 模糊语言替换表
VAGUE_REPLACEMENTS = [
    (r"(\d+\.?\d*%?\s*(?:提升|提高|改善|增加))", "有所提升"),
    (r"(F1\s*[=:]\s*\d+\.?\d+)", "F1 较好"),
    (r"(准确率\s*[=:]\s*\d+\.?\d+)", "准确率较高"),
    (r"(AUC\s*[=:]\s*\d+\.?\d+)", "AUC 表现良好"),
    (r"(Sharpe\s*Ratio\s*[=:]\s*\d+\.?\d+)", "Sharpe Ratio 理想"),
]


class DPODataAugmenter:
    """DPO 数据增强器"""

    def __init__(self, seed: int = 42):
        random.seed(seed)

    def generate_pairs(self, papers: List[Dict[str, Any]],
                       target_count: int = 500) -> List[Dict[str, Any]]:
        """从论文生成 preference pairs"""
        pairs = []

        for paper in papers:
            original_text = paper.get("paper", {}).get("content", "")
            if not original_text or len(original_text) < 200:
                continue

            # 1. 自然 pairs（同一篇论文的不同部分质量差异）
            natural_pairs = self._extract_natural_pairs(paper, original_text)
            pairs.extend(natural_pairs)

            # 2. 降质 pairs
            for method in DEGRADATION_METHODS:
                degraded = self._degrade_text(original_text, method)
                if degraded != original_text:
                    pairs.append({
                        "chosen": original_text[:2000],
                        "rejected": degraded[:2000],
                        "method": method,
                        "problem": paper.get("problem", {}),
                        "dimensions": self._score_pair(original_text, degraded),
                    })

        # 补充合成数据
        while len(pairs) < target_count:
            synthetic = self._generate_synthetic_pair()
            pairs.append(synthetic)

        random.shuffle(pairs)
        return pairs[:target_count]

    def _extract_natural_pairs(self, paper: Dict[str, Any],
                               text: str) -> List[Dict[str, Any]]:
        """从同一篇论文中提取自然质量差异"""
        pairs = []
        sections = self._split_sections(text)

        if len(sections) < 3:
            return pairs

        # 取不同质量的段落组合
        for i in range(len(sections)):
            for j in range(i + 1, min(i + 3, len(sections))):
                if len(sections[i]) > 100 and len(sections[j]) > 100:
                    # 判断哪个质量更高
                    quality_i = self._estimate_quality(sections[i])
                    quality_j = self._estimate_quality(sections[j])

                    if abs(quality_i - quality_j) > 0.1:
                        if quality_i > quality_j:
                            chosen, rejected = sections[i], sections[j]
                        else:
                            chosen, rejected = sections[j], sections[i]

                        pairs.append({
                            "chosen": chosen[:2000],
                            "rejected": rejected[:2000],
                            "method": "natural",
                            "problem": paper.get("problem", {}),
                            "dimensions": {
                                "structure": random.uniform(0.5, 0.9),
                                "innovation": random.uniform(0.4, 0.8),
                                "experiment": random.uniform(0.5, 0.9),
                                "writing": random.uniform(0.5, 0.9),
                            },
                        })

        return pairs[:5]  # 每篇最多 5 个自然 pairs

    def _degrade_text(self, text: str, method: str) -> str:
        """对文本进行降质处理"""
        if method == "delete_formula_derivation":
            return self._delete_formulas(text)
        elif method == "inject_wrong_numbers":
            return self._inject_wrong_numbers(text)
        elif method == "shuffle_sections":
            return self._shuffle_sections(text)
        elif method == "delete_experiment_table":
            return self._delete_tables(text)
        elif method == "vague_language":
            return self._make_vague(text)
        elif method == "delete_references":
            return self._delete_references(text)
        return text

    def _delete_formulas(self, text: str) -> str:
        """删除公式推导段落"""
        # 删除 LaTeX 公式块
        text = re.sub(r"\$.*?\$", "[公式]", text)
        text = re.sub(r"\\begin\{equation\}.*?\\end\{equation\}", "[公式]", text, flags=re.DOTALL)
        # 删除包含"推导"、"证明"的段落
        text = re.sub(r"(?:推导|证明|由此可得|综上所述).*?\n", "", text)
        return text

    def _inject_wrong_numbers(self, text: str) -> str:
        """注入错误数字"""
        def replace_number(match):
            num = float(match.group(0))
            # 随机偏移 5~20%
            factor = random.choice([0.8, 0.85, 0.9, 1.1, 1.15, 1.2])
            return f"{num * factor:.2f}"

        text = re.sub(r"\d+\.\d{2,}", replace_number, text)
        return text

    def _shuffle_sections(self, text: str) -> str:
        """打乱章节顺序"""
        sections = self._split_sections(text)
        if len(sections) > 2:
            # 保持第一个（标题）不动，打乱其余
            header = sections[0]
            rest = sections[1:]
            random.shuffle(rest)
            sections = [header] + rest
        return "\n\n".join(sections)

    def _delete_tables(self, text: str) -> str:
        """删除实验对比表格"""
        # 删除 markdown 表格
        text = re.sub(r"\|.*\|.*\|.*\n(\|[-:| ]+\|\n)?(\|.*\|\n)*", "[表格已删除]\n", text)
        # 删除包含"实验"、"对比"、"结果"的段落
        text = re.sub(r"(?:实验结果|对比分析|如表所示|如图所示).*?\n", "", text)
        return text

    def _make_vague(self, text: str) -> str:
        """用模糊语言替换精确描述"""
        for pattern, replacement in VAGUE_REPLACEMENTS:
            text = re.sub(pattern, replacement, text)
        return text

    def _delete_references(self, text: str) -> str:
        """删除参考文献"""
        text = re.sub(r"(?:参考文献|References|Bibliography).*", "", text, flags=re.DOTALL)
        text = re.sub(r"\[\d+\].*?\n", "", text)
        return text

    def _split_sections(self, text: str) -> List[str]:
        """将文本按章节分割"""
        sections = re.split(r"\n(?=#{1,3}\s)", text)
        if len(sections) <= 1:
            # 按段落分割
            sections = text.split("\n\n")
        return [s.strip() for s in sections if s.strip()]

    def _estimate_quality(self, text: str) -> float:
        """估计文本质量（简单启发式）"""
        score = 0.5
        # 有公式加分
        if "$" in text or "equation" in text.lower():
            score += 0.1
        # 有数字加分
        if re.search(r"\d+\.\d+", text):
            score += 0.1
        # 有引用加分
        if re.search(r"\[\d+\]", text):
            score += 0.1
        # 长度适中加分
        if 200 < len(text) < 2000:
            score += 0.1
        # 模糊语言扣分
        for pattern, _ in VAGUE_REPLACEMENTS:
            if re.search(pattern, text):
                score -= 0.1
        return max(0.0, min(1.0, score))

    def _score_pair(self, chosen: str, rejected: str) -> Dict[str, float]:
        """为 pair 生成 4 维度评分"""
        chosen_quality = self._estimate_quality(chosen)
        rejected_quality = self._estimate_quality(rejected)

        base = chosen_quality - rejected_quality
        return {
            "structure": max(0.1, min(0.9, 0.5 + base * random.uniform(0.5, 1.5))),
            "innovation": max(0.1, min(0.9, 0.5 + base * random.uniform(0.3, 1.2))),
            "experiment": max(0.1, min(0.9, 0.5 + base * random.uniform(0.4, 1.3))),
            "writing": max(0.1, min(0.9, 0.5 + base * random.uniform(0.5, 1.4))),
        }

    def _generate_synthetic_pair(self) -> Dict[str, Any]:
        """生成合成 preference pair"""
        # 好的论文片段
        chosen_templates = [
            "本文提出了一种基于{method}的{task}方法。实验结果表明，该方法在{dataset}数据集上达到了{metric}的性能，相比基线方法提升了{improvement}%。",
            "我们设计了一个{architecture}模型，包含{components}。通过{technique}优化，在{benchmark}上取得了SOTA结果。",
            "本文的主要贡献包括：（1）提出了{contribution1}；（2）设计了{contribution2}；（3）在{dataset}上验证了有效性。",
        ]
        # 差的论文片段
        rejected_templates = [
            "本文提出了一种方法来解决问题。实验表明效果有所提升。",
            "我们设计了一个模型，在一些数据集上进行了测试。",
            "本文做了一些工作，但还有很多不足之处。",
        ]

        methods = ["注意力机制", "图神经网络", "对比学习", "强化学习"]
        tasks = ["文本分类", "情感分析", "命名实体识别", "关系抽取"]
        datasets = ["IMDB", "SST-2", "CoNLL-2003", "ADE"]
        metrics = ["95.2%", "91.8%", "89.3%", "93.7%"]
        improvements = ["3.5", "2.1", "4.8", "1.9"]

        chosen = random.choice(chosen_templates).format(
            method=random.choice(methods),
            task=random.choice(tasks),
            dataset=random.choice(datasets),
            metric=random.choice(metrics),
            improvement=random.choice(improvements),
            architecture="Transformer",
            components="多头注意力和前馈网络",
            technique="AdamW",
            benchmark="标准基准",
            contribution1="新的模型架构",
            contribution2="高效的训练策略",
        )

        rejected = random.choice(rejected_templates)

        return {
            "chosen": chosen,
            "rejected": rejected,
            "method": "synthetic",
            "problem": {},
            "dimensions": {
                "structure": random.uniform(0.3, 0.7),
                "innovation": random.uniform(0.2, 0.6),
                "experiment": random.uniform(0.3, 0.7),
                "writing": random.uniform(0.3, 0.7),
            },
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="DPO 数据增强")
    parser.add_argument("--input", type=str, default="ml/collected_data/extracted_papers.json",
                       help="输入论文文件")
    parser.add_argument("--output", type=str, default="ml/collected_data",
                       help="输出目录")
    parser.add_argument("--target-count", type=int, default=500,
                       help="目标数据条数")
    args = parser.parse_args()

    # 加载论文
    input_path = Path(args.input)
    if input_path.exists():
        with open(input_path) as f:
            papers = json.load(f)
        print(f"加载 {len(papers)} 篇论文")
    else:
        print(f"未找到论文文件 {input_path}，使用合成数据")
        papers = []

    # 增强
    augmenter = DPODataAugmenter()
    pairs = augmenter.generate_pairs(papers, args.target_count)

    # 划分训练/验证
    random.shuffle(pairs)
    split = int(len(pairs) * 0.9)
    train_data = pairs[:split]
    eval_data = pairs[split:]

    # 保存
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_dir / "dpo_train_pairs.json", "w", encoding="utf-8") as f:
        json.dump(train_data, f, ensure_ascii=False, indent=2)

    with open(output_dir / "dpo_eval_pairs.json", "w", encoding="utf-8") as f:
        json.dump(eval_data, f, ensure_ascii=False, indent=2)

    print(f"生成 {len(train_data)} 条训练 pairs, {len(eval_data)} 条验证 pairs")


if __name__ == "__main__":
    main()
