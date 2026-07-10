/**
 * useSSE — 订阅服务器发送事件（Server-Sent Events）
 *
 * 兼容两种 SSE 格式：
 *  - 无名事件（`data: ...`）：由 onmessage 接收
 *  - 具名事件（`event: progress\ndata: ...`）：由 addEventListener 接收
 */
import { useEffect, useRef } from 'react';

export function useSSE<T = unknown>(
  url: string | null | undefined,
  onMessage: (data: T) => void,
): void {
  // ref 持有最新回调，避免 url 不变时反复重建连接
  const handlerRef = useRef(onMessage);
  useEffect(() => {
    handlerRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    if (!url) return;

    const es = new EventSource(url);

    const handle = (e: MessageEvent) => {
      try {
        const parsed = JSON.parse(e.data) as T;
        handlerRef.current(parsed);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn(`[useSSE] failed to parse message from ${url}:`, err);
      }
    };

    // 无名事件（data: ... 无 event: 前缀）
    es.onmessage = handle;

    // 具名 progress 事件（event: progress\ndata: ...）
    es.addEventListener('progress', handle);

    es.onerror = () => {
      // EventSource 内置自动重连，仅记录日志
      // eslint-disable-next-line no-console
      console.warn(`[useSSE] connection lost / reconnecting: ${url}`);
    };

    return () => {
      es.removeEventListener('progress', handle);
      es.close();
    };
  }, [url]);
}

export default useSSE;
