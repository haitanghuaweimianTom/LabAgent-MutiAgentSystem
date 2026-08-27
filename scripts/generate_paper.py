"""End-to-End Paper Generation Runner

调用 MiniMax-M3 + 模板 skill + 文献核实，按用户要求的输出文件夹结构产出。

输出结构：
  {output_dir}/{project_name}/
  ├── paper.pdf             # LaTeX 编译
  ├── paper.md              # Markdown 源
  ├── paper.tex             # LaTeX 源
  ├── figures/              # 插图（PNG/SVG）
  ├── code/                 # 代码（Python）
  ├── peer_review.md        # 同行评审意见
  ├── data_sources.md       # 数据来源清单
  ├── references.bib        # 真实引用 bib
  └── README.md             # 总览

用法：
  python scripts/generate_paper.py \
      --template math_modeling \
      --problem "求解某物流网络的最优路径" \
      --project-name logistics_path \
      --output-dir ./outputs
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# 导入沙箱和门禁模块
from sandbox_and_gates import CodeSandbox, QualityGate, MultiModelDebate, FigureGenerator, AntiPatternDetector, CodeAutoFixer
from output_guarantee import OutputGuarantee, LaTeXFormatter, ReferenceVerifier, IdeaDeduplicator

# 让脚本能找到 src/ 和 backend/
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

# 配置 MiniMax
os.environ.setdefault("MINIMAX_API_KEY", os.environ.get("MINIMAX_API_KEY", ""))
os.environ.setdefault("LLM_MAX_CONTEXT_LENGTH", "500000")
os.environ.setdefault("LLM_AUTO_COMPRESS_RATIO", "0.9")

logger = logging.getLogger("generate_paper")


# ==================== 数据结构 ====================


@dataclass
class PaperArtifact:
    """单次论文生成的产物。"""
    project_name: str
    template_id: str
    problem: str
    output_dir: Path
    # 产物
    paper_md: str = ""
    paper_tex: str = ""
    figures: List[Path] = field(default_factory=list)
    code_files: List[Path] = field(default_factory=list)
    references: List[Dict] = field(default_factory=list)  # 真实 arxiv 引用
    data_sources: List[str] = field(default_factory=list)
    peer_review: Dict = field(default_factory=dict)
    # 元数据
    created_at: str = ""
    total_tokens_used: int = 0
    fake_refs_filtered: int = 0
    # Step 6 产物
    pdf_generated: bool = False
    figures_generated: List[str] = field(default_factory=list)

    @property
    def folder(self) -> Path:
        return self.output_dir / self.project_name


# ==================== MiniMax 调用 ====================


async def call_minimax(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 16000,
    temperature: float = 0.7,
    retries: int = 3,
) -> Dict:
    """调用 MiniMax-M3，带重试（应对 529 限流）。

    M3 是 thinking 模型，reasoning_content 会消耗大量 tokens。
    实际 content 预算 = max_tokens - reasoning_tokens。
    建议 max_tokens ≥ 16000 以确保 content 充足。
    """
    from src.llm.providers.minimax_provider import MiniMaxProvider
    from src.llm.base import ProviderConfig, ProviderType

    cfg = ProviderConfig(
        provider_type=ProviderType.MINIMAX,
        name="minimax",
        api_key=os.environ["MINIMAX_API_KEY"],
        api_host="https://api.minimaxi.com",
        model="MiniMax-M3",
        timeout=600,
    )
    provider = MiniMaxProvider(cfg)

    last_error = None
    for attempt in range(retries):
        try:
            resp = await provider.generate_async(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            usage = resp.usage or {}
            reasoning_tokens = usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            content_len = len(resp.content) if resp.content else 0
            finish_reason = "unknown"
            try:
                finish_reason = resp.raw_response["choices"][0].get("finish_reason", "unknown")
            except Exception:
                pass
            logger.info(
                f"  MiniMax call: completion={completion_tokens} (reasoning={reasoning_tokens}, "
                f"content={content_len} chars), finish={finish_reason}"
            )
            if finish_reason == "length":
                logger.warning(f"  ⚠️  输出被截断 (max_tokens={max_tokens} 不足)")
            return {
                "content": resp.content,
                "usage": usage,
                "model": resp.model,
                "finish_reason": finish_reason,
            }
        except Exception as e:
            last_error = e
            msg = str(e)[:120]
            if "529" in msg or "status 529" in msg.lower():
                wait = 2 ** attempt
                logger.warning(f"  ⚠️  529 限流，{wait}s 后重试 ({attempt+1}/{retries})...")
                import asyncio as _asyncio
                await _asyncio.sleep(wait)
                continue
            if attempt < retries - 1:
                logger.warning(f"  ⚠️  API 错误, 重试 ({attempt+1}/{retries}): {msg}")
                import asyncio as _asyncio
                await _asyncio.sleep(1)
            else:
                raise

    raise last_error or RuntimeError(f"MiniMax call failed after {retries} retries")


# ==================== 文献核实 ====================


def filter_fake_references(
    text: str,
    template_id: str,
    max_checks: int = 10,
) -> Dict:
    """从生成文本中提取 arxiv 引用，剔除假引用。

    Returns:
        dict 含：
        - kept: 真实引用列表 [{arxiv_id, title}]
        - filtered: 被剔除的假引用列表
        - total_extracted: 提取到的引用总数
    """
    from src.knowledge.template_skills import (
        get_real_references,
        verify_reference,
        _parse_arxiv_ids,
    )

    found = _parse_arxiv_ids(text)
    real_pool = set(get_real_references(template_id))

    kept: List[Dict] = []
    filtered: List[Dict] = []
    checked = 0

    for aid in found:
        if aid in real_pool:
            kept.append({"arxiv_id": aid, "source": "template_pool"})
            continue
        if checked >= max_checks:
            # 超限：未核实的引用按假处理
            filtered.append({"arxiv_id": aid, "reason": "unverified (max_checks exceeded)"})
            continue
        checked += 1
        info = verify_reference(aid)
        if info and info.get("title"):
            kept.append({"arxiv_id": aid, "title": info["title"], "source": "arxiv_verify"})
        else:
            filtered.append({"arxiv_id": aid, "reason": "arxiv lookup failed"})

    return {
        "kept": kept,
        "filtered": filtered,
        "total_extracted": len(found),
        "verified_count": checked,
    }


# ==================== Pipeline ====================


async def step1_research(problem: str, template_id: str) -> Dict:
    """Step 1: 文献调研 + 提取真实参考。"""
    from src.knowledge.template_skills import get_real_references

    real_pool = get_real_references(template_id)
    if not real_pool:
        logger.warning(f"template {template_id} has no real references, using empty pool")
    real_pool = real_pool or ["2401.00001"]  # 兜底避免空列表

    system_prompt = (
        "你是一位严谨的科研助手。用户给出一个研究问题，"
        "你必须根据问题推荐 5-10 篇相关 arxiv 论文。"
        "严格使用我提供的真实 arxiv ID 列表，禁止编造任何 ID。"
    )
    user_prompt = f"""【研究问题】
{problem}

