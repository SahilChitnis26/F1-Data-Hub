import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const SEASON_MIN = 1950;
const SEASON_MAX = 2025;
const ROUND_MAX = 24;

const seasons = Array.from(
  { length: SEASON_MAX - SEASON_MIN + 1 },
  (_, i) => SEASON_MIN + i
).reverse();
const rounds = Array.from({ length: ROUND_MAX }, (_, i) => i + 1);

export type RaceResultsView = "finish" | "performance";

export interface RaceControlsProps {
  season: number;
  round: number;
  onSeasonChange: (season: number) => void;
  onRoundChange: (round: number) => void;
  /** Called when user clicks Search to fetch data for current season/round */
  onSearch?: () => void;
  /** Show Finish Position / Performance Score toggle (Race Overview only) */
  showViewToggle?: boolean;
  view?: RaceResultsView;
  onViewChange?: (view: RaceResultsView) => void;
  /** "stacked" = Season + Race centered on first row, View centered below (e.g. Race Overview) */
  layout?: "row" | "stacked";
  className?: string;
}

export function RaceControls({
  season,
  round,
  onSeasonChange,
  onRoundChange,
  onSearch,
  showViewToggle = false,
  view = "finish",
  onViewChange,
  layout = "row",
  className,
}: RaceControlsProps) {
  const isStacked = layout === "stacked";

  const searchButton = onSearch && (
    <Button
      type="button"
      variant="default"
      size={isStacked ? "default" : "default"}
      onClick={onSearch}
      className="shrink-0"
    >
      Search
    </Button>
  );

  const seasonRaceRow = (
    <div className={cn("flex flex-wrap items-end gap-4", isStacked && "justify-center")}>
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="season-select"
          className="text-sm font-semibold text-[var(--color-text-muted)]"
        >
          Season
        </label>
        <Select
          value={String(season)}
          onValueChange={(v) => onSeasonChange(Number(v))}
        >
          <SelectTrigger
            id="season-select"
            className="min-w-[100px] rounded-xl border-[var(--border)] bg-[var(--panel)] text-[var(--color-text-default)] backdrop-blur-[14px] transition-all hover:border-white/15 focus:ring-2 focus:ring-[var(--accent1)]/40"
          >
            <SelectValue placeholder="Season" />
          </SelectTrigger>
          <SelectContent>
            {seasons.map((s) => (
              <SelectItem key={s} value={String(s)}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="round-select"
          className="text-sm font-semibold text-[var(--color-text-muted)]"
        >
          Race
        </label>
        <Select value={String(round)} onValueChange={(v) => onRoundChange(Number(v))}>
          <SelectTrigger
            id="round-select"
            className="min-w-[80px] rounded-xl border-[var(--border)] bg-[var(--panel)] text-[var(--color-text-default)] backdrop-blur-[14px] transition-all hover:border-white/15 focus:ring-2 focus:ring-[var(--accent1)]/40"
          >
            <SelectValue placeholder="Round" />
          </SelectTrigger>
          <SelectContent>
            {rounds.map((r) => (
              <SelectItem key={r} value={String(r)}>
                {r}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {searchButton}
    </div>
  );

  const viewToggle = showViewToggle && onViewChange && (
    <div className={cn("flex items-center gap-2", isStacked && "justify-center")}>
      <span className="text-sm font-semibold text-[var(--color-text-muted)]">
        View
      </span>
      <div className="flex gap-1 rounded-xl border border-[var(--border)] bg-[var(--panel)]/60 p-0.5 backdrop-blur-[14px]">
        <Button
          type="button"
          variant={view === "finish" ? "default" : "ghost"}
          size="sm"
          className={view === "finish" ? "" : "text-[var(--color-text-muted)] hover:text-[var(--color-text-default)]"}
          onClick={() => onViewChange("finish")}
        >
          Finish Position
        </Button>
        <Button
          type="button"
          variant={view === "performance" ? "default" : "ghost"}
          size="sm"
          className={view === "performance" ? "" : "text-[var(--color-text-muted)] hover:text-[var(--color-text-default)]"}
          onClick={() => onViewChange("performance")}
        >
          Performance Score
        </Button>
      </div>
    </div>
  );

  if (isStacked) {
    return (
      <div className={cn("flex flex-col items-center gap-6", className)}>
        {seasonRaceRow}
        {viewToggle}
      </div>
    );
  }

  return (
    <div className={cn("flex flex-wrap items-end gap-4", className)}>
      {seasonRaceRow}
      {viewToggle}
    </div>
  );
}
