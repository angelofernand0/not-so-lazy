import assert from "node:assert/strict";
import test from "node:test";
import { searchCompanies } from "../lib/search.ts";
import type { SearchEntry } from "../lib/types.ts";
const entries: SearchEntry[] = [
  {
    ticker: "KO",
    cik: 1,
    name: "Coca-Cola Company (The)",
    sector: "Test",
    aliases: ["KO"],
    status: "ready",
  },
  {
    ticker: "BRK.B",
    cik: 2,
    name: "Berkshire Hathaway",
    sector: "Test",
    aliases: ["BRK-B", "BRK-A"],
    status: "ready",
  },
  {
    ticker: "GOOG",
    cik: 3,
    name: "Alphabet Inc. (Class C)",
    sector: "Test",
    aliases: ["GOOG", "GOOGL"],
    status: "ready",
  },
  {
    ticker: "O",
    cik: 4,
    name: "Realty Income",
    sector: "Test",
    aliases: ["O"],
    status: "ready",
  },
];
test("company search treats spaces, hyphens and dots consistently", () => {
  assert.equal(searchCompanies(entries, "Coca Cola")[0].ticker, "KO");
  assert.equal(searchCompanies(entries, "Coca-Cola")[0].ticker, "KO");
  assert.equal(searchCompanies(entries, "brk-b")[0].ticker, "BRK.B");
  assert.equal(searchCompanies(entries, "BRK.B")[0].ticker, "BRK.B");
});
test("aliases resolve to one issuer and exact tickers rank first", () => {
  assert.equal(searchCompanies(entries, "googl")[0].ticker, "GOOG");
  assert.equal(searchCompanies(entries, "o")[0].ticker, "O");
  assert.deepEqual(searchCompanies(entries, " "), []);
  assert.deepEqual(searchCompanies(entries, "unknown"), []);
});
