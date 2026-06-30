# 数据文件管理 v5.3.0

> v5.3.0 起，📁 数据文件管理从单层扁平列表重构为三 Tab 结构：**用户上传** / **系统自收集** / **知识库**。

## 三 Tab 结构

| Tab | 物理位置 | 数据来源 | 元数据 |
|-----|---------|---------|--------|
| 📤 用户上传 | `outputs/<project>/data/user_uploads/` | 用户手动上传 | 可选 shape/insights（自动分析） |
| 🌐 系统自收集 | `outputs/<project>/data/self_collected/` | Agent 任务期间下载 | URL / 来源 query / 下载时间 / 错误信息 |
| 📚 知识库 | `data/knowledge_bases/...` | 文档 + 向量索引 | 嵌入模型 / 重排模型 / scope / project_name |

> 向后兼容：旧文件位于 `outputs/<project>/data/` 根下时，启动时由 `migrate_legacy_data_dir()` 一次性迁移到 `user_uploads/` 子目录。

## REST API

### 上传文件
```
POST /api/v1/data/upload
  ?project_name=<name>&source=user_upload|self_collected
  multipart: file=<binary>
```

### 列出文件
```
GET /api/v1/data/files
  ?project_name=<name>&source=user_upload|self_collected|both
```

### 自收集文件 + 元数据
```
GET /api/v1/data/self-collected?project_name=<name>
→ { files: [...], index: [...], total: int }
```

### 手动触发自收集下载
```
POST /api/v1/data/self-collect/trigger
  ?project_name=<name>&concurrency=4&max_size_mb=50
  body: { "urls": ["..."], "query": "..." }
```

### 删除文件
```
DELETE /api/v1/data/files/{filename}
  ?project_name=<name>&source=user_upload|self_collected
```

### 分析文件
```
GET /api/v1/data/analyze
  ?dataset_name=<name>&project_name=<name>&source=user_upload|self_collected
```

## 目录迁移

启动时 `app.main.lifespan` 自动调用 `migrate_legacy_data_dir()`：

- 扫描所有 `outputs/<project>/data/` 目录（跳过 `_global`）
- 若有文件/未知子目录在根下 → 移动到 `user_uploads/` 子目录
- 写 `.migrated_v530` 标记文件（幂等）
- 失败的文件跳过（不覆盖已有同名文件）

```python
from app.core.paths import migrate_legacy_data_dir
stats = migrate_legacy_data_dir()
# {"projects_scanned": int, "files_moved": int, "skipped": int}
```

## 系统自收集（self_collector）

v5.3.0 起，`self_collect_data` 从「只记录 URL」升级为实际下载：

### 实现
- `app/services/self_collector.py` — httpx 异步并发下载（Semaphore 控制并发）
- Content-Type 白名单：`text/csv`、`application/json`、`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`、`text/plain` 等
- 拒绝列表：`text/html`、`application/xhtml+xml`（避免下载概览页）
- 大小限制：`max_size_mb=50`（默认）
- SHA1 短哈希命名（去重 + 隐藏 URL）
- 元数据写 `self_collected/_index.json`（含 url、source_query、http_status、error 等）
- 失败回退：httpx 未装时自动用 urllib（同步）

### 触发方式
1. **任务自动**：任务提交时 `data_source="self_collect"` → preflight 调用 `self_collect_data`
2. **手动测试**：`POST /data/self-collect/trigger` 传 urls 列表

## 关键文件

- 后端路径：`backend/app/core/paths.py`、`backend/app/services/data_directory.py`、`backend/app/services/self_collector.py`
- 后端路由：`backend/app/routers/data.py`
- 前端组件：`frontend/src/app/components/FileManager.tsx`、`FileManager.module.css`

## 测试

- `tests/test_paths_migration.py`（6 用例）
- `tests/test_data_router_source.py`（10 用例）
- `tests/test_self_collector.py`（16 用例）