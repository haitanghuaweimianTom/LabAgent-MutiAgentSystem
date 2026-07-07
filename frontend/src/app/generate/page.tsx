'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import ProblemInput from '@/app/components/ProblemInput'
import { useAppStore } from '@/app/store/useAppStore'
import { apiBase } from '@/lib/api'

export default function GeneratePage() {
  const [submitting, setSubmitting] = useState(false)
  const [taskStatus, setTaskStatus] = useState('idle')
  const [progress, setProgress] = useState(0)
  const router = useRouter()
  const activeProjectId = useAppStore((s) => s.activeProjectId)
  const addTaskToProject = useAppStore((s) => s.addTaskToProject)

  const handleSubmit = async (params: {
    problemText: string
    projectName: string
    workflow: string
    template: string
    mode: string
    useCritique: boolean
    knowledgeBaseId: string | null
    knowledgeBaseIds: string[]
    dataSource: 'upload' | 'self_collect' | 'upload_and_collect'
    problemType: string
    dataFiles: string[]
  }) => {
    setSubmitting(true)
    try {
      const body: Record<string, any> = {
        problem_text: params.problemText,
        project_name: params.projectName,
        mode: params.mode,
        options: { workflow: params.workflow, template: params.template, use_critique: params.useCritique },
        data_files: params.dataFiles,
        data_source: params.dataSource,
        problem_type: params.problemType,
      }
      if (params.knowledgeBaseIds && params.knowledgeBaseIds.length > 0) {
        body.knowledge_base_ids = params.knowledgeBaseIds
      } else if (params.knowledgeBaseId) {
        body.knowledge_base_id = params.knowledgeBaseId
      }
      const res = await fetch(apiBase() + '/tasks/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (!res.ok) {
        alert(data.detail?.message || `提交失败: ${res.status}`)
        return
      }
      const newTaskId = data.task_id
      if (activeProjectId && newTaskId) addTaskToProject(activeProjectId, newTaskId)
      router.push(`/task/${newTaskId}`)
    } catch (err) {
      console.error(err)
      alert('提交失败，请确认后端已启动')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="p-6">
      <ProblemInput
        onSubmit={handleSubmit}
        submitting={submitting}
        taskStatus={taskStatus}
        progress={progress}
      />
    </div>
  )
}
