'use client'

import { usePathname } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'
import { Sidebar } from '@/components/layout/Sidebar'
import { TopBar } from '@/components/layout/TopBar'
import DetailPanel from './components/DetailPanel'
import { TAB_META } from '@/lib/constants'

const pageVariants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
}

const ROUTE_META: Record<string, { title: string; subtitle: string }> = {
  '/': { title: 'LabAgent', subtitle: '全自动科研论文生产系统' },
  '/generate': TAB_META.generate,
  '/history': TAB_META.history,
  '/agents': TAB_META.agents,
  '/workflows': TAB_META.workflows,
  '/files': TAB_META.files,
  '/pdf': TAB_META.pdf,
  '/memory': TAB_META.memory,
  '/environment': TAB_META.environment,
  '/settings': TAB_META.settings,
  '/knowledge': { title: '知识库', subtitle: '知识库管理与检索' },
}

function getRouteMeta(pathname: string) {
  if (ROUTE_META[pathname]) return ROUTE_META[pathname]
  if (pathname.startsWith('/task/')) {
    if (pathname.endsWith('/report')) return { title: '研究报告', subtitle: '查看任务报告' }
    return TAB_META.generate
  }
  return { title: 'LabAgent', subtitle: '全自动科研论文生产系统' }
}

export function ClientLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const meta = getRouteMeta(pathname)

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <TopBar title={meta.title} subtitle={meta.subtitle} />
        <main className="flex-1 overflow-y-auto">
          <AnimatePresence mode="wait">
            <motion.div
              key={pathname}
              variants={pageVariants}
              initial="initial"
              animate="animate"
              exit="exit"
              transition={{ duration: 0.15, ease: 'easeInOut' }}
            >
              {children}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
      <DetailPanel />
    </div>
  )
}
