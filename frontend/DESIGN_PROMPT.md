# 全局可视化设计模式（拖拽改大小 + 行内重排 + 保存定死）

## Context（为什么做这个）

用户反复要我"扩大按钮横向""内容别贴边框"，我在代码里替目测比例始终调不准——根因之一是**目标元素若是 `flex-1`/`h-full`，设 inline width 会被 flex 覆盖，resize 根本不生效**，所以"怎么调都不对"。

用户的诉求转换为实现目标：

1. **改大小**：拖元素角/边改宽高，**字体大小绝对不变**（只写 `style.width/height`，从不碰 `fontSize`）。
2. **位置 = 行内重排**（用户已确认）：拖元素在所在 flex 行/列内重排顺序，保留响应式，任何屏宽不错位。不做 Figma 式绝对定位自由拖（会锁死屏宽）。
3. **保存 → 定死**：用户拖好点"保存"，设计定死。保存按钮不直接改源码，而是**落盘到一个 gitignored 文件**，用户告知后由 Claude 读盘 → Edit 源码 → 清盘 → 提交。用户全程不碰 JSON。
4. **排除左侧栏**：侧栏/顶栏/详情面板不挂手柄；其他"有文字的"元素（按钮/卡片框/tab 如「📚 知识库」/输入框）可拖。

## 技术事实（已验证）

