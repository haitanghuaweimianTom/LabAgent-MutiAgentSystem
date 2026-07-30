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
    <div data-design-id="report:root" className="mx-auto w-full max-w-[1320px] p-6 space-y-6 flex flex-col items-center">
      <h2 data-design-id="report:title" className="text-lg text-foreground font-semibold">研究报告</h2>
      <PaperList papers={result.papers ?? result} source={result.source} />
      <PaperPreview markdown={result.markdown} latexCode={result.latexCode} abstract={result.abstract} keywords={result.keywords} />
    </div>
  )
}
