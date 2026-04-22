"""建模Agent - 建立数学模型（支持批量建模）

参考 math_modeling_paper_system 的结构化建模：
- 内置模型模板（优化类/预测类/评价类/网络类）
- _build_all_models：一次性为所有子问题建模
- _smart_template_fallback：智能选择模板兜底
"""

import json
import logging
from typing import Any, Dict, List
from .base import BaseAgent, AgentFactory

logger = logging.getLogger(__name__)

# 模型模板库
MODEL_TEMPLATES = {
    "physics": {
        "interference_thickness": {
            "name": "双光束干涉厚度模型",
            "description": "基于红外薄膜干涉原理，通过反射光谱干涉条纹确定外延层厚度",
            "formula": "2·d·√(n(ν)² - sin²θ₀) = m/ν  （干涉极小条件）",
            "constraints_note": "干涉条件 + 斯涅尔定律 + 半波损失",
            "algorithm": "FFT频域分析 + 非线性最小二乘拟合",
            "variables": [
                "d: 外延层厚度(μm), 待求量",
                "n(ν): 外延层折射率(波数函数)",
                "m: 干涉级次(整数)",
            ],
        },
        "multi_beam_interference": {
            "name": "多光束干涉模型(Airy公式)",
            "description": "考虑多次反射透射的高阶干涉效应，使用Airy公式描述多光束干涉",
            "formula": "R(λ) = (R1+R2-2√(R1R2)cosδ)/(1+R1R2-2√(R1R2)cosδ), δ=4πndcosθ/λ",
            "constraints_note": "高反射率界面条件 + 多束相位叠加",
            "algorithm": "Airy公式拟合 + 全局优化算法",
            "variables": [
                "d: 外延层厚度(μm), 待求量",
                "n: 外延层等效折射率",
                "R1,R2: 界面反射率",
            ],
        },
        "sensitivity_analysis": {
            "name": "灵敏度分析与稳健性评估",
            "description": "分析入射角、折射率等参数扰动对厚度计算的影响",
            "formula": "S_i = (Δd/d)/(Δp_i/p_i)  灵敏度系数",
            "constraints_note": "参数扰动范围 + 物理约束",
            "algorithm": "One-at-a-Time + Sobol全局敏感性分析",
            "variables": ["Δd: 厚度变化", "p_i: 输入参数(入射角/折射率等)"],
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
        },
        "integer_programming": {
            "name": "整数规划",
            "description": "决策变量为整数的优化问题",
            "formula": "min Z = c'x, x ∈ Z^n",
            "constraints_note": "整数约束 + 非负约束",
            "algorithm": "分支定界法 / PuLP",
            "variables": ["x_j ∈ Z+: 第j个整数决策变量"],
        },
        "stochastic_optimization": {
            "name": "随机规划/库存优化（报童模型）",
            "description": "考虑需求不确定性的随机优化模型",
            "formula": "max E[利润] = sum(p_i·q_i - c_i·q_i - k_i·E[缺货量])",
            "constraints_note": "需求量约束 + 库存容量约束 + 保质期约束",
            "algorithm": "蒙特卡洛模拟 / 随机规划求解器",
            "variables": ["q_i: 第i种蔬菜的订货量", "d_i ~ N(μ_i, σ_i): 随机需求量", "s_i: 缺货成本系数"],
        },
        "nonlinear_programming": {
            "name": "非线性规划",
            "description": "目标函数或约束包含非线性项",
            "formula": "min f(x), s.t. g_i(x) <= 0",
            "constraints_note": "非线性约束",
            "algorithm": "SLSQP / 内点法",
            "variables": ["x: 决策向量(连续)"],
        },
    },
    "prediction": {
        "time_series": {
            "name": "时间序列预测(ARIMA/SARIMA)",
            "description": "基于历史数据的时间序列预测模型",
            "formula": "ARIMA(p,d,q): φ(B)(1-B)^d Y_t = θ(B)ε_t",
            "constraints_note": "平稳性假设 + 正态分布误差",
            "algorithm": "statsmodels.tsa.arima.ARIMA / pmdarima.auto_arima",
            "variables": ["Y_t: t时刻的值", "ε_t: 白噪声"],
        },
        "prophet": {
            "name": "Prophet时间序列预测",
            "description": "Facebook开源的时间序列预测模型",
            "formula": "Y(t) = g(t) + s(t) + h(t) + ε_t",
            "constraints_note": "趋势+季节性+节假日效应分解",
            "algorithm": "Prophet / statsmodels",
            "variables": ["g(t): 趋势函数", "s(t): 季节性函数", "h(t): 节假日效应"],
        },
        "neural_network": {
            "name": "LSTM神经网络预测",
            "description": "长短期记忆网络，适合捕捉复杂时间依赖关系",
            "formula": "h_t = LSTM(x_t, h_{t-1})",
            "constraints_note": "数据标准化 + 时序数据划分",
            "algorithm": "PyTorch / Keras LSTM / sklearn.MLPRegressor",
            "variables": ["x_t: t时刻输入特征", "h_t: t时刻隐藏状态", "y_hat: 预测值"],
        },
        "regression": {
            "name": "多元回归分析",
            "description": "建立因变量与自变量之间的回归关系",
            "formula": "Y = β_0 + β_1*X_1 + ... + β_p*X_p + ε",
            "constraints_note": "线性假设 + 独立性假设",
            "algorithm": "最小二乘法 / sklearn.linear_model",
            "variables": ["Y: 因变量", "X_j: 第j个自变量", "β_j: 回归系数"],
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
        },
        "entropy_weight": {
            "name": "熵权法",
            "description": "基于信息熵的客观赋权方法",
            "formula": "H_i = -k·sum(p_ij·ln(p_ij)), w_i = (1-H_i)/sum(1-H_i)",
            "constraints_note": "数据归一化处理",
            "algorithm": "信息熵计算 / pandas",
            "variables": ["w_i: 第i个指标的熵权"],
        },
        "topsis": {
            "name": "TOPSIS综合评价",
            "description": "逼近理想解的多指标排序方法",
            "formula": "C_i = D_i_minus / (D_i_plus + D_i_minus)",
            "constraints_note": "指标标准化 + 权重确定",
            "algorithm": "距离计算 / numpy.linalg.norm",
            "variables": ["D_i_plus: 到正理想解距离", "D_i_minus: 到负理想解距离", "C_i: 贴近度"],
        },
    },
    "sensitivity": {
        "sensitivity_analysis": {
            "name": "灵敏度分析与稳健性评估",
            "description": "分析参数变化对最优解的影响程度",
            "formula": "S_i = ΔZ/Δp_i (变化率之比)",
            "constraints_note": "参数扰动实验设计",
            "algorithm": "One-at-a-Time / Sobol指数 / Monte Carlo",
            "variables": ["Δp_i: 参数i的扰动量", "ΔZ: 目标函数变化量"],
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
        },
    },
}


