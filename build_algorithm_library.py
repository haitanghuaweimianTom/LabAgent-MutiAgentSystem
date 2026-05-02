#!/usr/bin/env python3
"""
算法知识库构建脚本
==================
扫描 Algorithms_MathModels 仓库，生成结构化的算法索引 JSON，
供系统在建模阶段自动检索和推荐。

使用方法:
    python build_algorithm_library.py --source /path/to/Algorithms_MathModels --output src/knowledge/algorithm_index.json
"""

import json
import os
import re
import argparse
from pathlib import Path
from typing import Dict, List, Any

# 核心算法类别定义（排除随书源码等辅助目录）
ALGORITHM_CATEGORIES = {
    "AHP层次分析法": {
        "name_en": "Analytic Hierarchy Process (AHP)",
        "description": "层次分析法，用于多准则决策分析，通过构建判断矩阵计算各因素权重。",
        "tags": ["评价", "权重", "决策", "层次", "多准则", "排序"],
        "applicable_scenarios": [
            "多因素综合评价",
            "方案优选排序",
            "指标权重确定",
            "决策问题分析"
        ],
        "key_functions": ["ahp.m", "CalculationRI.m", "tolsortvec.m", "sglsortexamine.m"],
        "mathematical_model": "构造判断矩阵 A，计算最大特征值 λ_max 及对应特征向量 w，一致性检验 CR = CI/RI < 0.1",
        "advantages": ["系统性强", "定性定量结合", "简洁实用"],
        "limitations": ["判断矩阵主观性强", "因素过多时一致性难保证"]
    },
    "CellularAutomata元胞向量机": {
        "name_en": "Cellular Automata",
        "description": "元胞自动机，离散化的时空动力学模型，通过局部规则演化模拟复杂系统行为。",
        "tags": ["模拟", "演化", "空间", "离散", "复杂系统", "动力学"],
        "applicable_scenarios": [
            "交通流模拟",
            "森林火灾蔓延",
            "传染病传播",
            "生物种群演化",
            "物理过程模拟"
        ],
        "subtypes": {
            "生命游戏": "经典二维元胞自动机，模拟生命诞生、存活、死亡过程",
            "森林火灾": "模拟森林中树木生长、雷击起火、火势蔓延的动态过程",
            "气体动力学": "模拟气体分子运动和碰撞过程",
            "扩散限制聚集": "模拟粒子随机扩散并聚集形成分形结构",
            "表面张力": "模拟液体表面张力和毛细现象",
            "激发介质": "模拟心脏电信号传导或化学反应波",
            "砂堆规则": "自组织临界性研究，模拟沙堆崩塌",
            "渗流集群": "研究多孔介质中的渗透现象"
        },
        "key_functions": [],
        "mathematical_model": "状态转移函数 s(t+1) = f(s(t), 邻居状态), 局部规则驱动全局模式",
        "advantages": ["并行计算", "直观易懂", "可模拟复杂涌现行为"],
        "limitations": ["规则设计依赖经验", "计算量大", "难以解析分析"]
    },
    "FuzzyMathematicalModel模糊数学模型": {
        "name_en": "Fuzzy Mathematical Model",
        "description": "模糊数学模型，处理边界不清晰、概念模糊的问题，通过隶属度函数将定性描述定量化。",
        "tags": ["模糊", "评价", "隶属度", "不确定性", "定性定量转换"],
        "applicable_scenarios": [
            "模糊综合评价",
            "模糊聚类分析",
            "多目标模糊决策",
            "语言变量量化"
        ],
        "subtypes": {
            "多层次模糊综合评价": "多层次指标体系下的模糊综合评判",
            "多目标模糊综合评价": "考虑多个冲突目标的模糊决策",
            "模糊聚类": "基于模糊等价关系的动态聚类方法"
        },
        "key_functions": [],
        "mathematical_model": "隶属度函数 μ(x)∈[0,1]，模糊矩阵运算，λ-截集",
        "advantages": ["处理模糊不确定性", "符合人类思维习惯", "无需精确数据"],
        "limitations": ["隶属度函数构造主观", "计算复杂度较高"]
    },
    "GoalProgramming目标规划": {
        "name_en": "Goal Programming",
        "description": "目标规划，用于求解具有多个目标的优化问题，通过引入偏差变量将多目标转化为单目标。",
        "tags": ["多目标", "规划", "优化", "偏差", "优先级"],
        "applicable_scenarios": [
            "生产计划优化",
            "资源配置",
            "投资决策",
            "多目标调度"
        ],
        "key_functions": ["main.m", "fun.m", "prediction.m"],
        "mathematical_model": "min Σ(w_i^+·d_i^+ + w_i^-·d_i^-)，s.t. f_i(x) + d_i^- - d_i^+ = g_i",
        "advantages": ["处理多目标冲突", "引入优先级", "灵活性强"],
        "limitations": ["目标权重确定困难", "大规模问题求解复杂"]
    },
    "GraphTheory图论": {
        "name_en": "Graph Theory",
        "description": "图论算法，用于求解网络结构中的路径、连接、流等问题。",
        "tags": ["最短路径", "网络", "图", "节点", "边", "连通性"],
        "applicable_scenarios": [
            "最短路径规划",
            "网络优化",
            "物流运输路径",
            "通信网络设计",
            "社交网络分析"
        ],
        "subtypes": {
            "dijkstra求解最短路径": "单源最短路径，非负权图，时间复杂度 O(V^2) 或 O(E+VlogV)",
            "floyd求解最短路径": "全源最短路径，动态规划，时间复杂度 O(V^3)"
        },
        "key_functions": [],
        "mathematical_model": "G=(V,E,w)，Dijkstra: 贪心松弛; Floyd: d_ij^(k)=min(d_ij^(k-1), d_ik^(k-1)+d_kj^(k-1))",
        "advantages": ["算法成熟", "适用性广", "有标准工具包"],
        "limitations": ["大规模图存储开销大", "动态图需重新计算"]
    },
    "GreySystem灰色系统": {
        "name_en": "Grey System Theory",
        "description": "灰色系统理论，处理小样本、贫信息的不确定性系统，通过数据生成和灰色微分方程实现预测。",
        "tags": ["预测", "小样本", "灰色", "序列", "贫信息", "微分方程"],
        "applicable_scenarios": [
            "小样本预测",
            "中长期趋势预测",
            "关联度分析",
            "系统行为预测"
        ],
        "key_functions": ["GM_1_1.m", "GM_2_1.m", "GM_Verhulst.m", "GM_full.m", "association_analysis.m", "strength_analysis.m"],
        "mathematical_model": "GM(1,1): dx^(1)/dt + a·x^(1) = b，通过一次累加生成(1-AGO)建立一阶线性微分方程",
        "advantages": ["小样本即可建模", "计算简单", "无需典型分布假设"],
        "limitations": ["预测精度有限", "长期预测偏差大", "对数据波动敏感"]
    },
    "HeuristicAlgorithm启发式算法": {
        "name_en": "Heuristic Algorithms",
        "description": "启发式智能优化算法，包括遗传算法、模拟退火、神经网络等，用于求解复杂非凸优化问题。",
        "tags": ["优化", "全局搜索", "智能算法", "非凸", "NP-hard"],
        "applicable_scenarios": [
            "组合优化",
            "函数极值求解",
            "参数优化",
            "路径规划",
            "调度问题"
        ],
        "subtypes": {
            "模拟退火算法": "模拟物理退火过程，以一定概率接受劣解，逃离局部最优",
            "遗传算法": "模拟自然选择和遗传机制，通过选择、交叉、变异进化寻优",
            "神经网络算法": "模拟生物神经网络，通过前向传播和反向学习拟合复杂映射"
        },
        "key_functions": [],
        "mathematical_model": "遗传算法: 编码→适应度评估→选择→交叉→变异→迭代; 模拟退火: Metropolis准则 P(accept)=exp(-ΔE/T)",
        "advantages": ["不依赖梯度信息", "可处理离散问题", "全局搜索能力强"],
        "limitations": ["参数调优困难", "收敛速度不确定", "结果可重复性差"]
    },
    "IntegerProgramming整数规划": {
        "name_en": "Integer Programming",
        "description": "整数规划，决策变量取整数值的数学规划，包括纯整数规划和混合整数规划。",
        "tags": ["整数", "规划", "组合", "离散", "0-1变量"],
        "applicable_scenarios": [
            "指派问题",
            "选址问题",
            "排班调度",
            "投资决策",
            "背包问题"
        ],
        "key_functions": ["assgin_integer_prog.m", "monte_carro.m", "example_1.m"],
        "mathematical_model": "min c^T·x, s.t. A·x ≤ b, x_i ∈ Z (或 {0,1})",
        "advantages": ["精确描述离散决策", "有成熟求解器"],
        "limitations": ["NP-hard 问题", "大规模问题求解困难"]
    },
    "Interpolation插值": {
        "name_en": "Interpolation",
        "description": "插值方法，通过已知离散数据点构造连续函数，用于数据补全、曲线拟合和图像处理。",
        "tags": ["插值", "拟合", "数据", "补全", "连续化"],
        "applicable_scenarios": [
            "缺失数据填补",
            "曲线光滑",
            "图像放大",
            "函数逼近",
            "数值微分积分"
        ],
        "key_functions": ["interp_1D.m", "interp_2D.m", "interp_2D_compare.m", "interp_grid.m"],
        "mathematical_model": "拉格朗日插值、牛顿插值、样条插值(Spline)、双线性/双三次插值",
        "advantages": ["精确通过已知点", "形式简洁", "有多样化方法"],
        "limitations": ["高次插值Runge现象", "外推不可靠", "对噪声敏感"]
    },
    "LinearProgramming线性规划": {
        "name_en": "Linear Programming",
        "description": "线性规划，目标函数和约束条件均为线性的优化问题，最常用的运筹学方法之一。",
        "tags": ["线性", "规划", "约束", "最优解", "单纯形法"],
        "applicable_scenarios": [
            "生产计划",
            "运输问题",
            "资源分配",
            "投资组合",
            " diet problem"
        ],
        "key_functions": ["solve_lp.m", "invest_model.m"],
        "mathematical_model": "min c^T·x, s.t. A·x ≤ b, x ≥ 0",
        "advantages": ["有精确最优解", "算法成熟高效", "广泛应用"],
        "limitations": ["要求线性关系", "对参数敏感", "整数需求需转整数规划"]
    },
    "MultivariateAnalysis多元分析": {
        "name_en": "Multivariate Analysis",
        "description": "多元统计分析，处理多变量数据的统计方法，包括聚类分析、主成分分析等。",
        "tags": ["聚类", "主成分", "降维", "多变量", "统计"],
        "applicable_scenarios": [
            "数据降维",
            "样本分类",
            "特征提取",
            "综合评价",
            "数据可视化"
        ],
        "subtypes": {
            "聚类分析": "将样本按相似度划分为不同类别，K-means、层次聚类等",
            "主成分分析": "通过正交变换将相关变量转化为线性无关主成分，实现降维"
        },
        "key_functions": [],
        "mathematical_model": "PCA: 对协方差矩阵特征分解，取前k大特征值对应特征向量; K-means: min Σ||x_i-μ_j||^2",
        "advantages": ["降低数据维度", "发现潜在结构", "消除变量相关性"],
        "limitations": ["结果解释性有限", "聚类数目需预设", "对异常值敏感"]
    },
    "NeuralNetwork神经网络": {
        "name_en": "Neural Network",
        "description": "人工神经网络，模拟生物神经元连接结构，通过训练学习数据中的非线性映射关系。",
        "tags": ["预测", "分类", "神经网络", "非线性", "深度学习"],
        "applicable_scenarios": [
            "非线性回归预测",
            "模式识别分类",
            "时间序列预测",
            "函数逼近",
            "图像识别"
        ],
        "key_functions": ["af_classify_BP.m", "af_classify_LVQ.m"],
        "mathematical_model": "BP网络: 前向传播 y=f(W·x+b)，反向传播误差 ΔW=-η·∂E/∂W",
        "advantages": ["强大的非线性拟合能力", "自适应学习", "容错性"],
        "limitations": ["需要大量训练数据", "易过拟合", "黑盒模型", "训练时间长"]
    },
    "NonLinearProgramming非线性规划": {
        "name_en": "Nonlinear Programming",
        "description": "非线性规划，目标函数或约束条件包含非线性项的优化问题，比线性规划更一般但求解更困难。",
        "tags": ["非线性", "规划", "约束", "优化", "梯度"],
        "applicable_scenarios": [
            "工程设计优化",
            "参数估计",
            "资源分配",
            "机器学习训练"
        ],
        "key_functions": ["non_linear_prog.m", "fun1.m", "fun2.m"],
        "mathematical_model": "min f(x), s.t. g_i(x)≤0, h_j(x)=0，f或g/h含非线性项",
        "advantages": ["描述能力强", "适用范围广"],
        "limitations": ["可能存在多个局部最优", "对初值敏感", "收敛性不确定"]
    },
    "RegressionAnalysis回归分析": {
        "name_en": "Regression Analysis",
        "description": "回归分析，研究变量间相关关系的统计方法，用于预测和因果分析。",
        "tags": ["回归", "拟合", "预测", "相关关系", "统计"],
        "applicable_scenarios": [
            "趋势预测",
            "因素分析",
            "因果关系推断",
            "数据拟合"
        ],
        "key_functions": ["linear_regression.m", "unlinear_regression.m", "stepwise_regression.m", "one_indeterminate_poly.m", "muti_indeterminate_2_degree_poly.m"],
        "mathematical_model": "线性回归: y=Xβ+ε, β=(X^T·X)^(-1)·X^T·y; 多项式回归: y=β_0+β_1·x+...+β_n·x^n",
        "advantages": ["解释性强", "计算简单", "理论基础扎实"],
        "limitations": ["假设线性关系", "对异常值敏感", "多重共线性问题"]
    },
    "TimeSeries时间序列": {
        "name_en": "Time Series Analysis",
        "description": "时间序列分析，研究按时间顺序排列的数据序列，揭示发展趋势和周期性规律。",
        "tags": ["时间序列", "预测", "趋势", "周期", "平稳性"],
        "applicable_scenarios": [
            "经济指标预测",
            "股票价格预测",
            "销售量预测",
            "气象预测",
            "人口增长预测"
        ],
        "subtypes": {
            "移动平均法": "用最近N期平均值作为预测值，平滑随机波动",
            "指数平滑法": "赋予近期数据更大权重，一阶/二阶/三阶(Holt-Winters)",
            "趋势外推预测法": "拟合趋势曲线并外推，线性/指数/多项式趋势",
            "自适应滤波法": "动态调整权重，使预测误差最小化"
        },
        "key_functions": [],
        "mathematical_model": "移动平均: F_{t+1}=(Y_t+Y_{t-1}+...+Y_{t-N+1})/N; 指数平滑: S_t=α·Y_t+(1-α)·S_{t-1}",
        "advantages": ["方法简单直观", "数据需求少", "适合短期预测"],
        "limitations": ["难以捕捉突变", "长期预测精度下降", "忽略因果关系"]
    }
}


