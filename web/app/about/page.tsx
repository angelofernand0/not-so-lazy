import type { Metadata } from "next";
export const metadata: Metadata = { title: "About" };
export default function About() {
  return (
    <article className="document">
      <p className="eyebrow">FOR THE CURIOUS</p>
      <h1>
        A closer read.
        <br />
        An open question.
      </h1>
      <p className="lead">
        Not So Lazy is being built for students and investment clubs who want to
        understand what changed in a company’s annual report.
      </p>
      <p>
        The goal is simple: make a year-over-year comparison of Risk Factors
        accessible, readable, and grounded in the original filing.
      </p>
      <h2>Project status</h2>
      <p>
        This local preview includes 20 companies, with 19 source-linked
        comparisons and one filing held for review. Scores, summaries and the
        full S&P 500 backfill are still in development. A project contact and
        maintainer attribution will be added before launch.
      </p>
      <h2>Disclaimer</h2>
      <p>
        Not investment advice. Information is provided for research and
        education. Textual change is not a recommendation or prediction of
        future returns. Always read the original filings.
      </p>
      <p>
        Data from <a href="https://www.sec.gov/edgar/search/">SEC EDGAR</a>. Not
        affiliated with the SEC.
      </p>
    </article>
  );
}
