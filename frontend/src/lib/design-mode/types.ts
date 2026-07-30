// 全局可视化设计模式 —— 类型定义
//
// 运行时覆盖（resize width/height + reorder order 数组），持久化到 localStorage，
// 用户点"保存"后落盘 .design-overrides.json 交接给 Claude 写回源码。
// 字体大小绝不改变：所有 SizeOverride 只写 width/height，不碰 fontSize。

export type DesignMode = 'edit' | 'view';

/** 单个元素的尺寸覆盖（原生 px）。undefined 表示该轴不覆盖。 */
export interface SizeOverride {
  width?: number;
  height?: number;
}

/** 一组 reorderable 兄弟节点（同一 flex 父容器）的顺序。 */
export interface GroupOrder {
  order: string[]; // data-design-id 数组，按视觉顺序排列
}

/** 落盘交接物（localStorage 同结构）。 */
export interface PersistedDesign {
  entries: Record<string, SizeOverride>; // key = data-design-id
  groups: Record<string, GroupOrder>; // key = 父 data-design-id
  savedAt: number | null;
}

/** 可编辑元素的运行时描述符（只存引用，不存 rect——rect 按需算）。 */
export interface EditableElement {
  id: string;
  el: HTMLElement;
  groupId: string | null; // 若父 flex 容器打了 data-design-id，则是其 id（用于 reorder）
}
