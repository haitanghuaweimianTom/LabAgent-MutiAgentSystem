# 知识库两级 Scope v5.3.0

> v5.3.0 起，知识库支持两级 scope：**全局公共**（global）+ **项目私有**（project），任务可同时关联多个 KB。

## 概念

| Scope | 可见性 | 物理路径 | 用途 |
|-------|--------|---------|------|
| `global` | 所有项目可用 | `data/knowledge_bases/global/<kb_id>.json` | 通用领域知识（数学建模方法、CCF-A 写作模板） |
| `project` | 仅指定项目可用 | `data/knowledge_bases/projects/<project_name>/<kb_id>.json` | 项目专属文献/数据 |

> 旧 KB（无 scope 字段）默认 `global`，向后兼容。

## 自动注入优先级

任务提交时不勾选 KB 时，Agent 会自动选择：

1. 项目私有 KB（project_name = 当前任务所在项目）
2. 全局公共 KB
3. 合并注入上下文（项目私有优先，按 KB 数均分 max_chars）

## 数据模型

```python
class KnowledgeBaseConfig(BaseModel):
    id: str
    name: str
    description: str = ""
    # ... items / chunkSize / 嵌入模型 / 重排模型 ...
    # v5.3.0:
    scope: Literal["global", "project"] = "global"
    project_name: Optional[str] = None  # scope="project" 时必填
```

## REST API

### 列出 KB（支持 scope 过滤）
```
GET /api/v1/knowledge/bases
  ?scope=global|project&project_name=<name>&include_task=false
```

### 创建 KB
```
POST /api/v1/knowledge/bases
{
  "name": "我的全局 KB",
  "description": "...",
  "scope": "global",            // 或 "project"
  "project_name": "work_2026_xxx"  // scope=project 时必填
}
```

### 多 KB 注入（任务级）
```
POST /api/v1/knowledge/query-context-for-task
{
  "query": "用户的研究问题",
  "base_ids": ["kb_abc", "kb_def"],  // 可选；不传则自动选
  "project_name": "work_2026_xxx",
  "top_k": 3,
  "max_chars": 4000
}
→ {
    "context": "【知识库: ...】...",
    "used_bases": [{ "id": "...", "scope": "global|project", ... }]
  }
```

## Python API

```python
from app.core.knowledge_manager import get_knowledge_manager

km = get_knowledge_manager()

# 创建
g = km.create_base(name="全局 KB", scope="global")
p = km.create_base(name="项目 KB", scope="project", project_name="my_proj")

# 列出
km.list_bases(scope="global")                            # 仅全局
km.list_bases(scope="project", project_name="my_proj")   # 仅 my_proj 项目私有
km.list_bases()                                          # 全部

# 任务级注入
context = km.query_context_for_task(
    task_project_name="my_proj",
    base_ids=None,  # None = 自动选
    query="研究问题",
    top_k=3,
    max_chars=4000,
)
```

## 关键文件

- 后端：`backend/app/core/knowledge_manager.py`、`backend/app/routers/knowledge.py`
- 前端：`frontend/src/app/components/KnowledgeBaseManager.tsx`、`frontend/src/app/components/ProblemInput.tsx`
- 状态：`frontend/src/app/store/useAppStore.ts`（`selectedKBIds`、`toggleKBSelection`）

## 测试

- `tests/test_kb_scope.py`（22 用例）
- `tests/test_multi_kb.py`（11 用例）