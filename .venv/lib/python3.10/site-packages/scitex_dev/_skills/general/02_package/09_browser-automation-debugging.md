---
description: |
  [TOPIC] Always-on debug capture for Playwright browser automation
  [DETAILS] Browser automation is fundamentally unreliable: selectors drift, SSO flows mutate, MFA pages change shape between vendor releases. The rule: every decision point in a Playwright automation MUST capture a screenshot AND the page HTML via `scitex_browser.debugging.capture_debug_artifacts_async`. The pair is what makes "the locator picked the wrong row" debuggable after the fact.
tags: [scitex-general-package-browser-automation-debugging]
---

# Browser-automation debugging — always-on capture

## The rule

Any code path that drives a Playwright `Page` MUST capture a screenshot
**and** the page HTML at every decision point — before/after each click,
form fill, navigation, or state transition. Use the canonical helper:

```python
from scitex_browser.debugging import capture_debug_artifacts_async

await capture_debug_artifacts_async(
    page,
    label="<short_descriptor>",        # e.g. "mfa_picker_before"
    base_dir=None,                     # default: ~/.scitex/browser/cache/debug/
    full_page=True,
    include_html=True,
)
```

`base_dir` may be overridden when the calling package wants its own
cache hierarchy (e.g. scitex-scholar uses
`~/.scitex/scholar/cache/engine/screenshots/`).

## Why both image and HTML

Image alone tells you what was rendered. HTML alone tells you what the
locator was reasoning over. Almost every selector regression in the
2026-05-06 SSO investigation needed BOTH to diagnose:

- Screenshot proved which Select button was visually clicked.
- HTML revealed that `div:has-text('Get a push notification')` matched
  the OUTER container that also contained "Enter a code" — making
  `.first` resolve to the top row's Select.

Without the HTML, the fix was a guess. With it, the fix was mechanical.

## Where to capture

At minimum, capture:

1. **On entry** to any multi-step flow (so you have the starting state
   even if the first action succeeds and you only debug a later step).
2. **Before** each non-trivial click / fill / navigation (input shape
   may change between page loads).
3. **After** each successful click whose outcome is a navigation or
   significant DOM change — confirms the action actually advanced
   state, not just resolved silently.
4. **On every failure path** — including no-match-found branches and
   timeout handlers.

For a 5-step SSO flow, expect ~10–15 capture calls. The volume isn't
the cost; missing the one screenshot you needed at 3am is.

## Capture is non-fatal

`capture_debug_artifacts_async` swallows all exceptions and logs at
debug level. A failed capture must NEVER break the calling flow. If
disk is full, permissions are wrong, or the page has navigated away
mid-screenshot, the automation continues.

## Naming convention for `label`

`<flow>_<step>_<phase>` — e.g.

- `sso_password_before` / `sso_password_after`
- `mfa_picker_before` / `mfa_picker_after_push` / `mfa_picker_no_match`
- `openathens_institution_select_before`
- `pdf_download_click_before` / `pdf_download_click_after`

The label is sanitized (non-alphanum → `_`) before becoming part of
the filename, so spaces/punctuation in labels are tolerated but
discouraged.

## File layout

Default base_dir → `~/.scitex/browser/cache/debug/`:

```
<label>_<YYYYMMDD_HHMMSS_microsec>.png
<label>_<YYYYMMDD_HHMMSS_microsec>.html
```

The microsecond suffix on the timestamp prevents collisions when
multiple captures fire within the same second (common — every step
of a fast automation).

## Override the cache location per-package

When a package has its own state directory (e.g. scitex-scholar uses
`~/.scitex/scholar/cache/engine/screenshots/`), pass `base_dir`:

```python
from pathlib import Path
from scitex_browser.debugging import capture_debug_artifacts_async

await capture_debug_artifacts_async(
    page,
    label="sso_mfa_picker_before",
    base_dir=Path.home() / ".scitex" / "scholar" / "cache" / "engine" / "screenshots",
)
```

Keep all artifacts for one package in one directory — debugging means
listing one folder, not chasing files across the home dir.

## Anti-patterns

❌ **Capturing only on failure.** "We'll add a screenshot if it
breaks." If you only capture on the failure path, you have no baseline
showing what success used to look like — diffing past-success vs
current-failure is what locates regressions.

❌ **Screenshot without HTML.** The image shows symptom; the HTML
shows cause. Always include HTML unless you have a measured reason
not to.

❌ **Per-class one-off helpers.** Every PR that adds Playwright
automation must use the canonical helper from
`scitex_browser.debugging`. If your package has a
`_save_debug_screenshot_async` method on a class, replace it with
the shared call. (Per-class helpers were the pre-2026-05-06 state
in scitex-scholar's SSO automator and led to image-only artifacts
that couldn't diagnose locator misuse.)

❌ **Bundled try/except that silences the capture.** The helper
already swallows failures with debug-level logging. Wrapping the
helper call in your own try/except hides the debug log line and
makes capture failures invisible.

## Audit / enforcement

- Currently advisory. A future audit-cli or audit-quality rule will
  scan for `from playwright.async_api` imports and require at least
  one `capture_debug_artifacts_async` call in the same module.
- For now: every PR adding or modifying browser automation must
  include capture calls at the decision points described above.
  Reviewers should reject PRs whose screenshots-only artifacts make
  selector regressions undiagnosable.

## See also

- `scitex_browser.debugging._capture_debug` — implementation.
- `scitex_browser.debugging.save_failure_artifacts` — sync,
  pytest-fixture-oriented variant for test scaffolds.
- `scitex_browser.debugging.browser_logger` — overlay that prints log
  text into the live browser (visual confirmation while debugging
  interactively).