def scan_source_files(source_dir: Path) -> Dict[str, List[str]]:
    """扫描源目录中的代码文件"""
    files_by_category = {}
    for category in ALGORITHM_CATEGORIES.keys():
        cat_dir = None
        for d in source_dir.iterdir():
            if d.is_dir() and category in d.name:
                cat_dir = d
                break
        if cat_dir:
            files = []
            for f in cat_dir.rglob("*"):
                if f.is_file() and f.suffix in ['.m', '.py', '.txt', '.md']:
                    files.append(str(f.relative_to(source_dir)))
            files_by_category[category] = files
    return files_by_category


def read_code_snippets(source_dir: Path, category: str, max_lines: int = 50) -> List[Dict[str, str]]:
    """读取算法目录下的代码片段"""
    snippets = []
    cat_dir = None
    for d in source_dir.iterdir():
        if d.is_dir() and category in d.name:
            cat_dir = d
            break
    if not cat_dir:
        return snippets

    for f in cat_dir.rglob("*"):
        if f.is_file() and f.suffix in ['.m', '.py']:
            try:
                content = f.read_text(encoding='utf-8', errors='ignore')
                lines = content.split('\n')[:max_lines]
                snippet = '\n'.join(lines)
                snippets.append({
                    "filename": f.name,
                    "path": str(f.relative_to(source_dir)),
                    "snippet": snippet,
                    "language": "matlab" if f.suffix == '.m' else "python"
                })
            except Exception:
                pass
    return snippets


