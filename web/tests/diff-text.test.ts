import assert from "node:assert/strict";
import test from "node:test";
import { pieces, isChanged } from "../lib/diff-text.ts";
import type { Factor, Span } from "../lib/types.ts";

test("Python code-point ranges preserve emoji and non-Latin characters", () => {
  const spans: Span[] = [
    { op: "equal", prior: [0, 2], current: [0, 2], trivial: false },
    { op: "insert", prior: null, current: [2, 4], trivial: false },
    { op: "equal", prior: [2, 3], current: [4, 5], trivial: false },
  ];
  assert.deepEqual(pieces("a🧠新年b", spans, "current", false), [
    { text: "a🧠", change: null },
    { text: "新年", change: "insert" },
    { text: "b", change: null },
  ]);
  assert.equal(
    pieces("a🧠b", spans, "prior", false)
      .map((p) => p.text)
      .join(""),
    "a🧠b",
  );
});
test("trivial toggle changes highlighting without hiding original dates", () => {
  const spans: Span[] = [
    { op: "equal", prior: [0, 11], current: [0, 11], trivial: true },
  ];
  assert.deepEqual(pieces("fiscal 2025", spans, "current", false), [
    { text: "fiscal 2025", change: null },
  ]);
  assert.equal(
    pieces("fiscal 2025", spans, "current", true)[0].change,
    "trivial",
  );
  const factor = { change_type: "unchanged", diff: { ops: spans } } as Factor;
  assert.equal(isChanged(factor, false), false);
  assert.equal(isChanged(factor, true), true);
});
test("invalid or incomplete offsets fail instead of dropping evidence", () => {
  const op: Span = {
    op: "equal",
    prior: [0, 1],
    current: [0, 1],
    trivial: false,
  };
  assert.throws(() => pieces("abc", [op], "prior", false));
  assert.throws(() => pieces("a", [{ ...op, prior: [1, 2] }], "prior", false));
  assert.throws(() => pieces("a", [{ ...op, prior: [0, 2] }], "prior", false));
});
