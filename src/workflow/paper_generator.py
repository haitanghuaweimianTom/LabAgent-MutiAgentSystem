"""
PaperGenerator - 大纲驱动的论文章节生成器
==========================================

借鉴 LLM-MM-Agent 的 PaperGenerator 设计：
- OutlineGenerator: 根据模板动态生成论文大纲
- ContextExtractor: 根据章节相关性映射提取上下文（避免全量堆入）
- ContentGenerator: 调用 LLM 生成章节内容
- 每章生成后进行字数检查与自动扩展
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass

from .templates import PaperTemplate, ChapterSpec
from .critique_engine import CritiqueEngine


class PaperGenerator:
    """
    论文生成器

    职责：
    1. 根据模板大纲逐章生成内容
    2. 利用相关性映射控制上下文长度
    3. 每章生成后进行字数检查与 Critique-Improvement
    4. 组装完整论文
    """

    def __init__(
        self,
        call_llm: Callable[[str, Optional[str]], str],
        template: PaperTemplate,
        output_dir: str = "work",
    ):
        self.call_llm = call_llm
        self.template = template
        self.output_dir = Path(output_dir)
        self.critique_engine = CritiqueEngine(call_llm)
        self.chapters: Dict[str, str] = {}
        self.chapter_summaries: Dict[str, str] = {}  # 各章结构化摘要

    def count_chinese_chars(self, text: str) -> int:
        """统计中文字符数"""
        return len(re.findall(r'[一-鿿]', text))

    def generate_chapter(
        self,
        chapter: ChapterSpec,
        context: Dict[str, Any],
        previous_chapters: Dict[str, str],
        use_critique: bool = True,
    ) -> str:
        """
        生成单个章节

        Args:
            chapter: 章节规格
            context: 全局上下文（分析/建模/执行结果等）
            previous_chapters: 已生成的前置章节（用于衔接）
            use_critique: 是否启用 Critique-Improvement

        Returns:
            str: 章节内容
        """
        print(f"    生成章节: {chapter.title} (目标 {chapter.target_chars} 字)")

        # 1. 提取相关性上下文（避免全量堆入）
        relevant_context = self.template.get_relevance_context(
            chapter, context, max_chars=5000
        )

        # 2. 提取前置章节的关键衔接内容
        previous_summary = self._get_previous_summary(previous_chapters, chapter.id)

        # 3. 构建 Prompt
        system_prompt = self.template.get_system_prompt()

        prompt = self._build_chapter_prompt(
            chapter=chapter,
            relevant_context=relevant_context,
            previous_summary=previous_summary,
        )

        # 4. 生成内容
        try:
            content = self.call_llm(prompt, system_prompt)
        except Exception as e:
            print(f"      生成失败: {e}")
            content = f"## {chapter.title}\n\n（内容生成失败，请补充）"

        content = self._sanitize_chapter_content(content, chapter.title)

        # 5. 字数检查与扩展
        content = self._ensure_length(content, chapter)

        # 6. Critique-Improvement（可选）
        if use_critique and chapter.id not in ["references", "appendix"]:
            print(f"      启动质量评估...")
            content = self.critique_engine.critique_and_improve(
                content=content,
                content_type="paper_chapter",
                context=f"题目：{context.get('problem_text', '')[:1000]}",
                max_iterations=1,
                score_threshold=7.5,
                min_chars=chapter.min_chars,
            )
            content = self._sanitize_chapter_content(content, chapter.title)
            # 再次确保字数
            content = self._ensure_length(content, chapter)

        self.chapters[chapter.id] = content
        return content

    def _build_chapter_prompt(
        self,
        chapter: ChapterSpec,
        relevant_context: str,
        previous_summary: str,
    ) -> str:
        """构建章节生成 Prompt"""
        prompt = f"""请撰写论文的"{chapter.title}"章节。

