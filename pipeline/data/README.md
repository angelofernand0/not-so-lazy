# Constituent snapshot

`sp500.csv` records ticker, company name, GICS sector and SEC CIK.
`sp500.meta.json` records source URLs, retrieval time, security and issuer counts,
code version and the SHA-256 of CSV bytes. The current snapshot has 503 securities
for 500 issuers and every CIK was cross-checked with the SEC ticker map.

Refresh from `pipeline/` with `uv run nsl universe refresh` after setting the
required SEC identity. Any mismatch aborts without changing the CSV. Duplicate
share classes keep their source tickers but map to one CIK in the database.
Raw HTML, HTTP caches, rate-limit state and local databases are ignored here.
