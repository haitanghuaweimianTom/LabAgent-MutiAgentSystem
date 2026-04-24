"""分析Agent - 理解问题、分解任务、制定策略

参考 math_modeling_paper_system 的结构化分析模式：
- 问题类型识别（优化/预测/评价/分类/仿真/网络）
- 关键词匹配 + LLM 联合分析
- 每个子问题包含：类型、难度、建议方法
- 支持多种子问题编号格式：问题1/要求1/（1）/1./第一问等
"""

import logging
import json
import re
from typing import Any, Dict, List, Tuple
from .base import BaseAgent, AgentFactory

logger = logging.getLogger(__name__)


# 问题类型定义（来自 math_modeling_paper_system）
PROBLEM_TYPES = {
    "optimization": {
        "keywords": ["优化", "最小化", "最大化", "最优", "调度", "配置", "分配", "规划", "订货", "采购", "库存"],
        "description": "优化问题",
        "typical_methods": ["线性规划", "整数规划", "非线性规划", "遗传算法", "粒子群优化", "模拟退火"],
    },
    "prediction": {
        "keywords": ["预测", "预报", "估计", "未来", "趋势", "需求", "forecast", "时间序列", "ARIMA", "LSTM"],
        "description": "预测问题",
        "typical_methods": ["时间序列分析", "回归分析", "灰色预测", "神经网络", "LSTM", "ARIMA", "Prophet"],
    },
    "evaluation": {
        "keywords": ["评价", "评估", "排序", "选择", "比较", "优先级", "topsis", "ahp", "层次分析", "综合"],
        "description": "评价问题",
        "typical_methods": ["层次分析法(AHP)", "熵权法", "TOPSIS", "模糊综合评价", "主成分分析"],
    },
    "classification": {
        "keywords": ["分类", "聚类", "识别", "判别", "分组", "分割", "cluster"],
        "description": "分类/聚类问题",
        "typical_methods": ["K-means聚类", "支持向量机", "决策树", "随机森林", "神经网络"],
    },
    "simulation": {
        "keywords": ["模拟", "仿真", "蒙特卡罗", "随机", "风险", "simulation"],
        "description": "模拟仿真问题",
        "typical_methods": ["蒙特卡罗模拟", "系统动力学", "元胞自动机", "排队论"],
    },
    "network": {
        "keywords": ["网络", "图", "路径", "连通", "最短路", "最大流", "network", "graph"],
        "description": "网络图论问题",
        "typical_methods": ["最短路算法", "最大流算法", "最小生成树", "旅行商问题"],
    },
}


def classify_by_keywords(text: str) -> List[Tuple]:
    """通过关键词匹配识别问题类型"""
    text_lower = text.lower()
    scores = []
    for ptype, config in PROBLEM_TYPES.items():
        score = 0
        for kw in config["keywords"]:
            if kw in text_lower:
                score += 1
        if score > 0:
            scores.append((ptype, config["description"], score, config["typical_methods"]))
    scores.sort(key=lambda x: x[2], reverse=True)
    return scores


