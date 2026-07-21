# Template & Workflow Completeness Fix Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sync CLI path templates with backend templates, and improve template quality for coursework/springer_lncs.

**Architecture:** The backend (LangGraph) has 8 paper templates via `backend/app/core/paper_templates/templates/*.json`. The CLI path (`main.py` → `src/workflow/templates.py`) only registers 3 templates (math_modeling, coursework, financial_analysis). This plan syncs them and improves weaker templates.

**Tech Stack:** Python, JSON config, LaTeX template system

## Global Constraints

- All 5 cls/sty files already exist — no file creation needed for LaTeX assets
- compliance_agent is already wired in LangGraph for financial_analysis — no fix needed
- Do NOT modify `backend/app/core/paper_templates/` — those are correct
- Changes are limited to `src/workflow/templates.py` and `main.py`

---

## Task 1: Sync CLI path with all 8 backend templates

**Covers:** CLI template registry gap (math_modeling, coursework, financial_analysis exist; neurips_2024, ieee_conference, acm_sigconf, springer_lncs, research_survey missing)

**Files:**
- Modify: `src/workflow/templates.py` — add 5 new template classes
- Modify: `main.py` — update `--template` choices

**Interfaces:**
- Consumes: `PaperTemplate` base class from `src/workflow/templates.py`
- Produces: 5 new template classes registered in `_TEMPLATE_REGISTRY`

- [ ] **Step 1: Add NeurIPS template class to `src/workflow/templates.py`**

Add after `FinancialAnalysisTemplate` class:

