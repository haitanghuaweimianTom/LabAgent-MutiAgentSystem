'use client'
import { useParams } from 'next/navigation'
import { useState, useEffect } from 'react'
import { apiBase } from '@/lib/api'
import PaperPreview from '@/app/components/PaperPreview'
import PaperList from '@/app/components/PaperList'

export default function ReportPage() {
  const params = useParams()
  const taskId = params.id as string
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(apiBase() + '/tasks/' + taskId + '/result')
        if (res.ok) setResult(await res.json())
      } catch {}
      setLoading(false)
    }
    load()
  }, [taskId])

  if (loading) return <div className="p-6 text-muted-foreground">加载中...</div>
  if (!result) return <div className="p-6 text-muted-foreground">暂无报告</div>

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-xl font-semibold">研究报告</h2>
      <PaperList papers={result.papers ?? result} source={result.source} />
      <PaperPreview markdown={result.markdown} latexCode={result.latexCode} abstract={result.abstract} keywords={result.keywords} />
    </div>
  )
}
