import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, type EventSummary, type Sort } from "../api";
import { EventBlock } from "../components/EventBlock";
import { usePolling } from "../usePolling";

const SORTS: { id: Sort; label: string }[] = [
  { id: "trending", label: "Trending" },
  { id: "volume", label: "Most traded" },
  { id: "closing", label: "Closing soon" },
  { id: "new", label: "Newest" },
];
const PAGE_SIZE = 20;

export function Markets() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const category = params.get("category") ?? "";
  const sort = (params.get("sort") as Sort) || "trending";

  const [query, setQuery] = useState(q);
  const [events, setEvents] = useState<EventSummary[] | null>(null);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const cats = usePolling(() => api.categories(), 0);

  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  // Debounce the search box into the URL
  useEffect(() => {
    const id = window.setTimeout(() => {
      if (query.trim() !== q) update("q", query.trim());
    }, 300);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  // Reload page 1 whenever filters change
  useEffect(() => {
    let cancelled = false;
    setEvents(null);
    setError(null);
    api
      .events({ q, category, sort, page: 1, page_size: PAGE_SIZE })
      .then((r) => {
        if (cancelled) return;
        setEvents(r.events);
        setPage(1);
        setHasMore(r.has_more);
        setTotal(r.total);
      })
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [q, category, sort]);

  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const r = await api.events({ q, category, sort, page: page + 1, page_size: PAGE_SIZE });
      setEvents((prev) => {
        const seen = new Set(prev?.map((e) => e.event_ticker));
        return [...(prev ?? []), ...r.events.filter((e) => !seen.has(e.event_ticker))];
      });
      setPage(page + 1);
      setHasMore(r.has_more);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn’t load more markets");
    } finally {
      setLoadingMore(false);
    }
  };

  return (
    <>
      <div className="page-head">
        <h1>Markets</h1>
        <div className="page-head__controls">
          <input
            className="search"
            type="search"
            placeholder="Search markets"
            aria-label="Search markets"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <select aria-label="Sort markets" value={sort} onChange={(e) => update("sort", e.target.value === "trending" ? "" : e.target.value)}>
            {SORTS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {cats.data && cats.data.length > 1 && (
        <div className="chips" role="group" aria-label="Filter by category">
          <button aria-pressed={!category} onClick={() => update("category", "")}>
            All
          </button>
          {cats.data.map((c) => (
            <button key={c.name} aria-pressed={category === c.name} onClick={() => update("category", c.name)}>
              {c.name}
            </button>
          ))}
        </div>
      )}

      {error && <p className="notice notice--error">{error}</p>}
      {!events && !error && <p className="notice">Loading markets…</p>}
      {events && events.length === 0 && (
        <p className="notice">
          {q ? `No open markets match “${q}”.` : "No open markets in this category right now."}
        </p>
      )}
      {events && events.length > 0 && (q || category) && (
        <p className="result-count">
          {total.toLocaleString()} {total === 1 ? "event" : "events"}
        </p>
      )}

      <div className="event-list">
        {events?.map((e) => <EventBlock key={e.event_ticker} event={e} />)}
      </div>

      {hasMore && (
        <div className="load-more">
          <button className="button button--quiet" onClick={loadMore} disabled={loadingMore}>
            {loadingMore ? "Loading…" : "Show more markets"}
          </button>
        </div>
      )}
    </>
  );
}
