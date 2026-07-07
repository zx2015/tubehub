/**
 * useSSE — 订阅服务器发送事件（Server-Sent Events）
 *
 * 设计依据：docs/design/04-frontend-components.md §4.3.2
 *
 * 行为：
 *  - url 变化时重建连接
 *  - 组件卸载或 url 变化时关闭 EventSource，防止泄漏
 *  - EventSource 自身具备自动重连能力，onerror 仅做日志记录
 *  - 解析失败时打印 warn，不抛出，避免单个坏消息中断整个流
 */
import { useEffect } from 'react';

export function useSSE<T = unknown>(
  url: string | null | undefined,
  onMessage: (data: T) => void,
): void {
  useEffect(() => {
    if (!url) return;

    const es = new EventSource(url);

    es.onmessage = (e) => {
      try {
        const parsed = JSON.parse(e.data) as T;
        onMessage(parsed);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn(`[useSSE] failed to parse message from ${url}:`, err);
      }
    };

    es.onerror = () => {
      // EventSource 自动重连，仅记录日志
      // eslint-disable-next-line no-console
      console.warn(`[useSSE] connection lost / reconnecting: ${url}`);
    };

    return () => {
      es.close();
    };
  }, [url, onMessage]);
}

export default useSSE;