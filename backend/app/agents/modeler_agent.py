"""建模Agent - 建立数学模型（支持批量建模 + Claude Code 代码生成）

参考 math_modeling_paper_system 的结构化建模：
- 内置模型模板（优化类/预测类/评价类/网络类/物理类）
- _build_all_models：一次性为所有子问题建模
- _smart_template_fallback：智能选择模板兜底
- _generate_model_code：使用 Claude Code 生成模型验证/分析代码
"""

import json
import logging
from typing import Any, Dict, List
from .base import BaseAgent, AgentFactory
from ..core.security import wrap_user_content

logger = logging.getLogger(__name__)

# 模型模板库（仅作为 LLM 输出无效时的兜底占位，不应被直接当作最终模型）
# 设计上要求 LLM 根据具体问题生成专属模型；本库只在解析失败或网络异常时提供可运行的占位结构。
MODEL_TEMPLATES = {
    "physics": {
        "generic_physics": {
            "name": "物理建模",
            "description": "基于物理定律和实验数据的通用定量模型",
            "formula": "由守恒律/几何关系/波动方程/经验公式根据具体问题建立",
            "constraints_note": "物理定律 + 边界条件 + 测量不确定性",
            "algorithm": "数值求解 / 曲线拟合 / 蒙特卡洛模拟",
            "variables": ["q: 待求物理量", "p: 模型参数", "x: 自变量/输入条件"],
            "code_hints": "physics_modeling",
        },
    },
    "optimization": {
        "linear_programming": {
            "name": "线性规划",
            "description": "目标函数和约束条件均为线性的优化问题",
            "formula": "min Z = sum(c_j * x_j)",
            "constraints_note": "线性不等式约束 + 非负约束",
            "algorithm": "单纯形法 / scipy.optimize.linprog",
            "variables": ["x_j: 第j个决策变量(连续)"],
            "code_hints": "linear_programming",
        },
        "integer_programming": {
            "name": "整数规划",
            "description": "决策变量为整数的优化问题",
            "formula": "min Z = c'x, x ∈ Z^n",
            "constraints_note": "整数约束 + 非负约束",
            "algorithm": "分支定界法 / PuLP",
            "variables": ["x_j ∈ Z+: 第j个整数决策变量"],
            "code_hints": "integer_programming",
        },
        "stochastic_optimization": {
            "name": "随机规划",
            "description": "考虑不确定性因素的优化模型",
            "formula": "min E[f(x, ξ)]  s.t.  g(x, ξ) ≤ 0",
            "constraints_note": "不确定性描述 + 机会约束/期望约束",
            "algorithm": "样本平均近似(SAA) / 随机规划求解器 / 蒙特卡洛模拟",
            "variables": ["x: 决策变量", "ξ: 随机变量/不确定性参数"],
            "code_hints": "stochastic_optimization",
        },
        "nonlinear_programming": {
            "name": "非线性规划",
            "description": "目标函数或约束包含非线性项",
            "formula": "min f(x), s.t. g_i(x) <= 0",
            "constraints_note": "非线性约束",
            "algorithm": "SLSQP / 内点法",
            "variables": ["x: 决策向量(连续)"],
            "code_hints": "nonlinear_programming",
        },
    },
    "prediction": {
        "time_series": {
            "name": "时间序列预测",
            "description": "基于历史数据的时间序列预测模型",
            "formula": "Y_t = f(Y_{t-1}, ..., ε_t)",
            "constraints_note": "平稳性假设 + 误差结构假设",
            "algorithm": "ARIMA / SARIMA / ETS / 状态空间模型",
            "variables": ["Y_t: t时刻的值", "ε_t: 白噪声/扰动项"],
            "code_hints": "time_series_forecast",
        },
        "prophet": {
            "name": "Prophet时间序列预测",
            "description": "趋势+季节性+节假日分解的时间序列预测",
            "formula": "Y(t) = g(t) + s(t) + h(t) + ε_t",
            "constraints_note": "趋势+季节性+节假日效应分解",
            "algorithm": "Prophet / statsmodels",
            "variables": ["g(t): 趋势函数", "s(t): 季节性函数", "h(t): 节假日效应"],
            "code_hints": "prophet_forecast",
        },
        "neural_network": {
            "name": "神经网络预测",
            "description": "基于神经网络的非线性预测模型",
            "formula": "y_hat = NN(x; θ)",
            "constraints_note": "数据标准化 + 训练/验证/测试划分",
            "algorithm": "PyTorch / Keras / sklearn.MLPRegressor",
            "variables": ["x: 输入特征", "θ: 网络参数", "y_hat: 预测值"],
            "code_hints": "neural_network_forecast",
        },
        "regression": {
            "name": "回归分析",
            "description": "建立因变量与自变量之间的回归关系",
            "formula": "Y = β_0 + β_1*X_1 + ... + β_p*X_p + ε",
            "constraints_note": "线性/可线性化假设 + 独立性假设",
            "algorithm": "最小二乘法 / 极大似然 / sklearn.linear_model",
            "variables": ["Y: 因变量", "X_j: 第j个自变量", "β_j: 回归系数"],
            "code_hints": "regression_analysis",
        },
    },
    "evaluation": {
        "ahp": {
            "name": "层次分析法(AHP)",
            "description": "多准则决策的层次分析",
            "formula": "CI = (λ_max-n)/(n-1), CR = CI/RI < 0.1",
            "constraints_note": "判断矩阵一致性检验",
            "algorithm": "特征值法 / 一致性检验",
            "variables": ["w_i: 各层指标的权重", "λ_max: 判断矩阵最大特征值"],
            "code_hints": "ahp_analysis",
        },
        "entropy_weight": {
            "name": "熵权法",
            "description": "基于信息熵的客观赋权方法",
            "formula": "H_i = -k·sum(p_ij·ln(p_ij)), w_i = (1-H_i)/sum(1-H_i)",
            "constraints_note": "数据归一化处理",
            "algorithm": "信息熵计算 / pandas",
            "variables": ["w_i: 第i个指标的熵权"],
            "code_hints": "entropy_weight",
        },
        "topsis": {
            "name": "TOPSIS综合评价",
            "description": "逼近理想解的多指标排序方法",
            "formula": "C_i = D_i_minus / (D_i_plus + D_i_minus)",
            "constraints_note": "指标标准化 + 权重确定",
            "algorithm": "距离计算 / numpy.linalg.norm",
            "variables": ["D_i_plus: 到正理想解距离", "D_i_minus: 到负理想解距离", "C_i: 贴近度"],
            "code_hints": "topsis_evaluate",
        },
    },
    "sensitivity": {
        "sensitivity_analysis": {
            "name": "灵敏度分析与稳健性评估",
            "description": "分析参数变化对最优解或预测结果的影响程度",
            "formula": "S_i = ΔY/Δp_i (变化率之比)",
            "constraints_note": "参数扰动实验设计",
            "algorithm": "One-at-a-Time / Sobol指数 / Monte Carlo",
            "variables": ["Δp_i: 参数i的扰动量", "ΔY: 输出结果变化量"],
            "code_hints": "sensitivity_analysis",
        },
    },
    "classification": {
        "svm": {
            "name": "支持向量机(SVM)",
            "description": "用于分类的监督学习方法",
            "formula": "f(x) = sign(sum(α_i*y_i*K(x_i,x)) + b)",
            "constraints_note": "核函数选择 + 正则化参数",
            "algorithm": "SMO算法 / sklearn.svm",
            "variables": ["x: 输入特征向量", "y: 类别标签"],
            "code_hints": "svm_classify",
        },
    },
}


