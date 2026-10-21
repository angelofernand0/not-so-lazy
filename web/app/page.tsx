import Link from "next/link";
import meta from "../public/site/meta.json";

export default function Home() {
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
        <div className="search-preview">
          <span aria-hidden="true">⌕</span>
          <label className="sr-only" htmlFor="company-search">
            Company search, available after the first backfill
          </label>
          <input
            id="company-search"
            placeholder="Search a company or ticker"
            disabled
          />
          <span className="keycap">SOON</span>
        </div>
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
            We’re preparing the first S&P 500 backfill. Once filings have been
            processed and checked, you’ll see the companies whose risk language
            changed most.
          </p>
          <span className="status-line">
            {meta.filing_count} filings published · No rankings available yet
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