【章节要求】
- 标题: {chapter.title}
- 目标字数: {chapter.target_chars} 中文字符（至少 {chapter.min_chars} 字）
- 要求内容充实、论证充分、有具体数据支撑
- 禁止空洞的套话和废话
"""

        if chapter.requires_coding:
            prompt += "- 必须引用代码执行产生的具体数值结果\n"
        if chapter.requires_data:
            prompt += "- 必须基于实际数据进行分析和讨论\n"

        if previous_summary:
            prompt += f"\n【与前文的衔接】\n{previous_summary}\n"

        if relevant_context:
            prompt += f"\n【相关资料】\n{relevant_context}\n"

        prompt += f"""
【输出格式要求】
1. 直接输出章节正文，不要输出章节标题（标题已在外部处理）
2. 数学公式使用 LaTeX 格式
3. 表格使用 Markdown 格式
4. 内容要具体深入，每个论点都要有解释和支撑
5. 如果涉及计算结果，必须引用具体数值
6. 确保字数达标，宁可多写不要少写
7. 严禁输出题目原文、摘要或其他章节的标题
"""
        return prompt

    def _get_previous_summary(
        self,
        previous_chapters: Dict[str, str],
        current_id: str,
    ) -> str:
        """获取前置章节的关键内容摘要（用于衔接）"""
        # 定义章节顺序
        chapter_ids = [c.id for c in self.template.get_outline()]
        if current_id not in chapter_ids:
            return ""

        current_idx = chapter_ids.index(current_id)
        summaries = []

        # 只取最近2个前置章节的关键内容
        for prev_id in chapter_ids[max(0, current_idx - 2):current_idx]:
            if prev_id in previous_chapters:
                text = previous_chapters[prev_id]
                # 提取前300字作为摘要
                summary = text[:400] if len(text) < 400 else text[:400] + "..."
                summaries.append(f"前文《{prev_id}》结尾: {summary}")

        return "\n".join(summaries)

    def _sanitize_chapter_content(self, content: str, chapter_title: str) -> str:
        """清理章节内容：移除题目原文、重复标题等污染内容"""
        import re

        # 1. 移除常见的题目原文前缀
        problem_markers = [
            "2025 年高教社杯全国大学生数学建模竞赛题目",
            "（请先阅读",
            "A 题",
            "烟幕干扰弹主要通过化学燃烧",
            "现考虑运用无人机完成烟幕干扰弹的投放策略问题",
            "来袭武器为空地导弹",
            "在导弹来袭过程中，通过投放烟幕干扰弹",
            "为实现更为有效的烟幕干扰效果",
        ]

        lines = content.split("\n")
        cleaned_lines = []
        skip_mode = False
        for line in lines:
            stripped = line.strip()
            # 检测题目原文开始
            if any(stripped.startswith(m) for m in problem_markers[:3]):
                skip_mode = True
                continue
            # 检测题目原文结束
            if skip_mode and stripped.startswith("##") and chapter_title not in stripped:
                skip_mode = False
            if skip_mode and stripped == "---":
                skip_mode = False
                continue
            if not skip_mode:
                cleaned_lines.append(line)

        # 2. 移除重复出现的摘要
        text = "\n".join(cleaned_lines)
        if chapter_title != "摘要":
            idx = text.find("\n## 摘要")
            if idx != -1:
                after = text[idx:]
                next_heading = re.search(r'\n## [^#]', after[1:])
                if next_heading:
                    text = text[:idx] + after[next_heading.start():]
                else:
                    text = text[:idx]

        # 3. 移除内容中重复出现的本章标题
        text = re.sub(rf'\n## {re.escape(chapter_title)}\s*\n', '\n', text)

        return text.strip()

    def _ensure_length(self, content: str, chapter: ChapterSpec) -> str:
        """确保章节字数达标"""
        current_chars = self.count_chinese_chars(content)

        if current_chars >= chapter.min_chars:
            print(f"      字数检查通过: {current_chars} 字")
            return content

        print(f"      字数不足: {current_chars}/{chapter.min_chars} 字，触发扩展...")

        expand_prompt = f"""请将以下论文章节扩充到至少 {chapter.min_chars} 中文字符。

当前内容：
{content}

