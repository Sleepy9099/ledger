---
id: T-otkmmt
title: init from the vendored copy must say the tool was not copied
status: done
priority: p2
size: xs
created: 2026-09-02T08:54:44Z
closed: 2026-09-02T09:16:31Z
tags: distribution
---

## Spec

### Defect (heavy-session feedback 2026-09-02, #3; verified)

`cmd_init` copies the script only when `dest_script.resolve() != script`, so `python .ledger/ledger.py init` regenerates scaffolding around the OLD tool and says nothing. The result JSON has no field about the copy.

### Design

`tool_copied: true|false` in the init result plus a human line (`tool: copied from <path>` / `tool: unchanged — running the vendored copy; run init from the newer ledger.py to re-vendor`). No warning severity (regenerating protocol files from the vendored copy is the normal flow); `doctor`'s `vendored-stale` remains the drift detector. The `protocol-stale` fix_hint keeps `python .ledger/ledger.py init` (correct for regeneration); the `schema-mismatch` hint already names `<newer>/ledger.py`. Test: init from the vendored copy reports false; init from an upstream file reports true and updates the vendored version.

## Next Steps

## Open Questions

## Commits

- 62fd891 2026-09-02 init reports tool_copied; linked-never-claimed names the live remedy; scan --exempt-policy-preview is the dry run before the switch

## Log

- 2026-09-02T08:54:44Z [claude-2026-09-01-b] add: created: init from the vendored copy must say the tool was not copied [p2/xs] (tags: distribution)
- 2026-09-02T09:12:54Z [claude-2026-09-01-b] claim: claimed
- 2026-09-02T09:16:31Z [claude-2026-09-01-b] link: 62fd891 init reports tool_copied; linked-never-claimed names the live remedy; scan --exempt-policy-preview is the dry run before the switch
- 2026-09-02T09:16:31Z [claude-2026-09-01-b] done: evidence: 62fd891
