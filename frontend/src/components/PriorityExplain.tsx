import { Info } from "lucide-react";
import { PRIORITY_COLOR } from "../lib/format";
import type { PriorityBreakdown } from "../lib/types";

/** Factor contributions as one-series horizontal bars + the score against the label thresholds. */
export function PriorityExplain({ b, compact }: { b: PriorityBreakdown; compact?: boolean }) {
  const max = Math.max(...b.factors.map((f) => f.points), 1);
  const scaleMax = Math.max(b.score, b.thresholds.critical * 1.6);
  const marks: [string, number][] = [
    ["medium", b.thresholds.medium],
    ["high", b.thresholds.high],
    ["critical", b.thresholds.critical],
  ];
  return (
    <div className="space-y-3">
      <div>
        <div className="mb-1 flex items-baseline justify-between text-xs">
          <span className="text-ink-2">
            Score <span className="font-mono text-ink">{b.score.toFixed(0)}</span> → computed{" "}
            <b style={{ color: PRIORITY_COLOR[b.computed_label] }}>{b.computed_label}</b>
            {b.label !== b.computed_label && (
              <>
                , shown as <b style={{ color: PRIORITY_COLOR[b.label] }}>{b.label}</b>
              </>
            )}
          </span>
        </div>
        <div className="relative h-9" aria-hidden>
          <div className="absolute inset-x-0 top-2 h-1 rounded bg-surface-3" />
          {marks.map(([name, v]) => (
            <div key={name} className="absolute top-0 h-5 border-l border-line-strong" style={{ left: `${(v / scaleMax) * 100}%` }}>
              <span className="absolute left-1 top-5 whitespace-nowrap text-[10px] text-ink-3">{name} ≥{v}</span>
            </div>
          ))}
          <div
            className="absolute top-[3px] h-3.5 w-3.5 -translate-x-1/2 rounded-full ring-2 ring-surface-1"
            style={{ left: `${Math.min(b.score / scaleMax, 1) * 100}%`, background: PRIORITY_COLOR[b.computed_label] }}
          />
        </div>
      </div>
      {b.factors.length ? (
        <table className="w-full text-xs">
          <caption className="sr-only">Contributing factors</caption>
          <tbody>
            {b.factors.map((f) => (
              <tr key={f.key} className="align-top">
                <td className="w-[45%] py-1 pr-2 text-ink">
                  {f.label}
                  {!compact && <div className="text-2xs text-ink-3">{f.detail}</div>}
                </td>
                <td className="py-1.5">
                  <div className="flex items-center gap-2">
                    <div className="h-2 rounded-r-[4px] bg-accent" style={{ width: `${(f.points / max) * 100}%`, maxWidth: "100%" }} />
                    <span className="font-mono text-ink-2">+{f.points}</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-xs text-ink-3">No severity factor identified in the reports.</p>
      )}
      {b.notes.map((n) => (
        <p key={n} className="text-xs text-[#f6c75a]">
          {n}
        </p>
      ))}
      {b.missing_info.length > 0 && (
        <div className="text-xs">
          <span className="text-ink-3">Missing critical information (does not lower severity): </span>
          <span className="text-ink-2">{b.missing_info.join(" · ")}</span>
        </div>
      )}
      {!compact && (
        <p className="flex items-start gap-1.5 text-2xs text-ink-3">
          <Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden /> {b.disclaimer}
        </p>
      )}
    </div>
  );
}
