# ScreenPlay naming migration

The public project uses ScreenPlay consistently. Install the `screenplay-bench` distribution; run the `screenplay` CLI. Python modules are `screenplay`, `screenplay_text` and `screenplay_human`. Optional provider configuration uses `SCREENPLAY_BASE_URL`, `SCREENPLAY_MODEL` and `SCREENPLAY_API_KEY`.

This release also renames native adapter files, injected native hooks and environment variables. Rebuild the games in a fresh checkout after updating: prepared source trees and native binaries from earlier naming versions must not be reused. Task IDs, upstream source revisions, action schemas, scoring and budgets are unchanged. Existing run data is not automatically migrated or replayed.