def build_index(source_dir: str, output_path: str):
    """构建算法知识库索引"""
    source = Path(source_dir)
    files_by_category = scan_source_files(source)

    index = {
        "meta": {
            "source": "https://github.com/HuangCongQing/Algorithms_MathModels",
            "version": "1.0",
            "total_categories": len(ALGORITHM_CATEGORIES),
            "description": "数学建模常用算法MATLAB实现知识库"
        },
        "categories": []
    }

    for category_name, meta in ALGORITHM_CATEGORIES.items():
        entry = {
            "id": category_name,
            "name_cn": category_name,
            "name_en": meta["name_en"],
            "description": meta["description"],
            "tags": meta["tags"],
            "applicable_scenarios": meta.get("applicable_scenarios", []),
            "mathematical_model": meta.get("mathematical_model", ""),
            "advantages": meta.get("advantages", []),
            "limitations": meta.get("limitations", []),
            "subtypes": meta.get("subtypes", {}),
            "source_files": files_by_category.get(category_name, []),
            "code_snippets": []
        }

        # 读取代码片段（限制数量避免索引过大）
        snippets = read_code_snippets(source, category_name, max_lines=40)
        # 只保留前 5 个关键文件
        for s in snippets[:5]:
            entry["code_snippets"].append(s)

        index["categories"].append(entry)

    # 保存索引
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"算法知识库索引已构建: {output}")
    print(f"共 {len(index['categories'])} 个算法类别")
    total_files = sum(len(c['source_files']) for c in index['categories'])
    print(f"共 {total_files} 个源文件")


def main():
    parser = argparse.ArgumentParser(description="构建数学建模算法知识库索引")
    parser.add_argument("--source", default="/tmp/Algorithms_MathModels", help="算法仓库路径")
    parser.add_argument("--output", default="src/knowledge/algorithm_index.json", help="输出索引文件路径")
    args = parser.parse_args()
    build_index(args.source, args.output)


if __name__ == "__main__":
    main()
