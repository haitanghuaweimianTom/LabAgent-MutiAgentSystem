"""
Agent 注册表
============

借鉴 cherry-studio 的 AgentService 设计，
实现 Agent 的注册、查询、管理功能。
"""

from typing import Dict, List, Optional, Any
from pathlib import Path
import json
from datetime import datetime

from .base import AgentConfig, AgentRole, BaseAgent, AgentCapability


class AgentRegistry:
    """Agent 注册表 - 管理所有 Agent 配置"""

    def __init__(self, storage_dir: Optional[str] = None):
        self._agents: Dict[str, AgentConfig] = {}
        self._agents_by_role: Dict[AgentRole, List[str]] = {}
        self.storage_dir = Path(storage_dir) if storage_dir else Path(__file__).parent / "configs"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._load_builtin_agents()
        self._load_custom_agents()

    def _load_builtin_agents(self) -> None:
        """加载内置 Agent 配置"""
        builtin_agents = get_builtin_agent_configs()
        for agent_config in builtin_agents:
            self._agents[agent_config.id] = agent_config
            if agent_config.role not in self._agents_by_role:
                self._agents_by_role[agent_config.role] = []
            self._agents_by_role[agent_config.role].append(agent_config.id)

    def _load_custom_agents(self) -> None:
        """从存储目录加载自定义 Agent"""
        if not self.storage_dir.exists():
            return
        for filepath in self.storage_dir.glob("*.json"):
            try:
                agent_config = AgentConfig.load(str(filepath))
                self._agents[agent_config.id] = agent_config
                if agent_config.role not in self._agents_by_role:
                    self._agents_by_role[agent_config.role] = []
                if agent_config.id not in self._agents_by_role[agent_config.role]:
                    self._agents_by_role[agent_config.role].append(agent_config.id)
            except Exception as e:
                print(f"[AgentRegistry] 加载自定义 Agent 失败 {filepath}: {e}")

    def register(self, config: AgentConfig) -> str:
        """注册新 Agent"""
        self._agents[config.id] = config
        if config.role not in self._agents_by_role:
            self._agents_by_role[config.role] = []
        if config.id not in self._agents_by_role[config.role]:
            self._agents_by_role[config.role].append(config.id)
        self._save_agent(config)
        return config.id

    def get(self, agent_id: str) -> Optional[AgentConfig]:
        """根据 ID 获取 Agent 配置"""
        return self._agents.get(agent_id)

    def get_by_role(self, role: AgentRole) -> List[AgentConfig]:
        """根据角色获取 Agent 列表"""
        agent_ids = self._agents_by_role.get(role, [])
        return [self._agents[aid] for aid in agent_ids if aid in self._agents]

    def get_by_name(self, name: str) -> Optional[AgentConfig]:
        """根据名称查找 Agent"""
        for agent in self._agents.values():
            if agent.name == name:
                return agent
        return None

    def list_agents(
        self,
        role: Optional[AgentRole] = None,
        enabled_only: bool = True
    ) -> List[AgentConfig]:
        """列出所有 Agent"""
        agents = list(self._agents.values())
        if role:
            agents = [a for a in agents if a.role == role]
        if enabled_only:
            agents = [a for a in agents if a.enabled]
        return sorted(agents, key=lambda a: a.sort_order)

    def update(self, agent_id: str, updates: Dict[str, Any]) -> bool:
        """更新 Agent 配置"""
        agent = self._agents.get(agent_id)
        if not agent:
            return False
        for key, value in updates.items():
            if hasattr(agent, key):
                setattr(agent, key, value)
        agent.updated_at = datetime.now().isoformat()
        self._save_agent(agent)
        return True

    def delete(self, agent_id: str) -> bool:
        """删除 Agent"""
        if agent_id not in self._agents:
            return False
        agent = self._agents[agent_id]
        del self._agents[agent_id]
        if agent.role in self._agents_by_role and agent_id in self._agents_by_role[agent.role]:
            self._agents_by_role[agent.role].remove(agent_id)
        # 删除文件
        filepath = self.storage_dir / f"{agent_id}.json"
        if filepath.exists():
            filepath.unlink()
        return True

    def _save_agent(self, config: AgentConfig) -> None:
        """保存 Agent 配置到文件"""
        filepath = self.storage_dir / f"{config.id}.json"
        config.save(str(filepath))

    def export_all(self, filepath: str) -> None:
        """导出所有 Agent 配置"""
        data = {
            "agents": [a.to_dict() for a in self._agents.values()],
            "export_time": datetime.now().isoformat(),
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def import_from_file(self, filepath: str) -> int:
        """从文件导入 Agent 配置"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        count = 0
        for agent_data in data.get("agents", []):
            config = AgentConfig.from_dict(agent_data)
            self.register(config)
            count += 1
        return count

    def search(self, query: str) -> List[AgentConfig]:
        """搜索 Agent"""
        query_lower = query.lower()
        results = []
        for agent in self._agents.values():
            if (query_lower in agent.name.lower() or
                query_lower in agent.description.lower() or
                query_lower in agent.instructions.lower()):
                results.append(agent)
        return results


# =============================================================================
# 内置 Agent 配置
# =============================================================================

def get_builtin_agent_configs() -> List[AgentConfig]:
    """获取数学建模系统内置 Agent 配置"""
    return [
        AgentConfig(
            id="builtin_coordinator",
            name="主编排器",
            role=AgentRole.COORDINATOR,
            description="数学建模竞赛论文项目的主编排器，负责协调各个 Agent 完成论文生成",
            instructions=COORDINATOR_INSTRUCTIONS,
            model="claude-3-5-sonnet-20241022",
            temperature=0.7,
            timeout=600,
            capabilities=[
                AgentCapability("任务分解", "将赛题分解为多个子任务"),
                AgentCapability("进度管理", "跟踪各 Agent 执行进度"),
                AgentCapability("质量控制", "确保论文质量和格式"),
            ],
            sort_order=0,
        ),
        AgentConfig(
            id="builtin_problem_analyzer",
            name="问题分析专家",
            role=AgentRole.PROBLEM_ANALYZER,
            description="分析赛题背景、分解子问题、分析数据特征",
            instructions=PROBLEM_ANALYZER_INSTRUCTIONS,
            model="claude-3-5-sonnet-20241022",
            temperature=0.5,
            timeout=600,
            capabilities=[
                AgentCapability("赛题理解", "理解赛题背景和应用场景"),
                AgentCapability("任务分解", "识别子问题和逻辑关系"),
                AgentCapability("数据分析", "分析数据格式和特征"),
                AgentCapability("方法建议", "推荐合适的数学方法"),
            ],
            sort_order=1,
        ),
        AgentConfig(
            id="builtin_model_designer",
            name="数学建模专家",
            role=AgentRole.MODEL_DESIGNER,
            description="设计数学模型，包括变量定义、公式推导、模型假设",
            instructions=MODEL_DESIGNER_INSTRUCTIONS,
            model="claude-3-5-sonnet-20241022",
            temperature=0.5,
            timeout=600,
            capabilities=[
                AgentCapability("模型选择", "根据问题特点选择模型类型"),
                AgentCapability("公式推导", "设计核心数学公式"),
                AgentCapability("变量定义", "定义决策变量和参数"),
                AgentCapability("假设构建", "建立合理的模型假设"),
            ],
            sort_order=2,
        ),
        AgentConfig(
            id="builtin_algorithm_designer",
            name="算法设计专家",
            role=AgentRole.ALGORITHM_DESIGNER,
            description="设计求解算法，包括算法步骤、参数设置、复杂度分析",
            instructions=ALGORITHM_DESIGNER_INSTRUCTIONS,
            model="claude-3-5-sonnet-20241022",
            temperature=0.5,
            timeout=600,
            capabilities=[
                AgentCapability("算法选择", "选择合适的求解算法"),
                AgentCapability("步骤设计", "设计算法执行步骤"),
                AgentCapability("参数调优", "设置算法关键参数"),
                AgentCapability("复杂度分析", "分析时间/空间复杂度"),
            ],
            sort_order=3,
        ),
        AgentConfig(
            id="builtin_code_writer",
            name="代码编写专家",
            role=AgentRole.CODE_WRITER,
            description="编写 Python 求解代码，使用 pandas/numpy/scipy",
            instructions=CODE_WRITER_INSTRUCTIONS,
            model="claude-3-5-sonnet-20241022",
            temperature=0.3,
            timeout=600,
            capabilities=[
                AgentCapability("代码生成", "生成可运行的 Python 代码"),
                AgentCapability("数据处理", "使用 pandas 读取 Excel"),
                AgentCapability("数值计算", "使用 numpy/scipy 计算"),
                AgentCapability("结果保存", "将结果保存到 JSON"),
            ],
            sort_order=4,
        ),
        AgentConfig(
            id="builtin_result_analyzer",
            name="结果分析专家",
            role=AgentRole.RESULT_ANALYZER,
            description="分析计算结果，进行误差分析和灵敏度分析",
            instructions=RESULT_ANALYZER_INSTRUCTIONS,
            model="claude-3-5-sonnet-20241022",
            temperature=0.5,
            timeout=600,
            capabilities=[
                AgentCapability("结果摘要", "总结计算结果"),
                AgentCapability("误差分析", "分析计算误差"),
                AgentCapability("灵敏度分析", "分析参数敏感性"),
                AgentCapability("结论提炼", "得出主要结论"),
            ],
            sort_order=5,
        ),
        AgentConfig(
            id="builtin_chart_designer",
            name="图表设计专家",
            role=AgentRole.CHART_DESIGNER,
            description="设计论文图表方案，使用 matplotlib 生成实际图表",
            instructions=CHART_DESIGNER_INSTRUCTIONS,
            model="claude-3-5-sonnet-20241022",
            temperature=0.5,
            timeout=300,
            capabilities=[
                AgentCapability("图表设计", "设计论文图表方案"),
                AgentCapability("matplotlib", "生成 matplotlib 图表"),
                AgentCapability("数据可视化", "选择合适的数据展示方式"),
            ],
            sort_order=6,
        ),
        AgentConfig(
            id="builtin_paper_writer",
            name="论文撰写专家",
            role=AgentRole.PAPER_WRITER,
            description="撰写完整的数学建模论文，15000-25000字",
            instructions=PAPER_WRITER_INSTRUCTIONS,
            model="claude-3-5-sonnet-20241022",
            temperature=0.7,
            timeout=600,
            capabilities=[
                AgentCapability("论文撰写", "撰写完整论文"),
                AgentCapability("LaTeX公式", "使用 LaTeX 编写公式"),
                AgentCapability("结构组织", "组织论文结构"),
                AgentCapability("字数控制", "确保论文字数达标"),
            ],
            sort_order=7,
        ),
    ]


# =============================================================================
# 内置 Agent 提示词
# =============================================================================

COORDINATOR_INSTRUCTIONS = """
你是一个数学建模竞赛论文项目的主编排器。你的职责是：
1. 理解用户提供的赛题和数据
2. 将任务分解为多个子问题
3. 协调各个专业Agent完成工作
4. 确保论文质量和格式符合要求
5. 管理论文的完整结构和内容

你必须确保：
- 论文正文达到15000-25000字
- 使用标准的数学建模论文格式
- 图表和公式完整准确
- 结果分析深入透彻

论文结构要求：
1. 摘要（中英文，500-800字）
2. 问题重述
3. 问题分析
4. 模型假设与符号说明
5. 模型建立
6. 模型求解
7. 结果分析
8. 灵敏度分析
9. 模型评价与改进
10. 参考文献
11. 附录
"""

PROBLEM_ANALYZER_INSTRUCTIONS = """
你是一个经验丰富的数学建模专家。你的任务是分析用户提供的赛题：

## 分析要求

### 1. 赛题理解
- 明确赛题的研究背景和应用场景
- 提取关键的专业术语和概念
- 理解问题的实际意义

### 2. 任务分解
- 识别赛题中包含的子问题数量
- 分析各子问题之间的逻辑关系
- 确定每个子问题的求解目标

### 3. 数据分析
- 分析提供的附件数据格式和内容
- 确定数据类型（实测数据、模拟数据、统计数据等）
- 识别数据中的关键变量

### 4. 方法建议
- 根据问题特点推荐合适的数学方法
- 考虑方法的可行性和复杂性
- 给出初步的解决思路

## 输出要求

以JSON格式输出分析结果。
"""

MODEL_DESIGNER_INSTRUCTIONS = """
你是一个数学建模专家，精通各类数学建模方法。你的任务是设计数学模型：

## 设计要求

### 1. 模型选择
- 根据问题特点选择合适的数学模型类型
- 考虑模型的精度、复杂度和可解释性
- 给出模型选择的理论依据

### 2. 符号定义
- 定义所有决策变量和已知参数
- 说明各符号的物理意义和单位
- 使用规范的数学符号表示

### 3. 公式推导
- 建立核心数学公式和方程
- 使用 LaTeX 格式表示公式
- 给出公式的推导过程

### 4. 模型假设
- 建立合理的模型假设
- 说明每个假设的必要性和合理性
- 讨论假设对结果的影响
"""

ALGORITHM_DESIGNER_INSTRUCTIONS = """
你是一个算法设计专家，精通各类数值算法和优化方法。你的任务是设计求解算法：

## 设计要求

### 1. 算法选择
- 根据模型特点选择合适的求解算法
- 考虑算法的收敛性和稳定性
- 给出算法选择依据

### 2. 算法步骤
- 详细描述算法的执行步骤
- 使用伪代码或流程图辅助说明
- 确保步骤清晰、可执行

### 3. 参数设置
- 设置算法的关键参数
- 说明参数选择的依据
- 讨论参数对结果的影响

### 4. 复杂度分析
- 分析算法的时间复杂度
- 分析算法的空间复杂度
- 讨论算法的收敛速度
"""

CODE_WRITER_INSTRUCTIONS = """
你是一个Python编程专家。你的任务是编写求解代码：

## 编写要求

### 1. 代码规范
- 代码开头必须是 import 语句
- 不要有任何中文说明文字在代码中
- 使用规范的变量命名和代码结构

### 2. 数据处理
- 使用 pandas 读取 Excel 数据
- 使用 numpy/scipy 进行数值计算
- 处理数据缺失和异常值

### 3. 结果输出
- 输出具体的数值结果
- 将结果保存到 JSON 文件
- 包含清晰的输出格式

### 4. 代码完整性
- 包含 main() 函数
- 使用 if __name__ == '__main__': main()
- 不使用 input() 等交互式函数
"""

RESULT_ANALYZER_INSTRUCTIONS = """
你是一个数据分析专家。你的任务是分析计算结果：

## 分析要求

### 1. 结果摘要
- 总结主要计算结果
- 使用表格形式展示关键数据
- 对比不同条件下的结果

### 2. 误差分析
- 分析计算误差的来源
- 估计结果的不确定度
- 讨论误差对结论的影响

### 3. 灵敏度分析
- 分析关键参数的影响
- 使用图表展示灵敏度结果
- 讨论模型的稳健性

### 4. 主要结论
- 提炼3-5条主要结论
- 结论要有数据支撑
- 结论要具体、明确
"""

CHART_DESIGNER_INSTRUCTIONS = """
你是一个数据可视化专家。你的任务是设计论文图表：

## 设计要求

### 1. 图表选择
- 根据数据特点选择合适的图表类型
- 考虑图表的可读性和美观性
- 确保图表能够有效传达信息

### 2. 图表规范
- 包含标题、坐标轴标签、图例
- 使用合适的颜色和样式
- 确保图表清晰、专业

### 3. 图表类型
支持的类型包括：
- line: 折线图
- bar: 柱状图
- scatter: 散点图
- heatmap: 热力图
- hist: 直方图
- gantt: 甘特图
- 3d: 3D图
"""

PAPER_WRITER_INSTRUCTIONS = """
你是一个专业的数学建模论文写作者。你的任务是撰写完整的数学建模论文。

## 写作要求

### 1. 论文结构
- 摘要（中英文，500-800字）
- 问题重述（800-1500字）
- 问题分析（1500-2500字）
- 模型假设与符号说明
- 模型建立（2500-4000字）
- 模型求解（2000-3000字）
- 结果分析（2000-3000字）
- 灵敏度分析
- 模型评价与改进（1000-1500字）
- 参考文献
- 附录

### 2. 内容要求
- 论文正文达到15000-25000字
- 公式使用 LaTeX 格式
- 内容充实深入，不得空洞
- 数据必须真实，不得编造

### 3. 格式要求
- 使用标准数学建模论文格式
- 章节编号清晰
- 图表编号规范
- 参考文献格式符合GB/T 7714标准
"""