扩充要求：
1. 在现有内容基础上增加详细推导、深入分析和实例说明
2. 不要简单重复已有内容，要增加新的论据和分析角度
3. 保持学术写作风格，语言严谨
4. 增加的内容要与前文自然衔接
5. 直接输出扩充后的完整内容
6. 严禁输出题目原文、摘要或其他章节的标题"""

        try:
            expanded = self.call_llm(expand_prompt, "你是一位优秀的学术写作专家。")
            expanded = self._sanitize_chapter_content(expanded, chapter.title)
            expanded_chars = self.count_chinese_chars(expanded)
            print(f"      扩展后: {expanded_chars} 字")
            return expanded
        except Exception as e:
            print(f"      扩展失败: {e}")
            return content

    def generate_paper(
        self,
        context: Dict[str, Any],
        use_critique: bool = True,
    ) -> str:
        """
        生成完整论文

        Args:
            context: 全局上下文
            use_critique: 是否启用 Critique-Improvement

        Returns:
            str: 完整论文 Markdown 文本
        """
        outline = self.template.get_outline()
        previous_chapters: Dict[str, str] = {}
        paper_parts = []

        print(f"\n[PaperGenerator] 开始生成论文 ({self.template.name}: {self.template.description})")
        print(f"[PaperGenerator] 共 {len(outline)} 个章节\n")

        for chapter in outline:
            content = self.generate_chapter(
                chapter=chapter,
                context=context,
                previous_chapters=previous_chapters,
                use_critique=use_critique,
            )

            # 格式化章节
            if chapter.id == "abstract":
                # 摘要特殊处理：不加章节号
                paper_parts.append(f"# {self.template.description}论文\n\n## {chapter.title}\n\n{content}\n")
            else:
                paper_parts.append(f"\n## {chapter.title}\n\n{content}\n")

            previous_chapters[chapter.id] = content

        # 组装论文
        paper = "\n".join(paper_parts)

        # 最终字数统计
        total_chars = self.count_chinese_chars(paper)
        print(f"\n[PaperGenerator] 论文生成完成")
        print(f"[PaperGenerator] 总中文字数: {total_chars}")

        return paper

        return paper

    def generate_paper_v2(
        self,
        context: Dict[str, Any],
        memory_pool: Dict[str, str],
        use_critique: bool = True,
    ) -> str:
        """
        生成完整论文 v2.1（显式记忆传递 + 逐章衔接）

        流程：
        1. 预生成：根据记忆池生成每章的详细大纲（要点列表）
        2. 逐章生成：每章 prompt 包含 本章大纲 + 相关阶段摘要 + 前2章摘要
        3. 章节摘要：每章生成后，调用LLM生成结构化摘要（200-300字），存入记忆池
        4. 组装论文
        """
        outline = self.template.get_outline()
        previous_chapters: Dict[str, str] = {}
        paper_parts = []

        print(f"\n[PaperGenerator] 开始生成论文 ({self.template.name})")
        print(f"[PaperGenerator] 共 {len(outline)} 个章节\n")

        # Step 1: 预生成各章大纲
        print("[PaperGenerator] 预生成各章大纲...")
        chapter_outlines = self._pre_generate_outlines(outline, memory_pool, context)

        # Step 2: 逐章生成
        for chapter in outline:
            content = self._generate_chapter_v2(
                chapter=chapter,
                chapter_outline=chapter_outlines.get(chapter.id, ""),
                context=context,
                memory_pool=memory_pool,
                previous_chapters=previous_chapters,
                use_critique=use_critique,
            )

            # 格式化章节
            if chapter.id == "abstract":
                paper_parts.append(f"# {self.template.description}论文\n\n## {chapter.title}\n\n{content}\n")
            else:
                paper_parts.append(f"\n## {chapter.title}\n\n{content}\n")

            previous_chapters[chapter.id] = content

        # 组装论文
        paper = "\n".join(paper_parts)

        # 最终字数统计
        total_chars = self.count_chinese_chars(paper)
        print(f"\n[PaperGenerator] 论文生成完成")
        print(f"[PaperGenerator] 总中文字数: {total_chars}")

        return paper

    def _pre_generate_outlines(
        self,
        outline: List[ChapterSpec],
        memory_pool: Dict[str, str],
        context: Dict[str, Any],
    ) -> Dict[str, str]:
        """
        预生成各章大纲：分批生成，避免单次prompt过长
        """
        summaries = []
        for key in ["analysis_summary", "modeling_summary", "algorithm_summary", "results_summary"]:
            if memory_pool.get(key):
                summaries.append(f"【{key}】\n{memory_pool[key][:250]}\n")

        summary_text = "\n".join(summaries)
        problem_text = context.get("problem_text", "")[:400]

        chapter_outlines = {}

        # 分批生成：每批最多4个章节
        batch_size = 4
        for i in range(0, len(outline), batch_size):
            batch = outline[i:i+batch_size]
            batch_names = "\n".join([f"- {c.id}: {c.title} (目标{c.target_chars}字)" for c in batch])

            prompt = f"""请为以下数学建模论文章节生成详细大纲。

