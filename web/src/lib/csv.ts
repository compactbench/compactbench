// CSV for the leaderboard download. Text that came from submitters is guarded against
// spreadsheet formula injection: a cell starting with = + - @ (or a tab/CR) is prefixed
// with an apostrophe so spreadsheets show it as text.
const FORMULA = /^[=+\-@\t\r]/;

export function cell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "";
  let text = String(value);
  if (FORMULA.test(text)) text = `'${text}`;
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export const toCsv = (header: string[], rows: unknown[][]): string =>
  [header, ...rows].map((r) => r.map(cell).join(",")).join("\r\n") + "\r\n";
