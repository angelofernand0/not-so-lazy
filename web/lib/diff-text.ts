import type { Factor, Span } from "./types";

export type Piece = {
  text: string;
  change: "insert" | "delete" | "trivial" | null;
};
export function pieces(
  text: string,
  ops: Span[],
  side: "prior" | "current",
  trivial: boolean,
): Piece[] {
  // Python stores Unicode code-point offsets. JS string.slice uses UTF-16.
  const points = Array.from(text);
  let cursor = 0;
  const result: Piece[] = [];
  for (const op of ops) {
    const range = op[side];
    if (!range) continue;
    const [start, end] = range;
    if (
      !Number.isInteger(start) ||
      !Number.isInteger(end) ||
      start !== cursor ||
      end <= start ||
      end > points.length
    )
      throw new Error("Invalid comparison offsets");
    result.push({
      text: points.slice(start, end).join(""),
      change: op.trivial
        ? trivial
          ? "trivial"
          : null
        : op.op === "equal"
          ? null
          : op.op,
    });
    cursor = end;
  }
  if (cursor !== points.length) throw new Error("Incomplete comparison text");
  return result;
}
export function isChanged(factor: Factor, trivial: boolean): boolean {
  return (
    factor.change_type !== "unchanged" ||
    (trivial && factor.diff.ops.some((op) => op.trivial))
  );
}