```python
class NeurIPS2024Template(PaperTemplate):
    """NeurIPS 2024 / ICML / ICLR 风格论文模板"""
    name = "neurips_2024"
    description = "NeurIPS 2024 (CCF-A ML)"

    def get_system_prompt(self) -> str:
        return """You are an expert ML researcher writing a paper for NeurIPS / ICML / ICLR.

[FORMAT]
- Use neurips_2024 style (single-column, 10pt).
- Main paper ≤ 9 pages; references and appendix excluded.
- Double-blind: no author names, no affiliations.

[SECTIONS]
Abstract → 1 Introduction → 2 Related Work → 3 Preliminaries → 4 Method → 5 Experiments → 6 Discussion → 7 Conclusion → References → Appendix

[RULES]
1. Abstract ≤ 250 words: problem → gap → approach → result.
2. Introduction: motivation + 3-4 numbered contributions.
3. Method: Algorithm box + mathematical derivation + proof sketch.
4. Experiments: ≥4 baselines, ablation ≥3 components, confidence intervals.
5. Discussion: limitations + broader impact.
6. Citations: author-year style."""

    def get_outline(self) -> List[ChapterSpec]:
        return [
            ChapterSpec(id="abstract", title="Abstract", level=0,
                        min_chars=200, target_chars=400, max_chars=600,
                        relevance_keys=["problem_text", "analysis", "modeling", "execution_result"]),
            ChapterSpec(id="introduction", title="1 Introduction", level=1,
                        min_chars=1500, target_chars=2500, max_chars=4000,
                        relevance_keys=["problem_text", "analysis", "modeling"]),
            ChapterSpec(id="related_work", title="2 Related Work", level=1,
                        min_chars=1000, target_chars=1500, max_chars=2500,
                        relevance_keys=["problem_text", "analysis"]),
            ChapterSpec(id="preliminaries", title="3 Preliminaries", level=1,
                        min_chars=800, target_chars=1200, max_chars=2000,
                        relevance_keys=["modeling", "formulas"]),
            ChapterSpec(id="method", title="4 Method", level=1,
                        min_chars=2000, target_chars=3500, max_chars=5000,
                        relevance_keys=["modeling", "algorithm", "formulas"],
                        requires_coding=True),
            ChapterSpec(id="experiments", title="5 Experiments", level=1,
                        min_chars=2000, target_chars=3000, max_chars=5000,
                        relevance_keys=["execution_result", "result_analysis", "charts"],
                        requires_coding=True),
            ChapterSpec(id="discussion", title="6 Discussion", level=1,
                        min_chars=800, target_chars=1200, max_chars=2000,
                        relevance_keys=["modeling", "execution_result", "result_analysis"]),
            ChapterSpec(id="conclusion", title="7 Conclusion", level=1,
                        min_chars=500, target_chars=800, max_chars=1200,
                        relevance_keys=["execution_result", "result_analysis"]),
            ChapterSpec(id="references", title="References", level=0,
                        min_chars=300, target_chars=600, max_chars=1000,
                        relevance_keys=["problem_text", "modeling"]),
            ChapterSpec(id="appendix", title="Appendix", level=0,
                        min_chars=500, target_chars=1000, max_chars=3000,
                        relevance_keys=["code", "execution_result"],
                        requires_coding=True),
        ]


class IEEEConferenceTemplate(PaperTemplate):
    """IEEE Conference (CCF-A) 风格论文模板"""
    name = "ieee_conference"
    description = "IEEE Conference (CCF-A: S&P / CCS / SIGCOMM / VLDB)"

    def get_system_prompt(self) -> str:
        return """You are an expert researcher writing an IEEE conference paper (CCF-A venues).

[FORMAT]
- Use IEEEtran document class (10pt, conference, two-column).
- Page limit: 6-12 main pages excluding references and appendix.

[SECTIONS]
Abstract → Index Terms → I. Introduction → II. Related Work → III. Background → IV. Method → V. Experiments → VI. Discussion → VII. Conclusion → References → Appendix

[RULES]
1. Abstract: 150-250 words, no citations.
2. Introduction: concrete example + prior work limitations + 3-5 contributions.
3. Method: architecture overview + component derivations + complexity analysis.
4. Experiments: datasets, ≥4 baselines, ablation ≥3, sensitivity, case study.
5. Discussion: threats to validity + limitations + ethics.
6. Citations: IEEE numeric [1], [2, 3]."""

    def get_outline(self) -> List[ChapterSpec]:
        return [
            ChapterSpec(id="abstract", title="Abstract", level=0,
                        min_chars=200, target_chars=400, max_chars=600,
                        relevance_keys=["problem_text", "analysis", "modeling", "execution_result"]),
            ChapterSpec(id="introduction", title="I. Introduction", level=1,
                        min_chars=1500, target_chars=2500, max_chars=4000,
                        relevance_keys=["problem_text", "analysis", "modeling"]),
            ChapterSpec(id="related_work", title="II. Related Work", level=1,
                        min_chars=1000, target_chars=1500, max_chars=2500,
                        relevance_keys=["problem_text", "analysis"]),
            ChapterSpec(id="background", title="III. Background", level=1,
                        min_chars=800, target_chars=1200, max_chars=2000,
                        relevance_keys=["modeling", "formulas"]),
            ChapterSpec(id="method", title="IV. Method", level=1,
                        min_chars=2000, target_chars=3500, max_chars=5000,
                        relevance_keys=["modeling", "algorithm", "formulas"],
                        requires_coding=True),
            ChapterSpec(id="experiments", title="V. Experiments", level=1,
                        min_chars=2000, target_chars=3000, max_chars=5000,
                        relevance_keys=["execution_result", "result_analysis", "charts"],
                        requires_coding=True),
            ChapterSpec(id="discussion", title="VI. Discussion", level=1,
                        min_chars=800, target_chars=1200, max_chars=2000,
                        relevance_keys=["modeling", "execution_result", "result_analysis"]),
            ChapterSpec(id="conclusion", title="VII. Conclusion", level=1,
                        min_chars=500, target_chars=800, max_chars=1200,
                        relevance_keys=["execution_result", "result_analysis"]),
            ChapterSpec(id="references", title="References", level=0,
                        min_chars=300, target_chars=600, max_chars=1000,
                        relevance_keys=["problem_text", "modeling"]),
            ChapterSpec(id="appendix", title="Appendix", level=0,
                        min_chars=500, target_chars=1000, max_chars=3000,
                        relevance_keys=["code", "execution_result"],
                        requires_coding=True),
        ]


class ACMSigConfTemplate(PaperTemplate):
    """ACM SIG Conference 风格论文模板"""
    name = "acm_sigconf"
    description = "ACM SIG Conference (CCF-A: SIGGRAPH / MobiCom / CHI)"

    def get_system_prompt(self) -> str:
        return """You are an expert researcher writing for ACM SIG conferences (CCF-A).

[FORMAT]
- Use acmart document class (sigconf, two-column, 10pt).
- Page limit: 6-14 main pages.
- Include CCS Concepts and Keywords after abstract.

[SECTIONS]
Abstract (with CCS Concepts) → 1 Introduction → 2 Related Work → 3 Method → 4 Implementation → 5 Evaluation → 6 Discussion → 7 Conclusion → References → Appendix

[RULES]
1. Abstract: 150-200 words + CCS Concepts (1-3) + Keywords (3-5).
2. Introduction: user-facing scenario + contributions.
3. Method: system overview + component details + algorithms.
4. Implementation: software stack, hardware, engineering decisions.
5. Evaluation: setup, baselines, metrics, results, case study.
6. Citations: ACM numeric [1], [2, 3]."""

    def get_outline(self) -> List[ChapterSpec]:
        return [
            ChapterSpec(id="abstract", title="Abstract", level=0,
                        min_chars=200, target_chars=350, max_chars=500,
                        relevance_keys=["problem_text", "analysis", "modeling", "execution_result"]),
            ChapterSpec(id="introduction", title="1 Introduction", level=1,
                        min_chars=1500, target_chars=2500, max_chars=4000,
                        relevance_keys=["problem_text", "analysis", "modeling"]),
            ChapterSpec(id="related_work", title="2 Related Work", level=1,
                        min_chars=1000, target_chars=1500, max_chars=2500,
                        relevance_keys=["problem_text", "analysis"]),
            ChapterSpec(id="method", title="3 Method", level=1,
                        min_chars=2000, target_chars=3500, max_chars=5000,
                        relevance_keys=["modeling", "algorithm", "formulas"],
                        requires_coding=True),
            ChapterSpec(id="implementation", title="4 Implementation", level=1,
                        min_chars=800, target_chars=1200, max_chars=2000,
                        relevance_keys=["code", "execution_result"],
                        requires_coding=True),
            ChapterSpec(id="evaluation", title="5 Evaluation", level=1,
                        min_chars=2000, target_chars=3000, max_chars=5000,
                        relevance_keys=["execution_result", "result_analysis", "charts"],
                        requires_coding=True),
            ChapterSpec(id="discussion", title="6 Discussion", level=1,
                        min_chars=800, target_chars=1200, max_chars=2000,
                        relevance_keys=["modeling", "execution_result", "result_analysis"]),
            ChapterSpec(id="conclusion", title="7 Conclusion", level=1,
                        min_chars=500, target_chars=800, max_chars=1200,
                        relevance_keys=["execution_result", "result_analysis"]),
            ChapterSpec(id="references", title="References", level=0,
                        min_chars=300, target_chars=600, max_chars=1000,
                        relevance_keys=["problem_text", "modeling"]),
            ChapterSpec(id="appendix", title="Appendix", level=0,
                        min_chars=500, target_chars=1000, max_chars=3000,
                        relevance_keys=["code", "execution_result"],
                        requires_coding=True),
        ]


class SpringerLNCSWriterTemplate(PaperTemplate):
    """Springer LNCS 风格论文模板"""
    name = "springer_lncs"
    description = "Springer LNCS (CCF-B, widely used)"

    def get_system_prompt(self) -> str:
        return """You are an expert researcher writing for Springer LNCS.

[FORMAT]
- Use llncs document class (two-column, 10pt, A4).
- Page limit: 8-14 pages including references.

[SECTIONS]
Abstract → 1 Introduction → 2 Related Work → 3 Preliminaries → 4 Method → 5 Experiments → 6 Conclusion → References

[RULES]
1. Abstract: 150-200 words + Keywords (footnote-style, right after abstract).
2. Introduction: motivation + gap + approach + 3-4 contributions.
3. Method: complete mathematical derivation + algorithm boxes.
4. Experiments: setup, ≥4 baselines, ablation ≥3, sensitivity.
5. Citations: Springer numeric [1], [AB12], [3, 4]."""

    def get_outline(self) -> List[ChapterSpec]:
        return [
            ChapterSpec(id="abstract", title="Abstract", level=0,
                        min_chars=200, target_chars=350, max_chars=500,
                        relevance_keys=["problem_text", "analysis", "modeling", "execution_result"]),
            ChapterSpec(id="introduction", title="1 Introduction", level=1,
                        min_chars=1200, target_chars=2000, max_chars=3000,
                        relevance_keys=["problem_text", "analysis", "modeling"]),
            ChapterSpec(id="related_work", title="2 Related Work", level=1,
                        min_chars=1000, target_chars=1500, max_chars=2500,
                        relevance_keys=["problem_text", "analysis"]),
            ChapterSpec(id="preliminaries", title="3 Preliminaries", level=1,
                        min_chars=800, target_chars=1200, max_chars=2000,
                        relevance_keys=["modeling", "formulas"]),
            ChapterSpec(id="method", title="4 Method", level=1,
                        min_chars=2000, target_chars=3000, max_chars=4500,
                        relevance_keys=["modeling", "algorithm", "formulas"],
                        requires_coding=True),
            ChapterSpec(id="experiments", title="5 Experiments", level=1,
                        min_chars=2000, target_chars=3000, max_chars=5000,
                        relevance_keys=["execution_result", "result_analysis", "charts"],
                        requires_coding=True),
            ChapterSpec(id="conclusion", title="6 Conclusion", level=1,
                        min_chars=500, target_chars=800, max_chars=1200,
                        relevance_keys=["execution_result", "result_analysis"]),
            ChapterSpec(id="references", title="References", level=0,
                        min_chars=300, target_chars=600, max_chars=1000,
                        relevance_keys=["problem_text", "modeling"]),
        ]


class ResearchSurveyTemplate(PaperTemplate):
    """研究调研报告 / 深度文献综述模板"""
    name = "research_survey"
    description = "研究调研报告 / 深度文献综述"

    def get_system_prompt(self) -> str:
        return """你是一个专业的学术调研报告写作专家，擅长撰写高质量的文献综述和研究现状调研报告。

【报告定位】
这是一份深度调研报告，不是简单的文献罗列。目标是：
1. 系统梳理研究现状，建立清晰的分类框架
2. 深度批判现有工作，识别具体的研究空白
3. 提出有学术价值的创新点，具备顶会发表潜力

【报告结构（8大章节）】
- 摘要（300-500字）
- 一、研究全景图：现有方法分类与SOTA剖析
- 二、核心Research Gaps分析
- 三、交叉学科启发与迁移
- 四、论文创新点提案（3-5个Idea）
- 五、调研必读文献清单（10-15篇）
- 六、数据集与实验设置
- 七、结果对比与讨论
- 八、结论与展望

【写作质量要求】
- 深度优先：每个观点都要有具体论文支撑
- 批判性思维：深度分析优缺点
- 技术具体：方法描述到算法/架构层面
- 逻辑严密：Motivation → Gap → Method → Evaluation 闭环"""

    def get_outline(self) -> List[ChapterSpec]:
        return [
            ChapterSpec(id="abstract", title="摘要", level=0,
                        min_chars=300, target_chars=500, max_chars=700,
                        relevance_keys=["problem_text", "analysis"]),
            ChapterSpec(id="landscape", title="一、研究全景图", level=1,
                        min_chars=2000, target_chars=3500, max_chars=5000,
                        relevance_keys=["problem_text", "analysis"]),
            ChapterSpec(id="gaps", title="二、Research Gaps分析", level=1,
                        min_chars=1500, target_chars=2500, max_chars=4000,
                        relevance_keys=["analysis", "modeling"]),
            ChapterSpec(id="cross_domain", title="三、交叉学科启发", level=1,
                        min_chars=1000, target_chars=1500, max_chars=2500,
                        relevance_keys=["analysis"]),
            ChapterSpec(id="ideas", title="四、创新点提案", level=1,
                        min_chars=2000, target_chars=3500, max_chars=5000,
                        relevance_keys=["analysis", "modeling"]),
            ChapterSpec(id="reading_list", title="五、必读文献清单", level=1,
                        min_chars=1000, target_chars=1500, max_chars=2500,
                        relevance_keys=["problem_text", "analysis"]),
            ChapterSpec(id="datasets", title="六、数据集与实验设置", level=1,
                        min_chars=800, target_chars=1200, max_chars=2000,
                        relevance_keys=["analysis"]),
            ChapterSpec(id="results", title="七、结果对比与讨论", level=1,
                        min_chars=1000, target_chars=1500, max_chars=2500,
                        relevance_keys=["analysis", "modeling"]),
            ChapterSpec(id="conclusion", title="八、结论与展望", level=1,
                        min_chars=600, target_chars=1000, max_chars=1500,
                        relevance_keys=["analysis"]),
        ]
```

