import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { companyData, searchIndex } from "../../../lib/site-data";
import CompanySearch from "../../../components/company-search";
import DiffView from "../../../components/diff-view";
import type { Filing } from "../../../lib/types";

export async function generateStaticParams() {
  return (await searchIndex()).map(({ ticker }) => ({ ticker }));
}
export const dynamicParams = false;
export async function generateMetadata({
  params,
}: {
  params: Promise<{ ticker: string }>;
}): Promise<Metadata> {
  const company = await companyData((await params).ticker);
  return {
    title: company
      ? `${company.ticker} — ${company.name} risk changes`
      : "Company not found",
  };
}
function FilingSource({
  filing,
  label,
}: {
  filing: Filing | null;
  label: string;
}) {
  return (
    <div className="filing-source">
      <span className="eyebrow">{label}</span>
      {filing ? (
        <>
          <strong>
            FY {filing.fiscal_year ?? filing.report_date?.slice(0, 4)} ·{" "}
            {filing.form}
          </strong>
          <span>Period ended {filing.report_date ?? "not available"}</span>
          <span>Filed {filing.filed_at}</span>
          {filing.source_url && (
            <a href={filing.source_url} target="_blank" rel="noreferrer">
              Read original on SEC.gov ↗
            </a>
          )}
        </>
      ) : (
        <p>No annual filing cached.</p>
      )}
    </div>
  );
}
export default async function CompanyPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const company = await companyData((await params).ticker);
  if (!company) notFound();
  const entries = await searchIndex();
  return (
    <article className="company-page">
      <div className="company-topline">
        <Link className="text-link" href="/">
          ← All companies
        </Link>
        <CompanySearch entries={entries} compact />
      </div>
      <header className="company-heading">
        <p className="eyebrow">
          {company.ticker} / {company.sector} / ITEM {company.item}
        </p>
        <h1>{company.name}</h1>
        <p className="company-dek">A closer reading of what changed.</p>
        <span className="preview-label">
          LOCAL PREVIEW · Latest cached annual filings
        </span>
      </header>
      <div className="filing-pair">
        <FilingSource filing={company.prior} label="PRIOR FILING" />
        <span className="pair-arrow" aria-hidden="true">
          →
        </span>
        <FilingSource filing={company.current} label="CURRENT FILING" />
      </div>
      {company.status === "ready" && company.diff_url ? (
        <>
          <section
            className="comparison-overview"
            aria-label="Comparison overview"
          >
            <div>
              <p className="eyebrow">THE LANGUAGE, YEAR OVER YEAR</p>
              <h2>What changed in Risk Factors</h2>
              <p>
                Follow each change back to the annual reports. Matches are
                automated; split or merged risks can appear as additions and
                removals.
              </p>
            </div>
            <div className="structural-counts">
              {(["added", "removed", "modified", "unchanged"] as const).map(
                (kind) => (
                  <div key={kind}>
                    <strong>{company.counts?.[kind] ?? 0}</strong>
                    <span>{kind}</span>
                  </div>
                ),
              )}
            </div>
          </section>
          {company.flags.length > 0 && (
            <p className="notice">
              This filing pair has review notes. Check the original reports for
              period or amendment differences.
            </p>
          )}
          <DiffView company={company} />
        </>
      ) : (
        <section className="notice company-empty">
          <p className="eyebrow">FILING STATUS</p>
          <h2>
            {company.status === "first_filing"
              ? "The first chapter starts here."
              : company.status === "review_required"
                ? "This comparison needs a closer read."
                : "No new annual filing in this preview yet."}
          </h2>
          <p>
            {company.status === "first_filing"
              ? "There is no prior annual filing to compare. Read the current report above."
              : company.status === "review_required"
                ? "We couldn't parse or compare this filing cleanly. The original filings are linked above while it awaits review."
                : "A comparison will appear after an annual filing and its prior-year report are available and checked."}
          </p>
        </section>
      )}
      <aside className="reading-note">
        <strong>A reading aid, not a rating.</strong> Counts describe changes in
        language. Scores and verified summaries are being prepared separately.{" "}
        <Link href="/methodology/">Read the methodology ↗</Link>
      </aside>
    </article>
  );
}
