import { useEffect, useMemo, useRef, useState } from "react";
import {
  ColorType,
  createChart,
  CrosshairMode,
  LineSeries,
  LineType,
  type IChartApi,
  type ISeriesApi,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import type { ChartRange } from "../api";

export interface ChartLine {
  id: string;
  label: string;
  color: string;
  points: { time: number | string; value: number }[];
}

interface Props {
  lines: ChartLine[];
  format: "percent" | "money";
  height?: number;
  loading?: boolean;
  emptyText?: string;
  ariaLabel: string;
}

function cssVar(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function useColorScheme() {
  const [dark, setDark] = useState(() => window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false);
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return;
    const onChange = (e: MediaQueryListEvent) => setDark(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return dark;
}

const formatters = {
  percent: (v: number) => `${Math.round(v * 100)}%`,
  money: (v: number) =>
    v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }),
};

/** Line chart for market probabilities (0–1) or account value (dollars). */
export function PriceChart({ lines, format, height = 280, loading, emptyText, ariaLabel }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const dark = useColorScheme();
  const [hover, setHover] = useState<Record<string, number> | null>(null);
  const fmt = formatters[format];
  const hasData = lines.some((l) => l.points.length > 1);

  // Build the chart once per theme
  useEffect(() => {
    if (!box.current) return;
    const ink = cssVar("--muted");
    const grid = cssVar("--line");
    const c = createChart(box.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: ink,
        fontFamily: "IBM Plex Sans, system-ui, sans-serif",
        fontSize: 12,
        attributionLogo: false,
      },
      grid: { vertLines: { visible: false }, horzLines: { color: grid } },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.1, bottom: 0.08 } },
      timeScale: { borderVisible: false, timeVisible: format === "percent", secondsVisible: false },
      crosshair: { mode: CrosshairMode.Magnet, horzLine: { visible: false } },
      localization: { priceFormatter: fmt },
      handleScroll: false,
      handleScale: false,
    });
    chart.current = c;
    c.subscribeCrosshairMove((param) => {
      if (!param.time || !param.seriesData.size) return setHover(null);
      const values: Record<string, number> = {};
      series.current.forEach((s, id) => {
        const d = param.seriesData.get(s) as { value?: number } | undefined;
        if (d?.value !== undefined) values[id] = d.value;
      });
      setHover(values);
    });
    return () => {
      c.remove();
      chart.current = null;
      series.current.clear();
    };
  }, [dark, format, fmt]);

  // Sync series data
  useEffect(() => {
    const c = chart.current;
    if (!c) return;
    const wanted = new Set(lines.map((l) => l.id));
    series.current.forEach((s, id) => {
      if (!wanted.has(id)) {
        c.removeSeries(s);
        series.current.delete(id);
      }
    });
    for (const line of lines) {
      let s = series.current.get(line.id);
      if (!s) {
        s = c.addSeries(LineSeries, {
          color: resolveColor(line.color),
          lineWidth: 2,
          lineType: format === "percent" ? LineType.WithSteps : LineType.Simple,
          priceLineVisible: false,
          lastValueVisible: lines.length === 1,
          crosshairMarkerRadius: 4,
          priceFormat: { type: "custom", formatter: fmt, minMove: format === "percent" ? 0.01 : 1 },
        });
        series.current.set(line.id, s);
      } else {
        s.applyOptions({ color: resolveColor(line.color) });
      }
      s.setData(line.points.map((p) => ({ time: p.time as UTCTimestamp | Time, value: p.value })));
    }
    c.timeScale().fitContent();
  }, [lines, dark, format, fmt]);

  const latest = useMemo(
    () => Object.fromEntries(lines.map((l) => [l.id, l.points.at(-1)?.value])),
    [lines],
  );

  return (
    <figure className="chart" aria-label={ariaLabel}>
      {lines.length > 1 && (
        <figcaption className="chart__legend">
          {lines.map((l) => {
            const v = hover?.[l.id] ?? latest[l.id];
            return (
              <span key={l.id}>
                <i style={{ background: l.color }} />
                {l.label}
                <strong>{v !== undefined ? fmt(v) : "—"}</strong>
              </span>
            );
          })}
        </figcaption>
      )}
      <div className="chart__canvas" style={{ height }}>
        <div ref={box} className="chart__box" />
        {!hasData && <p className="chart__empty">{loading ? "Loading chart…" : (emptyText ?? "No price history yet")}</p>}
      </div>
    </figure>
  );
}

const RANGES: { id: ChartRange; label: string }[] = [
  { id: "1d", label: "1D" },
  { id: "1w", label: "1W" },
  { id: "1m", label: "1M" },
  { id: "all", label: "All" },
];

export function RangePicker({ value, onChange }: { value: ChartRange; onChange: (r: ChartRange) => void }) {
  return (
    <div className="range-picker" role="group" aria-label="Chart range">
      {RANGES.map((r) => (
        <button key={r.id} type="button" aria-pressed={value === r.id} onClick={() => onChange(r.id)}>
          {r.label}
        </button>
      ))}
    </div>
  );
}

/** Distinct, colour-blind-friendly line colours for multi-outcome charts. */
export const LINE_COLORS = ["var(--yes)", "var(--no)", "#0f9d8f", "#8a5cf6", "#d6457a", "#6b7280"];

export function resolveColor(color: string) {
  const m = color.match(/^var\((--[\w-]+)\)$/);
  return m ? cssVar(m[1]) : color;
}
