# 前端重构需求提示词（治"逼仄"+按钮高瘦，按钮必须横向宽纵向短）

把这段直接喂给 AI，让它改 `frontend/src/app/components/*.tsx` 和 `frontend/src/app/globals.css`。

---

## 角色
你是资深前端 UI 工程师，精通 Tailwind CSS v4 + shadcn 设计令牌。任务：把一套 Next.js 14 应用的视觉从"逼仄紧凑"改到"宽松通透"，参照 Ant Design / Element Plus 的留白与层次感，但**保留近黑单色主色、不引入蓝色/彩色**。

## ⚠️ 最高优先级铁律：按钮必须"横向宽、纵向短"
之前几轮改错的根因就是搞反了——做出一堆"高瘦"按钮（纵向比横向大）。**绝对禁止高瘦按钮**。
- 按钮 padding 必须 **横向(px) ≥ 纵向(py) × 2**。
- 正确示例：`py-1.5 px-6`（纵6 横24）、`py-2 px-7`（纵8 横28）、`py-2.5 px-8`（纵10 横32）。
- **错误示例（一律禁止）**：`py-3 px-5`（纵12 横20，纵向偏大=高瘦）、`py-3 px-4`（纵向>横向）、任何 `py > px` 的组合。
- 横向 px 越大越好，字离按钮左右边框 ≥ 24px。
- 纵向 py 压到 `1.5`~`2.5`，配合 `min-h-[34px]`~`min-h-[40px]`，让按钮"扁而宽"。
- **不要参照 Agent 管理页做整体风格**（那页只是间隔尚可，风格不作为全局范本）。按钮比例规则按上面铁律走。

## 背景：当前痛点（用户原话）
1. "还是很贴"——按钮之间贴太近、按钮边框和字贴太近。
2. "只增大纵向不增大横向"——横向 padding 没跟上，改成了高瘦。
3. "按钮宽大长短，要横向宽纵向短，且不能贴字"——按钮要横向宽、纵向扁，文字离边框远。
4. "始终都是纵向比横向宽，废物"——前几轮反复把按钮做高瘦，必须根治。
5. "+新建 和 请选择知识库 贴太近"——分属左右两栏 header，中间只一条 border-r，没真正空开。
6. "左侧栏空白处减少（收窄，横向变窄即可），右边就有很多空间了"。
7. "框里内容不要贴框，框之间留一些空隙"。

## 硬性规则（必须全部遵守）

### 1. 按钮：横向宽、纵向短，字不贴边（铁律，见上）
- **改共享常量优先**：`KnowledgeBaseManager.tsx` 的 `actionBtnBase`/`modalInputBase`、`ProviderSettings.tsx` 的 `btnBase`/`btnSm`、`EnvironmentManager.tsx` 的 `fieldStyle`/`primaryBtnStyle`——**改常量本身，别去几十个引用处逐个改**。
- 改完每个常量，自查：横向 px 是否 ≥ 纵向 py × 2？不满足就重改。

### 2. 按钮之间：间距加大
- 按钮组容器 `gap-3`（12px）起步，按钮多的用 `gap-4`（16px）。
- 全局禁用 `gap-1`/`gap-1.5`/`gap-2`。

### 3. 知识库两栏（`KnowledgeBaseManager.tsx`）必须真正拉开
- 左栏 header `pr-7`/`pr-8`（让"+新建"离中线远）。
- 右栏 header **`pl-8`/`pl-10`**（让"请选择知识库"离中线远）。
- 左 scope 行 `pr-7`，右 Files tab 行 `pl-8`。
- 验收："+新建"和"请选择知识库"中间有**明显空隙**，不是只隔一条线。

### 4. 左侧栏（`Sidebar.tsx`）收窄
- 展开宽度 `240px`（收窄，让空间给右边）。
- 导航项 `text-[15px]`、`px-3.5 py-2.5`、`mb-1`、图标 `w-[18px]`。
- 新建任务按钮 `h-11`，主题/收起按钮 `py-2.5 text-sm rounded-lg`。

### 5. 卡片/框
- 卡片 `bg-card border border-border rounded-xl shadow-sm`，padding `p-5` 起（主容器 `p-6`）。
- 内嵌区块 `bg-muted rounded-md`，`p-3` 起。
- 内容离边框 ≥ 20px。

### 6. 全局布局（`client-layout.tsx` + `globals.css`）
- `<main>` 内容容器：`max-w-[1200px] mx-auto px-6 py-10 md:px-10`。
- 各 page.tsx 外层**不要**再写 `p-4`/`p-6`（padding 统一由全局管，避免叠加臃肿）。
- `globals.css`：`body{font-size:15px;line-height:1.6}`、`--radius:0.75rem`、`--shadow-card:0 1px 3px rgba(0,0,0,0.04),0 1px 2px rgba(0,0,0,0.06)`。
- `.btn-gradient`：`inline-flex items-center justify-center min-h-[40px] padding:10px 20px`（注意 10px 纵 / 20px 横，横向 2 倍，符合铁律）。

### 7. 环境管理页（`EnvironmentManager.tsx`）特殊：不改

## 防跑偏三条
1. **只动 class，不动逻辑**：禁止改 useState/useEffect/props/接口/条件渲染；禁止内联 className 重构成 CSS 模块。
2. **改共享常量优先于改单点**。
3. **任意值用方括号**：`w-[288px]`、`min-h-[34px]`，不要写 `style={{}}`（环境管理页除外）。

## 验收清单
- [ ] **所有按钮横向(px) ≥ 纵向(py) × 2，无高瘦按钮**（最关键）
- [ ] 按钮字离左右边 ≥ 24px
- [ ] 按钮之间 gap-3 起
- [ ] 知识库"+新建"和"请选择知识库"中间有明显空隙
- [ ] 左侧栏 240px，导航项字大、按钮大
- [ ] 卡片内容不贴框，有阴影层次
- [ ] 内容居中 max-w-1200，左右不贴屏幕边
- [ ] 环境管理页未改动

## 关键文件清单
- 全局令牌：`frontend/src/app/globals.css`
- 全局容器：`frontend/src/app/client-layout.tsx`
- 侧栏：`frontend/src/components/layout/Sidebar.tsx`
- 知识库：`frontend/src/app/components/KnowledgeBaseManager.tsx`（actionBtnBase 在 564 行）
- 系统设置壳：`frontend/src/app/components/SettingsPage.tsx`
- Provider 管理：`frontend/src/app/components/ProviderSettings.tsx`（btnBase 在 359 行）
- PDF 管理：`frontend/src/app/components/PdfManager.tsx`
- 文件管理：`frontend/src/app/components/FileManager.tsx`
- 记忆系统：`frontend/src/app/components/MemoryManager.tsx`
- 环境管理（不改）：`frontend/src/app/components/EnvironmentManager.tsx`

改完列出每个文件改了哪些 class，方便回滚。
