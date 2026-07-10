<!-- ---
!-- Timestamp: 2026-04-10 15:58:06
!-- Author: ywatanabe
!-- File: /home/ywatanabe/proj/claude-code-telegrammer/GITIGNORED/TODO.md
!-- --- -->

## Checklist
### Telegram Official Plugin
- [x] MUST NOT BE USED — tools denied in settings.json
- [x] MUST BE DISABLED — set to false in enabledPlugins
- [x] MUST TO BE DISABLED TO INSTALL — removed from installed_plugins.json, cache deleted

### Health Checker
- [x] `bin/telegrammer-health` — 5-point check with `--fix` auto-remediation
- [x] Wired into `telegrammer-hook pre-start` (runs on every agent boot)
- [x] Registered as `telegrammer-health` console script in pyproject.toml

### Backlog (not active — pull when prioritised)
- [ ] **agent_id → bot icon/emoji mapping in bridge** (lead, 2026-06-12, spin-off from op-2026-06-12-12-telegram-icons): cache or derive a per-`agent_id` visual marker (emoji or short tag) so inbound/outbound rendering can prefix messages with the originating agent's identity. Use cases: fleet operator routing fewer-bot multiplex chats; complements `signature.ts` (already has account/quota enrichment). Likely scope: small `ts/lib/identity.ts` + opt-in env flag, no schema change. Defer until lead requests.

<!-- hook-bypass: branch-guard (GITIGNORED file, safe to edit on develop) -->
<!-- EOF -->