- **无任何拖拽库**（react-rnd/@dnd-kit/react-resizable/sortablejs 都没装）；已装 `framer-motion ^12`、`zustand ^4`。Next 14.1 / React 18 / Tailwind v4（原生支持任意值 `w-[NNNpx]`）。
- 布局三段式（[client-layout.tsx](frontend/src/app/client-layout.tsx) L44）：`<div flex h-screen overflow-hidden>` → Sidebar + [TopBar + main(motion.div 仅 opacity 动画无 transform)] + DetailPanel。**overlay 必须 portal 到 document.body、z-[60]**（挂 main 内会随 route 卸载）。
- 30 个业务组件全手搓内联 className，**几乎不用** [components/ui](frontend/src/components/ui/) 基元，**零 data-* 属性**。打标只能靠给元素加 `data-design-id`。
- zustand 现有 pattern：[useAppStore.ts](frontend/src/app/store/useAppStore.ts) `create()(persist(...))` + localStorage `app-store`。新 store 照此。
- [layout.tsx](frontend/src/app/layout.tsx) 是 Server Component，Provider 必须加在 `client-layout.tsx`（`'use client'`）内。
- Sidebar 4 个顶级节点要排除：汉堡 [Sidebar.tsx:172](frontend/src/components/layout/Sidebar.tsx#L172)、移动遮罩 L182、桌面 motion.aside L193、移动 motion.aside L204。TopBar header、DetailPanel [DetailPanel.tsx:15](frontend/src/app/components/DetailPanel.tsx#L15) motion.aside 同理。
- TopBar 右侧按钮组 [TopBar.tsx:132](frontend/src/components/layout/TopBar.tsx#L132)，theme toggle 在 L188，设计开关挂 L188 后。

## 核心方案

### A. 自实现拖拽（~280 行），不引库

react-rnd 是绝对定位库（管 x/y），与"行内重排+保留响应式"直接冲突；@dnd-kit 靠移动 DOM/transform 重排，与"持久化为 order 数组 + 写回源码顺序"模型不匹配。两套机制（resize=改 inline w/h；reorder=改 flex 父内 CSS order）逻辑量小，体积 0。

### B. Resize 算法（无锚点重定位）

元素在 flow 内，从任意边/角拖只需设 width/height，无需平移（左/上边拖时起始边由 flow 决定），8 个 handle 统一成纯 w/h 计算：

```ts
const start = el.getBoundingClientRect(); const px=e.clientX, py=e.clientY;
move: dx=ev.clientX-px, dy=ev.clientY-py;
  w = start.width  + (h.includes('e')?dx : h.includes('w')?-dx:0)
  hgt= start.height + (h.includes('s')?dy : h.includes('n')?-dy:0)
  el.style.width=clamp(w)+'px'; el.style.height=clamp(hgt)+'px';  // live
up:  store.setSize(id, {width:w, height:hgt})  // 提交
```
拖拽期间全局 `pointer-events:none`（除手柄）。**只写 w/h，绝不碰 fontSize**。

### C. Reorder 算法（行内重排，CSS order，父 flex 容器）

父容器也打 `data-design-id`（作为 groupId），reorderable 子节点各打 `data-design-id`。拖动时实时设 `style.order`，pointerup 持久化 order 数组。保存 = 画插入提示线 + 持久化。

### D. 手柄布局（纠正"中心拖动=重排"的手势冲突）

- 角/边 8 个 resize handle。
- **独立 move handle**：选中后顶部中央冒 grip 图标，只它负责 reorder。元素本体 click=仅选中（避免误触业务按钮）。
- 选中环 = overlay 壳 border，**不动 target 的 box-shadow**（避开与 `shadow-card` 冲突）也**不碰 :focus-visible outline**。target 唯一改动就是 w/h/order。

### E. 元素 id 稳定性 → data-design-id 打标（源码作用域）

拒绝"文本签名自动发现"作持久化路径（文本随数据变、nth 随增删变，写不回源码，且动态列表行 `.map` 渲染的 id 天生不稳）。改为 `data-design-id="<route>:<语义名>"`，如 `pdf:card`、`pdf:btn-upload`、`pdf:btn-download`、`kb:tab-scope`、`kb:btn-new`。可编辑集合 = `querySelectorAll('[data-design-id]')` 排除 `closest('[data-design-exclude]')`。

未打标元素 hover 仅灰显 + tooltip"未标记"。**"所有有文字的"渐进达到**：先 PDF 试点跑通全链路，再用 Workflow 给高频组件批量打标（见 commit C7）。

### F. 性能（永不全量渲染手柄/不算 rect）

1. 只渲染**选中 + hover**元素的手柄（最多 1-2 个），不预渲染。
2. hover 命中用 `document.elementsFromPoint(x,y)` 取栈，向上找首个带 `data-design-id` 且不在 exclude 子树内的祖先。只算这 1 个 rect。
3. scroll/resize/侧栏 reflow 触发只重算"当前选中+hover"的 rect（2 个 getBoundingClientRect，微秒级），rAF 合并。
4. ResizeObserver observe `main` + 当前 selected 目标（侧栏 56↔200、DetailPanel 0↔380 reflow 触发重算）。
5. 手柄 `position:fixed`，坐标直接用 `getBoundingClientRect()`（已含滚动偏移，无需 +scrollY）。

### G. 持久化与写回源码

**localStorage**（照 useAppStore persist 模式，name=`design-overrides`）：
```ts
interface PersistedDesign {
  entries: Record<string, { width?: number; height?: number }>  // key=data-design-id
  groups:  Record<string, { order: string[] }>                   // key=父 data-design-id
  savedAt: number | null
}
```
store actions：`setMode/toggleMode/setSize/setGroupOrder/select/removeEntry/clearAll/markSaved/exportJSON`。

**保存按钮（落盘交接，非写源码）**：新增 [frontend/src/app/api/design/route.ts](frontend/src/app/api/design/route.ts)（Next route handler），POST 落盘到 `frontend/.design-overrides.json`（加入 .gitignore）。TopBar"💾 保存"按钮调它。用户点保存 → 落盘 → 告知 Claude"保存好了" → Claude 读盘 → Edit 源码 → 清盘 → 提交。

**写回可行性（诚实）**：
| 能力 | 运行时持久化 | 写回源码 |
|---|---|---|
| resize w/h px | localStorage 可靠 | 多数干净（className 加 `w-[NNNpx]`/`h-[NNNpx]`/`min-h-[NNNpx]`）；`flex-1`/`h-full` 元素**不可** resize（会被覆盖）→ 打标时优先选本征尺寸元素（button/input/select/tab），卡片只动 min-h |
| reorder | localStorage 可靠 | 推荐改源码顺序/数组字面量（不用 order-N class，脆弱且伤 a11y）；动态列表行重排改源码数组 |

## 文件清单

### 新增（全部在 `frontend/src/lib/design-mode/`）
1. `types.ts` — `DesignMode`/`SizeOverride`/`PersistedDesign`。
2. `store.ts` — zustand store，persist `design-overrides`。
3. `applyOverrides.ts` — `applyAll()`/`findEl(id)`/reapply（route 变化时调）。
4. `useEditableElements.ts` — hook：扫描 `[data-design-id]`、维护 hovered/selected、`elementsFromPoint` 命中。
5. `DesignOverlay.tsx` — portal 到 body、手柄渲染、resize/reorder pointer 逻辑、ResizeObserver/scroll/rAF。
6. `DesignModeProvider.tsx` — `'use client'`，包 children，挂 overlay，`usePathname` route 变化后 `setTimeout(rebuild,200)`（等 exit+mount）重建描述符列表 + 重放 overrides。

### 改动
7. [client-layout.tsx](frontend/src/app/client-layout.tsx) — L43 return 外包 `<DesignModeProvider>`（包住整个 `<div flex h-screen>`）。
8. [TopBar.tsx](frontend/src/components/layout/TopBar.tsx) — L188 后加"✏️ 设计模式"开关 + "💾 保存"按钮，接 store；`hidden md:inline-flex`（桌面端工具）。
9. [Sidebar.tsx](frontend/src/components/layout/Sidebar.tsx) — L172/L182/L193/L204 加 `data-design-exclude="sidebar"`。
10. [DetailPanel.tsx](frontend/src/app/components/DetailPanel.tsx) — L15 motion.aside 加 `data-design-exclude="detail"`。
11. [PdfManager.tsx](frontend/src/app/components/PdfManager.tsx) — **试点打标**：L166 `pdf:card`、L181 `pdf:btn-upload`、L191 `pdf:btn-download`、L201 `pdf:select-strategy`、L252 `pdf:btn-parse`、L172 行 `pdf:row-upload`（reorder 父组，可选）。
12. [api/design/route.ts](frontend/src/app/api/design/route.ts) — Next route handler，POST/GET `.design-overrides.json`。
13. `.gitignore` — 加 `frontend/.design-overrides.json`。

## commit 顺序（低风险先，基础设施→打标）

- **C1 基础设施**：`types.ts` + `store.ts`（纯逻辑，无 UI/wiring）。
- **C2 Provider 骨架 + 开关**：`DesignModeProvider`（挂空 overlay）+ `DesignOverlay`（portal 空 div 读 mode）+ 改 `client-layout.tsx`（包 Provider）+ 改 `TopBar.tsx`（开关）。验证：开关能切 mode，overlay 挂载但不画手柄。
- **C3 排除标记**：`Sidebar`/`DetailPanel`/`TopBar header` 加 `data-design-exclude`（纯属性，零行为风险）。
- **C4 Resize 完整**：`useEditableElements` + overlay resize 手柄 + `applyOverrides` w/h 重放 + 手柄样式。验证：对打标元素拖角改宽高，刷新保持。
- **C5 Reorder**：overlay move handle + order 算法 + applyOverrides order 重放。
- **C6 试点打标 + 保存落盘**：`PdfManager` 打 `data-design-id`；`api/design/route.ts` 落盘；TopBar"💾 保存"接落盘。端到端跑通 /pdf。
- **C7 增量（Workflow 并行）**：给高频组件批量打标（KnowledgeBaseManager、FileManager、MemoryManager、ProviderSettings 等），每个组件就几处（卡片根+主操作按钮+tab 组）。

## 边界情况

1. framer-motion route 切换：overlay 是 motion.div 兄弟（portal 到 body），无 transform 冲突；route 变化后 `setTimeout(rebuild,200)`（等 AnimatePresence exit 0.15s + mount）重建列表 + 重放；过渡期间禁用拖拽。
2. Sidebar 收起/展开 reflow（56↔200，0.2s）：ResizeObserver observe main → rAF 重算选中/hover rect（只算 2 个）。
3. 滚动容器 main overflow-y-auto：手柄 fixed + getBoundingClientRect 直接用（含滚动偏移），scroll→rAF 重算，无需 +scrollY。
4. backdrop-blur 裁剪：手柄一律 portal 到 body、fixed、z-[60]，绝不挂元素内部，不被 overflow:hidden/stacking context 裁剪。
5. 移动端 Sidebar translateX（L204 x:-280→0）：已 exclude；设计开关 `hidden md:inline-flex`，移动端不进 edit 模式。
6. Tailwind v4 px：拖出原生 px（如 183px），`w-[183px]` 任意值接受任意整数，存整数 px，不吸附 spacing scale（会扭曲意图）。
7. z-index：overlay z-[60] 高于现有 z-50（TopBar 搜索/通知/移动侧栏）；overlay 根 `pointer-events:none`，只有手柄壳 `auto`，不挡 TopBar 开关。

## 硬约束

- 不绑定本机：无 localhost/Windows cmd/个人路径。`.design-overrides.json` 是临时交接物，gitignored，写回源码后即清。
- 保留所有现有功能逻辑（输入/删除/tab/SSE），只加可视化设计层。
- 字体大小绝不改。

## 验证（端到端）

1. 启动：`cd frontend && PORT=3002 npm run dev`，开 `http://localhost:3002/pdf`。
2. 进 edit：点 TopBar"✏️ 设计模式"。确认侧栏/顶栏/详情面板**无手柄**（exclude 生效），PdfManager 卡片角出现 resize handle、顶部出现 move grip。
3. 测 resize：拖 `pdf:btn-upload` 右下角往右拉，按钮变宽、字体不变（devtools 查 `font-size` 未变）；松手 style.width 写入；点别处再选中，手柄贴新位置。
4. 测 reorder：选中行内某按钮拖 move grip 越过相邻按钮中点，见插入提示线 + 实时换位；松手顺序保持。
5. 测保存：点"💾 保存"→ 落盘 `frontend/.design-overrides.json`；DevTools Application → Local Storage `design-overrides` 有值。
6. 测持久化：F5 刷新，仍 view 模式但 overrides 已重放（宽/顺序保持）；开 design 模式手柄贴在已保存尺寸/位置。
7. 测退出：关设计开关→手柄消失，元素保留已保存 inline 尺寸/order（override 持续生效直到源码写回）；"清除该元素覆盖"（removeEntry）可还原。
8. 测边界：切 route（/pdf→/files→/pdf），0.15s 过渡后手柄在新页面元素上（无残留旧手柄）；收起 Sidebar/开 DetailPanel 手柄随 reflow 贴位。
9. 写回演练：用户告知"保存好了"→ Claude 读 `.design-overrides.json` → 按 `w-[NNNpx]`/数组重排规则 Edit `PdfManager.tsx` → 清 `.design-overrides.json` → 刷新确认源码即真相（尺寸/顺序仍对）。
