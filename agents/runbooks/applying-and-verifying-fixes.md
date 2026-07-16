# Applying and verifying a fix

1. Diagnose: settle on one setting and its correct value (log + config + health).
2. Apply: `fix.apply(setting, value)` writes the corrected value to the patient's
   real config (`app_settings`). It only accepts the six whitelisted settings.
3. Verify: run `healthcheck.run`. "Fixed" means EVERY watched page is green again,
   which also catches a fix that broke something else.
4. Never repair a symptom by editing anything other than `app_settings`, and never
   touch the fault registry — that would be cheating, not fixing.

A fix that doesn't turn `/health` fully green is not a fix; re-diagnose.
