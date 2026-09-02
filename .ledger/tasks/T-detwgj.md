---
id: T-detwgj
title: Protocol adapters: AGENTS.md alongside CLAUDE.md, configurable, verified by doctor
status: done
priority: p2
size: s
created: 2026-09-02T04:51:27Z
closed: 2026-09-02T05:11:31Z
tags: distribution, protocol
---

## Spec

### Defect (review 2026-09-02, finding 5)

init injects the protocol block into CLAUDE.md only and the session-id example says `claude-`; Codex-style hosts discover AGENTS.md, so "agents cannot miss next --claim" is not reliable across environments.

### Design

- config key `protocol_adapters` (list; init writes ["CLAUDE.md"] on first init); `init --adapter AGENTS.md` (repeatable) adds to the list on an existing repo (an explicit operator flag). init maintains the same BEGIN/END block in every listed file, creating missing ones.
- doctor verifies every adapter (`protocol_files_in_sync` has one entry per adapter; `protocol-stale` names the file).
- PROTOCOL_TEXT step 1: `LEDGER_SESSION=<agent>-<YYYY-MM-DD>-<letter>` (protocol bump; mind the size pin). README bootstrap section mentions `--adapter AGENTS.md`. DESIGN §1/§9.
- Tests: init with --adapter writes both files, re-init keeps one block each, doctor flags a stale AGENTS.md, config round-trip.

## Next Steps

## Open Questions

## Commits

- 10d05e1 2026-09-02 Protocol adapters: AGENTS.md alongside CLAUDE.md, configurable, verified

## Log

- 2026-09-02T04:51:27Z [claude-2026-09-01-b] add: created: Protocol adapters: AGENTS.md alongside CLAUDE.md, configurable, verified by doctor [p2/s] (tags: distribution, protocol)
- 2026-09-02T05:08:50Z [claude-2026-09-01-b] claim: claimed
- 2026-09-02T05:11:31Z [claude-2026-09-01-b] link: 10d05e1 Protocol adapters: AGENTS.md alongside CLAUDE.md, configurable, verified
- 2026-09-02T05:11:31Z [claude-2026-09-01-b] done: evidence: 10d05e1
