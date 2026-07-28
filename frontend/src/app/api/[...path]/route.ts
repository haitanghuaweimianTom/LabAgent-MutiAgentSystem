import { NextRequest, NextResponse } from 'next/server';

// 同源反向代理：浏览器只请求 3002/api/...，由本 handler 转发到后端 8001。
// 解决三大坑：
//  1. Windows 浏览器直连 localhost:8001 被 Clash 劫持 → 502（改同源 3002）
//  2. Next rewrites 的 :path* 吃掉尾斜杠 → 后端 307 → Location 用绝对 host
//     127.0.0.1:8001 → 浏览器跟随时 502。本 handler 完整保留路径(含尾斜杠)，
//     并把 3xx 的 Location 改写为同源相对路径，杜绝暴露 8001。
//  3. localhost→IPv6 ::1 但 uvicorn 只监听 IPv4 → 用 127.0.0.1 强制 IPv4。
//  4. Node undici 默认连接池复用 keep-alive 连接，后端关闭空闲连接时
//     route handler 的 fetch 抛 UND_ERR_SOCKET「other side closed」→ 浏览器
//     「无法加载响应数据」。用流式透传(body 不缓冲全量) + 显式 Connection:close。
const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8001';

const HOP_HEADERS = new Set([
  'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
  'te', 'trailers', 'transfer-encoding', 'upgrade', 'host', 'content-length',
]);

const RESP_HOP = new Set([
  'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
  'te', 'trailers', 'transfer-encoding', 'upgrade', 'content-encoding',
  'content-length',
]);

async function handler(req: NextRequest) {
  const { pathname, search } = req.nextUrl;
  const url = `${BACKEND_URL}${pathname}${search}`;

  const reqHeaders: Record<string, string> = {};
  req.headers.forEach((value, key) => {
    const lk = key.toLowerCase();
    if (HOP_HEADERS.has(lk)) return;
    reqHeaders[key] = value;
  });
  // 显式关闭 keep-alive，避免连接池复用导致的 other side closed
  reqHeaders['connection'] = 'close';

  let body: BodyInit | null = null;
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    body = await req.arrayBuffer();
    if (body.byteLength === 0) body = null;
  }

  let backendRes: Response;
  try {
    backendRes = await fetch(url, {
      method: req.method,
      headers: reqHeaders,
      body,
      redirect: 'manual',
    });
  } catch (e) {
    return NextResponse.json(
      { error: `Backend unreachable: ${e instanceof Error ? e.message : 'unknown'}` },
      { status: 502 }
    );
  }

  const respHeaders = new Headers();
  backendRes.headers.forEach((value, key) => {
    const lk = key.toLowerCase();
    if (RESP_HOP.has(lk)) return;
    if (lk === 'location') {
      let loc = value;
      try {
        const u = new URL(value, BACKEND_URL);
        if (u.pathname.startsWith('/api/')) {
          loc = u.pathname + u.search;
        }
      } catch {
        // 非 URL 直接透传
      }
      respHeaders.set(key, loc);
      return;
    }
    respHeaders.set(key, value);
  });

  // 流式透传 body（不缓冲全量，避免大响应/慢连接 socket 断开）
  const stream = new ReadableStream({
    async start(controller) {
      try {
        const reader = backendRes.body?.getReader();
        if (!reader) {
          controller.close();
          return;
        }
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          controller.enqueue(value);
        }
        controller.close();
      } catch (e) {
        controller.error(e);
      }
    },
    cancel() {
      // 浏览器取消请求时，释放后端 reader
    },
  });

  return new NextResponse(stream, {
    status: backendRes.status,
    statusText: backendRes.statusText,
    headers: respHeaders,
  });
}

export {
  handler as GET,
  handler as POST,
  handler as PUT,
  handler as DELETE,
  handler as PATCH,
  handler as OPTIONS,
};
