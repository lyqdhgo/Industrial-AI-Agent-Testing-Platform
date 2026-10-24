import { useEffect, useState, type DependencyList } from "react";

interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
}

export interface AsyncResult<T> extends AsyncState<T> {
  reload: () => void;
}

function errorText(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return "请求失败，请检查后端服务是否可用。";
}

/**
 * 轻量数据加载器：首次加载显示骨架；轮询刷新不整页闪烁。
 * deps 的长度在组件生命周期内必须保持稳定。
 */
export function useAsync<T>(
  loader: () => Promise<T>,
  deps: DependencyList = [],
  pollMs = 0,
): AsyncResult<T> {
  const [version, setVersion] = useState(0);
  const [state, setState] = useState<AsyncState<T>>({
    data: null,
    loading: true,
    refreshing: false,
    error: null,
  });

  useEffect(() => {
    let alive = true;
    setState((previous) => ({
      data: previous.data,
      loading: previous.data === null,
      refreshing: previous.data !== null,
      error: null,
    }));

    const run = (): void => {
      loader()
        .then((data) => {
          if (alive) {
            setState({ data, loading: false, refreshing: false, error: null });
          }
        })
        .catch((error: unknown) => {
          if (alive) {
            setState((previous) => ({
              ...previous,
              loading: false,
              refreshing: false,
              error: errorText(error),
            }));
          }
        });
    };

    run();
    const timer = pollMs > 0 ? window.setInterval(run, pollMs) : undefined;
    return () => {
      alive = false;
      if (timer !== undefined) {
        window.clearInterval(timer);
      }
    };
    // deps 由调用方显式声明；loader 每次渲染重建不应触发请求。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version, pollMs, ...deps]);

  return {
    ...state,
    reload: () => setVersion((value) => value + 1),
  };
}