def _smart_template_select(suggested_method: str, problem_type: str, sub_problem_desc: str) -> tuple:
    """根据推荐方法和问题类型智能选择通用模型模板（兜底占位用）"""
    text = (suggested_method + problem_type + sub_problem_desc).lower()

    # 物理/光学/工程领域 → 通用物理模型
    if any(kw in text for kw in [
        "物理", "光学", "干涉", "外延", "厚度", "折射率", "光程差", "波数",
        "双光束", "多光束", "反射率", "相位差", "菲涅尔", "碳化硅", "硅晶圆",
        "sic", "红外", "opd", "反射光谱", "薄膜", "光波", "入射角", "干涉条纹",
        "膜厚", "力学", "热传导", "电磁", "流体力学"
    ]):
        return "generic_physics", "physics"

    if any(kw in text for kw in ["灵敏度", "稳健性", "鲁棒性", "sensitivity", "参数扰动", "稳定性"]):
        return "sensitivity_analysis", "sensitivity"
    if any(kw in text for kw in ["sarima", "arima", "arma", "ma", "指数平滑", "holt-winter", "prophet", "时序预测", "预测", "forecast"]):
        if "prophet" in text:
            return "prophet", "prediction"
        if any(kw in text for kw in ["lstm", "gru", "rnn", "深度学习", "神经网络预测", "neural"]):
            return "neural_network", "prediction"
        return "time_series", "prediction"
    if any(kw in text for kw in ["回归", "多元", "线性拟合", "regression"]):
        return "regression", "prediction"
    if any(kw in text for kw in ["库存", "报童", "随机规划", "订货量", "采购", "newsvendor", "stochastic", "不确定性"]):
        return "stochastic_optimization", "optimization"
    if any(kw in text for kw in ["ahp", "层次分析", "层次分析法", "analytic hierarchy"]):
        return "ahp", "evaluation"
    if any(kw in text for kw in ["熵权", "熵", "entropy"]):
        return "entropy_weight", "evaluation"
    if any(kw in text for kw in ["topsis", "逼近理想", "综合评价", "评价", "multi-criteria"]):
        return "topsis", "evaluation"
    if any(kw in text for kw in ["整数", "指派", "调度", "分配问题", "integer"]):
        return "integer_programming", "optimization"
    if any(kw in text for kw in ["svm", "支持向量", "分类", "聚类", "classification", "clustering"]):
        return "svm", "classification"
    return "linear_programming", "optimization"