def _extract_sub_problems(text: str) -> List[Tuple[int, str]]:
    """从文本中提取多个子问题/任务/要求

    策略：用 finditer 找"问题N"边界，然后切分文本
    - "问题N"后面紧跟空格→新问题，内容是"问题N"之后到下一"问题M"之前
    - "问题N"后面紧跟"请/的/等"→引用（如"问题2请根据"、"问题1的"），内容被前一个任务吞掉，跳过
    - 太短的描述（<20字符）且后面紧跟中文→引用，跳过
    """
    import re
    tasks: List[Tuple[int, str]] = []

    try:
        pattern = r'问题(\d+)'
        matches = list(re.finditer(pattern, text))

        for i, m in enumerate(matches):
            num = int(m.group(1))
            next_char = text[m.end()] if m.end() < len(text) else ''

            # 如果后面紧跟常见的引用性词语（如"的"、"请"）且描述很短→ 引用，跳过
            # 但注意："问题2请根据"实际上包含了完整问题2的内容，不能简单跳过
            # 关键判断：如果描述很短（<20）且不是该编号的第一次出现→跳过（是重复引用）
            # 如果描述较长→不是引用，是真正的问题描述
            is_short = len(text[m.end():matches[i+1].start() if i+1 < len(matches) else len(text)].strip()) < 20
            already_have_this_num = any(t_num == num for t_num, _ in tasks)
            if next_char in '的的请了并且但若如要能可应被让给被会已曾还正将将才就便就那就的话' and is_short and already_have_this_num:
                continue
            
            # start: after the match (position right after "问题N")
            start = m.end()
            # end: start of the next match (NOT end of next match)
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            desc = text[start:end].strip()

            if len(desc) < 20 and len(tasks) > 0:
                # Short description → might be a reference like "问题2请根据" or "问题1的"
                # Check if we already have a task with this number that has a MUCH longer description
                existing_idx = None
                for t_idx, (t_num, _) in enumerate(tasks):
                    if t_num == num:
                        existing_idx = t_idx
                        break
                if existing_idx is not None and len(tasks[existing_idx][1]) > 50:
                    # We already have a long description for this number → this is a reference, skip
                    continue
                # Otherwise try to get the full content
                full_start = m.start()  # start from "问题N" itself
                full_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                full_desc = text[full_start:full_end].strip()
                # Remove the "问题N" prefix from the beginning
                full_desc = re.sub(rf'^问题{num}\s*', '', full_desc, count=1)
                # Also truncate at next "问题" occurrence to avoid "问题1的" leaking
                next_prob_m = re.search(r'问题', full_desc)
                if next_prob_m and next_prob_m.start() < 10:
                    full_desc = full_desc[:next_prob_m.start()].strip()
                if len(full_desc) >= 20:
                    desc = full_desc
                else:
                    # Still too short, skip
                    continue

            if len(desc) >= 5:
                # 截断到下一个"问题N"之前，但要注意区分"问题1的"（引用）与"问题2请根据"（新问题开头）
                # "问题1的" → 前面是"的"，是小编号引用，应该截断
                # "问题2请" / "问题3光" → 前面是数字或空白，是新问题开始，不截断
                next_prob_match = re.search(r'问题(\d+)', desc)
                if next_prob_match:
                    m_num = int(next_prob_match.group(1))
                    m_start = next_prob_match.start()
                    # 如果匹配到"问题N"且N比当前编号大，说明是新问题，跳过不截断
                    if m_num > num:
                        pass  # 不截断，继续使用完整desc
                    elif m_start < 5:
                        # "问题1的"在小编号引用这种情况下才截断
                        # 检查前面是否是已有的子问题描述中引用的格式
                        desc = desc[:m_start].strip()
                if len(desc) >= 5:
                    tasks.append((num, desc[:300]))

    except Exception:
        pass

    # 去重（按编号，保留第一次出现的）
    seen = {}
    for num, desc in tasks:
        if num not in seen:
            seen[num] = desc
    result = [(k, v) for k, v in sorted(seen.items(), key=lambda x: x[0])]

    # 如果只有1个或2个子问题但题目明确有3个问题，说明可能漏了问题2
    # 手动检测：题目中有"问题1"和"问题3"但没有"问题2"的结果 → 问题2被漏
    if len(result) <= 2:
        problem_2_match = re.search(r'问题2', text)
        problem_3_match = re.search(r'问题3', text)
        if problem_2_match and problem_3_match:
            # 提取问题2的内容（在"问题2"和"问题3"之间）
            p2_start = problem_2_match.end()
            p2_end = problem_3_match.start()
            p2_desc = text[p2_start:p2_end].strip()
            # 去除开头的前文引用形式（如"请根据问题1的数学模型，"），但保留后面的主要内容
            # 先把"请根据问题1的数学模型，"去掉
            p2_desc = re.sub(r'^请根据问题1的数学模型[，,]\s*', '', p2_desc, count=1)
            # 再把"请根据"去掉
            p2_desc = re.sub(r'^请根据\s*', '', p2_desc, count=1)
            # 再把开头的"的"去掉（来自"问题1的"这种引用）
            p2_desc = re.sub(r'^的\s*', '', p2_desc, count=1)
            p2_desc = p2_desc.strip()
            if len(p2_desc) >= 20:
                # 检查result里是否已有问题2
                existing_nums = {num for num, _ in result}
                if 2 not in existing_nums:
                    result.append((2, p2_desc[:300]))
                    result.sort(key=lambda x: x[0])

    # 如果没找到任何任务，尝试备用方案
    if not result:
        try:
            req_match = re.search(r'(?:要求|问题)[:：]\s*(.{50,1000})', text)
            if req_match:
                result = [(1, req_match.group(1).strip()[:500])]
        except Exception:
            pass

    return result


