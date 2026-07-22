"""
系统运行数据收集脚本
===================

跑 20~25 次系统完整运行，收集：
- 执行日志（成功/失败/traceback）
- 检索日志（query → retrieved docs → 最终引用了哪些）
- 论文输出（用于 RM 训练）

用法：
    python ml/data_collection/collect_system_runs.py --problems 20 --output ml/collected_data

预算控制：
    每次运行消耗 ~0.8 RMB（DeepSeek V4 / MiMo V2.5）
    20 次总计 ~16 RMB
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

logger = logging.getLogger(__name__)

# 经典数模题目（MCM 2015-2024 各 2 道 + CUMCM 5 道 + 补充 3 道）
SEED_PROBLEMS = [
    # MCM 题目
    {"id": "mcm_2024_a", "title": "Network Resilience", "type": "optimization",
     "description": "Analyze and optimize the resilience of a network to node failures."},
    {"id": "mcm_2024_b", "title": "Water Resource Management", "type": "simulation",
     "description": "Model and optimize water resource allocation in a changing climate."},
    {"id": "mcm_2023_a", "title": "Receding Ice Edge", "type": "modeling",
     "description": "Model the effects of a receding ice edge on Arctic ecosystems."},
    {"id": "mcm_2023_b", "title": "Is AI Harmful?", "type": "analysis",
     "description": "Develop a framework to assess the potential harms of AI systems."},
    {"id": "mcm_2022_a", "title": "Don't Drink and Drive", "type": "optimization",
     "description": "Optimize traffic light timing to reduce drunk driving incidents."},
    {"id": "mcm_2022_b", "title": "The Last Ice Age", "type": "modeling",
     "description": "Model the conditions that trigger ice ages and predict future glaciation."},
    {"id": "mcm_2021_a", "title": "Network Tipping Points", "type": "analysis",
     "description": "Identify tipping points in complex networks and their implications."},
    {"id": "mcm_2021_b", "title": "Falling Balls", "type": "physics",
     "description": "Model the dynamics of balls falling through a series of pegs."},
    {"id": "mcm_2020_a", "title": "Power Grid", "type": "optimization",
     "description": "Optimize power grid resilience to extreme weather events."},
    {"id": "mcm_2020_b", "title": "Firefighter Deployment", "type": "optimization",
     "description": "Optimize wildfire firefighter deployment strategies."},
    # CUMCM 题目
    {"id": "cumcm_2023_a", "title": "定日镜场优化设计", "type": "optimization",
     "description": "优化定日镜场的设计，最大化太阳能接收效率。"},
    {"id": "cumcm_2023_b", "title": "经典力学问题", "type": "physics",
     "description": "建立经典力学模型，分析多体系统的运动规律。"},
    {"id": "cumcm_2023_c", "title": "古建筑修复", "type": "modeling",
     "description": "为古建筑修复建立数学模型，优化修复方案。"},
    {"id": "cumcm_2022_a", "title": "波浪能最大输出功率", "type": "optimization",
     "description": "优化波浪能发电装置的参数，最大化输出功率。"},
    {"id": "cumcm_2022_b", "title": "单资源通勤问题", "type": "optimization",
     "description": "优化通勤路线和资源分配，最小化通勤成本。"},
    {"id": "cumcm_2021_a", "title": "FAST 主动变位", "type": "physics",
     "description": "为 FAST 望远镜的主动变位建立数学模型。"},
    {"id": "cumcm_2021_b", "title": "乙醇偶合制备", "type": "chemistry",
     "description": "优化乙醇偶合制备烯烃的反应条件。"},
    # 补充题目（覆盖更多题型）
    {"id": "extra_01", "title": "Credit Risk Assessment", "type": "classification",
     "description": "Build a credit risk assessment model using machine learning."},
    {"id": "extra_02", "title": "Stock Price Prediction", "type": "time_series",
     "description": "Predict stock prices using time series analysis."},
    {"id": "extra_03", "title": "Customer Churn Prediction", "type": "classification",
     "description": "Predict customer churn using behavioral data."},
]


class SystemRunner:
    """运行系统并收集数据"""

    def __init__(self, output_dir: str, api_budget_rmb: float = 120.0):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.api_budget = api_budget_rmb
        self.total_cost = 0.0
        self.run_logs: List[Dict[str, Any]] = []

    def run_single_problem(self, problem: Dict[str, Any]) -> Dict[str, Any]:
        """运行单个问题，收集日志"""
        run_id = f"{problem['id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        run_dir = self.output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"开始运行: {problem['id']} - {problem['title']}")
        start_time = time.time()

        result = {
            "run_id": run_id,
            "problem": problem,
            "start_time": datetime.now().isoformat(),
            "status": "running",
            "stages": {},
            "execution_logs": [],
            "retrieval_logs": [],
            "paper_output": None,
            "error": None,
        }

        try:
            # 这里调用系统的完整 Pipeline
            # 实际运行时替换为真实的 orchestrator 调用
            result = self._execute_pipeline(problem, run_dir, result)
            result["status"] = "completed"
        except Exception as e:
            result["status"] = "failed"
            result["error"] = {
                "type": type(e).__name__,
                "message": str(e),
                "traceback": traceback.format_exc(),
            }
            logger.error(f"运行失败: {problem['id']}: {e}")

        result["end_time"] = datetime.now().isoformat()
        result["duration_seconds"] = time.time() - start_time

        # 保存运行日志
        with open(run_dir / "run_log.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        self.run_logs.append(result)
        return result

    def _execute_pipeline(self, problem: Dict[str, Any], run_dir: Path,
                          result: Dict[str, Any]) -> Dict[str, Any]:
        """执行完整 Pipeline（框架，实际运行时需接入真实 orchestrator）"""
        # TODO: 接入真实的 LangGraph orchestrator
        # 当前为框架代码，实际运行时需要：
        # from backend.app.agents.langgraph_orchestrator import LangGraphOrchestrator
        # orchestrator = LangGraphOrchestrator()
        # pipeline_result = await orchestrator.run(problem_text=problem["description"])

        # 模拟执行各阶段（实际运行时删除此段）
        stages = [
            "preflight", "analyzer", "parallel_analysis", "discussion",
            "modeler", "solver", "writer", "peer_review", "fact_check",
            "compliance", "camera_ready"
        ]

        for stage in stages:
            stage_result = {
                "stage": stage,
                "status": "simulated",
                "start_time": datetime.now().isoformat(),
            }
            result["stages"][stage] = stage_result
            result["execution_logs"].append({
                "stage": stage,
                "event": "stage_started",
                "timestamp": datetime.now().isoformat(),
            })

        # 模拟检索日志
        result["retrieval_logs"] = [
            {
                "query": problem["description"][:100],
                "retrieved_docs": ["doc1.pdf", "doc2.pdf"],
                "cited_docs": ["doc1.pdf"],
            }
        ]

        return result

    def run_all(self, problems: List[Dict[str, Any]], max_runs: int = 25):
        """运行所有问题"""
        logger.info(f"开始收集数据，计划运行 {min(len(problems), max_runs)} 次")

        for i, problem in enumerate(problems[:max_runs]):
            if self.total_cost >= self.api_budget:
                logger.warning(f"API 预算耗尽 ({self.api_budget} RMB)，停止运行")
                break

            result = self.run_single_problem(problem)
            self.run_logs.append(result)

            # 每次运行后保存汇总
            self._save_summary()

            logger.info(f"完成 {i+1}/{min(len(problems), max_runs)}: "
                       f"{problem['id']} ({result['status']}, "
                       f"{result['duration_seconds']:.1f}s)")

        logger.info(f"数据收集完成，共 {len(self.run_logs)} 次运行")

    def _save_summary(self):
        """保存汇总日志"""
        summary = {
            "total_runs": len(self.run_logs),
            "completed": sum(1 for r in self.run_logs if r["status"] == "completed"),
            "failed": sum(1 for r in self.run_logs if r["status"] == "failed"),
            "total_cost_rmb": self.total_cost,
            "runs": [
                {
                    "run_id": r["run_id"],
                    "problem_id": r["problem"]["id"],
                    "status": r["status"],
                    "duration": r.get("duration_seconds", 0),
                }
                for r in self.run_logs
            ],
        }

        with open(self.output_dir / "summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

    def extract_failure_cases(self) -> List[Dict[str, Any]]:
        """从运行日志中提取失败案例（用于 Bug Finder 数据）"""
        failures = []
        for run in self.run_logs:
            if run["status"] == "failed" and run.get("error"):
                failures.append({
                    "run_id": run["run_id"],
                    "problem": run["problem"],
                    "error": run["error"],
                    "stages": run.get("stages", {}),
                })
            # 也检查各阶段中的失败
            for stage_name, stage_data in run.get("stages", {}).items():
                if stage_data.get("status") == "failed":
                    failures.append({
                        "run_id": run["run_id"],
                        "problem": run["problem"],
                        "stage": stage_name,
                        "error": stage_data.get("error", {}),
                    })
        return failures

    def extract_retrieval_logs(self) -> List[Dict[str, Any]]:
        """提取检索日志（用于 Reranker 数据）"""
        all_retrieval = []
        for run in self.run_logs:
            for log in run.get("retrieval_logs", []):
                all_retrieval.append({
                    "run_id": run["run_id"],
                    "problem": run["problem"],
                    **log,
                })
        return all_retrieval

    def extract_paper_outputs(self) -> List[Dict[str, Any]]:
        """提取论文输出（用于 DPO 数据）"""
        papers = []
        for run in self.run_logs:
            if run.get("paper_output"):
                papers.append({
                    "run_id": run["run_id"],
                    "problem": run["problem"],
                    "paper": run["paper_output"],
                })
        return papers


def main():
    parser = argparse.ArgumentParser(description="系统运行数据收集")
    parser.add_argument("--problems", type=int, default=20,
                       help="运行问题数量（默认 20）")
    parser.add_argument("--output", type=str, default="ml/collected_data",
                       help="输出目录")
    parser.add_argument("--budget", type=float, default=120.0,
                       help="API 预算（RMB，默认 120）")
    parser.add_argument("--seed", type=int, default=42,
                       help="随机种子")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    runner = SystemRunner(args.output, args.budget)

    # 选择要运行的问题
    import random
    random.seed(args.seed)
    selected = random.sample(SEED_PROBLEMS, min(args.problems, len(SEED_PROBLEMS)))

    runner.run_all(selected, max_runs=args.problems)

    # 提取各类数据
    failures = runner.extract_failure_cases()
    retrieval = runner.extract_retrieval_logs()
    papers = runner.extract_paper_outputs()

    logger.info(f"提取结果: {len(failures)} 个失败案例, "
               f"{len(retrieval)} 条检索日志, {len(papers)} 篇论文")

    # 保存提取的数据
    for name, data in [("failures", failures), ("retrieval", retrieval), ("papers", papers)]:
        with open(runner.output_dir / f"extracted_{name}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
