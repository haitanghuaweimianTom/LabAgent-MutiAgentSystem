"""
消融实验脚本
===========

逐个移除模块，验证每个模块的独立贡献。

评估维度：
1. Bug Finder 对代码修复成功率的影响
2. Reward Model 对论文质量评分的影响
3. Reranker 对检索质量的影响
4. Bandit 对重试次数的影响

用法：
    python ml/evaluation/eval_ablation.py --baseline-results ml/results/baseline.json --ablation-results ml/results/ablation/
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# 消融实验配置
ABLATION_CONFIGS = [
    {
        "name": "full_system",
        "description": "完整系统（所有模块启用）",
        "modules": ["bug_finder", "reward_model", "reranker", "bandit"],
    },
    {
        "name": "no_bug_finder",
        "description": "移除 Bug Finder（使用原始 DebuggerAgent）",
        "modules": ["reward_model", "reranker", "bandit"],
    },
    {
        "name": "no_reward_model",
        "description": "移除 Reward Model（使用原始 prompt-based 评估）",
        "modules": ["bug_finder", "reranker", "bandit"],
    },
    {
        "name": "no_reranker",
        "description": "移除 Reranker（仅使用 BM25 + 语义检索）",
        "modules": ["bug_finder", "reward_model", "bandit"],
    },
    {
        "name": "no_bandit",
        "description": "移除 Bandit（使用原始规则熔断器）",
        "modules": ["bug_finder", "reward_model", "reranker"],
    },
    {
        "name": "only_bug_finder",
        "description": "仅启用 Bug Finder",
        "modules": ["bug_finder"],
    },
    {
        "name": "baseline",
        "description": "基线系统（无任何新增模块）",
        "modules": [],
    },
]


class AblationEvaluator:
    """消融实验评估器"""

    def __init__(self, results_dir: str):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def load_results(self, config_name: str) -> Dict[str, Any]:
        """加载实验结果"""
        path = self.results_dir / f"{config_name}.json"
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return {}

    def save_results(self, config_name: str, results: Dict[str, Any]):
        """保存实验结果"""
        path = self.results_dir / f"{config_name}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

    def compare_all(self) -> Dict[str, Any]:
        """对比所有消融实验结果"""
        comparison = {}

        for config in ABLATION_CONFIGS:
            results = self.load_results(config["name"])
            if results:
                comparison[config["name"]] = {
                    "description": config["description"],
                    "modules": config["modules"],
                    "metrics": results,
                }

        return comparison

    def generate_report(self) -> str:
        """生成消融实验报告"""
        comparison = self.compare_all()

        if not comparison:
            return "无实验结果"

        report_lines = [
            "# 消融实验报告",
            "",
            "## 实验配置",
            "",
            "| 配置 | 描述 | 启用模块 |",
            "|------|------|---------|",
        ]

        for config in ABLATION_CONFIGS:
            name = config["name"]
            desc = config["description"]
            modules = ", ".join(config["modules"]) if config["modules"] else "无"
            report_lines.append(f"| {name} | {desc} | {modules} |")

        report_lines.extend([
            "",
            "## 实验结果",
            "",
        ])

        # 提取关键指标
        key_metrics = [
            "code_fix_rate",
            "paper_quality_score",
            "mrr_at_10",
            "avg_retries",
            "total_api_cost",
        ]

        for metric in key_metrics:
            report_lines.append(f"### {metric}")
            report_lines.append("")
            report_lines.append("| 配置 | 值 | 相对基线 |")
            report_lines.append("|------|-----|---------|")

            baseline_value = None
            for config in ABLATION_CONFIGS:
                name = config["name"]
                if name in comparison:
                    value = comparison[name]["metrics"].get(metric, "N/A")
                    if name == "baseline":
                        baseline_value = value

                    if isinstance(value, float):
                        value_str = f"{value:.4f}"
                        if baseline_value and isinstance(baseline_value, float) and baseline_value > 0:
                            relative = ((value - baseline_value) / baseline_value) * 100
                            relative_str = f"{relative:+.1f}%"
                        else:
                            relative_str = "-"
                    else:
                        value_str = str(value)
                        relative_str = "-"

                    report_lines.append(f"| {name} | {value_str} | {relative_str} |")

            report_lines.append("")

        # 结论
        report_lines.extend([
            "## 结论",
            "",
            "基于消融实验结果，分析各模块的独立贡献：",
            "",
        ])

        return "\n".join(report_lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="消融实验")
    parser.add_argument("--results-dir", type=str, default="ml/results/ablation",
                       help="结果目录")
    parser.add_argument("--generate-report", action="store_true",
                       help="生成报告")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    evaluator = AblationEvaluator(args.results_dir)

    if args.generate_report:
        report = evaluator.generate_report()
        report_path = Path(args.results_dir) / "ablation_report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        logger.info(f"报告已保存到 {report_path}")
        print(report)
    else:
        print("消融实验配置：")
        for config in ABLATION_CONFIGS:
            print(f"  - {config['name']}: {config['description']}")
        print(f"\n结果目录: {args.results_dir}")
        print("请运行实验并保存结果后，使用 --generate-report 生成报告")


if __name__ == "__main__":
    main()
