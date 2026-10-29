// Durations as the API sends them (`h:mm`, with a minus for negative values) and as minutes.

/** `-1:45` → -105, `12:30` → 750 */
export function toMinutes(duration: string): number {
  const negative = duration.startsWith('-');
  const [hours = 0, minutes = 0] = duration.replace(/^[-+]/, '').split(':').map(Number);
  return (negative ? -1 : 1) * (hours * 60 + minutes);
}

/** -105 → `-1:45`, 750 → `12:30` */
export function fromMinutes(minutes: number): string {
  const sign = minutes < 0 ? '-' : '';
  const absolute = Math.abs(minutes);
  return `${sign}${Math.floor(absolute / 60)}:${String(absolute % 60).padStart(2, '0')}`;
}
