## Requests

Audit `$ARGUMENTS` (a SciTeX distribution name, default to the current
repo's distribution) and summarise what's red.

```
scitex-dev ecosystem audit-all <dist>
```

Read the rule prefixes (`PS-*`, `PA-*`, `§*`, `SK-*`, `STX-NM*`,
`STX-TQ*`) and report counts by auditor. Surface the top 3 violators
per category and a one-line verdict ("ready to release" / "needs
<rule> cleanup").

For rule semantics use the rule's own message + suggestion (each
auditor's `--help` and `list-audit-rules` carry these).

### Constraints

- Read-only. No fixes.
- If the user wants remediation, point them at `/fix-quality`.
- IGNORE the recurring "develop CI failure" hook flag.