def _smart_template_select(suggested_method: str, problem_type: str, sub_problem_desc: str) -> tuple:
    """根据推荐方法和问题类型智能选择模型模板"""
    text = (suggested_method + problem_type + sub_problem_desc).lower()

    # ===== 物理/光学领域优先 =====
    if any(kw in text for kw in [
        "干涉", "外延", "厚度", "折射率", "光程差", "波数",
        "双光束", "多光束", "干涉仪", "反射率", "相位差", "菲涅尔",
        "碳化硅", "硅晶圆", "SiC", "红外", "opd", "反射光谱",
        "薄膜", "光波", "入射角", "干涉条纹", "膜厚"
    ]):
        if any(kw in text for kw in ["多光束", "多次反射", "airy", "多束", "硅晶圆", "消除影响"]):
            return "multi_beam_interference", "physics"
        if any(kw in text for kw in ["灵敏度", "稳健性", "鲁棒", "参数扰动", "sensitivity", "可靠性", "误差分析"]):
            return "sensitivity_analysis", "physics"
        return "interference_thickness", "physics"

    if any(kw in text for kw in ["灵敏度", "稳健性", "鲁棒性", "sensitivity", "参数扰动"]):
        return "sensitivity_analysis", "sensitivity"
    if any(kw in text for kw in ["sarima", "arima", "arma", "ma", "指数平滑", "holt-winter", "prophet", "时序预测", "预测"]):
        if "prophet" in text:
            return "prophet", "prediction"
        if any(kw in text for kw in ["lstm", "gru", "rnn", "深度学习", "神经网络预测"]):
            return "neural_network", "prediction"
        return "time_series", "prediction"
    if any(kw in text for kw in ["回归", "多元", "线性拟合"]):
        return "regression", "prediction"
    if any(kw in text for kw in ["库存", "报童", "随机规划", "订货量", "采购", "newsvendor"]):
        return "stochastic_optimization", "optimization"
    if any(kw in text for kw in ["ahp", "层次分析", "层次分析法"]):
        return "ahp", "evaluation"
    if any(kw in text for kw in ["熵权", "熵"]):
        return "entropy_weight", "evaluation"
    if any(kw in text for kw in ["topsis", "逼近理想", "综合评价", "评价"]):
        return "topsis", "evaluation"
    if any(kw in text for kw in ["整数", "指派", "调度", "分配问题"]):
        return "integer_programming", "optimization"
    if any(kw in text for kw in ["svm", "支持向量", "分类", "聚类"]):
        return "svm", "classification"
    return "linear_programming", "optimization"


