import { ColoredCheckbox } from "@/components/ui/colored-checkbox";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type DriverFilterPanelProps = {
  drivers: string[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  driverColors?: Record<string, string>;
};

/** Fallback palette when driverColors not provided (matches chart line colors) */
const FALLBACK_COLORS = [
  "#73cfa8",
  "#73b1ff",
  "#fde179",
  "#fb9289",
  "#c084fc",
  "#94a3b8",
  "#f472b6",
  "#34d399",
  "#fbbf24",
  "#a78bfa",
  "#22d3ee",
  "#a3e635",
  "#f97316",
  "#e879f9",
  "#38bdf8",
  "#4ade80",
  "#facc15",
  "#fb7185",
  "#818cf8",
  "#2dd4bf",
];

function getColorForDriver(driver: string, index: number, driverColors?: Record<string, string>): string {
  if (driverColors?.[driver]) return driverColors[driver];
  return FALLBACK_COLORS[index % FALLBACK_COLORS.length];
}

export function DriverFilterPanel({
  drivers,
  selected,
  onChange,
  driverColors,
}: DriverFilterPanelProps) {
  const selectAll = () => onChange(new Set(drivers));
  const selectNone = () => onChange(new Set());

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-sm font-medium text-[var(--color-text-muted)]">
          Drivers
        </span>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={selectAll}
            className="rounded-lg"
          >
            Select All
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={selectNone}
            className="rounded-lg"
          >
            Select None
          </Button>
        </div>
      </div>
      <div
        className={cn(
          "grid gap-2",
          "grid-cols-[repeat(auto-fill,minmax(5rem,1fr))]",
          "sm:grid-cols-4 md:grid-cols-5"
        )}
      >
        {drivers.map((driver, i) => (
          <ColoredCheckbox
            key={driver}
            checked={selected.has(driver)}
            onCheckedChange={(checked) => {
              const next = new Set(selected);
              if (checked) next.add(driver);
              else next.delete(driver);
              onChange(next);
            }}
            label={driver}
            color={getColorForDriver(driver, i, driverColors)}
          />
        ))}
      </div>
    </div>
  );
}
