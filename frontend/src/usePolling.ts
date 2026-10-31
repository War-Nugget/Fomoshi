import { useCallback, useEffect, useRef, useState } from "react";

/** Load data now and re-fetch every `intervalMs` while the tab is visible.
 *  With `keepData`, changing `deps` keeps showing the old data until the new load lands. */
export function usePolling<T>(
  load: () => Promise<T>,
  intervalMs: number,
  deps: unknown[] = [],
  { keepData = false }: { keepData?: boolean } = {},
) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loadRef = useRef(load);
  loadRef.current = load;
  const latest = useRef(0);

  const reload = useCallback(async () => {
    const id = ++latest.current;
    try {
      const result = await loadRef.current();
      if (id !== latest.current) return; // a newer request already started; drop this one
      setData(result);
      setError(null);
    } catch (e) {
      if (id !== latest.current) return;
      setError(e instanceof Error ? e.message : "Something went wrong");
    }
  }, []);

  useEffect(() => {
    if (!keepData) setData(null);
    reload();
    if (!intervalMs) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") reload();
    }, intervalMs);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, reload, ...deps]);

  return { data, error, reload };
}