- [ ] **Step 2: Update `_TEMPLATE_REGISTRY` in `src/workflow/templates.py`**

Replace the existing registry:

```python
_TEMPLATE_REGISTRY = {
    "math_modeling": MathModelingTemplate,
    "coursework": CourseworkTemplate,
    "financial_analysis": FinancialAnalysisTemplate,
    "neurips_2024": NeurIPS2024Template,
    "ieee_conference": IEEEConferenceTemplate,
    "acm_sigconf": ACMSigConfTemplate,
    "springer_lncs": SpringerLNCSWriterTemplate,
    "research_survey": ResearchSurveyTemplate,
}
```

- [ ] **Step 3: Update `main.py` template choices**

Change line 41 from:
```python
choices=['math_modeling', 'coursework', 'financial_analysis'],
```
to:
```python
choices=['math_modeling', 'coursework', 'financial_analysis', 'neurips_2024', 'ieee_conference', 'acm_sigconf', 'springer_lncs', 'research_survey'],
```

Also update the help text and usage examples to mention all templates.

- [ ] **Step 4: Update `scripts/run_auto.py` template help**

Update the `--template` help text in `run_auto.py` to mention all available templates.

- [ ] **Step 5: Verify imports work**

Run: `python -c "from src.workflow.templates import list_templates; print(list_templates())"`
Expected: 8 templates listed.

