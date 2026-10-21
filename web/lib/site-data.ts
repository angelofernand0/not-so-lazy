import { readFile } from "node:fs/promises";
import path from "node:path";
import type { CompanyData, SearchEntry } from "./types";

export async function searchIndex(): Promise<SearchEntry[]> {
  return JSON.parse(
    await readFile(
      path.join(process.cwd(), "public/site/search-index.json"),
      "utf8",
    ),
  );
}
export async function companyData(ticker: string): Promise<CompanyData | null> {
  if (!/^[A-Z0-9.-]{1,20}$/.test(ticker)) return null;
  if (!(await searchIndex()).some((entry) => entry.ticker === ticker))
    return null;
  return JSON.parse(
    await readFile(
      path.join(process.cwd(), "public/site/companies", `${ticker}.json`),
      "utf8",
    ),
  );
}
