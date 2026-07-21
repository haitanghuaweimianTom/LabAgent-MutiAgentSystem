# 前端重构设计文档

## [S1] 问题与目标

### 问题
当前前端是一个单页 SPA，所有功能集中在 467 行的 `page.tsx` 中，通过 `useState` 切换 10 个 tab。存在以下问题：
- 无真实路由，URL 不可分享，浏览器前进后退失效
- 三种样式系统混用（Tailwind v4、CSS Modules、内联样式）
- `apiBase()`、`TEAM_COLORS` 等在 15+ 文件中重复定义
- 组件目录结构不统一（`src/app/components/` 与 `src/components/` 混用）

### 目标
采用渐进式重构，第一步建立三栏布局骨架 + 纯路由迁移，将 10 个 tab 转换为独立路由页面。保留所有现有组件和 API 逻辑，不改动后端。

## [S2] 路由结构

```
src/app/
├── layout.tsx                    # 根布局：三栏结构
├── page.tsx                      # 仪表盘 (/)
├── generate/page.tsx             # 新建任务 (/generate)
├── task/[id]/page.tsx            # 任务执行监控 (/task/[id])
├── task/[id]/report/page.tsx     # 报告查看 (/task/[id]/report)
├── files/page.tsx                # 数据文件管理 (/files)
├── pdf/page.tsx                  # PDF 管理 (/pdf)
├── history/page.tsx              # 任务历史 (/history)
├── agents/page.tsx               # Agent 管理 (/agents)
├── knowledge/page.tsx            # 知识库管理 (/knowledge)
├── memory/page.tsx               # 经验记忆 (/memory)
├── workflows/page.tsx            # 工作流 (/workflows)
├── environment/page.tsx          # 环境管理 (/environment)
└── settings/page.tsx             # 设置中心 (/settings)
```

## [S3] 三栏布局设计

根布局 `layout.tsx` 提供三栏结构：

- **左侧栏** (260px, 可折叠)：系统 Logo + 导航菜单 + 新建项目按钮 + 项目列表 + 底部设置/主题切换
- **主工作区** (flex-1)：`{children}` 渲染当前路由页面
- **右侧面板** (380px, 可折叠)：仅在 `/task/[id]` 等需要详情展示的页面显示

左右栏状态通过 Zustand store 管理（`sidebarCollapsed`、`detailPanelOpen`、`detailPanelContent`）。

## [S4] 共享模块抽取

从现有代码中抽取重复定义：

1. **`lib/api.ts`**：统一 `apiBase()` 函数和通用 fetch 封装
2. **`lib/constants.ts`**：`TEAM_COLORS`、`TEAM_LABELS`、`TEAM_ICONS`、Agent 定义常量
3. **`lib/types.ts`**：共享 TypeScript 类型（Message、AgentInfo、TaskStatus 等）

## [S5] 页面到组件映射

每个路由页面包装现有组件，不改动组件内部逻辑：

| 路由 | 页面组件 | 包装的现有组件 |
|------|---------|--------------|
| `/` | DashboardPage | SystemStatusClient, StatCard |
| `/generate` | GeneratePage | ProblemInput, PreFlightPanel, TemplateSelector |
| `/task/[id]` | TaskDetailPage | TaskDetail, AgentChat, StageProgress, DiscussionPanel, CameraReadyPanel |
| `/task/[id]/report` | ReportPage | PaperPreview, PaperList |
| `/files` | FilesPage | FileManager |
| `/pdf` | PdfPage | (新建，包装 pdf 相关功能) |
| `/history` | HistoryPage | TaskHistory |
| `/agents` | AgentsPage | AgentManager |
| `/knowledge` | KnowledgePage | KnowledgeBaseManager |
| `/memory` | MemoryPage | (新建，包装 memory API) |
| `/workflows` | WorkflowsPage | WorkflowManager |
| `/environment` | EnvironmentPage | EnvironmentManager |
| `/settings` | SettingsPage | SettingsPage (已有), ProviderSettings, McpManager |

## [S6] 状态管理变更

- 现有 `useAppStore` 保持不变（项目/文件/知识库状态）
- 新增 `useLayoutStore`：管理 `sidebarCollapsed`、`detailPanelOpen`、`detailPanelContent`
- `page.tsx` 中的 19 个 `useState` 拆分到各路由页面组件中
- `useTaskState` hook 保持不变，在 `/task/[id]/page.tsx` 中使用

## [S7] 迁移策略

1. **Phase 1**：创建根布局 + 抽取共享模块 + 迁移 dashboard
2. **Phase 2**：迁移 generate、task/[id]、history
3. **Phase 3**：迁移 files、pdf、agents、knowledge
4. **Phase 4**：迁移 memory、workflows、environment、settings
5. **Phase 5**：清理旧 page.tsx，统一样式

每个 Phase 完成后系统可正常运行，不会出现功能缺失。

## [S8] 约束

- 不改动任何后端 API
- 不改动现有组件内部逻辑
- 不删除任何现有功能
- CSS Modules 暂不迁移，后续 Phase 处理
- 保持现有 SSE + 轮询机制不变
