"use client";
import { useEffect, useState } from "react";
import { isChanged, pieces } from "../lib/diff-text";
import type { CompanyData, DiffData, Factor, Span } from "../lib/types";

function HighlightedText({
  text,
  ops,
  side,
  trivial,
}: {
  text: string;
  ops: Span[];
  side: "prior" | "current";
  trivial: boolean;
}) {
  return (
    <div className="diff-prose">
      {pieces(text, ops, side, trivial).map((piece, index) => {
        if (piece.change === "insert")
          return (
            <ins key={index}>
              <span className="diff-marker" aria-hidden="true">
                +
              </span>
              <span className="sr-only">Added: </span>
              {piece.text}
            </ins>
          );
        if (piece.change === "delete")
          return (
            <del key={index}>
              <span className="diff-marker" aria-hidden="true">
                −
              </span>
              <span className="sr-only">Removed: </span>
              {piece.text}
            </del>
          );
        if (piece.change === "trivial")
          return (
            <mark
              key={index}
              title="Fiscal year or report-date update"
              className="trivial-change"
            >
              {piece.text}
            </mark>
          );
        return <span key={index}>{piece.text}</span>;
      })}
    </div>
  );
}
function validate(data: DiffData, company: CompanyData) {
  if (
    data.schema_version !== 1 ||
    data.pair_id !== company.current?.accession ||
    data.item !== company.item ||
    !Array.isArray(data.factors)
  )
    throw new Error("Comparison does not match this filing");
  for (const factor of data.factors) {
    if (
      !["added", "removed", "modified", "moved", "unchanged"].includes(
        factor.change_type,
      ) ||
      !Array.isArray(factor.diff?.ops)
    )
      throw new Error("Invalid comparison");
    for (const side of ["prior", "current"] as const) {
      const unit = factor[side];
      if (
        unit &&
        (typeof unit.text !== "string" ||
          typeof unit.heading !== "string" ||
          typeof unit.group !== "string")
      )
        throw new Error("Invalid risk text");
      pieces(unit?.text ?? "", factor.diff.ops, side, false);
    }
  }
}
export default function DiffView({ company }: { company: CompanyData }) {
  const [data, setData] = useState<DiffData | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [changedOnly, setChangedOnly] = useState(true);
  const [trivial, setTrivial] = useState(false);
  const [group, setGroup] = useState("");
  const [kind, setKind] = useState("all");
  const [allOpen, setAllOpen] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setError(false);
      setData(null);
      try {
        if (!company.diff_url?.startsWith("/site/diffs/"))
          throw new Error("Missing comparison");
        const response = await fetch(company.diff_url, {
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("Comparison unavailable");
        const raw = await response.text();
        const hash = await crypto.subtle.digest(
          "SHA-256",
          new TextEncoder().encode(raw),
        );
        const sha = Array.from(new Uint8Array(hash))
          .map((value) => value.toString(16).padStart(2, "0"))
          .join("");
        if (sha !== company.diff_sha256)
          throw new Error("Comparison checksum mismatch");
        const payload: DiffData = JSON.parse(raw);
        validate(payload, company);
        if (!controller.signal.aborted) setData(payload);
      } catch {
        if (!controller.signal.aborted) setError(true);
      }
    }
    void load();
    return () => controller.abort();
  }, [company, attempt]);
  if (error)
    return (
      <section className="notice">
        <h2>The comparison could not be loaded.</h2>
        <p>Please try again, or use the original SEC filings above.</p>
        <button
          className="quiet-button"
          onClick={() => setAttempt(attempt + 1)}
        >
          Try again
        </button>
      </section>
    );
  if (!data)
    return (
      <p className="loading-comparison" role="status">
        Loading the source-linked comparison…
      </p>
    );
  const groups = Array.from(
    new Set(
      data.factors
        .flatMap((factor) => [factor.current?.group, factor.prior?.group])
        .filter((value): value is string => Boolean(value)),
    ),
  );
  const visible = data.factors.filter(
    (factor) =>
      (!changedOnly || isChanged(factor, trivial)) &&
      (!group ||
        factor.current?.group === group ||
        factor.prior?.group === group) &&
      (kind === "all" || factor.change_type === kind),
  );
  const context = data.context;
  return (
    <section className="diff-section" aria-label="Risk factor comparison">
      <div className="diff-toolbar">
        <div className="toggle-controls">
          <label>
            <input
              type="checkbox"
              checked={changedOnly}
              onChange={(event) => setChangedOnly(event.target.checked)}
            />{" "}
            Changed only
          </label>
          <label>
            <input
              type="checkbox"
              checked={trivial}
              onChange={(event) => setTrivial(event.target.checked)}
            />{" "}
            Show trivial changes
          </label>
        </div>
        <div className="select-controls">
          <label>
            <span className="sr-only">Risk group</span>
            <select
              value={group}
              onChange={(event) => setGroup(event.target.value)}
              aria-label="Risk group"
            >
              <option value="">All groups</option>
              {groups.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="sr-only">Change type</span>
            <select
              aria-label="Change type"
              value={kind}
              onChange={(event) => setKind(event.target.value)}
            >
              <option value="all">All change types</option>
              {["added", "removed", "modified", "moved", "unchanged"].map(
                (value) => (
                  <option value={value} key={value}>
                    {value[0].toUpperCase() + value.slice(1)}
                  </option>
                ),
              )}
            </select>
          </label>
        </div>
      </div>
      <div className="diff-status">
        <p aria-live="polite">
          Showing {visible.length} of {data.factors.length} risks
        </p>
        <button className="quiet-button" onClick={() => setAllOpen(!allOpen)}>
          {allOpen ? "Collapse all" : "Expand all"}
        </button>
      </div>
      <div className="diff-legend">
        <span>
          <ins>+ Added</ins>
        </span>
        <span>
          <del>− Removed</del>
        </span>
        <span>Year and date rolls are unhighlighted by default.</span>
      </div>
      {visible.length === 0 && (
        <div className="notice">
          <h3>No risks match these filters.</h3>
          <p>
            Try all change types, another group, or turn off “Changed only”.
          </p>
          <button
            className="quiet-button"
            onClick={() => {
              setChangedOnly(false);
              setGroup("");
              setKind("all");
            }}
          >
            Show all risks
          </button>
        </div>
      )}
      {visible.map((factor, index) => (
        <Risk
          key={`${factor.prior_id}-${factor.current_id}-${allOpen}`}
          factor={factor}
          index={index}
          open={allOpen}
          trivial={trivial}
          priorYear={company.prior?.fiscal_year}
          currentYear={company.current?.fiscal_year}
        />
      ))}
      {context &&
        (context.prior?.length > 0 || context.current?.length > 0) && (
          <details className="context-panel">
            <summary>Read introductory text and risk summaries</summary>
            <p className="caption">
              These passages are retained as context and excluded from
              individual risk matching.
            </p>
            <div className="side-by-side">
              {(["prior", "current"] as const).map((side) => (
                <div key={side}>
                  <h3>
                    {side === "prior" ? "Prior filing" : "Current filing"}
                  </h3>
                  {context[side].map((unit) => (
                    <p className="context-text" key={unit.id}>
                      {unit.text}
                    </p>
                  ))}
                </div>
              ))}
            </div>
          </details>
        )}
    </section>
  );
}
function Risk({
  factor,
  index,
  open,
  trivial,
  priorYear,
  currentYear,
}: {
  factor: Factor;
  index: number;
  open: boolean;
  trivial: boolean;
  priorYear: number | null | undefined;
  currentYear: number | null | undefined;
}) {
  const heading = factor.current?.heading || factor.prior?.heading;
  const fallback = (factor.current?.text || factor.prior?.text || "").slice(
    0,
    180,
  );
  return (
    <details
      className={`risk-card risk-${factor.change_type}`}
      open={open}
      id={`risk-${factor.current_id ?? factor.prior_id}`}
    >
      <summary>
        <div className="risk-number">{String(index + 1).padStart(2, "0")}</div>
        <div className="risk-title">
          <div className="risk-tags">
            <span className={`badge badge-${factor.change_type}`}>
              {factor.change_type}
            </span>
            {factor.moved && factor.change_type !== "moved" && (
              <span className="badge badge-moved">Moved</span>
            )}
            {factor.current?.group || factor.prior?.group ? (
              <span className="risk-group">
                {factor.current?.group || factor.prior?.group}
              </span>
            ) : null}
          </div>
          <h3>
            {heading || `${fallback}${fallback.length === 180 ? "…" : ""}`}
          </h3>
          {!heading && (
            <span className="caption">
              Paragraph comparison · no clear source heading
            </span>
          )}
        </div>
        <span className="disclosure-icon" aria-hidden="true">
          ⌄
        </span>
      </summary>
      <div className="side-by-side">
        {(["prior", "current"] as const).map((side) => (
          <div className={`diff-column ${side}`} key={side}>
            <div className="column-label">
              {side === "prior"
                ? `PRIOR · FY ${priorYear ?? "—"}`
                : `CURRENT · FY ${currentYear ?? "—"}`}
            </div>
            {factor[side] ? (
              <HighlightedText
                text={factor[side].text}
                ops={factor.diff.ops}
                side={side}
                trivial={trivial}
              />
            ) : (
              <p className="absent-factor">
                {side === "prior"
                  ? "+ No matched risk in the prior filing."
                  : "− No matched risk in the current filing."}
              </p>
            )}
          </div>
        ))}
      </div>
      <div className="match-note">
        {factor.method === "embedding"
          ? "Matched by semantic similarity"
          : factor.method === "fuzzy_heading"
            ? "Matched by similar heading"
            : factor.method.startsWith("exact")
              ? "Matched by heading"
              : "No one-to-one match"}
        . Check source reports for context.
      </div>
    </details>
  );
}
