import type { Metadata } from "next";
export const metadata: Metadata = { title: "Methodology" };
export default function Methodology() {
  return (
    <article className="document">
      <p className="eyebrow">SHOW YOUR WORK</p>
      <h1>Every change needs a source.</h1>
      <p className="lead">
        Our intended methodology, and what still needs to be validated.
      </p>
      <div className="notice">
        Development preview. No filing comparisons, scores, or AI summaries have
        been published.
      </div>
      <h2>Start with the original.</h2>
      <p>
        The pipeline will compare Item 1A, Risk Factors, in a company’s latest
        10-K with its prior fiscal year’s annual report, sourced from{" "}
        <a href="https://www.sec.gov/edgar/search/">SEC EDGAR</a>. Companies are
        keyed by CIK to handle ticker changes and multiple share classes.
      </p>
      <h2>Measure language change.</h2>
      <p>
        The planned headline measure is one minus cosine similarity of
        word-frequency vectors, after removing standard stop words and masking
        trivial fiscal-year updates. Percentiles will compare filings whose
        fiscal years end in the same calendar year. Reordering alone will not
        count as language change.
      </p>
      <h2>Keep the evidence visible.</h2>
      <p>
        Diffs will preserve the original words and link to both filings.
        Optional AI summaries must include quotes verified against their source
        factors. Comparisons that fail extraction checks will be held for
        review.
      </p>
      <h2>Research context.</h2>
      <p>
        The name refers to Cohen, Malloy, and Nguyen’s <cite>Lazy Prices</cite>,
        Journal of Finance (2020). The product uses this as research context;
        its scores are not trading signals or predictions of returns.{" "}
        <a href="https://doi.org/10.1111/jofi.12885">Read the paper ↗</a>
      </p>
      <h2>Known limits and update cadence.</h2>
      <p>
        Formatting, split headings, amendments, transition periods, and changes
        in segmentation can affect comparisons. Extraction accuracy, alignment
        accuracy, and correlation with the Brain dataset have not yet been
        measured. Planned cadence: daily ingestion and weekly publication on
        Sundays.
      </p>
    </article>
  );
}
