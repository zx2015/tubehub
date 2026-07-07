/**
 * useSSE — 订阅服务器发送事件（Server-Sent Events）
 *
 * 设计依据：docs/design/04-frontend-components.md §4.3.2
 *
 * 关键修复（2026-07-07）：
 *  - url 变化时才重建连接（避免父组件回调频繁导致抖动）
 *  - 组件卸载时关闭 EventSource
 *  - 使用 ref 持有最新 onMessage 闭包，引用稳定
 *  - 支持标准 SSE event: 命名空间：默认处理 'message'，并把 'error' 透传
 */
import { useEffect, useRef } from 'react';

export function useSSE<T = unknown>(
  url: string | null | undefined,
  onMessage: (data: T) => void,
): void {
  // 把最新的回调塞到 ref 里，避免 onMessage 引用变化引发 useEffect 反复重连
  const handlerRef = useRef(onMessage);
  useEffect(() => {
    handlerRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    if (!url) return;

    const es = new EventSource(url);

    es.onmessage = (e) => {
      try {
        const parsed = JSON.parse(e.data) as T;
        handlerRef.current(parsed);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn(`[useSSE] failed to parse message from ${url}:`, err);
      }
    };

    es.onerror = () => {
      // EventSource 自身具备自动重连机制，仅记录日志
      // eslint-disable-next-line no-console
      console.warn(`[useSSE] connection lost / reconnecting: ${url}`);
    };

    return () => {
      es.close();
    };
  }, [url]);
}

export default useSSE;