【题目摘要】
{problem_text}

【阶段摘要】
{summary_text}

【本批章节】
{batch_names}

要求：
1. 为每个章节列出3-5个必须覆盖的核心要点
2. 要点要具体、可执行
3. 数值章节必须列出要引用的具体数值结果
4. 公式章节必须列出核心公式

输出格式（严格按此格式）：
---chapter_id---
1. 要点1
2. 要点2
3. 要点3
---end---
"""
            try:
                print(f"    生成大纲批次 {i//batch_size + 1}/{(len(outline)-1)//batch_size + 1}...")
                response = self.call_llm(prompt, "你是数学建模论文写作专家，擅长规划论文结构。")
            except Exception as e:
                print(f"    大纲生成失败: {e}")
                continue

            # 解析本批大纲
            current_id = None
            current_lines = []
            for line in response.split("\n"):
                stripped = line.strip()
                if stripped.startswith("---") and stripped.endswith("---") and "end" not in stripped:
                    if current_id and current_lines:
                        chapter_outlines[current_id] = "\n".join(current_lines)
                    current_id = stripped.strip("-").strip()
                    current_lines = []
                elif stripped == "---end---":
                    if current_id and current_lines:
                        chapter_outlines[current_id] = "\n".join(current_lines)
                    current_id = None
                    current_lines = []
                elif current_id is not None:
                    current_lines.append(stripped)
            if current_id and current_lines:
                chapter_outlines[current_id] = "\n".join(current_lines)

        # 为缺失的章节生成默认大纲
        for ch in outline:
            if ch.id not in chapter_outlines or not chapter_outlines[ch.id]:
                chapter_outlines[ch.id] = f"1. 撰写{ch.title}的核心内容\n2. 与前后章节衔接\n3. 确保字数达标"

        return chapter_outlines

    def _generate_chapter_v2(
        self,
        chapter: ChapterSpec,
        chapter_outline: str,
        context: Dict[str, Any],
        memory_pool: Dict[str, str],
        previous_chapters: Dict[str, str],
        use_critique: bool = True,
    ) -> str:
        """
        生成单个章节 v2.1（显式记忆传递）
        """
        print(f"    生成章节: {chapter.title} (目标 {chapter.target_chars} 字)")

        # 1. 提取前置章节摘要（用于衔接）
        prev_summaries = self._get_previous_summaries(previous_chapters, chapter.id)

        # 2. 选择相关阶段摘要
        relevant_summaries = self._select_relevant_summaries(chapter.id, memory_pool)

        # 3. 构建 Prompt
        system_prompt = self.template.get_system_prompt()

        prompt = self._build_chapter_prompt_v2(
            chapter=chapter,
            chapter_outline=chapter_outline,
            relevant_summaries=relevant_summaries,
            previous_summaries=prev_summaries,
        )

        # 4. 生成内容
        try:
            content = self.call_llm(prompt, system_prompt)
        except Exception as e:
            print(f"      生成失败: {e}")
            content = f"## {chapter.title}\n\n（内容生成失败，请补充）"

        # 4.5 清理污染内容
        content = self._sanitize_chapter_content(content, chapter.title)

        # 5. 字数检查与扩展
        content = self._ensure_length(content, chapter)

        # 6. Critique-Improvement（可选）
        if use_critique and chapter.id not in ["references", "appendix"]:
            print(f"      启动质量评估...")
            content = self.critique_engine.critique_and_improve(
                content=content,
                content_type="paper_chapter",
                context=f"题目：{context.get('problem_text', '')[:1000]}",
                max_iterations=1,
                score_threshold=7.5,
                min_chars=chapter.min_chars,
            )
            content = self._sanitize_chapter_content(content, chapter.title)
            content = self._ensure_length(content, chapter)

        # 7. 生成章节摘要（用于后续章节衔接）
        chapter_summary = self._summarize_chapter(chapter.id, chapter.title, content)
        self.chapter_summaries[chapter.id] = chapter_summary
        self.chapters[chapter.id] = content

        return content

    def _build_chapter_prompt_v2(
        self,
        chapter: ChapterSpec,
        chapter_outline: str,
        relevant_summaries: str,
        previous_summaries: str,
    ) -> str:
        """构建 v2.1 章节生成 Prompt"""
        prompt = f"""请撰写论文的"{chapter.title}"章节。

