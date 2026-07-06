declare global {
  interface Window {
    __API_BASE__?: string;
  }
}

export const apiBase = (): string =>
  window.__API_BASE__ || 'http://localhost:8000/api/v1';

export async function fetchApi<T = any>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(apiBase() + path, options);
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail?.message || `请求失败: ${res.status}`);
  }
  return res.json();
}