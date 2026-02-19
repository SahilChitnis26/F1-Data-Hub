import { cn } from "@/lib/utils";

export interface KeyTakeawaysProps {
  insights: string[];
  className?: string;
}

export function KeyTakeaways({ insights, className }: KeyTakeawaysProps) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-[var(--border)] bg-[var(--panel)] p-6 shadow-[var(--shadow)] backdrop-blur-[14px]",
        className
      )}
    >
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-secondary)]">
        Key Takeaways
      </h3>
      <ul className="list-none space-y-1.5 border-t border-white/5 pt-2">
        {insights.length > 0 ? (
          insights.map((insight, i) => (
            <li
              key={i}
              className="border-b border-white/5 pb-1.5 text-sm last:border-0 last:pb-0 text-[var(--color-text-muted)] before:mr-1.5 before:content-['•'] before:text-[var(--color-quaternary)]"
            >
              {insight}
            </li>
          ))
        ) : (
          <li className="text-sm text-[var(--color-text-muted)]">
            No insights for this race.
          </li>
        )}
      </ul>
    </div>
  );
}