def _suggest_method_for_subproblem(desc: str, primary_type: str, primary_methods: List[str]) -> str:
    """根据子问题描述推荐具体方法"""
    desc_lower = desc.lower()

    # 针对预测类
    if any(kw in desc_lower for kw in ["预测", "预报", "forecast", "未来需求", "需求量"]):
        if "lstm" in desc_lower or "深度学习" in desc_lower or "神经网络" in desc_lower:
            return "LSTM神经网络"
        if "prophet" in desc_lower:
            return "Prophet时间序列预测"
        if "arima" in desc_lower or "sarima" in desc_lower or "时间序列" in desc_lower:
            return "ARIMA/SARIMA时间序列分析"
        return "时间序列分析"

    # 针对库存/订货优化
    if any(kw in desc_lower for kw in ["订货", "库存", "采购", "报童", "随机规划", "newsvendor", "optimal order"]):
        return "报童模型(随机规划)"

    # 针对灵敏度分析
    if any(kw in desc_lower for kw in ["灵敏度", "灵敏度分析", "稳健性", "鲁棒性", "sensitivity", "参数扰动"]):
        return "灵敏度分析"

    # 针对综合评价
    if any(kw in desc_lower for kw in ["评价", "评估", "排序", "优先级", "重点", "topsis", "ahp"]):
        if "ahp" in desc_lower or "层次" in desc_lower:
            return "层次分析法(AHP)"
        if "熵权" in desc_lower:
            return "熵权法"
        if "topsis" in desc_lower:
            return "TOPSIS综合评价"
        return "TOPSIS综合评价"

    # 针对整数规划/分配
    if any(kw in desc_lower for kw in ["整数", "指派", "调度", "分配"]):
        return "整数规划"

    # 针对分类/聚类
    if any(kw in desc_lower for kw in ["分类", "聚类", "cluster"]):
        return "K-means聚类"

    # 针对回归分析
    if any(kw in desc_lower for kw in ["回归", "相关性", "影响因素"]):
        return "多元回归分析"

    # 默认用主方法
    return primary_methods[0] if primary_methods else "待定"