- [ ] **Step 6: Commit**

```bash
git add src/workflow/templates.py main.py scripts/run_auto.py
git commit -m "feat: sync CLI path with all 8 backend paper templates"
```

---

## Task 2: Improve coursework template

**Covers:** coursework template lacks differentiation from math_modeling

**Files:**
- Modify: `src/workflow/templates.py` — enhance `CourseworkTemplate`

- [ ] **Step 1: Enhance CourseworkTemplate system prompt and outline**

Update `CourseworkTemplate.get_system_prompt()` to include coursework-specific elements:

```python
def get_system_prompt(self) -> str:
    return """你是一位优秀的学术论文写作助手，擅长撰写课程作业论文。

【课程作业论文特点】
- 语言风格：学术但简洁，适合同年级学生理解
- 篇幅：适中（6-20页）
- 重点：方法原理、实现过程、结果分析
- 特有章节：学习心得与反思、参考资料分类

【写作要求】
1. 语言通顺、结构清晰、论述有理有据
2. 对理论部分要解释清楚概念，避免过度抽象
3. 实验/计算部分要有具体步骤和结果
4. 讨论部分要有自己的思考，不能只是罗列结果
5. 适当使用图表辅助说明
6. 结尾需包含"学习心得与反思"章节
7. 参考文献需分类标注（教材/论文/网络资源）
8. 中文学术写作风格"""
```

