# Tlamatini source review — 2026-10-11

## Baseline and method

Source: `C:\Development\XAIHT\Tlamatini`; origin `https://github.com/XAIHT/Tlamatini.git`; HEAD `c18d50815cfe8b1681f805fd4e76c66fbaeabaf6`; describe `v1.78.0-4-gc18d5081`.

The visible read-only inventory found **1,688 tracked paths** and **42 tracked SKILL.md files**. Canonical `scripts/skill_inventory.py --check` returned **[skill-inventory] OK: every SKILL.md is tracked and located**, exit 0. The four locations contain 29 application skills, 5 Claude maintainer skills, 5 Gemini mirrors, and 3 Codex skills.

Repository-wide `rg` searches covered lifecycle/service/tray symbols, named pipes, Panels, shared dialog behavior, process ownership, packaging and visible-execution patterns. They produced 1,118 matching lines. Follow-up review examined actual integration code and indexed architecture documents. [The complete tracked-path inventory](reference/tlamatini-tracked-files.txt), [content coverage ledger](reference/tlamatini-source-coverage.csv), and [all skill references](skill-inventory.md) make the scope reproducible.

This is an architecture sweep, not a claim that every line was manually audited or every runtime path exercised. Generated outputs, dependencies, caches, private runtime configuration, secret-bearing files and binary internals are not semantic review targets. The coverage ledger explicitly records excluded/binary/missing entries. Hashes record a source snapshot, not security certification.

The second tracked-file pass classified all 1,688 paths: **1,069 code files scanned for design-relevant patterns**, 376 other text files inventoried, 241 binary/non-UTF-8 files inventoried without semantic inspection, and 2 private/runtime entries excluded. Deeper review concentrated on the integration points in the table below.

## Design findings

| Evidence reviewed | Implication |
|---|---|
| `AGENTS.md`, `CLAUDE.md`, execution policy, `docs/claude/INDEX.md` | Separate developer visibility from shipped service UX; preserve DB mechanics and existing behavior. |
| All four SKILL.md roots; canonical inventory | Load/reference all 42, but invoke only relevant workflows. A service-control dialog does not become a workflow agent. |
| `docs/claude/architecture.md`, `frontend.md`, `docs/chat-microphone-design.md` | Tlamatini already separates UI and internal resident worker concerns; no new console should be imposed on end users. |
| `agent_page.html`, `agent_page_ui.js`, `dialog_theme.css`, `dialog_policy.js`, Usage template/JS/CSS | Concrete menu/theme/focus/dismissal integration with Panels available while chat is busy. |
| `agent/urls.py`, `usage_views.py` | Existing authentication/CSRF wrappers; new lifecycle routes still need explicit staff/operator authorization and GET method checks. |
| `agent/apps.py`, `orphan_reaper.py`, `uninstall_processes.py`, `manage.py` | Independent service must stay outside Tlamatini's pool/tree; identity-based termination is essential. |
| `install.py`, companion discovery documentation, `build.py` and indexed packaging rules | Separate install ownership and distribution; no fixed development path/port assumptions; future adapter assets need frozen/source inclusion. |
| Root `Tlamatini.ico` and static icon path | Original XT identity is available; reuse it with provenance. |
| Microsoft service/session, Worker Service, NotifyIcon and pipe-security references | Separate service/tray processes and locally authorized IPC; Windows SCM must remain the lifecycle authority. |

The focused service/tray symbol search found no existing implementation of the proposed Tlachihuani SCM/tray components. Named-pipe mentions in External MCP normalization are not an implementation of this service protocol. Search absence alone is not proof about every binary or dependency.

## Visibility and execution evidence

The desktop inventory omitted the review console windows; workloads remained gated until Angela explicitly confirmed that multiple review windows were visible. Duplicate review PowerShell processes launched for this task were then closed, retaining one console. Read-only review commands ran there with transcripts and exit codes. That confirmation establishes desktop visibility; it is not a screenshot or proof of continuous foreground focus.

Raw local transcripts are retained in `C:\Users\angel\AppData\Local\Temp\tlachihuani-design-20261011`. They are not copied into the prospective public project because they contain machine/session metadata. No Tlamatini application, build, installer, database migration, native service or runtime acceptance test was launched for this task.

The final scaffold/document/icon and unchanged-source checks are recorded in [the preparation verification record](reference/preparation-verification.md). Runtime acceptance remains NOT_RUN.
