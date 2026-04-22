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

    使用安全的split策略（避免复杂非贪婪正则崩溃）：
    - 格式（1）...（2）...（3）...
    - 格式：问题1：...问题2：...
    - 格式：1. ... 2. ... 3. ...
    - 格式：第一问...第二问...
    """
    tasks: List[Tuple[int, str]] = []

    try:
        # ===== 格式1: （1）...（2）...（3）...（中文全角括号）=====
        # 先split on "（数字）"边界，再提取每段
        pattern_split1 = r'（(\d+)）'
        parts = re.split(pattern_split1, text)
        # parts格式: [前缀, "1", "内容1", "2", "内容2", ...]
        i = 1
        while i < len(parts) - 1:
            num = int(parts[i])
            desc = parts[i + 1].strip()
            # 合并后续文本片段直到遇到下一个数字
            j = i + 2
            while j < len(parts):
                next_part = parts[j]
                if re.match(r'^\d+$', next_part):
                    break
                desc += next_part
                j += 1
            desc = desc.strip()
            if len(desc) >= 5:
                tasks.append((num, desc[:200]))
            i = j

        # ===== 格式2: （一）(二)(三)... =====
        chinese_nums_map = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
            '甲': 1, '乙': 2, '丙': 3, '丁': 4
        }
        pattern_split2 = r'（([一二三四五六七八九十甲乙丙丁]+)）'
        parts2 = re.split(pattern_split2, text)
        i = 1
        while i < len(parts2) - 1:
            key = parts2[i]
            if key in chinese_nums_map:
                num = chinese_nums_map[key]
                desc = parts2[i + 1].strip()
                if len(desc) >= 5:
                    tasks.append((num, desc[:200]))
            i += 2

    except Exception:
        pass

    # ===== 格式3: 问题1：... 问题2：... 或 要求1：... =====
    try:
        pattern3 = r'(?:问题|任务|要求|子问题)(\d+)[:：]\s*'
        parts3 = re.split(pattern3, text)
        if len(parts3) > 1:
            i = 1
            while i < len(parts3) - 1:
                num = int(parts3[i])
                desc = parts3[i + 1].strip()
                if len(desc) >= 5:
                    tasks.append((num, desc[:200]))
                i += 2
    except Exception:
        pass

    # ===== 格式4: 1. ... 2. ... 3. ... =====
    try:
        pattern4 = r'(?<![问题任务要求])(\d+)[.、.、]\s*'
        parts4 = re.split(pattern4, text)
        if len(parts4) > 1:
            i = 1
            while i < len(parts4) - 1:
                num = int(parts4[i])
                desc = parts4[i + 1].strip()
                if len(desc) >= 5:
                    tasks.append((num, desc[:200]))
                i += 2
    except Exception:
        pass

    # ===== 格式5: 第一问...第二问... =====
    try:
        chinese_int_map = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10
        }
        pattern5 = r'第([一二三四五六七八九十\d]+)问\s*'
        parts5 = re.split(pattern5, text)
        if len(parts5) > 1:
            i = 1
            while i < len(parts5) - 1:
                key = parts5[i]
                if key.isdigit():
                    num = int(key)
                elif key in chinese_int_map:
                    num = chinese_int_map[key]
                else:
                    num = len(tasks) + 1
                desc = parts5[i + 1].strip()
                if len(desc) >= 5:
                    tasks.append((num, desc[:200]))
                i += 2
    except Exception:
        pass

    # 去重（保留第一次出现的）
    seen = {}
    for num, desc in tasks:
        key = num
        if key not in seen:
            seen[key] = desc
    result = [(k, v) for k, v in seen.items()]

    # 如果没找到任何任务，尝试整体扫描（备用方案）
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
        return """分析数学建模问题，将其分解为多个子问题，逐步建模求解。

输入格式：
{
    "problem_text": "赛题全文"
}

输出格式（严格JSON）：
{
    "sub_problems": [
        {
            "id": 1,
            "name": "子问题名称",
            "description": "该子问题要解决的核心问题",
            "approach": "求解思路"
        }
    ]
}

请仔细阅读赛题，识别每个子问题。输出JSON，不要有任何其他文字。"""

    async def execute(self, task_input: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        problem_text = task_input.get("problem_text", context.get("problem_text", ""))
        logger.info(f"AnalyzerAgent: 分析问题 {problem_text[:80]}...")

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": f'{{"problem_text": "{problem_text}"}}'},
        ]

        try:
            response = await self.call_llm(messages=messages, temperature=0.3)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                result = json.loads(content[start:end])
                logger.info(f"AnalyzerAgent 完成: {len(result.get('sub_problems', []))}个子问题")
                return result
        except Exception as e:
            logger.warning(f"AnalyzerAgent LLM解析失败: {e}")

        return {
            "sub_problems": [{
                "id": 1,
                "name": "问题求解",
                "description": problem_text[:200],
                "approach": "分析求解"
            }]
        }

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
                if "预测" in desc or "forecast" in desc_lower:
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

        return {
            "problem_type": ptype_desc,
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
