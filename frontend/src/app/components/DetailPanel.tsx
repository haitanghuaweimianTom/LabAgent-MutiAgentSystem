'use client'

import { motion, AnimatePresence } from 'framer-motion'
import { X, Bot, FileText } from 'lucide-react'
import { useLayoutStore } from '@/app/store/useLayoutStore'
import { TEAM_COLORS, TEAM_LABELS } from '@/lib/constants'
import { cn } from '@/lib/utils'

export default function DetailPanel() {
  const { detailPanelOpen, detailPanelContent, closeDetailPanel } = useLayoutStore()

  return (
    <AnimatePresence>
      {detailPanelOpen && detailPanelContent && (
        <motion.aside
          initial={{ width: 0, opacity: 0 }}
          animate={{ width: 380, opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={{ duration: 0.2, ease: 'easeInOut' }}
          className="h-screen border-l border-border bg-slate-900/50 backdrop-blur-xl overflow-hidden flex flex-col"
        >
          {/* Header */}
          <div className="h-14 flex items-center justify-between px-4 border-b border-border shrink-0">
            <div className="flex items-center gap-2">
              {detailPanelContent.type === 'agent' ? (
                <Bot className="w-4 h-4 text-primary" />
              ) : (
                <FileText className="w-4 h-4 text-primary" />
              )}
              <span className="text-sm font-semibold text-foreground">
                {detailPanelContent.type === 'agent'
                  ? TEAM_LABELS[detailPanelContent.agentName || ''] || detailPanelContent.agentName
                  : '任务详情'}
              </span>
            </div>
            <button
              onClick={closeDetailPanel}
              className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-4">
            {detailPanelContent.type === 'agent' && detailPanelContent.agentName && (
              <AgentDetail agentName={detailPanelContent.agentName} />
            )}
            {detailPanelContent.type === 'task' && detailPanelContent.taskId && (
              <TaskDetail taskId={detailPanelContent.taskId} />
            )}
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  )
}

function AgentDetail({ agentName }: { agentName: string }) {
  const color = TEAM_COLORS[agentName] || '#666'
  const label = TEAM_LABELS[agentName] || agentName

  return (
    <div className="space-y-4">
      {/* Agent avatar */}
      <div className="flex items-center gap-3">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center text-white text-sm font-bold"
          style={{ backgroundColor: color }}
        >
          {label[0]}
        </div>
        <div>
          <div className="text-sm font-semibold text-foreground">{label}</div>
          <div className="text-xs text-muted-foreground font-mono">{agentName}</div>
        </div>
      </div>

      {/* Status */}
      <div className="rounded-lg border border-border bg-muted/30 p-3">
        <div className="text-xs text-muted-foreground mb-1">状态</div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-success animate-pulse" />
          <span className="text-sm text-foreground">就绪</span>
        </div>
      </div>

      {/* Description */}
      <div className="rounded-lg border border-border bg-muted/30 p-3">
        <div className="text-xs text-muted-foreground mb-1">职责描述</div>
        <p className="text-sm text-foreground/80 leading-relaxed">
          {getAgentDescription(agentName)}
        </p>
      </div>
    </div>
  )
}

function TaskDetail({ taskId }: { taskId: string }) {
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-muted/30 p-3">
        <div className="text-xs text-muted-foreground mb-1">任务 ID</div>
        <div className="text-sm text-foreground font-mono">{taskId}</div>
      </div>
    </div>
  )
}

function getAgentDescription(name: string): string {
  const descriptions: Record<string, string> = {
    coordinator: '负责任务分配、流程编排和团队协调，确保各 Agent 按照正确顺序执行',
    requirement_decomposer: '将复杂问题分解为可管理的子问题，生成结构化的需求计划',
    analyzer_agent: '分析问题类型、数据特征，推荐建模方法和求解策略',
    data_agent: '负责数据收集、清洗、预处理和特征工程',
    research_agent: '检索和分析相关文献、方法和技术，提供研究支撑',
    innovation_agent: '分析研究空白，提出创新思路和改进方向',
    modeler_agent: '构建数学模型，选择合适的建模方法和假设',
    algorithm_engineer_agent: '设计和实现算法，优化计算效率',
    solver_agent: '执行数值计算、符号求解和实验验证',
    experimentation_agent: '设计实验方案，执行实验并评估结果质量',
    writer_agent: '撰写论文各章节，确保学术规范和逻辑连贯',
    peer_review_agent: '审阅论文质量，提出修改建议和改进意见',
    summary_agent: '总结任务成果，整理经验教训，更新知识库',
    financial_analyst_agent: '专注金融数据分析和量化建模',
    figure_agent: '生成科研图表和可视化展示',
  }
  return descriptions[name] || 'AI 智能体'
}