【章节大纲 - 必须覆盖以下要点】
{chapter_outline}

【字数要求】
- 目标字数: {chapter.target_chars} 中文字符
- 最低字数: {chapter.min_chars} 中文字符
- 内容必须充实、论证充分、有具体数据/公式支撑
- 禁止空洞的套话和废话
"""

        if previous_summaries:
            prompt += f"\n【与前文的衔接 - 必须呼应以下内容】\n{previous_summaries}\n"

        if relevant_summaries:
            prompt += f"\n【相关资料 - 可引用以支撑本章】\n{relevant_summaries}\n"

        prompt += """
【输出格式要求】
1. 直接输出章节正文，不要输出章节标题（标题已在外部处理）
2. 数学公式使用 LaTeX 格式
3. 表格使用 Markdown 格式
4. 内容要具体深入，每个论点都要有解释和支撑
5. 如果涉及计算结果，必须引用具体数值
6. 确保字数达标，宁可多写不要少写
7. 必须与本章大纲的每个要点对应
"""
        return prompt

    def _get_previous_summaries(
        self,
        previous_chapters: Dict[str, str],
        current_id: str,
    ) -> str:
        """获取前置章节的结构化摘要（优先使用已生成的摘要）"""
        chapter_ids = [c.id for c in self.template.get_outline()]
        if current_id not in chapter_ids:
            return ""

        current_idx = chapter_ids.index(current_id)
        summaries = []

        # 优先使用已生成的结构化摘要
        for prev_id in chapter_ids[max(0, current_idx - 2):current_idx]:
            if prev_id in self.chapter_summaries:
                summaries.append(f"前文《{prev_id}》核心结论:\n{self.chapter_summaries[prev_id]}")
            elif prev_id in previous_chapters:
                # 回退到原始文本截断
                text = previous_chapters[prev_id]
                summary = text[:300] if len(text) < 300 else text[:300] + "..."
                summaries.append(f"前文《{prev_id}》结尾: {summary}")

        return "\n\n".join(summaries)

    def _select_relevant_summaries(self, chapter_id: str, memory_pool: Dict[str, str]) -> str:
        """根据章节类型选择最相关的阶段摘要"""
        parts = []

        # 摘要、问题重述、问题分析 -> 主要用 analysis_summary
        if chapter_id in ["abstract", "problem_statement", "problem_analysis"]:
            if memory_pool.get("analysis_summary"):
                parts.append(f"【问题分析摘要】\n{memory_pool['analysis_summary'][:600]}")

        # 模型假设、符号说明、模型建立 -> 主要用 modeling_summary
        if chapter_id in ["model_assumptions", "symbol_definition", "model_establishment"]:
            if memory_pool.get("modeling_summary"):
                parts.append(f"【数学建模摘要】\n{memory_pool['modeling_summary'][:800]}")
            if memory_pool.get("analysis_summary"):
                parts.append(f"【问题分析摘要】\n{memory_pool['analysis_summary'][:400]}")

        # 模型求解 -> 用 modeling + algorithm
        if chapter_id in ["model_solution"]:
            if memory_pool.get("modeling_summary"):
                parts.append(f"【数学建模摘要】\n{memory_pool['modeling_summary'][:600]}")
            if memory_pool.get("algorithm_summary"):
                parts.append(f"【算法摘要】\n{memory_pool['algorithm_summary'][:400]}")

        # 结果分析 -> 用 results_summary
        if chapter_id in ["result_analysis", "sensitivity_analysis"]:
            if memory_pool.get("results_summary"):
                parts.append(f"【计算结果摘要】\n{memory_pool['results_summary'][:800]}")
            if memory_pool.get("modeling_summary"):
                parts.append(f"【数学建模摘要】\n{memory_pool['modeling_summary'][:400]}")

        # 模型评价 -> 用 modeling + results
        if chapter_id in ["model_evaluation"]:
            if memory_pool.get("modeling_summary"):
                parts.append(f"【数学建模摘要】\n{memory_pool['modeling_summary'][:500]}")
            if memory_pool.get("results_summary"):
                parts.append(f"【计算结果摘要】\n{memory_pool['results_summary'][:500]}")

        # 附录 -> 用 code
        if chapter_id == "appendix":
            parts.append("【代码说明】\n代码已附在附录中，请描述核心算法流程。")

        return "\n\n".join(parts)

    def _summarize_chapter(self, chapter_id: str, chapter_title: str, content: str) -> str:
        """生成章节的结构化摘要（200-300字），供后续章节衔接"""
        # 简单截断作为fallback
        if len(content) < 300:
            return content

        prompt = f"""请对以下论文章节进行结构化提炼，生成200-300字的摘要。

