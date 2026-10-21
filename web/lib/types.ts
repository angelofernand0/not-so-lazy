export type CompanyStatus =
  | "ready"
  | "first_filing"
  | "review_required"
  | "awaiting_filing";
export type SearchEntry = {
  ticker: string;
  cik: number;
  name: string;
  sector: string;
  aliases: string[];
  status: CompanyStatus;
};
export type Filing = {
  accession: string;
  form: string;
  filed_at: string;
  report_date: string | null;
  fiscal_year: number | null;
  source_url: string | null;
};
export type Change = "added" | "removed" | "modified" | "moved" | "unchanged";
export type CompanyData = SearchEntry & {
  schema_version: number;
  item: string;
  flags: string[];
  current: Filing | null;
  prior: Filing | null;
  counts: Partial<Record<Change, number>> | null;
  diff_url: string | null;
  diff_sha256: string | null;
};
export type Unit = {
  id: string;
  heading: string;
  body: string;
  text: string;
  group: string;
  segmentation: "heading" | "paragraph";
  role: string;
  position: number;
  start: number;
  end: number;
};
export type Span = {
  op: "equal" | "insert" | "delete";
  prior: [number, number] | null;
  current: [number, number] | null;
  trivial: boolean;
};
export type Factor = {
  prior_id: string | null;
  current_id: string | null;
  prior: Unit | null;
  current: Unit | null;
  method: string;
  similarity: number | null;
  change_type: Change;
  moved: boolean;
  diff: { ops: Span[]; prior_masks: unknown[]; current_masks: unknown[] };
};
export type DiffData = {
  schema_version: number;
  pair_id: string;
  item: string;
  factors: Factor[];
  context: { prior: Unit[]; current: Unit[] };
};
