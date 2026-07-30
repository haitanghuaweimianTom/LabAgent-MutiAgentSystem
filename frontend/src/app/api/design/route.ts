// 设计模式交接物端点：用户点"保存"后把 store 数据落盘到 frontend/.design-overrides.json
// （gitignored），Claude 读盘后 Edit 源码定死，再 DELETE 清盘。
// 这是 Next route handler（不走 Python 后端），同源 /api/design。

import { NextRequest, NextResponse } from 'next/server'
import { promises as fs } from 'fs'
import path from 'path'

const FILE = path.join(process.cwd(), '.design-overrides.json')

export async function GET() {
  try {
    const raw = await fs.readFile(FILE, 'utf-8')
    return NextResponse.json(JSON.parse(raw))
  } catch {
    return NextResponse.json({ entries: {}, groups: {}, savedAt: null })
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    await fs.writeFile(FILE, JSON.stringify(body, null, 2), 'utf-8')
    return NextResponse.json({ ok: true })
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: e?.message }, { status: 500 })
  }
}

export async function DELETE() {
  try {
    await fs.unlink(FILE)
  } catch {
    // 文件不存在也视为成功
  }
  return NextResponse.json({ ok: true })
}