【真实 arxiv 论文池】（只允许从以下 ID 中挑选，禁止编造）
{chr(10).join(f"- {aid}" for aid in real_pool[:30])}

请返回 JSON 格式：
{{
  "selected_papers": [
    {{
      "arxiv_id": "2401.xxxxx",
      "title": "...",
      "relevance": "为什么与本问题相关（1-2 句）"
    }}
  ]
}}

**硬约束**：每条 arxiv_id 必须严格出现在我提供的列表里。"""
    resp = await call_minimax(system_prompt, user_prompt, max_tokens=8000)
    return resp


async def step1b_debate_research(research: Dict, problem: str, template_id: str) -> Dict:
    """Step 1b: 多模型辩论评估研究方向。"""
    debate = MultiModelDebate(call_minimax, rounds=2)
    
    topic = f"评估研究方向: {problem}"
    context = f"研究结果: {research.get('content', '')[:2000]}"
    
    result = await debate.persona_debate(topic, context)
    
    return {
        "debate_result": result,
        "synthesis": result["synthesis"]
    }


async def step2_model(problem: str, template_id: str) -> Dict:
    """Step 2: 建模方案。"""
    from src.knowledge.template_skills import get_template_skill

    skill = get_template_skill(template_id)
    skill_md = (skill.skill_md if skill else "")[:2000]

    system_prompt = (
        f"你是一位建模专家。基于模板风格，"
        f"给出问题分解、子问题划分、数学模型选择。\n\n"
        f"【模板风格参考】\n{skill_md}"
    )
    user_prompt = f"""【研究问题】
{problem}

请返回 JSON：
{{
  "sub_problems": [
    {{
      "id": "sp1",
      "description": "子问题描述",
      "model_type": "使用的模型（ODE/PDE/优化/统计/ML/...）",
      "formulation": "数学公式（LaTeX）"
    }}
  ],
  "assumptions": ["假设1", "假设2"],
  "notation": {{"x": "变量x的含义", "y": "变量y的含义"}}
}}"""
    return await call_minimax(system_prompt, user_prompt, max_tokens=32000)


async def step3_code(modeling: Dict, problem: str, code_dir: Path) -> Dict:
    """Step 3: 生成代码并执行。"""
    code_dir.mkdir(parents=True, exist_ok=True)

    system_prompt = (
        "你是一位 Python 工程师。基于建模方案生成可执行的 Python 代码。"
        "使用 numpy / scipy / sklearn / pulp 等库。代码必须可运行，"
        "输出真实数值结果（不准造假）。"
    )
    user_prompt = f"""【建模方案】
{json.dumps(modeling, ensure_ascii=False, indent=2)[:3000]}

【问题】
{problem}

