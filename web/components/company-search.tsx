"use client";
import Link from "next/link";
import { useId, useState } from "react";
import { useRouter } from "next/navigation";
import type { SearchEntry } from "../lib/types";

export default function CompanySearch({
  entries,
  compact = false,
}: {
  entries: SearchEntry[];
  compact?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(-1);
  const [open, setOpen] = useState(false);
  const id = useId();
  const router = useRouter();
  const term = query.trim().toLowerCase().replaceAll(".", "-");
  const results = entries
    .filter((entry) =>
      `${entry.ticker} ${entry.name} ${entry.aliases.join(" ")}`
        .toLowerCase()
        .replaceAll(".", "-")
        .includes(term),
    )
    .sort(
      (a, b) =>
        Number(b.ticker.toLowerCase() === term) -
          Number(a.ticker.toLowerCase() === term) ||
        a.ticker.localeCompare(b.ticker),
    )
    .slice(0, 7);
  const visible = open && term.length > 0;
  return (
    <div
      className={`company-search ${compact ? "compact-search" : ""}`}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
    >
      <div className="search-preview">
        <span aria-hidden="true">⌕</span>
        <label className="sr-only" htmlFor={id}>
          Search companies
        </label>
        <input
          id={id}
          placeholder="Search a company or ticker"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={visible}
          aria-controls={`${id}-results`}
          aria-activedescendant={
            visible && active >= 0 && results[active]
              ? `${id}-${active}`
              : undefined
          }
          autoComplete="off"
          value={query}
          onFocus={() => setOpen(true)}
          onChange={(event) => {
            setQuery(event.target.value);
            setActive(-1);
            setOpen(true);
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setOpen(false);
              setActive(-1);
            }
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
              event.preventDefault();
              setOpen(true);
              setActive((index) =>
                Math.max(
                  0,
                  Math.min(
                    results.length - 1,
                    index + (event.key === "ArrowDown" ? 1 : -1),
                  ),
                ),
              );
            }
            if (event.key === "Enter" && results[active >= 0 ? active : 0]) {
              event.preventDefault();
              router.push(`/c/${results[active >= 0 ? active : 0].ticker}/`);
              setOpen(false);
            }
          }}
        />
        <span className="keycap" aria-hidden="true">
          ↵
        </span>
      </div>
      {visible && (
        <div className="search-results">
          <ul
            id={`${id}-results`}
            role="listbox"
            aria-label="Matching companies"
          >
            {results.map((entry, index) => (
              <li
                key={entry.ticker}
                id={`${id}-${index}`}
                role="option"
                aria-selected={index === active}
              >
                <Link
                  href={`/c/${entry.ticker}/`}
                  onPointerDown={(event) => event.preventDefault()}
                  onClick={() => setOpen(false)}
                >
                  <strong>{entry.ticker}</strong>
                  <span>{entry.name}</span>
                  <small>
                    {entry.status === "ready"
                      ? "Compare ↗"
                      : "Filing status ↗"}
                  </small>
                </Link>
              </li>
            ))}
          </ul>
          {results.length === 0 && (
            <p role="status">
              No match in this {entries.length}-company preview. Try AAPL or
              MSFT.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