@AgentFactory.register("analyzer_agent")
class AnalyzerAgent(BaseAgent):
    name = "analyzer_agent"
    label = "分析师"
    description = "理解问题、分解任务、制定策略"
    default_model = "minimax-m2.7"
    default_llm_backend = "claude"  # 默认使用 Claude Code

    def get_system_prompt(self) -> str:
        return """你是一个专业的数学建模分析师，专门分析全国大学生数学建模竞赛（CUMCM）赛题。

你的职责：
1. 识别赛题的核心问题类型（物理/光学测量类 / 优化类 / 预测类 / 评价类 / 综合类）
2. 将赛题分解为若干个子问题
3. 为每个子问题推荐求解方法

【重要】子问题识别规则：
- 每个"问题N"（N=1,2,3,...）都是一个独立子问题，即使它的开头是"请根据"、"请分析"等词语
- 特别注意："问题2请根据问题1..."的意思是"问题2：（请根据问题1...）"，这是一个完整的子问题
- 同理："问题1的数学模型"是前一句的引用，不是新子问题；真正的子问题2是"请根据问题1的数学模型，设计..."这部分
- 子问题的 description 字段应该从"问题N"之后开始，到下一个"问题M"之前结束（不包含对前序问题的引用）

【重要】子问题边界识别（极其关键）：
- 子问题从"问题N"之后开始，到下一个"问题M"之前结束
- 注意题目原文的格式："问题1 如果考虑..."（有空格）和"问题2请根据..."（无空格）和"问题3光波..."（无空格）都是正确的子问题开头
- description 应该从"问题N"之后（跳过任何空格）开始，到下一"问题M"之前结束
- 特别注意：当题目中写"问题2请根据问题1..."时，子问题2的description就是"请根据问题1的数学模型，设计..."（从"请"开始，不是从"问题1的"开始）

【强制规则 - 务必遵守】：
- 如果赛题中出现了"问题1"、"问题2"、"问题3"，则必须输出3个子问题
- 不能输出1个或2个子问题
- problem_type 不能是"网络图论问题"、"评价问题"等与物理/光学无关的类型

【示例 - 与本题格式完全相同】

示例赛题原文：
"问题1 如果考虑外延层和衬底界面只有一次反射，透射所产生的干涉条纹的情形(图1)，建立确定外延层厚度的数学模型。问题2请根据问题1的数学模型，设计确定外延层厚度的算法。对附件1和附件2提供的数据，给出计算结果。问题3光波可以在外延层界面和衬底界面产生多次反射和透射(图2)..."

正确识别结果（description 不包含"问题N"这几个字，只包含问题N之后的内容）：
- 子问题1：description = "如果考虑外延层和衬底界面只有一次反射，透射所产生的干涉条纹的情形(图1)，建立确定外延层厚度的数学模型。"（注意：开头是"如果"，不是"问题1"）
- 子问题2：description = "请根据问题1的数学模型，设计确定外延层厚度的算法。对附件1和附件2提供的数据，给出计算结果，并分析结果的可靠性。"（注意：开头是"请"，不是"问题2请根据"）
- 子问题3：description = "光波可以在外延层界面和衬底界面产生多次反射和透射(图2)，从而产生多光束干涉..."（从"光波"开始，不是"问题3光波"）

输出格式（必须以JSON格式返回，不要有任何其他文字）：
{
    "problem_type": "物理/光学测量类/优化类/预测类/评价类/综合类",
    "difficulty": "简单/中等/困难",
    "overall_approach": "一句话描述总体分析思路",
    "sub_problems": [
        {
            "id": 1,
            "name": "子问题名称（如：双光束干涉厚度测量模型）",
            "description": "该子问题的完整描述，从'问题N'之后开始，到下一'问题M'之前结束",
            "problem_type": "该子问题的类型（物理建模/优化/预测/评价/分析等）",
            "approach": "求解思路",
            "suggested_method": "推荐的具体方法（如：FFT频域分析、Airy公式拟合等）"
        }
    ],
    "key_difficulties": ["难点1", "难点2"],
    "suggested_tools": ["Python", "NumPy", "SciPy"],
    "modeling_hints": ["建模提示1", "建模提示2"]
}

请严格按上述规则识别所有子问题，确保每个"问题N"都有对应的子问题！"""

    async def execute(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        problem_text = task_input.get("problem_text", context.get("problem_text", ""))

        # 预分析：统计"问题N"的数量，提前告知LLM
        problem_markers = re.findall(r'问题(\d+)', problem_text)
        unique_markers = sorted(set(int(m) for m in problem_markers))
        marker_hint = f"本题包含 {len(unique_markers)} 个子问题：{unique_markers}。请为每个子问题输出一个条目。"
        logger.info(f"AnalyzerAgent: 分析问题 (检测到问题标记: {unique_markers}) {problem_text[:80]}...")

        # 调用LLM分析
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": f"请分析以下数学建模竞赛赛题，识别所有子问题：\n\n{problem_text}\n\n{marker_hint}"},
        ]

        try:
            response = await self.call_llm(messages=messages, temperature=0.3)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                result = json.loads(content[start:end])
                subs = result.get("sub_problems", [])
                logger.info(f"AnalyzerAgent 完成: {result.get('problem_type', 'unknown')}, {len(subs)}个子问题")
                for s in subs:
                    logger.info(f"  [{s.get('id')}] {s.get('name', s.get('description','')[:60])}")

                # 验证结果：如果检测到N个问题标记但LLM只返回了1个子问题，认为LLM质量不足，使用fallback
                if len(subs) == 1 and len(unique_markers) >= 2:
                    logger.warning(f"LLM只返回1个子问题但检测到{len(unique_markers)}个问题标记，使用fallback重新分析")
                    raise ValueError("LLM sub-problem count mismatch")

                return result
        except ValueError:
            # LLM质量不足，显式重新执行fallback
            pass
        except Exception as e:
            logger.warning(f"AnalyzerAgent LLM解析失败: {e}")

        # LLM失败时的兜底 - 使用正则提取 + 关键词分析
        extracted_tasks = _extract_sub_problems(problem_text)
        keyword_results = classify_by_keywords(problem_text)
        if keyword_results and not extracted_tasks:
            # 完全没有提取到子问题但有关键词，用fallback
            extracted_tasks = [(1, problem_text[:300])]
        return self._keyword_fallback(problem_text, keyword_results, extracted_tasks)

    def _keyword_fallback(self, text: str, keyword_results: List[Tuple], extracted_tasks: List[Tuple]) -> Dict[str, Any]:
        """关键词+正则分析兜底方案"""
        if not keyword_results:
            keyword_results = [("general", "综合问题", 0, ["系统分析"])]

        top = keyword_results[0]
        ptype_desc = top[1]
        ptype_key = top[0]
        methods = top[3] if len(top) > 3 else ["系统分析"]

        # 使用正则提取的子问题（最可靠）
        sub_problems = []

        if extracted_tasks:
            # 按编号排序
            sorted_tasks = sorted(extracted_tasks, key=lambda x: x[0])
            for idx, (tid, desc) in enumerate(sorted_tasks, 1):
                sp_type = ptype_desc
                sp_method = _suggest_method_for_subproblem(desc, ptype_key, methods)

                # 根据描述中的关键词更新子问题类型和方法
                desc_lower = desc.lower()
                # 优先检测物理/光学关键词（最高优先级）
                if any(kw in desc_lower for kw in ["干涉", "光束", "外延", "厚度", "折射率", "光程差", "波数", "反射率", "多光束", "薄膜", "红外", "光学", "物理"]):
                    sp_type = "物理/光学测量类"
                    sp_method = "干涉法建模"
                elif "预测" in desc or "forecast" in desc_lower:
                    sp_type = "预测问题"
                    if "lstm" in desc_lower: sp_method = "LSTM神经网络"
                    elif "prophet" in desc_lower: sp_method = "Prophet时间序列预测"
                    elif "arima" in desc_lower: sp_method = "ARIMA/SARIMA时间序列"
                    else: sp_method = "时间序列分析"
                elif "订货" in desc or "库存" in desc_lower or "采购" in desc_lower:
                    sp_type = "优化问题"
                    sp_method = "报童模型(随机规划)"
                elif "评价" in desc or "评估" in desc_lower:
                    sp_type = "评价问题"
                    if "ahp" in desc_lower: sp_method = "层次分析法(AHP)"
                    elif "熵权" in desc_lower: sp_method = "熵权法"
                    elif "topsis" in desc_lower: sp_method = "TOPSIS综合评价"
                    else: sp_method = "TOPSIS综合评价"
                elif "灵敏度" in desc or "稳健性" in desc_lower:
                    sp_type = "综合问题"
                    sp_method = "灵敏度分析"
                elif "论文" in desc or "写作" in desc_lower:
                    sp_type = ptype_desc
                    sp_method = "论文写作"
                elif "分配" in desc or "调度" in desc_lower or "整数" in desc_lower:
                    sp_type = "优化问题"
                    sp_method = "整数规划"

                sub_problems.append({
                    "id": idx,
                    "name": f"子问题{idx}: {desc[:30]}",
                    "description": desc,
                    "problem_type": sp_type,
                    "approach": f"采用{sp_method}方法进行分析和求解",
                    "suggested_method": sp_method,
                })
        else:
            # 没有提取到任何任务，使用整体描述
            sub_problems = [{
                "id": 1,
                "name": "问题求解",
                "description": text[:200],
                "problem_type": ptype_desc,
                "approach": f"采用{ptype_desc}方法进行分析",
                "suggested_method": methods[0] if methods else "待定",
            }]

        # 根据字数估算难度
        difficulty = "简单" if len(text) < 200 else "中等" if len(text) < 800 else "困难"

        # 如果有多个子问题，整体难度提升
        if len(sub_problems) >= 3:
            difficulty = "中等"
        if len(sub_problems) >= 5:
            difficulty = "困难"

        # 如果有物理/光学关键词，整体类型改为物理/光学测量类
        text_lower = text.lower()
        if any(kw in text_lower for kw in ["干涉", "外延", "厚度", "折射率", "光程差", "波数", "反射率", "多光束", "碳化硅", "红外"]):
            final_problem_type = "物理/光学测量类"
        else:
            final_problem_type = ptype_desc

        return {
            "problem_type": final_problem_type,
            "difficulty": difficulty,
            "overall_approach": f"采用{ptype_desc}方法，通过{len(sub_problems)}个子问题逐步求解",
            "sub_problems": sub_problems,
            "key_difficulties": [
                f"共{len(sub_problems)}个子问题，子问题间的关联性分析",
                "模型选择的合理性验证",
                "求解算法的效率优化",
            ],
            "suggested_tools": ["Python", "NumPy", "SciPy", "Matplotlib", "Pandas"],
            "modeling_hints": [f"优先使用{top[0]}相关模型", "注意结果验证和灵敏度分析"],
        }


def _build_sub_problems_from_tasks(
    tasks: List[Tuple[int, str]],
    llm_result: Dict[str, Any],
    keyword_results: List[Tuple]
) -> List[Dict[str, Any]]:
    """当LLM只返回1个子问题时，用正则提取的任务列表补充"""
    top = keyword_results[0] if keyword_results else ("general", "综合问题", 0, ["系统分析"])
    ptype_key = top[0]
    ptype_desc = top[1]
    methods = top[3] if len(top) > 3 else ["系统分析"]

    sub_problems = []
    sorted_tasks = sorted(tasks, key=lambda x: x[0])

    for idx, (tid, desc) in enumerate(sorted_tasks, 1):
        sp_method = _suggest_method_for_subproblem(desc, ptype_key, methods)
        sub_problems.append({
            "id": idx,
            "name": f"子问题{idx}: {desc[:30]}",
            "description": desc,
            "problem_type": ptype_desc,
            "approach": f"采用{sp_method}方法进行分析和求解",
            "suggested_method": sp_method,
        })

    return sub_problems