@AgentFactory.register("modeler_agent")
class ModelerAgent(BaseAgent):
    name = "modeler_agent"
    label = "建模师"
    description = "建立数学模型、设计算法"
    default_model = "minimax-m2.7"
    default_llm_backend = "claude"  # 默认使用 Claude Code
    _max_tokens_override = 16000  # 批量建模需要更大的输出

    def get_system_prompt(self) -> str:
        return """你是一个专业的数学建模专家。你需要：
1. 根据问题描述和前期分析，建立精确的数学模型
2. 定义清晰的决策变量、目标函数和约束条件
3. 选择合适的求解算法
4. 给出模型的假设和优缺点

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

请建立完整、准确的数学模型。"""

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

            prompt = f"""你是一个专业的数学建模专家。请为以下数学建模问题的第{i+1}个子问题建立精确的数学模型。

【问题背景】
{problem_text}

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
            try:
                response = await self.call_llm(messages=messages, temperature=0.3)
                content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                start = content.find("{")
                end = content.rfind("}") + 1
                if start != -1 and end > start:
                    model_result = json.loads(content[start:end])
            except Exception as e:
                logger.warning(f"ModelerAgent 逐个建模LLM失败: {e}，使用模板")

            if not model_result:
                model_result = self._smart_template_fallback(sp, suggested, sp_type)

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
{problem_text}

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
        try:
            response = await self.call_llm(messages=messages)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                result = json.loads(content[start:end])
                result["sub_problem_index"] = sub_idx
                result["sub_problem_name"] = sub_problem.get("name", f"子问题{sub_idx+1}")
                logger.info(f"ModelerAgent 完成: {result.get('model_name', 'unknown')}")
                return result
        except Exception as e:
            logger.warning(f"ModelerAgent LLM解析失败: {e}，使用智能模板")

        result = self._smart_template_fallback(sub_problem, suggested_method, problem_type)
        result["sub_problem_index"] = sub_idx
        result["sub_problem_name"] = sub_problem.get("name", f"子问题{sub_idx+1}")
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
{problem_text}

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
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                result = json.loads(content[start:end])
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
                "model_limitations": ["假设可能过于理想化", "需要根据具体数据调整参数"],
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

    def _smart_template_fallback(self, sub_problem: Dict, suggested_method: str, problem_type: str) -> Dict[str, Any]:
        sub_desc = sub_problem.get("description", "")
        template_key, category = _smart_template_select(suggested_method, problem_type, sub_desc)
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
            "model_limitations": [f"假设可能过于理想化，未完全反映实际情况", "对数据质量和样本量有一定要求", f"需要根据{tmpl['algorithm']}进行参数调优"],
        }
