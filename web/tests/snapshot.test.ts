import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import { pieces } from "../lib/diff-text.ts";
import type { CompanyData, DiffData, SearchEntry } from "../lib/types.ts";

test("real preview snapshots are complete, source-linked and reconstruct every diff", async () => {
  const root = path.join(process.cwd(), "public/site");
  const index: SearchEntry[] = JSON.parse(
    await readFile(path.join(root, "search-index.json"), "utf8"),
  );
  const meta = JSON.parse(await readFile(path.join(root, "meta.json"), "utf8"));
  assert.equal(index.length, 20);
  assert.equal(meta.company_count, index.length);
  const statuses: Record<string, number> = {};
  const accessions = new Set<string>();
  for (const entry of index) {
    const company: CompanyData = JSON.parse(
      await readFile(
        path.join(root, "companies", entry.ticker + ".json"),
        "utf8",
      ),
    );
    assert.equal(company.ticker, entry.ticker);
    assert.equal(company.cik, entry.cik);
    statuses[company.status] = (statuses[company.status] ?? 0) + 1;
    for (const filing of [company.prior, company.current]) {
      if (filing) {
        assert.match(
          filing.source_url ?? "",
          /^https:\/\/www\.sec\.gov\/Archives\/edgar\/data\//,
        );
        accessions.add(filing.accession);
      }
    }
    if (company.status !== "ready") {
      assert.equal(company.diff_url, null);
      assert.equal(company.counts, null);
      continue;
    }
    assert.match(company.diff_url ?? "", /^\/site\/diffs\/[0-9-]+\.json$/);
    const raw = await readFile(
      path.join(root, company.diff_url!.replace("/site/", "")),
      "utf8",
    );
    assert.equal(
      createHash("sha256").update(raw).digest("hex"),
      company.diff_sha256,
    );
    const data: DiffData = JSON.parse(raw);
    assert.equal(data.pair_id, company.current?.accession);
    const counts: Record<string, number> = {};
    for (const factor of data.factors) {
      counts[factor.change_type] = (counts[factor.change_type] ?? 0) + 1;
      for (const side of ["prior", "current"] as const) {
        const text = factor[side]?.text ?? "";
        assert.equal(
          pieces(text, factor.diff.ops, side, false)
            .map((p) => p.text)
            .join(""),
          text,
        );
        assert.equal(
          pieces(text, factor.diff.ops, side, true)
            .map((p) => p.text)
            .join(""),
          text,
        );
      }
    }
    assert.deepEqual(company.counts, counts);
  }
  assert.equal(statuses.ready, 19);
  assert.equal(statuses.review_required, 1);
  assert.equal(statuses.ready, meta.comparison_count);
  assert.equal(accessions.size, meta.filing_count);
});
