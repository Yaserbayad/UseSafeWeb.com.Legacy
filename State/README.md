# UseSafeWeb state split — revision 50

This directory archives state detail so the authoritative checkpoint remains small enough for the normal GitHub connector. It does not modify the frozen Master Plan/WBS.

- `archive/CURRENT_STATE_REV49_FULL.json`: exact pre-migration checkpoint/rollback copy.
- `archive/DONE_ARCHIVE_REV50.json`: full completed/PASS records.
- `open/TODO_REV50.json`, `open/WAITING_REV50.json`, `open/BLOCKED_REV50.json`: read-only state shards with full source detail.
- `candidate/CURRENT_STATE_REV50_COMPACT.json`: proposed authoritative checkpoint.
- `MANIFEST_REV50.json`: counts, hashes, authorization, and preservation assertions.

Only `CURRENT_STATE.md` on `main` is authoritative after qualified promotion. These archive/shard files preserve detail and recovery evidence; they do not independently control project state.
