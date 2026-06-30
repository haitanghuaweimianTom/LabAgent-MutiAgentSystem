# RAG 架构 v5.3.0

> v5.3.0 起，RAG 注入从「单 KB」升级为「多 KB + 自动选择 + scope 隔离」。

## 架构总览

```
┌──────────────────────────────────────────────────────────────┐
│  任务提交 (TaskCreateRequest)                                │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  knowledge_base_id?: str        # 旧，向后兼容         │   │
│  │  knowledge_base_ids?: [str]     # v5.3.0: 多 KB        │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  LangGraph Orchestrator                                      │
│  initial_state:                                             │
│    - knowledge_base_id: str                                 │
│    - knowledge_base_ids: [str]    # v5.3.0                   │
│    - project_name: str                                     │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  Agent._inject_knowledge_context() — 多 KB 优先级            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  1. base_ids / self._knowledge_base_ids (显式多选)   │   │
│  │     → km.query_context_for_task(base_ids=...)        │   │
│  │                                                      │   │
│  │  2. base_id / self._knowledge_base_id (旧单 KB)      │   │
│  │     → km.query_context(base_id)                      │   │
│  │                                                      │   │
│  │  3. task_project_name (自动选)                        │   │
│  │     → km.query_context_for_task(base_ids=None)       │   │
│  │     = 项目私有 KB + 全局公共 KB                       │   │
│  │                                                      │   │
│  │  4. 全部 KB (兜底)                                   │   │
│  │     → km.query_all_context()                         │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  KnowledgeManager.query_context_for_task()                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  1. _resolve_task_bases(project_name, base_ids)       │   │
│  │     a. base_ids 非空 → 直接用                          │   │
│  │     b. 自动模式 → 项目私有 + 全局公共                  │   │
│  │     c. 排序：项目私有优先，全局在后                    │   │
│  │                                                      │   │
│  │  2. per_base_chars = max_chars // len(bases)          │   │
│  │                                                      │   │
│  │  3. 对每个 KB 调 query_context(top_k, per_base_chars)│   │
│  │     合并 + 加 header【知识库: <name>】                  │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  KnowledgeBase (向量索引)                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  嵌入模型:                                           │   │
│  │    - paraphrase-multilingual-MiniLM-L12-v2 (默认)    │   │
│  │    - OpenAI text-embedding-3-small/large             │   │
│  │    - TF-IDF (fallback)                               │   │
│  │                                                      │   │
│  │  重排模型 (可选):                                     │   │
│  │    - cross-encoder/ms-marco-MiniLM-L-6-v2            │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

## 多 KB 注入示例

### 场景 1：显式选 2 个 KB
```python
# 前端
selectedKBIds = Set(["kb_global_methods", "kb_proj_literature"])

# 提交时
{
  "knowledge_base_ids": ["kb_global_methods", "kb_proj_literature"]
}

# Agent 注入
kb_context = "【知识库: 全局方法库】... \n---\n 【知识库: 项目文献库 (项目私有)】..."
```

### 场景 2：自动模式（不勾选）
```python
# 项目 my_proj 下有：
#   - kb_global_methods (scope=global)
#   - kb_proj_data     (scope=project, project_name=my_proj)
#   - kb_other_proj    (scope=project, project_name=other_proj)

# 任务在 my_proj 下运行 → 自动选：
#   1. kb_proj_data    (project=my_proj 匹配)
#   2. kb_global_methods (global)
# 不选 kb_other_proj（项目不匹配）
```

## Token 预算控制

多 KB 注入时按 KB 数均分 `max_chars`：

```python
# 假设 3 个 KB + max_chars=4000
per_base_chars = 4000 // 3 = 1333
# 每个 KB 最多返回 1333 字符
# 总共最多 4000 字符（实际略少因为分隔符）
```

可避免单 KB 上下文超 token 预算。

## 错误处理

- KB 查询失败 → 该 KB 被静默跳过，不影响其他 KB
- 单个 KB 无匹配文档 → 仅该 KB 段落为空
- 嵌入模型加载失败 → fallback 到 TF-IDF
- 所有 KB 都没匹配 → 注入空字符串，Agent 不报错

## 嵌入模型下载

启动 KB 之前建议预下载嵌入模型：

```bash
python scripts/download_embedding_model.py
# 下载 paraphrase-multilingual-MiniLM-L12-v2 (~470MB)
# 缓存到 data/models/embedding/
```

下载失败时自动 fallback 到 TF-IDF（无嵌入模型也能跑，只是检索质量差一点）。

## 关键文件

- 后端 KB 管理：`backend/app/core/knowledge_manager.py`
- 后端路由：`backend/app/routers/knowledge.py`
- Agent 注入：`backend/app/agents/base.py:_inject_knowledge_context`
- Orchestrator：`backend/app/agents/langgraph_orchestrator.py`
- 前端：KnowledgeBaseManager.tsx + ProblemInput.tsx + useAppStore.ts

## 测试

- `tests/test_kb_scope.py`（22 用例）
- `tests/test_multi_kb.py`（11 用例）
- `tests/test_knowledge_manager.py`（现有测试仍全过）