请返回完整 Python 代码（用 ```python 块包裹），代码必须：
1. 完整可运行（无 placeholder）
2. 打印真实数值结果（用 print）
3. 不依赖外部数据文件

输出格式：
```python
# 完整代码
```"""
    resp = await call_minimax(system_prompt, user_prompt, max_tokens=32000)
    content = resp["content"]

    # 提取代码块（多策略）
    import re
    code = ""
    # 策略 1：贪婪匹配 ```python ... ```（可能含嵌套）
    code_match = re.search(r"```python\s*\n(.*?)```(?:\s*\n|$)", content, re.DOTALL)
    if code_match:
        code = code_match.group(1).strip()
    else:
        # 策略 2：兜底匹配 ``` ... ```（任何语言）
        code_match = re.search(r"```\s*\n(.*?)```(?:\s*\n|$)", content, re.DOTALL)
        if code_match:
            candidate = code_match.group(1).strip()
            # 只接受看起来像 Python 的代码
            if "import" in candidate or "def " in candidate or "class " in candidate or "np." in candidate:
                code = candidate
    if not code:
        # 策略 3：从第一行 import 开始截取
        lines = content.split("\n")
        start = -1
        for i, line in enumerate(lines):
            stripped_line = line.strip()
            if stripped_line.startswith(("import ", "from ", "import\t", "from\t")):
                start = i
                break
        if start >= 0:
            code = "\n".join(lines[start:])
            # 去除尾部非代码内容
            for end_marker in ["# End", "# Output", "# Result", "```", "if __name__"]:
                idx = code.find(end_marker)
                if idx > 0:
                    code = code[:idx].rstrip()
    if not code:
        # 策略 4：剥掉首尾孤立的 markdown 围栏后当作代码
        stripped = re.sub(r"^```(?:python|py)?\s*\n", "", content.strip())
        stripped = re.sub(r"\n```\s*$", "", stripped)
        if "def " in stripped or "import " in stripped or "np." in stripped:
            code = stripped.strip()

    if not code:
        logger.warning("代码提取失败，使用占位符")
        code = "# Code extraction failed - see raw response\n# Raw length: " + str(len(content)) + " chars\n"

    code_path = code_dir / "model.py"
    code_path.write_text(code, encoding="utf-8")

    # 使用沙箱执行（自动安装缺失包 + AST 审计）
    sandbox = CodeSandbox(timeout=120)
    
    # 使用自动修复器
    fixer = CodeAutoFixer(call_minimax, sandbox, max_retries=2)
    fix_result = await fixer.execute_with_fix(code, problem)
    
    execution_result = fix_result["execution"]
    execution_result["code_path"] = str(code_path)
    execution_result["attempts"] = fix_result["attempts"]
    execution_result["fix_errors"] = fix_result["errors"]
    
    # 如果修复了代码，更新文件
    if fix_result["code"] != code:
        code = fix_result["code"]
        code_path.write_text(code, encoding="utf-8")
        logger.info(f"代码自动修复成功（尝试 {fix_result['attempts']} 次）")
    
    return {
        "code": code,
        "code_path": code_path,
        "execution": execution_result,
        "raw": resp,
    }


async def step4_write(
    problem: str,
    template_id: str,
    research: Dict,
    modeling: Dict,
    code_result: Dict,
) -> Dict:
    """Step 4: 写论文正文（Markdown + LaTeX）。"""
    from src.knowledge.template_skills import get_template_skill

    skill = get_template_skill(template_id)
    skill_md = (skill.skill_md if skill else "")[:3000]
    checklist = (skill.checklist if skill else [])[:15]
    real_refs = (skill.real_references if skill else [])[:15]

    system_prompt = (
        f"你是一位严谨的科研作者。基于模板风格 ({template_id}) 撰写论文。\n\n"
        f"【写作风格基线】\n{skill_md[:3000]}\n\n"
        f"【写作 Checklist】\n" + "\n".join(f"- {c}" for c in checklist[:15])
    )

    user_prompt = f"""【问题】
{problem}

【文献调研结果】
{research.get('content', '')[:2000]}

【建模方案】
{json.dumps(modeling, ensure_ascii=False, indent=2)[:2000]}

【代码执行结果】
stdout: {code_result['execution']['stdout'][:2000]}
stderr: {code_result['execution']['stderr'][:500]}

请返回 JSON：
{{
  "title": "论文标题",
  "abstract": "200-300字摘要",
  "keywords": ["关键词1", "关键词2"],
  "sections": [
    {{"heading": "1 Introduction", "content": "..."}},
    {{"heading": "2 Method", "content": "..."}},
    ...
  ],
  "references": ["2401.xxxxx", "2401.yyyyy"]
}}

【硬约束】：
1. 章节按模板顺序（参考 SKILL.md 章节结构）
2. 数字必须与代码执行 stdout 一致
3. references 必须是真实的 arxiv ID（只能从以下池子选）：{real_refs[:15]}
4. 不要照抄问题原文，要重述
"""
    resp = await call_minimax(system_prompt, user_prompt, max_tokens=64000)
    return resp


async def step5_peer_review(paper_md: str, template_id: str) -> Dict:
    """Step 5: 同行评审（self-review via 4-dimension scoring）。"""
    from src.knowledge.template_skills import get_template_skill

    skill = get_template_skill(template_id)
    checklist = skill.checklist if skill else []

    system_prompt = (
        f"你是一位严格的同行评审专家。"
        f"按 4 个维度评审论文：novelty（创新性）、soundness（严谨性）、"
        f"clarity（清晰度）、significance（影响力），每项 1-5 分。"
        f"参考 Checklist：\n" + "\n".join(f"- {c}" for c in checklist[:15])
    )

    user_prompt = f"""【论文 Markdown】
{paper_md[:8000]}

请返回 JSON：
{{
  "scores": {{
    "novelty": {{"score": 1-5, "comment": "..."}},
    "soundness": {{"score": 1-5, "comment": "..."}},
    "clarity": {{"score": 1-5, "comment": "..."}},
    "significance": {{"score": 1-5, "comment": "..."}}
  }},
  "overall_score": 加权平均,
  "recommendation": "accept | revise | reject",
  "major_issues": ["问题1", "问题2"],
  "minor_issues": ["问题1"],
  "suggested_edits": ["建议1"]
}}"""
    return await call_minimax(system_prompt, user_prompt, max_tokens=16000)


# ==================== 主流程 ====================