@AgentFactory.register("modeler_agent")
class ModelerAgent(BaseAgent):
    name = "modeler_agent"
    label = "建模师"
    description = "建立数学模型、设计算法"
    default_model = ""
    
    _max_tokens_override = 16000  # 批量建模需要更大的输出

    def get_system_prompt(self) -> str:
        return """你是一个专业的数学建模专家。你需要：
1. 根据问题描述和前期分析，建立面向当前具体问题的数学模型
2. 定义清晰的决策变量、目标函数和约束条件
3. 选择合适的求解算法
4. 给出模型的假设、优缺点和适用边界

核心纪律：
- **problem-specific**：禁止直接套用通用模板或预设模型。每个字段必须基于当前问题的实际背景、数据和目标推导。
- **no fabrication**：禁止编造不存在的参数值、数据来源、实验结果或引用。无数据时说明"待估计/待补充"，不得假设虚假数值。
- **traceable**：所有假设、参数、约束必须能在问题描述或已提供数据中找到依据。

重要：你必须以JSON格式输出，不要有任何其他文字！

输出格式：
{
    "model_type": "优化/预测/评价/分类/仿真/网络",
    "model_name": "具体模型名称",
    "decision_variables": [{"name": "变量名", "description": "变量含义", "type": "连续/整数/0-1", "range": "取值范围"}],
    "parameters": [{"name": "参数名", "description": "参数含义", "source": "参数值或来源"}],
    "objective_function": "目标函数表达式",
    "constraints": [{"name": "约束名称", "expression": "约束表达式", "type": "等式/不等式"}],
    "algorithm": {"name": "算法名称", "description": "算法原理简述"},
    "model_assumptions": ["假设1", "假设2"],
    "model_advantages": ["优点1", "优点2"],
    "model_limitations": ["局限性1", "局限性2"]
}

请建立完整、准确、可求解的数学模型。"""

    async def execute(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        action = task_input.get("action", "build_model")
        if action == "build_all_models":
            return await self._build_all_models(task_input, context)
        if action == "build_sequential":
            return await self._build_sequential_models(task_input, context)
        return await self._build_single_model(task_input, context)

    async def _build_sequential_models(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        逐个建模模式：每个子问题的建模都会收到前序子问题的建模结果，
        实现递进式依赖（如：问题2的模型需要问题1的预测结果作为输入）
        """
        problem_text = task_input.get("problem_text", "")
        sub_problems = context.get("sub_problems", [])
        analyzer_result = context.get("analyzer_result", context.get("results", {}).get("analyzer_agent", {}))
        data_result = context.get("data_result", {})
        previous_models = []  # 前序子问题的建模结果

        all_models = []

        for i, sp in enumerate(sub_problems):
            sp_id = sp.get("id", i + 1)
            sp_name = sp.get("name", sp.get("description", f"子问题{sp_id}")[:80])
            sp_desc = sp.get("description", "")
            sp_type = sp.get("problem_type", "")
            suggested = sp.get("suggested_method", sp.get("approach", ""))

            # 递进依赖上下文：前序建模结果
            prev_model_summary = ""
            for j, pm in enumerate(previous_models):
                prev_sp_name = pm.get("sub_problem_name", f"子问题{j+1}")
                prev_model_name = pm.get("model_name", "")
                prev_obj = pm.get("objective_function", "")
                prev_vars = pm.get("decision_variables", [])
                vars_str = ", ".join([v.get("name", "") for v in prev_vars[:5]])
                prev_model_summary += f"- {prev_sp_name}（{prev_model_name}）:\n  目标函数: {prev_obj[:100]}\n  决策变量: {vars_str}\n"

            wrapped_problem = wrap_user_content(problem_text, "problem")
        prompt = f"""你是一个专业的数学建模专家。请为以下数学建模问题的第{i+1}个子问题建立精确的数学模型。

【问题背景】
{wrapped_problem}

【当前子问题】
名称：{sp_name}
描述：{sp_desc}
问题类型：{sp_type}
建议方法：{suggested}

【前序子问题建模结果（当前建模的已知条件/依赖）】
{prev_model_summary or "（这是第一个子问题，无前序依赖）"}

【数据分析结果摘要】
{self._summarize_data(data_result)}

重要提示：
- 如果当前子问题依赖前序子问题的结果（如：需要使用问题1的预测值、问题2的优化结果作为输入），请在决策变量、参数或约束中体现这种依赖关系
- 前序结果用"前序结果X"表示，具体数值在求解阶段代入
- 建立完整、可操作的数学模型"""

            messages = [
                {"role": "system", "content": self.get_system_prompt()},
                {"role": "user", "content": prompt},
            ]

            model_result = None
            # 重试最多 2 次
            for attempt in range(2):
                try:
                    response = await self.call_llm(messages=messages, temperature=0.3)
                    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                    model_result = self.extract_json(content)
                    if model_result:
                        break
                except Exception as e:
                    logger.warning(f"ModelerAgent 逐个建模LLM失败 (attempt {attempt+1}): {e}")
                    if attempt < 1:
                        import asyncio
                        await asyncio.sleep(2)

            if not model_result:
                # 兜底模板：标记为降级模式，非真实建模结果
                model_result = self._smart_template_fallback(sp, suggested, sp_type)
                model_result["_degraded_mode"] = True
                model_result["_degraded_reason"] = "LLM 调用失败（含重试），使用模板兜底"

            model_result["sub_problem_id"] = sp_id
            model_result["sub_problem_name"] = sp_name
            model_result["sub_problem_desc"] = sp_desc

            # 在模型中记录前序依赖
            if prev_model_summary:
                model_result["depends_on"] = [pm.get("sub_problem_id") for pm in previous_models]
                model_result["dependency_note"] = f"该模型依赖前序{len(previous_models)}个子问题的结果"

            all_models.append(model_result)
            previous_models.append(model_result)
            logger.info(f"ModelerAgent: 逐个建模完成 {i+1}/{len(sub_problems)} - {sp_name}，依赖前{len(previous_models)-1}个子问题")

        return {
            "sub_problem_models": all_models,
            "mode": "sequential",
            "total": len(all_models),
        }

    async def _build_single_model(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        problem_text = task_input.get("problem_text", "")
        sub_problem = context.get("sub_problem", {})
        sub_idx = context.get("sub_problem_index", 0)
        analyzer_result = context.get("results", {}).get("analyzer_agent", {})
        suggested_method = sub_problem.get("suggested_method", analyzer_result.get("problem_type", ""))
        problem_type = sub_problem.get("problem_type", analyzer_result.get("problem_type", ""))

        logger.info(f"ModelerAgent: 子问题{sub_idx+1} 建议方法={suggested_method[:50]}...")

        prompt = f"""请为以下数学建模问题建立精确的数学模型：

【问题背景】
{wrap_user_content(problem_text, 'problem')}

【子问题信息】
名称：{sub_problem.get('name', f'子问题{sub_idx+1}')}
描述：{sub_problem.get('description', '')}
问题类型：{problem_type}
建议方法：{suggested_method}

请建立完整的数学模型。"""

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": prompt},
        ]
        # 重试最多 2 次
        for attempt in range(2):
            try:
                response = await self.call_llm(messages=messages)
                content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                result = self.extract_json(content)
                if result:
                    result["sub_problem_index"] = sub_idx
                    result["sub_problem_name"] = sub_problem.get("name", f"子问题{sub_idx+1}")
                    logger.info(f"ModelerAgent 完成: {result.get('model_name', 'unknown')}")
                    return result
            except Exception as e:
                logger.warning(f"ModelerAgent LLM解析失败 (attempt {attempt+1}): {e}")
                if attempt < 1:
                    import asyncio
                    await asyncio.sleep(2)

        # 重试全部失败，使用兜底模板（标记为降级）
        result = self._smart_template_fallback(sub_problem, suggested_method, problem_type)
        result["sub_problem_index"] = sub_idx
        result["sub_problem_name"] = sub_problem.get("name", f"子问题{sub_idx+1}")
        result["_degraded_mode"] = True
        result["_degraded_reason"] = "LLM 调用失败（含重试），使用模板兜底"
        logger.info(f"ModelerAgent 智能模板: {result.get('model_name')}")
        return result

    async def _build_all_models(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """一次性为所有子问题建立数学模型"""
        problem_text = task_input.get("problem_text", "")
        sub_problems = context.get("sub_problems", [])
        analyzer_result = context.get("analyzer_result", context.get("results", {}).get("analyzer_agent", {}))
        data_result = context.get("data_result", {})
        research_result = context.get("research_result", {})

        logger.info(f"ModelerAgent: 批量建模 {len(sub_problems)} 个子问题")

        sp_summary = "\n".join([
            f"[子问题{i+1}] {sp.get('name', sp.get('description','')[:60])}"
            f"\n  类型: {sp.get('problem_type', '-')}"
            f"\n  建议方法: {sp.get('suggested_method', sp.get('approach', '待定'))}"
            for i, sp in enumerate(sub_problems)
        ])

        prompt = f"""你是一个专业的数学建模专家。请为以下数学建模问题的所有子问题一次性建立完整的数学模型。

【问题背景】
{wrap_user_content(problem_text, 'problem')}

【已识别的子问题】
{sp_summary}

【问题类型总览】
{analyzer_result.get('problem_type', '-')}，难度：{analyzer_result.get('difficulty', '-')}
整体思路：{analyzer_result.get('overall_approach', '-')}

【数据分析结果摘要】
{self._summarize_data(data_result)}

【参考文献/方法摘要】
{self._summarize_research(research_result)}

请为每个子问题建立精确的数学模型，输出JSON格式（必须以{{开头，以}}结尾，不要有任何其他文字）：

{{
    "sub_problem_models": [
        {{
            "sub_problem_id": 1,
            "sub_problem_name": "子问题1名称（与上面列表一致）",
            "sub_problem_desc": "子问题完整描述",
            "model_type": "优化/预测/评价/分类/仿真/灵敏度分析",
            "model_name": "具体模型名称",
            "decision_variables": [
                {{"name": "变量名", "description": "变量含义", "type": "连续/整数", "range": "取值范围"}}
            ],
            "parameters": [
                {{"name": "参数名", "description": "参数含义", "source": "参数值或来源"}}
            ],
            "objective_function": "目标函数表达式（如：min Z = ...）",
            "constraints": [
                {{"name": "约束名称", "expression": "约束表达式", "type": "等式/不等式"}}
            ],
            "algorithm": {{"name": "算法名称", "description": "算法原理简述"}},
            "model_assumptions": ["假设1", "假设2"],
            "model_advantages": ["优点1", "优点2"],
            "model_limitations": ["局限性1", "局限性2"]
        }},
        ...（每个子问题都要有一项，共{len(sub_problems)}个）
    ]
}}

要求：
- 每个子问题都要有独立的、完整的数学模型
- 模型要与该子问题的特点高度匹配，不要套用通用模板
- 决策变量要具体、可操作，结合具体问题的变量含义
- 约束条件要完整、合理
- 包含所有{len(sub_problems)}个子问题，不要遗漏"""

        messages = [
            {"role": "system", "content": self._get_batch_system_prompt()},
            {"role": "user", "content": prompt},
        ]
        try:
            response = await self.call_llm(messages=messages, temperature=0.3)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            result = self.extract_json(content)
            if result:
                models = result.get("sub_problem_models", [])
                logger.info(f"ModelerAgent: LLM返回 {len(models)}/{len(sub_problems)} 个模型")

                # LLM截断：返回数量不足，用模板兜底缺失部分
                if 0 < len(models) < len(sub_problems):
                    fallback_result = self._batch_template_fallback(sub_problems, analyzer_result)
                    fallback_models = fallback_result.get("sub_problem_models", [])
                    returned_ids = {m.get("sub_problem_id") for m in models}
                    for fm in fallback_models:
                        if fm.get("sub_problem_id") not in returned_ids:
                            models.append(fm)
                            logger.info(f"ModelerAgent: 模板补充缺失子问题 {fm['sub_problem_id']} - {fm['model_name']}")
                    result["sub_problem_models"] = models
                    logger.info(f"ModelerAgent: 合并后共 {len(models)} 个模型")

                return result
        except Exception as e:
            logger.warning(f"ModelerAgent 批量建模LLM失败: {e}")

        logger.info("ModelerAgent: 使用智能模板批量生成模型")
        return self._batch_template_fallback(sub_problems, analyzer_result)

    def _batch_template_fallback(self, sub_problems: List, analyzer_result: Dict) -> Dict[str, Any]:
        models = []
        for i, sp in enumerate(sub_problems):
            sp_id = sp.get("id", i + 1)
            sp_name = sp.get("name", f"子问题{sp_id}")
            sp_desc = sp.get("description", "")
            sp_type = sp.get("problem_type", "")
            suggested = sp.get("suggested_method", sp.get("approach", ""))
            template_key, category = _smart_template_select(suggested, sp_type, sp_desc)
            templates = MODEL_TEMPLATES.get(category, MODEL_TEMPLATES["optimization"])
            tmpl = templates.get(template_key, list(templates.values())[0])

            variables = []
            for v_str in tmpl.get("variables", []):
                parts = v_str.split(":")
                name = parts[0].strip()
                desc = parts[1].strip() if len(parts) >= 2 else ""
                vtype = "连续"
                if "整数" in v_str:
                    vtype = "整数"
                variables.append({"name": name, "description": desc, "type": vtype, "range": "≥0" if vtype == "连续" else "∈Z+"})

            assumptions = ["假设所有数据真实可靠", "假设模型参数在研究期间保持稳定", "假设各变量满足模型所要求的数学性质"]
            if "预测" in category:
                assumptions += ["假设历史数据模式在未来仍然适用", "假设随机误差服从正态分布"]
            elif "评价" in category:
                assumptions += ["假设评价指标之间相互独立"]

            models.append({
                "sub_problem_id": sp_id,
                "sub_problem_name": sp_name,
                "sub_problem_desc": sp_desc,
                "model_type": category,
                "model_name": tmpl["name"],
                "decision_variables": variables,
                "parameters": [],
                "objective_function": tmpl["formula"],
                "constraints": [{"name": "约束条件", "expression": tmpl.get("constraints_note", ""), "type": "不等式"}],
                "algorithm": {"name": tmpl["algorithm"], "description": tmpl["description"]},
                "model_assumptions": assumptions,
                "model_advantages": [f"模型结构清晰，基于{tmpl['name']}方法", "求解方法成熟"],
                "model_limitations": [
                    f"【兜底模板】本模型由系统根据关键词 '{template_key}' 自动填充，仅作占位参考，必须根据具体问题重新校验或替换",
                    "假设可能过于理想化",
                    "需要根据具体数据调整参数",
                ],
                "_used_fallback_template": True,
                "_fallback_template_key": template_key,
            })
        return {"sub_problem_models": models}

    def _summarize_data(self, data_result: Dict) -> str:
        analyses = data_result.get("analyses", [])
        if not analyses:
            return "（无可用数据文件）"
        parts = [f"- {a.get('file_name', '未知')}: {a.get('shape', [0,0])[0]}行×{a.get('shape',[0,0])[1]}列" for a in analyses[:3]]
        return "\n".join(parts) or "（无可用数据文件）"

    def _summarize_research(self, research_result: Dict) -> str:
        methods = research_result.get("methods", [])
        if not methods:
            return "（无文献资料）"
        return "；".join([m.get("name", str(m)[:50]) for m in methods[:5]])

    def _get_batch_system_prompt(self) -> str:
        return """你是一个专业的数学建模专家。你需要为数学建模问题的所有子问题建立精确的数学模型。

每个子问题的模型必须包含：
1. 决策变量（变量名、含义、类型、取值范围）
2. 参数（参数名、含义、来源）
3. 目标函数（明确的数学表达式）
4. 约束条件（所有约束的完整列表）
5. 求解算法（算法名称和原理）
6. 模型假设、优点、局限性

重要：必须为每个子问题建立独立的、针对性的模型，不能泛泛而谈！"""

    async def _generate_model_code(
        self,
        model: Dict[str, Any],
        data_context: str,
        problem_text: str,
        sp_id: int = 1,
    ) -> Dict[str, Any]:
        """
        使用 Claude Code 生成模型验证/分析代码。

        对于物理类问题（如 SiC 外延层厚度测量），生成：
        - 数据预处理代码（加载 Excel、滤波）
        - 干涉峰检测代码
        - 厚度计算代码（FFT 频域分析或 Airy 公式拟合）
        - 可视化代码
        """
        model_type = model.get("model_type", "")
        model_name = model.get("model_name", "")
        code_hints = model.get("code_hints", "")

        # 构建任务描述
        task_description = f"""请为以下数学建模问题生成数据处理和模型验证代码。

## 问题背景
{wrap_user_content(problem_text, 'problem')}

## 模型信息
- 模型类型：{model_type}
- 模型名称：{model_name}
- 算法：{model.get('algorithm', {}).get('name', '') if isinstance(model.get('algorithm'), dict) else ''}
- 目标函数：{model.get('objective_function', '')}

## 数据文件
{data_context}

## 代码要求
1. 使用 Python，依赖：numpy, scipy, pandas, openpyxl, matplotlib
2. 读取 Excel 数据文件（使用 openpyxl 或 pandas read_excel）
3. 实现完整的{code_hints or model_name}算法
4. 生成可视化图表
5. 代码末尾用 json.dumps() 输出结果 JSON

## 输出格式（必须为 JSON，不要有任何其他文字）
{{
    "code": "完整 Python 代码（包含所有 import，末尾用 json.dumps 打印结果）",
    "file_path": "code/model_validation_sp{sp_id}.py",
    "key_steps": ["步骤1", "步骤2"],
    "expected_output": "输出描述"
}}"""

        try:
            coder_result = await self._call_claude_coder(
                task_description=task_description,
                system_instruction="你是一个专业的算法工程师，擅长用 Python 实现数学模型的验证代码。",
                workspace_dir=None,
                timeout=300,
            )
            return {
                "success": coder_result.get("success", False),
                "code": coder_result.get("code", ""),
                "file_path": coder_result.get("file_path", ""),
                "execution_output": coder_result.get("execution_output", ""),
                "key_findings": coder_result.get("key_findings", []),
                "numerical_results": coder_result.get("numerical_results", {}),
            }
        except Exception as e:
            logger.error(f"ModelerAgent._generate_model_code failed: {e}")
            return {"success": False, "error": str(e)}

    def _smart_template_fallback(self, sub_problem: Dict, suggested_method: str, problem_type: str) -> Dict[str, Any]:
        sub_desc = sub_problem.get("description", "")
        template_key, category = _smart_template_select(suggested_method, problem_type, sub_desc)
        templates = MODEL_TEMPLATES.get(category, MODEL_TEMPLATES["optimization"])
        tmpl = templates.get(template_key, list(templates.values())[0])

        logger.warning(
            f"ModelerAgent 对子问题 '{sub_desc[:40]}' 使用兜底模板 '{template_key}'，"
            f"该结果仅为占位，需人工复核或重新生成问题专属模型。"
        )

        variables = []
        for v_str in tmpl.get("variables", []):
            parts = v_str.split(":")
            name = parts[0].strip()
            desc = parts[1].strip() if len(parts) >= 2 else ""
            vtype = "连续"
            if "整数" in v_str:
                vtype = "整数"
            elif "0-1" in v_str:
                vtype = "0-1"
            variables.append({"name": name, "description": desc, "type": vtype, "range": "≥ 0" if "连续" in vtype else "∈ Z+"})

        assumptions = [
            "假设所有数据真实可靠，来源于实际测量或权威统计",
            "假设模型参数在研究期间保持相对稳定",
            "假设各变量之间满足模型所要求的数学性质",
        ]
        if "预测" in category:
            assumptions += ["假设历史数据的模式在未来仍然适用", "假设随机误差服从正态分布"]
        elif "评价" in category:
            assumptions += ["假设评价指标之间相互独立", "假设评价者的主观判断具有合理一致性"]
        elif "stochastic" in template_key:
            assumptions += ["假设各蔬菜品类的需求相互独立", "假设供应商配送时间稳定"]

        return {
            "model_type": category,
            "model_name": tmpl["name"],
            "decision_variables": variables,
            "parameters": [],
            "objective_function": tmpl["formula"],
            "constraints": [{"name": "约束条件", "expression": tmpl.get("constraints_note", "根据具体问题确定"), "type": "不等式"}],
            "algorithm": {"name": tmpl["algorithm"], "description": tmpl["description"]},
            "model_assumptions": assumptions,
            "model_advantages": ["模型结构清晰，便于理解和解释", "求解方法成熟，计算效率高", f"基于{tmpl['name']}方法，结果具有较好的可解释性"],
            "model_limitations": [
                f"【兜底模板】本模型由系统根据关键词 '{template_key}' 自动填充，仅作占位参考，必须根据具体问题重新校验或替换",
                "假设可能过于理想化，未完全反映实际情况",
                "对数据质量和样本量有一定要求",
                f"需要根据{tmpl['algorithm']}进行参数调优",
            ],
            "_used_fallback_template": True,
            "_fallback_template_key": template_key,
        }
