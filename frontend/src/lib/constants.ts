export const TEAM_COLORS: Record<string, string> = {
  coordinator: '#3B82F6',
  research_agent: '#6366F1',
  data_agent: '#10B981',
  analyzer_agent: '#F59E0B',
  modeler_agent: '#EC4899',
  algorithm_engineer_agent: '#8B5CF6',
  financial_analyst_agent: '#14B8A6',
  solver_agent: '#EF4444',
  writer_agent: '#06B6D4',
  peer_review_agent: '#F97316',
  experimentation_agent: '#A855F7',
  figure_agent: '#22D3EE',
  requirement_decomposer: '#84CC16',
  innovation_agent: '#E879F9',
  summary_agent: '#FB923C',
};

export const TEAM_LABELS: Record<string, string> = {
  coordinator: '协调者',
  research_agent: '研究员',
  data_agent: '数据分析师',
  analyzer_agent: '分析师',
  modeler_agent: '建模师',
  algorithm_engineer_agent: '算法工程师',
  financial_analyst_agent: '金融分析师',
  solver_agent: '求解器',
  writer_agent: '写作专家',
  peer_review_agent: '审稿人',
  experimentation_agent: '实验设计专家',
  figure_agent: '科研绘图师',
  requirement_decomposer: '需求分解器',
  innovation_agent: '创新发现专家',
  summary_agent: '总结专家',
  system: '系统',
  user: '你',
};

export const TEAM_ICONS: Record<string, string> = {
  coordinator: 'Users',
  research_agent: 'Search',
  data_agent: 'Database',
  analyzer_agent: 'BarChart3',
  modeler_agent: 'Box',
  algorithm_engineer_agent: 'Code2',
  financial_analyst_agent: 'TrendingUp',
  solver_agent: 'Cpu',
  writer_agent: 'PenTool',
  peer_review_agent: 'CheckCircle2',
  experimentation_agent: 'FlaskConical',
  figure_agent: 'Palette',
  requirement_decomposer: 'ListTodo',
  innovation_agent: 'Lightbulb',
  summary_agent: 'FileText',
};

export const TAB_META: Record<string, { title: string; subtitle: string }> = {
  dashboard: { title: '仪表盘', subtitle: '系统状态与快速开始' },
  generate: { title: '任务执行', subtitle: '实时监控 Agent 协作' },
  files: { title: '文件管理', subtitle: '数据文件与知识库' },
  pdf: { title: 'PDF 管理', subtitle: '论文解析与下载' },
  history: { title: '历史任务', subtitle: '任务记录与回溯' },
  agents: { title: 'Agent 管理', subtitle: '团队配置与模型路由' },
  workflows: { title: '工作流', subtitle: 'LangGraph 编排配置' },
  memory: { title: '记忆系统', subtitle: '经验教训与任务记忆' },
  environment: { title: '环境管理', subtitle: 'Conda / Venv 管理' },
  settings: { title: '系统设置', subtitle: 'Provider / MCP / 知识库' },
};

/**
 * LangGraph 节点名（current_step / phase 字段）→ 中文显示名映射。
 * 覆盖全部 40 个图节点（含 v8.4 新增 17 个质检/增强节点）。
 * 后端 current_step 可能是英文节点名，也可能是中文文案（如"数据质量门禁校验中"）；
 * 前端用 nodeLabel() 统一翻译，找不到则 fallback 原值。
 */
export const NODE_LABELS: Record<string, string> = {
  // 原有 23 节点
  requirement_decomposition: '需求分解',
  preflight_decision: '预检决策',
  analyzer: '问题分析',
  research_vote: '研究决策投票',
  parallel_analysis: '并行分析',
  discuss_approach: '方案讨论',
  modeler: '数学建模',
  algorithm_engineer: '算法设计',
  financial_analyst: '金融建模',
  iterative_solver: '算法求解',
  writer: '论文写作',
  peer_review: '同行评议',
  experiment: '实验设计',
  figure: '科研绘图',
  fact_check: '事实核查',
  compliance_check: '合规审查',
  summary: '总结归档',
  cannot_solve: '无法求解',
  self_collect: '数据自采',
  wait_user: '等待用户',
  coder_agent_node: '代码生成',
  ast_audit_node: 'AST 审计',
  sandbox_execution_node: '沙箱执行',
  reviewer_reflection_node: '审稿反思',
  // v8.4 新增 17 节点
  requirement_validation: '需求校验',
  data_quality_check: '数据质量检查',
  literature_dedup: '文献去重',
  novelty_check: '创新性核查',
  method_feasibility: '方法可行性评估',
  context_compression_node: '上下文压缩',
  code_style_check: '代码风格检查',
  reproducibility_check: '可复现性审查',
  formula_validity_check: '公式有效性校验',
  table_consistency_check: '表格一致性校验',
  figure_caption_check: '图表说明校验',
  citation_density_check: '引用密度校验',
  reference_completeness: '参考文献完整性',
  terminology_consistency: '术语一致性校验',
  structure_coherence_check: '章节连贯性校验',
  abstract_quality_check: '摘要质量校验',
  final_polish: '终稿润色',
};

/**
 * 把后端传来的 current_step/phase 翻译成中文显示名。
 * 先查 NODE_LABELS；命中则返回中文节点名；未命中则原样返回
 *（后端有时直接传中文文案如"数据质量门禁校验中"，此时原样显示即可）。
 */
export function nodeLabel(step: string | undefined | null): string {
  if (!step) return '';
  return NODE_LABELS[step] ?? step;
}
