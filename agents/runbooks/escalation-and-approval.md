# Escalation and human approval

Not every fix should auto-apply. Policy:

- **Auto-fix (whitelisted, low-risk):** restoring a known config value to its
  documented healthy baseline (e.g. `db_pool_available` -> 10, `edit_save_route`
  -> edit.save) may be applied automatically after the Verifier's pre-check.
- **Human approval required:** anything touching data-bearing config
  (`user_store_path`) or a value not matching a documented baseline, or when the
  two Investigators disagree and confidence is low.

The Verifier runs a health check BEFORE and AFTER any fix and gates auto vs
human-approval accordingly. When in doubt, request approval.
