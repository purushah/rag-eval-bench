# Errata

## Staleness question set (`eval/questions-staleness.json`) — 2026-08-20

A documentation-grounded expert audit (second-provider model given the current official
Apache Flink documentation; 100 sampled answers across all arms, blinded to arm) agreed with
the benchmark's judge on 80% of resolvable rows and preserved the sign of every paper-level
staleness contrast, but flagged nuances in 4 of the 46 gold current/stale rules:

1. **`state.backend` vs `state.backend.type`** — current docs recommend `state.backend.type`
   but still document `state.backend`; answers using the older key are dual-documented, not
   strictly stale.
2. **Queryable State** — removal status is more nuanced than the gold rule's phrasing.
3. **Elasticsearch 8 connector** — connector naming/versioning is decoupled from core Flink
   releases; version-specific claims need the connector docs, not core release notes.
4. **Table API `insertInto`** — the flagged form has a currently-documented equivalent.

Treat per-question labels on these four topics as advisory. Aggregate results are robust to
these rows (removing them changes no conclusion's direction). A revision of the four rules is
planned for the next dataset version.
