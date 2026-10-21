import Link from "next/link";
import meta from "../public/site/meta.json";
import { searchIndex } from "../lib/site-data";
import CompanySearch from "../components/company-search";

export default async function Home() {
  const entries = await searchIndex();
  return (
    <>
      <section className="hero">
        <div className="eyebrow">
          <span className="dot" /> THE ANNUAL REPORT, BETWEEN THE LINES
        </div>
        <h1>
          Same company.
          <br />
          <em>New risks.</em>
        </h1>
        <p className="dek">
          See what changed in every 10-K. Compare this year’s risk factors with
          last year’s, and get straight to the language that matters.
        </p>
        <CompanySearch entries={entries} />
        <p className="caption">
          Free for curious students. Built for your next stock pitch.
        </p>
        <div className="hero-note">
          <span>01 / RISK FACTORS</span>
          <p>
            Companies update thousands of words.
            <br />
            Start with the ones they changed.
          </p>
        </div>
      </section>
      <section className="edition">
        <div>
          <span className="eyebrow">THE READING ROOM</span>
          <h2>Open a company’s latest comparison</h2>
        </div>
        <span className="caption">
          {entries.length} companies in this preview
        </span>
      </section>
      <div className="company-directory">
        {entries.map((entry) => (
          <Link
            href={`/c/${entry.ticker}/`}
            className="directory-company"
            key={entry.ticker}
          >
            <span className="directory-ticker">{entry.ticker}</span>
            <strong>{entry.name}</strong>
            <span>{entry.sector}</span>
            <small>
              {entry.status === "ready"
                ? "Read the changes ↗"
                : "View filing status ↗"}
            </small>
          </Link>
        ))}
      </div>
      <section className="edition">
        <div>
          <span className="eyebrow">THE CHANGE REPORT</span>
          <h2>Biggest changers</h2>
        </div>
        <Link href="/leaderboard/" className="text-link">
          View leaderboard ↗
        </Link>
      </section>
      <section className="empty-state" aria-labelledby="empty-heading">
        <span className="empty-icon" aria-hidden="true">
          ↔
        </span>
        <div>
          <p className="eyebrow">FIRST EDITION IN PROGRESS</p>
          <h3 id="empty-heading">The next filing season starts here.</h3>
          <p>
            The reading room is open for this preview. Rankings will follow the
            broader S&P 500 backfill and validation of the language-change
            scores.
          </p>
          <span className="status-line">
            {meta.filing_count} annual filings in the local preview · No
            rankings available yet
          </span>
        </div>
      </section>
      <section className="explainer">
        <div>
          <span className="eyebrow">LESS SCROLLING. MORE UNDERSTANDING.</span>
          <h2>
            A year of change,
            <br />
            without a year of reading.
          </h2>
          <Link className="text-link" href="/methodology/">
            How it works ↗
          </Link>
        </div>
        <ol>
          <li>
            <span>01</span>
            <div>
              <h3>Find the differences.</h3>
              <p>
                Read Risk Factors side by side, with added, removed, and
                rewritten language highlighted.
              </p>
            </div>
          </li>
          <li>
            <span>02</span>
            <div>
              <h3>Follow the evidence.</h3>
              <p>Trace changes to the original annual reports on SEC EDGAR.</p>
            </div>
          </li>
          <li>
            <span>03</span>
            <div>
              <h3>Bring it to your pitch.</h3>
              <p>
                Use source-linked context to ask better questions about a
                company.
              </p>
            </div>
          </li>
        </ol>
      </section>
    </>
  );
}
