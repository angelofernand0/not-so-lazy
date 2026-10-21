import type { Metadata } from "next";
import Link from "next/link";
export const metadata: Metadata = { title: "Biggest changers" };
export default function Leaderboard() {
  return (
    <article className="document">
      <p className="eyebrow">THE CHANGE REPORT</p>
      <h1>Biggest changers</h1>
      <p className="lead">How much the language changed.</p>
      <div className="notice">
        <h2>No rankings published yet.</h2>
        <p>
          The first S&P 500 backfill is still being prepared. Weekly and
          season-to-date rankings will appear after filing comparisons pass
          validation.
        </p>
      </div>
      <p>
        Rankings will measure changes in Risk Factors language. They do not
        measure business quality or predict returns.
      </p>
      <Link className="text-link" href="/methodology/">
        Read the methodology ↗
      </Link>
    </article>
  );
}
