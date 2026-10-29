"""Guardrail Manager: owner console for deployment policy templates.

Two layers, kept strictly separate:

- Deployment policy template (owner config): data files a deploying user
  writes and tunes per deployment. Fully editable in this app: edit raw,
  add/remove entries, clear to zero, delete the file, or apply Jay's
  template default. Absent/empty config means no soft blocks, by design.
- Hard floor: hardcoded checks in code (stolen cards, phishing/fraud,
  wallet theft, unauthorized hacking, weapons of mass harm, CSAM,
  doxxing, plus money/approval/scope gates). Listed view-only here.
  This app has no edit/delete mechanism for them, on purpose.
"""
