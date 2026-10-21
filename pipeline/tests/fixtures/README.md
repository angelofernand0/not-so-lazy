# Fixtures

`aapl-annual-submissions.json` contains saved real SEC submissions rows for the
Apple 2025 and 2024 10-Ks, with its source URL. The fixture omits unrelated forms
and history shards deliberately. Other discovery/client tests use explicitly
synthetic data with mocked HTTP transport. Tests cannot open network sockets.

Real HTML fixtures and labeled extraction anchors arrive in Milestone 3.