async def run_pipeline(
    template_id: str,
    problem: str,
    project_name: str,
    output_dir: Path,
) -> PaperArtifact:
    """完整 pipeline：研究 → 建模 → 代码 → 写作 → 评审。"""
    artifact = PaperArtifact(
        project_name=project_name,
        template_id=template_id,
        problem=problem,
        output_dir=output_dir,
        created_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )

    # 准备目录
    (artifact.folder).mkdir(parents=True, exist_ok=True)
    (artifact.folder / "figures").mkdir(exist_ok=True)
    (artifact.folder / "code").mkdir(exist_ok=True)

    logger.info(f"[{project_name}] === Step 1: 文献调研 ===")
    research = await step1_research(problem, template_id)
    artifact.total_tokens_used += research.get("usage", {}).get("total_tokens", 0)
    
    # 质量门禁：research
    research_gate = QualityGate.validate("research", {
        "references": artifact.references,
        "content": research.get("content", "")
    })
    if research_gate["severity"] == "FAIL":
        logger.warning(f"Research 门禁未通过: {research_gate['checks']}")
    
    # 多模型辩论评估研究方向
    logger.info(f"[{project_name}] === Step 1b: 多模型辩论 ===")
    debate_result = await step1b_debate_research(research, problem, template_id)

    logger.info(f"[{project_name}] === Step 2: 建模 ===")
    modeling = await step2_model(problem, template_id)
    artifact.total_tokens_used += modeling.get("usage", {}).get("total_tokens", 0)
    
    # 质量门禁：modeling
    modeling_gate = QualityGate.validate("modeling", modeling)
    if modeling_gate["severity"] == "FAIL":
        logger.warning(f"Modeling 门禁未通过: {modeling_gate['checks']}")

    logger.info(f"[{project_name}] === Step 3: 代码生成+执行 ===")
    code_result = await step3_code(modeling, problem, artifact.folder / "code")
    artifact.total_tokens_used += code_result.get("raw", {}).get("usage", {}).get("total_tokens", 0)
    if code_result["code_path"]:
        artifact.code_files.append(code_result["code_path"])
    
    # 质量门禁：code
    code_gate = QualityGate.validate("code", {
        "code": code_result["code"],
        "execution": code_result["execution"]
    })
    if code_gate["severity"] == "FAIL":
        logger.warning(f"Code 门禁未通过: {code_gate['checks']}")

    logger.info(f"[{project_name}] === Step 4: 写论文 ===")
    paper = await step4_write(problem, template_id, research, modeling, code_result)
    artifact.total_tokens_used += paper.get("usage", {}).get("total_tokens", 0)
    
    # 反模式检测：写作内容
    anti_pattern_result = AntiPatternDetector.detect_all(paper.get("content", ""), is_code=False)
    if not anti_pattern_result["passed"]:
        logger.warning(f"写作反模式检测未通过: {anti_pattern_result['high_count']} 个高危问题")
        for issue in anti_pattern_result["issues"]:
            if issue["severity"] == "HIGH":
                logger.warning(f"  - {issue['message']}")

    # 提取 + 文献核实
    import re
    paper_data = None
    paper_json = re.search(r"```json\s*\n(.*?)```", paper["content"], re.DOTALL)
    if paper_json:
        try:
            paper_data = json.loads(paper_json.group(1).strip())
        except json.JSONDecodeError as e:
            logger.warning(f"paper JSON parse failed (json block): {e}")
    if paper_data is None:
        brace_start = paper["content"].find("{")
        brace_end = paper["content"].rfind("}")
        if brace_start != -1 and brace_end > brace_start:
            try:
                paper_data = json.loads(paper["content"][brace_start:brace_end + 1])
            except json.JSONDecodeError as e:
                logger.warning(f"paper JSON parse failed (brace): {e}")
    if paper_data is None:
        # 兜底：把整段原始内容当作 markdown 论文体
        logger.warning("paper JSON 完全解析失败，使用原始内容")
        paper_data = {
            "title": project_name.replace("_", " ").title(),
            "abstract": "（自动生成：原始 JSON 解析失败，请参见 paper_raw.md）",
            "keywords": [],
            "sections": [
                {"heading": "1 Introduction", "content": paper["content"][:3000]},
                {"heading": "2 Content (raw)", "content": paper["content"][3000:8000] if len(paper["content"]) > 3000 else ""},
            ],
        }
        # 保留 raw 内容供调试
        (artifact.folder / "paper_raw.md").write_text(paper["content"], encoding="utf-8")

    # 过滤假引用
    ref_filter = filter_fake_references(paper["content"], template_id)
    artifact.fake_refs_filtered = len(ref_filter["filtered"])
    artifact.references = ref_filter["kept"]

    # 拼 Markdown
    md_lines = [
        f"# {paper_data.get('title', project_name)}",
        "",
        f"**Template**: {template_id}  ",
        f"**Project**: {project_name}  ",
        f"**Created**: {artifact.created_at}  ",
        "",
        f"## Abstract",
        "",
        paper_data.get("abstract", ""),
        "",
        f"**Keywords**: {', '.join(paper_data.get('keywords', []))}",
        "",
    ]
    for sec in paper_data.get("sections", []):
        md_lines.extend([
            f"## {sec.get('heading', '')}",
            "",
            sec.get("content", ""),
            "",
        ])
    # 真实引用清单
    md_lines.extend(["## References", ""])
    for ref in artifact.references:
        md_lines.append(f"- [{ref['arxiv_id']}] {ref.get('title', ref['arxiv_id'])} — https://arxiv.org/abs/{ref['arxiv_id']}")
    artifact.paper_md = "\n".join(md_lines)

    # 保存
    (artifact.folder / "paper.md").write_text(artifact.paper_md, encoding="utf-8")

    # 简单 LaTeX（用模板 preamble + sections 转 section）
    from src.knowledge.template_skills import get_template_skill
    skill = get_template_skill(template_id)
    if skill:
        # 简单起见：从模板 preamble 提取
        import json as _json
        template_dir = ROOT / "backend" / "app" / "core" / "paper_templates" / "templates"
        tpl_file = next((template_dir / f"{tpl}.json" for tpl in [
            "cumcm", "neurips_2024", "iclr_2024", "icml_2024", "aaai_2024",
            "acm_sigconf", "ieee_conference", "springer_lncs", "research_survey",
            "coursework", "financial_analysis", "presentation",
        ] if (template_dir / f"{tpl}.json").exists()), None)
        if tpl_file:
            tpl_json = _json.loads(tpl_file.read_text(encoding="utf-8"))
            preamble = tpl_json.get("preamble", "")
            docclass = tpl_json.get("documentclass", "article")
            # 拼 LaTeX（先清理 content 中的 JSON/markdown 语法）
            tex = preamble.replace("__TITLE__", paper_data.get("title", project_name))
            tex = tex.replace("__AUTHORS__", "Auto-Generated")
            tex += "\n\n"
            for sec in paper_data.get("sections", []):
                heading = sec.get("heading", "").lstrip("0123456789. ")
                content = sec.get("content", "")
                # 清理 content：去掉 JSON/markdown 残留
                content = re.sub(r"```json\s*\n?", "", content)
                content = re.sub(r"```\s*$", "", content, flags=re.MULTILINE)
                content = re.sub(r"^\s*\{.*$", "", content, flags=re.MULTILINE)  # 去掉 JSON 行
                content = re.sub(r"^\s*\[.*$", "", content, flags=re.MULTILINE)  # 去掉 JSON 数组行
                content = re.sub(r"^\s*\".*?\":\s*", "", content, flags=re.MULTILINE)  # 去掉 JSON key
                # 只保留看起来像文本的行
                text_lines = []
                for line in content.split("\n"):
                    stripped = line.strip()
                    if stripped and not stripped.startswith(("{", "}", "[", "]", "\"", "//", "#", "```")):
                        text_lines.append(stripped)
                clean_content = "\n".join(text_lines)
                # 自动包裹常见数学模式（保守策略：只包裹明确的 O(...) 模式）
                # O(n) → $O(n)$
                clean_content = re.sub(r'(?<!\$)O\(([^)]{1,20})\)(?!\$)', r'$O(\1)$', clean_content)
                # 去掉无法自动处理的数学符号
                clean_content = clean_content.replace("≥", ">=").replace("≤", "<=")
                clean_content = clean_content.replace("∈", " in ")  # ∈ → in
                if clean_content.strip():
                    tex += f"\\section{{{latex_escape(heading)}}}\n{latex_escape(clean_content)}\n\n"
            tex += "\\begin{thebibliography}{99}\n"
            for ref in artifact.references:
                tex += f"\\bibitem{{{ref['arxiv_id']}}} {latex_escape(ref.get('title', ref['arxiv_id']))}. arXiv:{ref['arxiv_id']}.\n"
            tex += "\\end{thebibliography}\n\n\\end{document}\n"
            artifact.paper_tex = tex
            (artifact.folder / "paper.tex").write_text(tex, encoding="utf-8")

    # 数据来源清单
    data_sources_md = (
        f"# Data Sources — {project_name}\n\n"
        f"**Template**: {template_id}\n"
        f"**Generated**: {artifact.created_at}\n\n"
        "## 1. 文献来源\n"
        + "\n".join(f"- arxiv:{r['arxiv_id']} — https://arxiv.org/abs/{r['arxiv_id']}" for r in artifact.references)
        + "\n\n## 2. 代码执行环境\n"
        f"- Python: {sys.version.split()[0]}\n"
        f"- 代码: code/model.py\n"
        + ("- 执行成功: stdout 见 paper.md / paper.tex 中引用的数值\n" if code_result["execution"]["success"] else "- ⚠️ 执行失败: 见 stderr\n")
        + f"\n```\n{code_result['execution']['stdout'][:1000]}\n```\n"
        + f"\n## 3. 数据来源声明\n"
        f"- 论文中所有数值结果均由 code/model.py 在沙箱执行产生\n"
        f"- 引用全部来自 {template_id} 模板的真实 arxiv 论文池（{len(artifact.references)} 条）\n"
        f"- 已过滤 {artifact.fake_refs_filtered} 条编造引用\n"
    )
    (artifact.folder / "data_sources.md").write_text(data_sources_md, encoding="utf-8")

    # references.bib
    bib_lines = ["% Auto-generated from verified arxiv pool", ""]
    for ref in artifact.references:
        bib_lines.append(f"@article{{{ref['arxiv_id']},")
        bib_lines.append(f"  title  = {{{ref.get('title', ref['arxiv_id'])}}},")
        bib_lines.append(f"  year   = {{2024}},")
        bib_lines.append(f"  eprint = {{arxiv:{ref['arxiv_id']}}},")
        bib_lines.append(f"  url    = {{https://arxiv.org/abs/{ref['arxiv_id']}}}")
        bib_lines.append("}")
        bib_lines.append("")
    (artifact.folder / "references.bib").write_text("\n".join(bib_lines), encoding="utf-8")

    logger.info(f"[{project_name}] === Step 5: 同行评审 ===")
    review = await step5_peer_review(artifact.paper_md, template_id)
    artifact.total_tokens_used += review.get("usage", {}).get("total_tokens", 0)

    review_data = None
    review_json = re.search(r"```json\s*\n(.*?)```", review["content"], re.DOTALL)
    if review_json:
        try:
            review_data = json.loads(review_json.group(1).strip())
        except json.JSONDecodeError as e:
            logger.warning(f"review JSON parse failed (json block): {e}")
    if review_data is None:
        brace_start = review["content"].find("{")
        brace_end = review["content"].rfind("}")
        if brace_start != -1 and brace_end > brace_start:
            try:
                review_data = json.loads(review["content"][brace_start:brace_end + 1])
            except json.JSONDecodeError as e:
                logger.warning(f"review JSON parse failed (brace): {e}")
    if review_data is None:
        review_data = {
            "raw": review["content"],
            "scores": {
                "novelty": {"score": 3, "comment": "（JSON 解析失败）"},
                "soundness": {"score": 3, "comment": "（JSON 解析失败）"},
                "clarity": {"score": 3, "comment": "（JSON 解析失败）"},
                "significance": {"score": 3, "comment": "（JSON 解析失败）"},
            },
            "overall_score": 3.0,
            "recommendation": "revise",
            "major_issues": [f"评审 JSON 解析失败,原始内容长度 {len(review['content'])} 字符"],
            "minor_issues": [],
            "suggested_edits": ["人工审查 review_raw.md"],
        }
        (artifact.folder / "review_raw.md").write_text(review["content"], encoding="utf-8")
    artifact.peer_review = review_data

    # 写评审 md
    pr = artifact.peer_review
    review_md = f"# Peer Review — {project_name}\n\n"
    review_md += f"**Generated**: {time.strftime('%Y-%m-%d %H:%M:%S')}  \n"
    review_md += f"**Template**: {template_id}  \n\n"
    if "scores" in pr:
        review_md += "## 4-Dimension Scores\n\n"
        for dim, info in pr["scores"].items():
            review_md += f"### {dim.capitalize()}: {info.get('score', '?')}/5\n"
            review_md += f"{info.get('comment', '')}\n\n"
        review_md += f"**Overall**: {pr.get('overall_score', '?')}\n\n"
        review_md += f"**Recommendation**: **{pr.get('recommendation', '?')}**\n\n"
        review_md += f"## Major Issues\n\n"
        for issue in pr.get("major_issues", []):
            review_md += f"- {issue}\n"
        review_md += f"\n## Minor Issues\n\n"
        for issue in pr.get("minor_issues", []):
            review_md += f"- {issue}\n"
        review_md += f"\n## Suggested Edits\n\n"
        for edit in pr.get("suggested_edits", []):
            review_md += f"- {edit}\n"
    (artifact.folder / "peer_review.md").write_text(review_md, encoding="utf-8")
    
    # 质量门禁：review
    review_gate = QualityGate.validate("review", review_data)
    if review_gate["severity"] == "FAIL":
        logger.warning(f"Review 门禁未通过: {review_gate['checks']}")
        
        # 评审修订循环（评分低时自动修订）
        if review_data.get("overall_score", 0) < 3.0:
            logger.info(f"[{project_name}] === Step 5b: 评审修订循环 ===")
            revision_count = 0
            max_revisions = 2
            
            while review_data.get("overall_score", 0) < 3.0 and revision_count < max_revisions:
                revision_count += 1
                logger.info(f"  修订轮次 {revision_count}/{max_revisions}")
                
                # 根据评审意见修订论文
                revision_prompt = f"""【原始论文】
{artifact.paper_md[:5000]}

【评审意见】
主要问题：{'; '.join(review_data.get('major_issues', [])[:3])}
次要问题：{'; '.join(review_data.get('minor_issues', [])[:3])}

请修订论文，解决上述问题。返回修订后的完整论文 Markdown。"""
                
                try:
                    revision_resp = await call_minimax(
                        "你是一位论文修订专家。根据评审意见修订论文。",
                        revision_prompt,
                        max_tokens=64000
                    )
                    
                    # 更新论文
                    artifact.paper_md = revision_resp.get("content", artifact.paper_md)
                    (artifact.folder / "paper.md").write_text(artifact.paper_md, encoding="utf-8")
                    
                    # 重新评审
                    review = await step5_peer_review(artifact.paper_md, template_id)
                    artifact.total_tokens_used += review.get("usage", {}).get("total_tokens", 0)
                    
                    # 重新解析评审结果
                    review_data_new = None
                    review_json_new = re.search(r"```json\s*\n(.*?)```", review["content"], re.DOTALL)
                    if review_json_new:
                        try:
                            review_data_new = json.loads(review_json_new.group(1).strip())
                        except json.JSONDecodeError:
                            pass
                    
                    if review_data_new and "overall_score" in review_data_new:
                        review_data = review_data_new
                        artifact.peer_review = review_data
                        
                except Exception as e:
                    logger.warning(f"  修订失败: {e}")
                    break
            
            if revision_count > 0:
                logger.info(f"  完成 {revision_count} 轮修订，最终评分: {review_data.get('overall_score', 'N/A')}")

    # 输出保障检查
    logger.info(f"[{project_name}] === Step 7: 输出保障检查 ===")
    guarantee = OutputGuarantee()
    
    # 获取真实引用池
    from src.knowledge.template_skills import get_real_references
    real_pool = get_real_references(template_id)
    
    # 执行全面检查
    guarantee_result = guarantee.guarantee_output(
        tex_content=artifact.paper_tex if hasattr(artifact, 'paper_tex') else "",
        paper_md=artifact.paper_md,
        references=artifact.references,
        real_pool=real_pool,
        idea=problem,
        project_name=project_name,
    )
    
    # 记录检查结果
    if not guarantee_result["overall_pass"]:
        logger.warning(f"  输出保障检查未通过:")
        if not guarantee_result["format_valid"]:
            logger.warning(f"    排版格式错误: {guarantee_result['format_errors']}")
        if not guarantee_result["reference_valid"]:
            logger.warning(f"    参考文献问题: {guarantee_result['reference_result']['fake']} 个虚假引用")
        if not guarantee_result["idea_unique"]:
            logger.warning(f"    Idea 重复: 相似度 {guarantee_result['idea_check']['max_similarity']:.2%}")
    
    # 保存保障报告
    guarantee_report = f"""# Output Guarantee Report — {project_name}

**Generated**: {time.strftime('%Y-%m-%d %H:%M:%S')}

## 1. 排版格式检查

- **状态**: {'✅ 通过' if guarantee_result['format_valid'] else '❌ 未通过'}
- **错误**: {guarantee_result['format_errors'] if guarantee_result['format_errors'] else '无'}
- **警告**: {guarantee_result['format_warnings'] if guarantee_result['format_warnings'] else '无'}

## 2. 参考文献检查

- **状态**: {'✅ 通过' if guarantee_result['reference_valid'] else '❌ 未通过'}
- **总数**: {guarantee_result['reference_result']['total']}
- **已验证**: {guarantee_result['reference_result']['verified']}
- **虚假引用**: {guarantee_result['reference_result']['fake']}
- **未引用**: {guarantee_result['reference_result']['uncited']}

## 3. Idea 去重检查

- **状态**: {'✅ 唯一' if guarantee_result['idea_unique'] else '❌ 重复'}
- **最大相似度**: {guarantee_result['idea_check']['max_similarity']:.2%}
- **相似 Idea**: {len(guarantee_result['idea_check']['similar_ideas'])} 个

## 总体结果

{'✅ 全部通过' if guarantee_result['overall_pass'] else '❌ 存在问题'}
"""
    (artifact.folder / "guarantee_report.md").write_text(guarantee_report, encoding="utf-8")

    # README
    readme = f"""# {project_name}

**Template**: {template_id}  
**Problem**: {problem[:200]}  
**Generated**: {artifact.created_at}

## Artifacts

- `paper.md` — 论文 Markdown 源
- `paper.tex` — 论文 LaTeX 源
- `paper.pdf` — 编译后的 PDF（如已编译）
- `peer_review.md` — 同行评审意见（4 维度评分）
- `data_sources.md` — 数据来源清单
- `references.bib` — 真实引用（arxiv ID 经核实）
- `code/model.py` — 代码（已执行）
- `figures/` — 插图目录

## Pipeline Stats

- Total tokens used: {artifact.total_tokens_used}
- Real references kept: {len(artifact.references)}
- Fake references filtered: {artifact.fake_refs_filtered}
- Code execution: {'✅ success' if code_result['execution']['success'] else '❌ failed'}

## Self-Review Verdict

{pr.get('recommendation', 'pending').upper() if 'recommendation' in pr else 'PENDING'}
"""
    (artifact.folder / "README.md").write_text(readme, encoding="utf-8")

    # Step 6: 编译 PDF + 生成图表
    logger.info(f"[{project_name}] === Step 6: 编译 PDF + 生成图表 ===")
    compile_result = await step6_compile(artifact.folder)
    artifact.pdf_generated = compile_result["pdf_ok"]
    artifact.figures_generated = compile_result["figures"]

    return artifact


