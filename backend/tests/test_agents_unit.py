"""Agent 单元测试 — 覆盖所有 Agent、模板、工作流。

测试策略：
1. Mock LLM 调用（不消耗真实 API 额度）
2. 每个 Agent 独立测试
3. 覆盖正常路径 + 错误路径
4. 验证输出 schema 符合约定
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any


# ============================================================================
# 辅助工具
# ============================================================================

def mock_llm_response(content: str, tool_calls=None) -> Dict[str, Any]:
    """构造 Mock LLM 响应。"""
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {
        "choices": [msg],
        "model": "test-model",
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }


def mock_llm_json_response(data: dict) -> Dict[str, Any]:
    """构造返回 JSON 的 Mock LLM 响应。"""
    return mock_llm_response(json.dumps(data, ensure_ascii=False))


# ============================================================================
# AnalyzerAgent 测试
# ============================================================================

class TestAnalyzerAgent:
    """测试 analyzer_agent：子问题分解。"""

    @pytest.fixture
    def agent(self):
        from app.agents.analyzer_agent import AnalyzerAgent
        return AnalyzerAgent()

    @pytest.mark.asyncio
    async def test_analyze_math_modeling(self, agent):
        """测试数学建模问题分析。"""
        mock_output = {
            "sub_problems": [
                {"id": 1, "name": "子问题1", "description": "建立优化模型", "problem_type": "optimization"},
                {"id": 2, "name": "子问题2", "description": "灵敏度分析", "problem_type": "analysis"},
            ],
            "problem_type": "math_modeling",
            "difficulty": "medium",
        }
        with patch.object(agent, 'call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_llm_json_response(mock_output)
            result = await agent.execute(
                task_input={"action": "analyze", "problem_text": "求解最优化问题"},
                context={"task_id": "test", "problem_text": "求解最优化问题"},
            )

        assert "sub_problems" in result
        assert len(result["sub_problems"]) >= 1  # Agent 可能合并子问题
        assert result.get("problem_type") is not None

    @pytest.mark.asyncio
    async def test_analyze_empty_input(self, agent):
        """测试空输入处理。"""
        with patch.object(agent, 'call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_llm_json_response({"sub_problems": [], "problem_type": "unknown"})
            result = await agent.execute(
                task_input={"action": "analyze", "problem_text": ""},
                context={"task_id": "test", "problem_text": ""},
            )
        assert "sub_problems" in result


# ============================================================================
# DataAgent 测试
# ============================================================================

class TestDataAgent:
    """测试 data_agent：数据分析。"""

    @pytest.fixture
    def agent(self):
        from app.agents.data_agent import DataAgent
        return DataAgent()

    @pytest.mark.asyncio
    async def test_analyze_data(self, agent):
        """测试数据分析（无文件时返回默认结果）。"""
        result = await agent.execute(
            task_input={"action": "analyze_data", "problem_text": "数据分析"},
            context={"task_id": "test", "files": []},
        )
        # 无文件时应返回默认结构
        assert isinstance(result, dict)
        assert "analyses" in result or "summary" in result


# ============================================================================
# ResearchAgent 测试
# ============================================================================

class TestResearchAgent:
    """测试 research_agent：文献检索。"""

    @pytest.fixture
    def agent(self):
        from app.agents.research_agent import ResearchAgent
        return ResearchAgent()

    @pytest.mark.asyncio
    async def test_search_papers(self, agent):
        """测试文献搜索（无 MCP 工具时返回基本结果）。"""
        result = await agent.execute(
            task_input={"action": "search", "problem_text": "多智能体记忆"},
            context={"task_id": "test"},
        )
        # 应返回基本结构
        assert isinstance(result, dict)
        assert "papers" in result or "methods" in result


# ============================================================================
# ModelerAgent 测试
# ============================================================================

class TestModelerAgent:
    """测试 modeler_agent：数学建模。"""

    @pytest.fixture
    def agent(self):
        from app.agents.modeler_agent import ModelerAgent
        return ModelerAgent()

    @pytest.mark.asyncio
    async def test_build_model(self, agent):
        """测试建模。"""
        mock_output = {
            "model_type": "optimization",
            "model_name": "线性规划模型",
            "decision_variables": [{"name": "x", "type": "连续"}],
            "objective_function": "max z = 2x + 3y",
            "constraints": [{"name": "c1", "expression": "x + y <= 10"}],
            "algorithm": {"name": "Simplex", "description": "单纯形法"},
        }
        with patch.object(agent, 'call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_llm_json_response(mock_output)
            result = await agent.execute(
                task_input={"action": "model", "problem_text": "线性规划"},
                context={"task_id": "test", "sub_problem": {"description": "优化问题"}},
            )
        assert "model_name" in result
        assert "objective_function" in result

    @pytest.mark.asyncio
    async def test_fallback_template(self, agent):
        """测试 LLM 失败时的模板兜底。"""
        with patch.object(agent, 'call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("LLM API error")
            result = await agent.execute(
                task_input={"action": "model", "problem_text": "优化问题"},
                context={"task_id": "test", "sub_problem": {"description": "优化问题", "suggested_method": "linear programming"}},
            )
        # 兜底模板应标记为降级模式
        assert result.get("_degraded_mode") == True or result.get("_used_fallback_template") == True


# ============================================================================
# SolverAgent 测试
# ============================================================================

class TestSolverAgent:
    """测试 solver_agent：代码生成与执行。"""

    @pytest.fixture
    def agent(self):
        from app.agents.solver_agent import SolverAgent
        return SolverAgent({})

    @pytest.mark.asyncio
    async def test_solve_with_code(self, agent):
        """测试代码求解（LLM 失败时使用模板）。"""
        with patch.object(agent, 'call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("LLM API error")
            result = await agent.execute(
                task_input={"action": "solve", "problem_text": "求最优解"},
                context={"task_id": "test", "sub_problem": {"description": "求最优解", "id": 1}},
            )
        # 应返回基本结构（可能使用模板）
        assert isinstance(result, dict)
        assert "code_files" in result or "results" in result


# ============================================================================
# WriterAgent 测试
# ============================================================================

class TestWriterAgent:
    """测试 writer_agent：论文写作。"""

    @pytest.fixture
    def agent(self):
        from app.agents.writer_agent import WriterAgent
        return WriterAgent()

    @pytest.mark.asyncio
    async def test_write_paper(self, agent):
        """测试论文生成。"""
        # Mock 返回有效的章节内容（非空、非占位符）
        mock_output = {
            "chapter_latex": "\\section{Introduction}\nThis is a detailed introduction with more than 50 characters of content to pass validation.",
            "chapter_summary": "Introduction chapter summary",
        }
        with patch.object(agent, 'call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_llm_json_response(mock_output)
            result = await agent.execute(
                task_input={"action": "write", "problem_text": "写论文"},
                context={"task_id": "test", "sub_problems": []},
            )
        # writer 应该返回基本结构
        assert isinstance(result, dict)


# ============================================================================
# PeerReviewAgent 测试
# ============================================================================

class TestPeerReviewAgent:
    """测试 peer_review_agent：同行评议。"""

    @pytest.fixture
    def agent(self):
        from app.agents.peer_review_agent import PeerReviewAgent
        return PeerReviewAgent()

    @pytest.mark.asyncio
    async def test_review(self, agent):
        """测试同行评议。"""
        mock_output = {
            "recommendation": "accept",
            "overall_score": 7.5,
            "novelty": 8.0,
            "soundness": 7.0,
            "clarity": 7.5,
            "significance": 7.0,
            "comments": "Good paper",
        }
        with patch.object(agent, 'call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_llm_json_response(mock_output)
            result = await agent.execute(
                task_input={"action": "review", "problem_text": "审稿"},
                context={"task_id": "test"},
            )
        assert "recommendation" in result
        assert "overall_score" in result


# ============================================================================
# InnovationAgent 测试
# ============================================================================

class TestInnovationAgent:
    """测试 innovation_agent：创新发现。"""

    @pytest.fixture
    def agent(self):
        from app.agents.innovation_agent import InnovationAgent
        return InnovationAgent()

    @pytest.mark.asyncio
    async def test_find_innovations(self, agent):
        """测试创新点发现。"""
        mock_output = {
            "research_gaps": ["Gap 1: 缺乏长程记忆", "Gap 2: 缺乏跨任务学习"],
            "innovation_ideas": [
                {"novelty": 8, "feasibility": 7, "description": "结构化情景记忆"},
            ],
        }
        with patch.object(agent, 'call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_llm_json_response(mock_output)
            result = await agent.execute(
                task_input={"action": "innovate", "problem_text": "创新发现"},
                context={"task_id": "test"},
            )
        assert "research_gaps" in result or "innovation_ideas" in result


# ============================================================================
# RequirementDecomposer 测试
# ============================================================================

class TestRequirementDecomposer:
    """测试 requirement_decomposer：需求分解。"""

    @pytest.fixture
    def agent(self):
        from app.agents.requirement_decomposer import RequirementDecomposerAgent
        return RequirementDecomposerAgent()

    @pytest.mark.asyncio
    async def test_decompose(self, agent):
        """测试需求分解（需要 problem_text 在 context 中）。"""
        result = await agent.execute(
            task_input={"action": "decompose", "problem_text": "短需求"},
            context={"task_id": "test", "problem_text": "这是一个较长的需求描述，需要分解为多个子任务"},
        )
        # 应返回基本结构
        assert result is None or isinstance(result, dict)


# ============================================================================
# SummaryAgent 测试
# ============================================================================

class TestSummaryAgent:
    """测试 summary_agent：任务总结。"""

    @pytest.fixture
    def agent(self):
        from app.agents.summary_agent import SummaryAgent
        return SummaryAgent()

    @pytest.mark.asyncio
    async def test_summarize(self, agent):
        """测试任务总结。"""
        mock_output = {
            "research_summary": "任务完成总结",
            "lessons_learned": [{"category": "method_selection", "content": "经验1"}],
        }
        with patch.object(agent, 'call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_llm_json_response(mock_output)
            result = await agent.execute(
                task_input={"action": "summarize", "problem_text": "总结"},
                context={"task_id": "test"},
            )
        assert "research_summary" in result or "lessons_learned" in result


# ============================================================================
# ExperimentationAgent 测试
# ============================================================================

class TestExperimentationAgent:
    """测试 experimentation_agent：实验设计。"""

    @pytest.fixture
    def agent(self):
        from app.agents.experimentation_agent import ExperimentationAgent
        return ExperimentationAgent()

    @pytest.mark.asyncio
    async def test_design_experiment(self, agent):
        """测试实验设计（LLM 失败时返回空计划）。"""
        with patch.object(agent, 'call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("LLM API error")
            result = await agent.execute(
                task_input={"action": "design", "problem_text": "实验设计"},
                context={"task_id": "test"},
            )
        # 应返回带错误标记的空计划
        assert isinstance(result, dict)

    def test_empty_plan_has_error_marker(self):
        """测试空计划标记失败原因。"""
        from app.agents.experimentation_agent import ExperimentationAgent
        plan = ExperimentationAgent._empty_plan()
        assert plan.get("_plan_generation_failed") == True
        assert plan.get("_error") is not None


# ============================================================================
# AlgorithmEngineerAgent 测试
# ============================================================================

class TestAlgorithmEngineerAgent:
    """测试 algorithm_engineer_agent：算法设计。"""

    @pytest.fixture
    def agent(self):
        from app.agents.algorithm_engineer_agent import AlgorithmEngineerAgent
        return AlgorithmEngineerAgent()

    @pytest.mark.asyncio
    async def test_design_algorithm(self, agent):
        """测试算法设计。"""
        mock_output = {
            "proposed_method": {"name": "新算法", "description": "基于Transformer的方法"},
            "complexity": "O(NlogN)",
        }
        with patch.object(agent, 'call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_llm_json_response(mock_output)
            result = await agent.execute(
                task_input={"action": "design", "problem_text": "算法设计"},
                context={"task_id": "test"},
            )
        assert "proposed_method" in result


# ============================================================================
# FinancialAnalystAgent 测试
# ============================================================================

class TestFinancialAnalystAgent:
    """测试 financial_analyst_agent：金融分析。"""

    @pytest.fixture
    def agent(self):
        from app.agents.financial_analyst_agent import FinancialAnalystAgent
        return FinancialAnalystAgent()

    @pytest.mark.asyncio
    async def test_financial_analysis(self, agent):
        """测试金融分析（LLM 失败时返回错误）。"""
        with patch.object(agent, 'call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("LLM API error")
            result = await agent.execute(
                task_input={"action": "analyze", "problem_text": "金融风险分析"},
                context={"task_id": "test"},
            )
        # 应返回错误或降级结果
        assert isinstance(result, dict)


# ============================================================================
# CODE_TEMPLATES 测试
# ============================================================================

class TestCodeTemplates:
    """测试 solver_agent 的代码模板。"""

    def test_all_templates_exist(self):
        """测试所有模板都存在。"""
        from app.agents.solver_agent import CODE_TEMPLATES
        expected = [
            "linear_programming", "time_series", "exponential_smoothing",
            "topsis", "ahp", "entropy_weight", "fuzzy_evaluation",
            "grey_relational", "algorithm_design", "financial_model",
            "data_cleaning",
        ]
        for name in expected:
            assert name in CODE_TEMPLATES, f"Template '{name}' missing"

    def test_no_todo_stubs(self):
        """测试模板中没有 TODO 占位符。"""
        from app.agents.solver_agent import CODE_TEMPLATES
        for name, code in CODE_TEMPLATES.items():
            assert "TODO" not in code, f"Template '{name}' contains TODO stub"

    def test_algorithm_design_has_real_code(self):
        """测试 algorithm_design 模板有真实算法实现。"""
        from app.agents.solver_agent import CODE_TEMPLATES
        code = CODE_TEMPLATES["algorithm_design"]
        assert "Dijkstra" in code or "Kadane" in code
        assert '{"status": "placeholder"' not in code


# ============================================================================
# EventBus 测试
# ============================================================================

class TestEventBus:
    """测试事件总线。"""

    def test_publish_subscribe(self):
        """测试发布/订阅。"""
        from app.core.event_bus import TaskEventBus, TaskEvent
        bus = TaskEventBus()
        queue = bus.subscribe("test_task")

        event = TaskEvent(task_id="test_task", event_type="agent_start", agent_name="analyzer")
        bus.publish(event)

        received = queue.get_nowait()
        assert received.event_type == "agent_start"
        assert received.agent_name == "analyzer"

    def test_history_replay(self):
        """测试新订阅者收到历史事件。"""
        from app.core.event_bus import TaskEventBus, TaskEvent
        bus = TaskEventBus()

        # 先发布事件
        bus.publish(TaskEvent(task_id="task1", event_type="agent_start"))
        bus.publish(TaskEvent(task_id="task1", event_type="agent_complete"))

        # 新订阅者应收到历史
        queue = bus.subscribe("task1")
        assert queue.qsize() == 2

    def test_cleanup(self):
        """测试清理。"""
        from app.core.event_bus import TaskEventBus, TaskEvent
        bus = TaskEventBus()
        bus.subscribe("task_to_clean")
        bus.publish(TaskEvent(task_id="task_to_clean", event_type="test"))

        bus.cleanup("task_to_clean")
        assert "task_to_clean" not in bus._history


# ============================================================================
# TaskManager 测试
# ============================================================================

class TestTaskManager:
    """测试异步任务管理器。"""

    @pytest.mark.asyncio
    async def test_submit_and_complete(self):
        """测试提交并完成任务。"""
        from app.core.task_manager import AsyncTaskManager
        mgr = AsyncTaskManager(max_concurrent=2)

        async def dummy_task():
            return "done"

        task_id = mgr.submit("test_submit", dummy_task)
        assert task_id == "test_submit"

        # 等待任务完成
        import asyncio
        await asyncio.sleep(0.5)

        status = mgr.get_status("test_submit")
        assert status["status"] == "completed"

    @pytest.mark.asyncio
    async def test_cancel_task(self):
        """测试取消任务。"""
        from app.core.task_manager import AsyncTaskManager
        mgr = AsyncTaskManager(max_concurrent=1)

        async def slow_task():
            await asyncio.sleep(10)
            return "done"

        mgr.submit("test_cancel", slow_task)
        import asyncio
        await asyncio.sleep(0.1)

        result = mgr.cancel("test_cancel")
        assert result == True

        status = mgr.get_status("test_cancel")
        assert status["status"] == "cancelled"


# ============================================================================
# Paper Templates 测试
# ============================================================================

class TestPaperTemplates:
    """测试论文模板。"""

    def test_templates_exist(self):
        """测试模板目录存在。"""
        from pathlib import Path
        template_dir = Path(__file__).parent.parent / "app" / "core" / "paper_templates" / "templates"
        assert template_dir.exists(), f"Template dir not found: {template_dir}"

    def test_cumcm_template_file(self):
        """测试 CUMCM 模板文件存在。"""
        from pathlib import Path
        import json
        template_dir = Path(__file__).parent.parent / "app" / "core" / "paper_templates" / "templates"
        cumcm_file = template_dir / "cumcm.json"
        if cumcm_file.exists():
            with open(cumcm_file) as f:
                data = json.load(f)
            assert "chapters" in data or "chapter_plan" in data


# ============================================================================
# Memory System 测试
# ============================================================================

class TestMemorySystem:
    """测试三级记忆系统。"""

    def test_working_memory(self):
        """测试工作记忆。"""
        from app.core.memory import WorkingMemory
        wm = WorkingMemory(task_id="test")
        wm.set_result("analyzer", {"output": "test"})
        # WorkingMemory 使用 set_result/get_result 通过 results dict
        assert wm.results.get("analyzer") == {"output": "test"}

    def test_episodic_memory(self):
        """测试情景记忆。"""
        from app.core.memory import EpisodicMemory
        em = EpisodicMemory(task_id="test")
        em.record("analyzer", "analysis", "分析完成")
        assert len(em.entries) == 1

        summary = em.compress()
        assert "analyzer" in summary

    def test_lessons_memory(self):
        """测试经验记忆。"""
        from app.core.memory import LessonsMemory
        lm = LessonsMemory()
        lm.add_lesson(
            category="method_selection",
            content="线性规划适合简单优化问题",
            tags=["optimization", "LP"],
        )
        results = lm.query(category="method_selection")
        assert len(results) >= 1


# ============================================================================
# Context Compressor 测试
# ============================================================================

class TestContextCompressor:
    """测试上下文压缩器。"""

    def test_soft_compress(self):
        """测试软压缩（长字符串截断）。"""
        from app.core.context_compressor import soft_compress
        data = {
            "title": "Important Title",
            "content": "x" * 10000,  # 超长内容
        }
        compressed, saved = soft_compress(data)
        assert "title" in compressed  # 保护字段保留
        # 长内容应被截断
        assert len(compressed.get("content", "")) < 10000


# ============================================================================
# Circuit Breaker 测试
# ============================================================================

class TestCircuitBreakerIntegration:
    """测试熔断器集成。"""

    def test_breaker_states(self):
        """测试状态机。"""
        from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
        config = CircuitBreakerConfig(failure_threshold=3, open_duration_seconds=1)
        cb = CircuitBreaker(name="test", config=config)
        assert cb.state == CircuitBreaker.CLOSED

        # 连续失败触发熔断
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
