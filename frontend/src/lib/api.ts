declare global {
  interface Window {
    __API_BASE__?: string;
  }
}

export const apiBase = (): string =>
  window.__API_BASE__ || 'http://localhost:8001/api/v1';
