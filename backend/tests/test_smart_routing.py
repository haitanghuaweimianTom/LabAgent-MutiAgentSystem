"""测试智能路由功能"""
import pytest
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.routers.tasks import _route_user_message
from app.core.chat_room import ChatRoom


class TestSmartRouting:
    """测试用户消息智能路由"""

    def test_route_to_research_agent(self):
        """测试路由到研究员"""
        msgs = [
            "请搜索相关文献",
            "需要查找论文引用",
            "文献综述怎么写",
        ]
        for msg in msgs:
            result = _route_user_message(msg)
            assert "research_agent" in result, f"'{msg}' 应该路由到 research_agent"

    def test_route_to_data_agent(self):
        """测试路由到数据分析师"""
        msgs = [
            "数据需要清洗",
            "特征怎么提取",
            "CSV文件预处理",
        ]
        for msg in msgs:
            result = _route_user_message(msg)
            assert "data_agent" in result, f"'{msg}' 应该路由到 data_agent"

    def test_route_to_modeler_agent(self):
        """测试路由到建模师"""
        msgs = [
            "模型需要调整",
            "数学公式有问题",
            "约束条件怎么设",
        ]
        for msg in msgs:
            result = _route_user_message(msg)
            assert "modeler_agent" in result, f"'{msg}' 应该路由到 modeler_agent"

    def test_route_to_solver_agent(self):
        """测试路由到求解器"""
        msgs = [
            "代码运行报错",
            "Python实现有问题",
            "求解器不收敛",
            "计算结果不对",
        ]
        for msg in msgs:
            result = _route_user_message(msg)
            assert "solver_agent" in result, f"'{msg}' 应该路由到 solver_agent"

    def test_route_to_algorithm_engineer(self):
        """测试路由到算法工程师"""
        msgs = [
            "算法设计有问题",
            "复杂度太高",
            "需要新的优化策略",
        ]
        for msg in msgs:
            result = _route_user_message(msg)
            assert "algorithm_engineer_agent" in result, f"'{msg}' 应该路由到 algorithm_engineer_agent"

    def test_route_to_writer_agent(self):
        """测试路由到写作专家"""
        msgs = [
            "论文摘要需要修改",
            "LaTeX格式不对",
            "英文表达有问题",
        ]
        for msg in msgs:
            result = _route_user_message(msg)
            assert "writer_agent" in result, f"'{msg}' 应该路由到 writer_agent"

    def test_route_to_figure_agent(self):
        """测试路由到科研绘图师"""
        msgs = [
            "图表需要重新画",
            "可视化效果不好",
            "figure怎么调整",
        ]
        for msg in msgs:
            result = _route_user_message(msg)
            assert "figure_agent" in result, f"'{msg}' 应该路由到 figure_agent"

    def test_fallback_to_coordinator(self):
        """测试无匹配时回退到协调者"""
        msgs = [
            "你好",
            "随便看看",
            "这个系统怎么用",
        ]
        for msg in msgs:
            result = _route_user_message(msg)
            assert result == ["coordinator"], f"'{msg}' 应该路由到 coordinator"

    def test_current_step_routing(self):
        """测试根据当前步骤路由"""
        # 当关键词匹配不足时，根据当前步骤推断
        # 使用不含任何关键词的消息测试步骤推断
        result = _route_user_message("hello", current_step="modeler working")
        # "modeler" 在步骤中，应该路由到 modeler_agent
        assert "modeler_agent" in result, f"Expected modeler_agent in {result}"

        result = _route_user_message("test", current_step="solver running")
        assert "solver_agent" in result, f"Expected solver_agent in {result}"

    def test_multiple_agents(self):
        """测试可能返回多个 Agent"""
        # "数据" 匹配 data_agent，"模型" 匹配 modeler_agent
        result = _route_user_message("数据模型都有问题")
        assert len(result) >= 1
        assert len(result) <= 2  # 最多返回2个


class TestUserFeedbackExtraction:
    """测试用户反馈提取"""

    def test_extract_correction(self):
        """测试提取修正建议"""
        room = ChatRoom("test_room", "test_task", "测试问题")

        room.user_post("这个模型有问题，应该修改约束条件")

        feedback = room.get_user_feedback()
        assert len(feedback) == 1
        assert feedback[0]["type"] == "correction"
        assert feedback[0]["action"] == "revise"

    def test_extract_approval(self):
        """测试提取确认"""
        room = ChatRoom("test_room", "test_task", "测试问题")

        room.user_post("好的，确认继续")

        feedback = room.get_user_feedback()
        assert len(feedback) == 1
        assert feedback[0]["type"] == "approval"
        assert feedback[0]["action"] == "proceed"

    def test_extract_question(self):
        """测试提取疑问"""
        room = ChatRoom("test_room", "test_task", "测试问题")

        room.user_post("为什么这样设计？")

        feedback = room.get_user_feedback()
        assert len(feedback) == 1
        assert feedback[0]["type"] == "question"
        assert feedback[0]["action"] == "clarify"

    def test_feedback_summary(self):
        """测试反馈摘要"""
        room = ChatRoom("test_room", "test_task", "测试问题")

        room.user_post("模型需要修正")
        room.user_post("数据也有问题")

        summary = room.get_latest_feedback_summary()
        assert "用户反馈摘要" in summary
        assert "修正建议" in summary


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
