import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Not So Lazy — See what changed in every 10-K",
    template: "%s | Not So Lazy",
  },
  description:
    "A free annual-report change tracker for students. Compare Risk Factors year over year, with source-linked evidence.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main">
          Skip to content
        </a>
        <header className="masthead shell">
          <Link href="/" className="brand" aria-label="Not So Lazy home">
            <span className="brand-mark" aria-hidden="true">
              nsl.
            </span>
            Not So Lazy<span className="beta">IN DEVELOPMENT</span>
          </Link>
          <nav aria-label="Main navigation">
            <Link href="/leaderboard/">Biggest changers</Link>
            <Link href="/methodology/">Methodology</Link>
            <Link href="/about/">About</Link>
          </nav>
        </header>
        <main id="main" className="shell">
          {children}
        </main>
        <footer className="shell">
          <span className="footer-name">Read the changes. Find the story.</span>
          <p>
            Not investment advice. Data from SEC EDGAR. Not affiliated with the
            SEC.
          </p>
          <Link href="/methodology/">Sources & methodology ↗</Link>
        </footer>
      </body>
    </html>
  );
}