章节：{chapter_title}
内容：
{content[:1500]}

摘要要求：
1. 核心结论（1-2句话）
2. 关键数据/公式（如有）
3. 与下文的衔接点（本章为后文奠定了什么基础）

输出纯文本，不要标题。"""

        try:
            summary = self.call_llm(prompt, "你是学术写作专家，擅长提炼章节要点。")
            return summary.strip()
        except Exception:
            # Fallback: 提取前250字
            return content[:250] + "..."

    def _ensure_length(self, content: str, chapter: ChapterSpec) -> str:
        """确保章节字数达标"""
        current_chars = self.count_chinese_chars(content)

        if current_chars >= chapter.min_chars:
            print(f"      字数检查通过: {current_chars} 字")
            return content

        print(f"      字数不足: {current_chars}/{chapter.min_chars} 字，触发扩展...")

        expand_prompt = f"""请将以下论文章节扩充到至少 {chapter.min_chars} 中文字符。

当前内容：
{content}

扩充要求：
1. 在现有内容基础上增加详细推导、深入分析和实例说明
2. 不要简单重复已有内容，要增加新的论据和分析角度
3. 保持学术写作风格，语言严谨
4. 增加的内容要与前文自然衔接
5. 直接输出扩充后的完整内容
6. 严禁输出题目原文、摘要或其他章节的标题"""

        try:
            expanded = self.call_llm(expand_prompt, "你是一位优秀的学术写作专家。")
            expanded = self._sanitize_chapter_content(expanded, chapter.title)
            expanded_chars = self.count_chinese_chars(expanded)
            print(f"      扩展后: {expanded_chars} 字")
            return expanded
        except Exception as e:
            print(f"      扩展失败: {e}")
            return content

    def save_paper(self, paper: str, filename: str = "paper.md"):
        """保存论文到文件"""
        output_path = self.output_dir / "final" / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(paper, encoding="utf-8")
        print(f"[PaperGenerator] 论文已保存: {output_path}")
        return output_path

    def export_chapters_json(self, filepath: str):
        """导出各章节为 JSON（便于调试和复用）"""
        data = {
            "template": self.template.name,
            "chapters": self.chapters,
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