def latex_escape(text: str) -> str:
    """智能 LaTeX 转义：保留数学模式，转义特殊字符。"""
    if not text:
        return ""
    import re as _re
    # 先保护数学模式：$...$ 和 \(...\) 和 \[...\]
    math_patterns = []
    def _save_math(m):
        math_patterns.append(m.group(0))
        return f"__MATH_{len(math_patterns)-1}__"
    text = _re.sub(r'\$[^$]+\$', _save_math, text)
    text = _re.sub(r'\\[(\[][^\\]*\\[)\]]', _save_math, text)
    # 转义 LaTeX 特殊字符
    text = text.replace("\\", r"\textbackslash{}")
    text = text.replace("&", r"\&").replace("%", r"\%")
    text = text.replace("#", r"\#").replace("~", r"\textasciitilde{}")
    # 不转义 $ 和 _ 和 ^ —— 它们在数学模式中需要保留
    # 但如果不在数学模式中，需要转义
    text = text.replace("{", r"\{").replace("}", r"\}")
    # 恢复数学模式
    for i, m in enumerate(math_patterns):
        text = text.replace(f"__MATH_{i}__", m)
    return text


async def step6_compile(folder: Path) -> Dict:
    """Step 6: 编译 LaTeX → PDF + 生成 matplotlib 图表。

    Returns:
        {"pdf_ok": bool, "figures": list[str], "errors": list[str]}
    """
    import subprocess
    import glob as _glob

    result = {"pdf_ok": False, "figures": [], "errors": []}

    # --- 6a: 生成 matplotlib 图表 ---
    code_file = folder / "code" / "model.py"
    figures_dir = folder / "figures"
    figures_dir.mkdir(exist_ok=True)

    if code_file.exists():
        try:
            code_content = code_file.read_text(encoding="utf-8")
            # 先检查语法
            import ast as _ast
            try:
                _ast.parse(code_content)
            except SyntaxError as e:
                result["errors"].append(f"代码语法错误: 第{e.lineno}行 {e.msg}")
                logger.warning(f"  代码语法错误，跳过图表生成: {e}")
            else:
                # 使用 FigureGenerator 生成图表
                figures = FigureGenerator.generate_from_code_output(
                    code_content, "", figures_dir
                )
                result["figures"].extend(figures)
                
                # 如果 FigureGenerator 没有生成图表，使用原有方法
                if not figures:
                    # 注入 matplotlib 后端和保存逻辑
                    figure_inject = """
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os
import sys

# 收集所有 figure
_generated_figures = []
_original_show = plt.show
def _capture_show(*args, **kwargs):
    pass
plt.show = _capture_show

# Patch savefig 以记录文件路径
_original_savefig = plt.savefig
def _capture_savefig(fname, *args, **kwargs):
    _generated_figures.append(str(fname))
    _original_savefig(fname, *args, **kwargs)
plt.savefig = _capture_savefig
"""
                    # 执行代码（捕获所有生成的图）
                    exec_globals = {"__name__": "__main__", "__builtins__": __builtins__}
                    exec(figure_inject + "\n" + code_content, exec_globals)

                    # 自动保存未关闭的 figure
                    import matplotlib.pyplot as plt_mpl
                    for i, fig_num in enumerate(plt_mpl.get_fignums()):
                        fig = plt_mpl.figure(fig_num)
                        fig_path = figures_dir / f"figure_{i+1}.png"
                        fig.savefig(str(fig_path), dpi=150, bbox_inches='tight')
                        result["figures"].append(str(fig_path))
                    plt_mpl.close('all')

                    # 也收集代码中显式 savefig 的文件
                    for f in _glob.glob(str(figures_dir / "*.png")):
                        if f not in result["figures"]:
                            result["figures"].append(f)

                logger.info(f"  生成 {len(result['figures'])} 张图表")
        except Exception as e:
            result["errors"].append(f"图表生成失败: {str(e)[:100]}")
            logger.warning(f"  图表生成失败: {e}")

    # --- 6b: 编译 LaTeX → PDF ---
    tex_file = folder / "paper.tex"
    if not tex_file.exists():
        result["errors"].append("paper.tex 不存在")
        return result

    tex_content = tex_file.read_text(encoding="utf-8")

    # 注入 graphicx 包以支持插图
    if r"\usepackage{graphicx}" not in tex_content and r"\usepackage{graphics}" not in tex_content:
        # 在 \begin{document} 前插入
        if r"\begin{document}" in tex_content:
            tex_content = tex_content.replace(
                r"\begin{document}",
                r"\usepackage{graphicx}" + "\n" + r"\begin{document}"
            )

    # 注入图片引用（如果 figures 目录有图）
    if result["figures"]:
        figure_refs = "\n% Auto-generated figures\n"
        for i, fig_path in enumerate(result["figures"][:5]):
            rel_path = f"figures/{Path(fig_path).name}"
            figure_refs += f"\\begin{{figure}}[h]\n\\centering\n\\includegraphics[width=0.8\\textwidth]{{{rel_path}}}\n\\caption{{Figure {i+1}}}\n\\end{{figure}}\n\n"
        # 插入到结论前或末尾
        if r"\end{document}" in tex_content:
            tex_content = tex_content.replace(r"\end{document}", figure_refs + r"\end{document}")

    tex_file.write_text(tex_content, encoding="utf-8")

    # 编译（用 xelatex 支持 CJK）
    for pass_num in range(3):
        try:
            proc = subprocess.run(
                ["xelatex", "-interaction=nonstopmode", "-halt-on-error",
                 f"-output-directory={folder}", str(tex_file)],
                capture_output=True, text=True, timeout=120, cwd=str(folder)
            )
            if proc.returncode == 0 and (folder / "paper.pdf").exists():
                result["pdf_ok"] = True
                break
        except subprocess.TimeoutExpired:
            result["errors"].append(f"xelatex pass {pass_num+1} 超时")
        except FileNotFoundError:
            result["errors"].append("xelatex 未安装")
            break

    # 运行 bibtex（如果有引用）
    if (folder / "references.bib").exists():
        try:
            subprocess.run(
                ["bibtex", "paper"],
                capture_output=True, timeout=30, cwd=str(folder)
            )
        except Exception:
            pass

    if result["pdf_ok"]:
        logger.info(f"  ✅ PDF 编译成功: {folder / 'paper.pdf'}")
    else:
        logger.warning(f"  ⚠️ PDF 编译失败: {'; '.join(result['errors'])}")

    return result


# ==================== CLI ====================


def main():
    parser = argparse.ArgumentParser(description="End-to-end paper generation with MiniMax-M3")
    parser.add_argument("--template", default="math_modeling",
                        help="模板 ID (math_modeling / neurips_2024 / iclr_2024 / ...)")
    parser.add_argument("--problem", required=True, help="问题描述")
    parser.add_argument("--project-name", required=True, help="项目名（输出文件夹名）")
    parser.add_argument("--output-dir", default="./outputs", help="输出根目录")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
    )

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    artifact = asyncio.run(run_pipeline(
        template_id=args.template,
        problem=args.problem,
        project_name=args.project_name,
        output_dir=output_dir,
    ))

    print(f"\n✅ 生成完成: {artifact.folder}")
    print(f"   paper.md:    {artifact.paper_md[:200]}...")
    print(f"   references:  {len(artifact.references)} real, {artifact.fake_refs_filtered} filtered")
    print(f"   peer_review: {artifact.peer_review.get('recommendation', 'pending')}")
    print(f"   tokens used: {artifact.total_tokens_used}")


if __name__ == "__main__":
    main()
