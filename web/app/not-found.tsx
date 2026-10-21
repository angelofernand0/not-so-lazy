import Link from "next/link";
export default function NotFound() {
  return (
    <article className="document">
      <p className="eyebrow">404</p>
      <h1>Nothing filed here.</h1>
      <p>This page is unavailable.</p>
      <Link href="/">Return home ↗</Link>
    </article>
  );
}
