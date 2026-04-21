# 数学建模多Agent论文自动生成系统

## 概述

这是一个基于多Agent协作的数学建模论文自动生成系统。系统通过多个专业Agent的协作，自动完成从问题分析、数学建模、编程求解到论文写作的全流程。

## 核心架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      Orchestrator (主编排器)                      │
├──────────┬──────────┬──────────┬──────────┬──────────────────────┤
│ Research │ Analyzer │ Modeler  │  Solver  │      Writer         │
│  Agent   │  Agent   │  Agent   │  Agent   │       Agent         │
│  (研究)  │  (分析)  │  (建模)  │  (求解)  │       (写作)        │
└────┬─────┴────┬─────┴────┬─────┴────┬─────┴──────────┬─────────┘
     │          │          │          │                │
     └──────────┴──────────┴──────────┴────────────────┘
                              │
                        MCP Tools
              (Web Search / Code Execute / File I/O)
```

## Agent说明

| Agent | 职责 | 默认模型 | 主要MCP工具 |
|-------|------|----------|-------------|
| ResearchAgent | 搜集资料、文献、数据 | minimax-m2.7 | web_search, paper_search |
| AnalyzerAgent | 问题分析、任务分解 | minimax-m2.7 | web_search |
| ModelerAgent | 建立数学模型、设计算法 | minimax-m2.7 | - |
| SolverAgent | 编程求解、结果验证 | minimax-m2.7 | code_execute, file_write |
| WriterAgent | 生成完整LaTeX论文 | minimax-m2.7 | file_write, latex_compile |

## 工作流程

1. **研究阶段** - 搜索相关文献和数据
2. **分析阶段** - 理解问题，分解任务
3. **建模阶段** - 建立数学模型
4. **求解阶段** - 编写代码，求解模型
5. **写作阶段** - 生成完整LaTeX论文

## 项目结构

```
math_modeling_multi_agent/
├── backend/                      # 后端服务
│   ├── app/
│   │   ├── agents/              # Agent实现
│   │   │   ├── base.py          # Agent基类
│   │   │   ├── orchestrator.py  # 主编排器
│   │   │   ├── research_agent.py
│   │   │   ├── analyzer_agent.py
│   │   │   ├── modeler_agent.py
│   │   │   ├── solver_agent.py
│   │   │   └── writer_agent.py
│   │   ├── routers/             # API路由
│   │   ├── schemas/             # Pydantic模型
│   │   ├── mcp/                 # MCP配置
│   │   ├── config.py            # 配置管理
│   │   └── main.py              # FastAPI入口
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/                     # 前端应用
│   ├── src/
│   │   └── app/                 # Next.js页面
│   └── package.json
│
├── config/                      # 配置文件
│   ├── mcp_config.json          # MCP工具配置
│   └── latex_templates/         # LaTeX模板
│
├── docker-compose.yml           # Docker编排
├── .env.example                 # 环境变量示例
└── README.md
```

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
cd E:/cherryClaw/math_modeling_multi_agent

# 安装后端依赖
cd backend
pip install -r requirements.txt

# 安装前端依赖
cd ../frontend
npm install
```

### 2. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑.env，填入你的API Key
MINIMAX_API_KEY=your_api_key_here
```

### 3. 启动服务

#### 开发模式

```bash
# 启动后端
cd backend
uvicorn app.main:app --reload --port 8000

# 启动前端（新终端）
cd frontend
npm run dev
```

#### Docker部署

```bash
# 构建并启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f
```

### 4. 访问系统

- 前端界面: http://localhost:3000
- API文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/health

## API接口

### 任务管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/v1/tasks | 创建任务 |
| POST | /api/v1/tasks/submit | 提交并执行任务 |
| GET | /api/v1/tasks/{task_id}/status | 获取任务状态 |
| GET | /api/v1/tasks/{task_id}/result | 获取任务结果 |
| GET | /api/v1/tasks/{task_id}/stream | SSE流式进度 |
| POST | /api/v1/tasks/{task_id}/cancel | 取消任务 |

### Agent管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/agents | 列出所有Agent |
| GET | /api/v1/agents/{name} | 获取Agent详情 |
| GET | /api/v1/agents/{name}/tools | 获取Agent工具列表 |
| PUT | /api/v1/agents/{name}/model | 更新Agent模型 |

## MCP工具集成

系统支持通过MCP（Model Context Protocol）集成各种工具：

### 内置工具

- `web_search` - 网页搜索
- `paper_search` - 学术论文搜索
- `code_execute` - 代码执行
- `file_write` - 文件写入
- `latex_compile` - LaTeX编译

### 添加自定义工具

编辑 `config/mcp_config.json`:

```json
{
  "servers": {
    "custom_server": {
      "name": "custom_server",
      "command": "npx",
      "args": ["-y", "@custom/mcp-server"],
      "enabled": true
    }
  },
  "tools": {
    "custom_tool": {
      "name": "custom_tool",
      "server": "custom_server",
      "description": "自定义工具"
    }
  }
}
```

## 模型配置

每个Agent可以使用不同的模型。修改Agent配置：

```bash
curl -X PUT http://localhost:8000/api/v1/agents/solver_agent/model \
  -H "Content-Type: application/json" \
  -d '{"model": "minimax-m2.1"}'
```

## 配置说明

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| MINIMAX_API_KEY | MiniMax API密钥 | - |
| API_BASE_URL | API基础URL | https://api.minimax.chat/v1 |
| DEFAULT_MODEL | 默认模型 | minimax-m2.7 |
| DEBUG | 调试模式 | false |

### CORS配置

在生产环境中，请修改 `CORS_ORIGINS` 为具体的域名列表。

## 开发指南

### 添加新的Agent

1. 继承 `BaseAgent` 类
2. 实现 `execute()` 和 `get_system_prompt()` 方法
3. 使用 `@AgentFactory.register("agent_name")` 注册

```python
from .base import BaseAgent, AgentFactory

@AgentFactory.register("new_agent")
class NewAgent(BaseAgent):
    name = "new_agent"
    description = "新Agent"
    default_model = "minimax-m2.7"

    def get_system_prompt(self) -> str:
        return "你的系统提示词..."

    async def execute(self, task_input, context):
        # 执行逻辑
        return {"result": "..."}
```

### 自定义工作流

```python
custom_workflow = [
    {"agent": "research_agent", "input": {"action": "search"}},
    {"agent": "analyzer_agent", "input": {"action": "analyze"}},
    # 添加更多步骤...
]
```

## 论文结构

生成的论文包含以下章节：

1. 摘要
2. 问题重述
3. 问题分析
4. 模型假设与符号说明
5. 模型建立
6. 模型求解
7. 结果分析
8. 灵敏度分析
9. 模型评价
10. 参考文献

## 注意事项

1. **API Key**: 请确保正确配置MiniMax API Key
2. **LaTeX编译**: 如需编译LaTeX，需安装xelatex
3. **网络问题**: 部分MCP工具需要访问外网
4. **并发限制**: 建议同时运行的任务不超过3个

## License

MIT License

## 版本历史

- **v2.0.0** (2026-04-16) - 多Agent架构重构，支持MCP工具集成
- **v1.0.0** (2026-04-10) - 基础论文生成功能