Update `get_outline()` to add coursework-specific chapters:

```python
def get_outline(self) -> List[ChapterSpec]:
    return [
        ChapterSpec(id="abstract", title="摘要", level=1,
                    min_chars=300, target_chars=500, max_chars=800,
                    relevance_keys=["problem_text", "analysis", "execution_result"]),
        ChapterSpec(id="introduction", title="一、引言", level=1,
                    min_chars=800, target_chars=1200, max_chars=2000,
                    relevance_keys=["problem_text", "analysis"]),
        ChapterSpec(id="theory", title="二、理论基础", level=1,
                    min_chars=1000, target_chars=2000, max_chars=3500,
                    relevance_keys=["problem_text", "analysis", "modeling"]),
        ChapterSpec(id="problem_description", title="三、问题描述", level=1,
                    min_chars=800, target_chars=1200, max_chars=2000,
                    relevance_keys=["problem_text", "analysis"]),
        ChapterSpec(id="methodology", title="四、方法设计", level=1,
                    min_chars=1500, target_chars=2500, max_chars=4000,
                    relevance_keys=["modeling", "algorithm", "formulas"]),
        ChapterSpec(id="experiment", title="五、实验与计算", level=1,
                    min_chars=1500, target_chars=2500, max_chars=4000,
                    relevance_keys=["code", "execution_result", "algorithm"],
                    requires_coding=True),
        ChapterSpec(id="discussion", title="六、结果讨论", level=1,
                    min_chars=1200, target_chars=2000, max_chars=3500,
                    relevance_keys=["execution_result", "result_analysis", "charts"],
                    requires_coding=True),
        ChapterSpec(id="conclusion", title="七、结论", level=1,
                    min_chars=600, target_chars=1000, max_chars=1500,
                    relevance_keys=["execution_result", "result_analysis"]),
        ChapterSpec(id="reflection", title="八、学习心得与反思", level=1,
                    min_chars=500, target_chars=800, max_chars=1200,
                    relevance_keys=["problem_text", "analysis"]),
        ChapterSpec(id="references", title="参考文献", level=1,
                    min_chars=200, target_chars=400, max_chars=800,
                    relevance_keys=["problem_text", "modeling"]),
    ]
```

