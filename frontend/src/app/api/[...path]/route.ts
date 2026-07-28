import { NextRequest, NextResponse } from 'next/server';

// 同源反向代理：浏览器只请求 3002/api/...，由本 handler 转发到后端 8001。
// 解决三大坑：
//  1. Windows 浏览器直连 localhost:8001 被 Clash 劫持 → 502（改同源 3002）
//  2. Next rewrites 的 :path* 会吃掉尾斜杠 → 后端 redirect_slashes 307 →
//     Location 用绝对 host 127.0.0.1:8001 → 浏览器跟随时又 502。
//     本 handler 完整保留路径(含尾斜杠)，并把响应里 3xx 的 Location 改写为
//     同源相对路径，杜绝暴露 8001。
//  3. localhost→IPv6 ::1 但 uvicorn 只监听 IPv4 → 用 127.0.0.1 强制 IPv4。
const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8001';

// 透传的请求头（hop-by-hop 头要剔除）
const HOP_HEADERS = new Set([
  'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
  'te', 'trailers', 'transfer-encoding', 'upgrade', 'host', 'content-length',
]);

// 透传的响应头
const RESP_HOP = new Set([
  'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
  'te', 'trailers', 'transfer-encoding', 'upgrade', 'content-encoding',
  'content-length',
]);

async function handler(req: NextRequest) {
  const { pathname, search } = req.nextUrl;
  // pathname 形如 /api/v1/tasks/...，原样拼到后端（保留尾斜杠）
  const url = `${BACKEND_URL}${pathname}${search}`;

  // 构建转发请求头
  const reqHeaders: Record<string, string> = {};
  req.headers.forEach((value, key) => {
    if (!HOP_HEADERS.has(key.toLowerCase())) {
      reqHeaders[key] = value;
    }
  });

  // 读取请求体（GET/HEAD 无 body）
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
      // 不自动跟随重定向——我们要改写 Location
      redirect: 'manual',
    });
  } catch (e) {
    return NextResponse.json(
      { error: `Backend unreachable: ${e instanceof Error ? e.message : 'unknown'}` },
      { status: 502 }
    );
  }

  // 构建响应头
  const respHeaders = new Headers();
  backendRes.headers.forEach((value, key) => {
    const lk = key.toLowerCase();
    if (RESP_HOP.has(lk)) return;
    // ★关键：改写 3xx Location，去掉 127.0.0.1:8001，改为同源相对路径
    if (lk === 'location') {
      let loc = value;
      try {
        const u = new URL(value, BACKEND_URL);
        // 只代理 /api/ 下的后端地址，把绝对 URL 改成相对路径
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

  const respBody = await backendRes.arrayBuffer();
  return new NextResponse(respBody, {
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
