## Requests

Apply the SciTeX no-mocks + test-quality migration to `$ARGUMENTS` (a
SciTeX distribution name, default to current repo).

Canonical playbook:
`<scitex-dev>/src/scitex_dev/_skills/general/05_development/09_ecosystem-tq-migration.md`

Four passes, in order: NM → TQ003 → TQ002 → TQ007.

Per-pass verification:

```
scitex-linter check-files <repo>/tests --no-color | awk '/STX-<RULE>/' | wc -l
```

Final gate:

```
scitex-dev ecosystem audit-python-apis <dist>   # → SUCC: exit 0
pytest tests/ -q -p no:randomly                  # all pass
pytest tests/ -q                                 # random order surfaces ordering bugs
```

### Constraints

- DO NOT use `# stx-allow:` to suppress.
- DO NOT change production code unless required for testability.
- DO NOT delete tests — split them.
- DO NOT commit; user reviews.
- IGNORE the recurring "develop CI failure" hook flag.
