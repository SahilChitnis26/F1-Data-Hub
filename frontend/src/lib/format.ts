/**
 * Format helpers (aligned with legacy dashboard.html formatLapTime).
 */

export function formatLapTime(seconds: number | null | undefined): string {
  if (seconds == null || seconds === undefined || Number.isNaN(seconds))
    return "–";
  const totalSeconds = Number(seconds);
  const minutes = Math.floor(totalSeconds / 60);
  const secs = totalSeconds % 60;
  return `${minutes}:${secs.toFixed(3).padStart(6, "0")}`;
}
