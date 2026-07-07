/**
 * useApi — 轻量 GET fetch wrapper
 *
 * 设计依据：docs/design/04-frontend-components.md §4.3.1
 *
 * 行为：
 *  - 组件挂载或 url 变化时自动 fetch
 *  - 内置 AbortController，组件卸载或 url 变化时取消未完成请求
 *  - 失败时设置 error 为 Error 对象，调用方决定如何展示
 *  - loading 状态用于按钮 / 占位符
 */
import { useEffect, useState } from 'react';

export interface UseApiResult<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
  reload: () => void;
}

export function useApi<T = unknown>(url: string | null | undefined): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(Boolean(url));
  const [error, setError] = useState<Error | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!url) {
      setData(null);
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    setLoading(true);
    setError(null);

    fetch(url, { signal: controller.signal })
      .then(async (resp) => {
        if (!resp.ok) {
          throw new Error(`HTTP ${resp.status}`);
        }
        return (await resp.json()) as T;
      })
      .then((json) => {
        setData(json);
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === 'AbortError') {
          return;
        }
        setError(err instanceof Error ? err : new Error(String(err)));
      })
      .finally(() => {
        setLoading(false);
      });

    return () => {
      controller.abort();
    };
  }, [url, tick]);

  return {
    data,
    loading,
    error,
    reload: () => setTick((n) => n + 1),
  };
}

export default useApi;