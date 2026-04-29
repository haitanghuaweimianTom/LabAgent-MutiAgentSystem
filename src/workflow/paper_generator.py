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
5. 直接输出扩充后的完整内容"""

        try:
            expanded = self.call_llm(expand_prompt, "你是一位优秀的学术写作专家。")
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
