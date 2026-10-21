import type { SearchEntry } from "./types";

export function normalizeSearch(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}
export function searchCompanies(
  entries: SearchEntry[],
  query: string,
): SearchEntry[] {
  const term = normalizeSearch(query);
  if (!term) return [];
  return entries
    .filter((entry) =>
      normalizeSearch(
        `${entry.ticker} ${entry.name} ${entry.aliases.join(" ")}`,
      ).includes(term),
    )
    .sort(
      (a, b) =>
        Number(normalizeSearch(b.ticker) === term) -
          Number(normalizeSearch(a.ticker) === term) ||
        a.ticker.localeCompare(b.ticker),
    )
    .slice(0, 7);
}