- [ ] **Step 2: Verify**

Run: `python -c "from src.workflow.templates import get_template; t = get_template('coursework'); print([c.title for c in t.get_outline()])"`
Expected: 10 chapters including "八、学习心得与反思".

- [ ] **Step 3: Commit**

```bash
git add src/workflow/templates.py
git commit -m "feat: improve coursework template with reflection chapter"
```

---

## Task 3: Improve springer_lncs system prompt

**Covers:** springer_lncs template has shorter system_prompt than other CCF-A templates

**Files:**
- Modify: `src/workflow/templates.py` — enhance `SpringerLNCSWriterTemplate`

- [ ] **Step 1: Enhance springer_lncs system prompt**

Update `SpringerLNCSWriterTemplate.get_system_prompt()` (already included in Task 1 Step 1 above — the version there is already improved compared to the original short version).

- [ ] **Step 2: Verify all 8 templates load correctly**

Run: `python -c "
from src.workflow.templates import list_templates
templates = list_templates()
print(f'Total: {len(templates)} templates')
for k, v in templates.items():
    print(f'  {k}: {v}')
"`
Expected: 8 templates, all with descriptions.

- [ ] **Step 3: Commit (same as Task 1)**

Already committed in Task 1.

---

## Verification Checklist

After all tasks:

- [ ] `python main.py --help` shows all 8 template choices
- [ ] `python -c "from src.workflow.templates import list_templates; print(len(list_templates()))"` returns 8
- [ ] All cls/sty files exist (verified: mcmthesis.cls, neurips_2024.sty, IEEEtran.cls, acmart.cls, llncs.cls)
- [ ] compliance_agent auto-triggers for financial_analysis (already wired in LangGraph: fact_check → compliance_check → summary)
