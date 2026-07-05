---
description: |
  [TOPIC] Scientific Pdf Reports
  [DETAILS] Library-agnostic standards for generating scientific PDF analysis reports — timestamped filenames, mandatory section structure (title / executive summary / methods / results / comparison tables / per-subject summary / pipeline status), navigable PDF bookmarks (fpdf2 or pikepdf post-hoc), figure rules (aspect-ratio preservation, numbered captions, compact multi-panel layout, shared axes for comparisons), size management for email delivery (DPI control, ghostscript compression, splitting), and delivery tracking (email + issue-tracker comment with PDF attachment, summary, file path, and back-link). Use when authoring a recurring analysis report, preparing a results PDF for collaborators, or auditing a delivery pipeline for reproducibility and traceability.
tags: [scitex-scientific-reporting-pdf-reports]
---

# Scientific PDF Reports (universal principles)

Library-agnostic conventions for recurring analysis reports delivered as PDF
to collaborators. Pairs with [01_figures_01_standards.md](01_figures_01_standards.md)
for figure-level rules.

## File Naming

Always use a timestamped filename so successive deliveries never overwrite
each other and provenance is obvious from the filename alone:

```
<project>-report-YYYYMMDD-HHmmss.pdf
```

Save under a project-scoped reports directory (e.g. `<project_root>/reports/`
or `~/proj/<project>/reports/`). Do **not** save reports under `data/` or
inside source trees.

## Report Structure (required sections)

Every analysis report MUST include, in order:

1. **Title page** — project name, report timestamp, dataset summary
   (n subjects, n channels/samples, time range).
2. **Executive summary** — key findings as bullet points; readable in
   under one minute.
3. **Methods** — dataset, computation pipeline, statistical tests,
   multiple-comparison correction, effect-size measure(s).
4. **Results — primary metric** — per-subject effect-size + spatial/temporal
   plots with numbered captions.
5. **Results — secondary metric(s)** — same structure as primary.
6. **Correction comparison table** — uncorrected vs FDR vs Bonferroni
   (or equivalent), so the reader can assess sensitivity to correction choice.
7. **Per-subject summary table** — one row per subject (`subject_id`,
   `n_significant`, `max |effect|`, etc.).
8. **Pipeline status** — completion counts of each pipeline stage,
   disk usage, last-success timestamps.

Every figure MUST have a numbered caption (`Figure 1: ...`, `Figure 2: ...`)
with a one-sentence explanation. Captions are not optional.

## PDF Bookmarks (required)

Every report MUST include navigable bookmarks for each top-level section so
collaborators can jump directly to results without scrolling. Use one of:

### `fpdf2` (preferred — bookmarks integrated into authoring)

```python
from fpdf import FPDF

pdf = FPDF()
pdf.set_auto_page_break(auto=True, margin=15)

pdf.add_page()
pdf.start_section("Executive Summary", level=0)

pdf.add_page()
pdf.start_section("Methods", level=0)

pdf.add_page()
pdf.start_section("Results: Primary Metric", level=0)
pdf.start_section("Subject S01", level=1)  # nested bookmark
```

### `pikepdf` (post-hoc — when authoring with `matplotlib.PdfPages`)

```python
import pikepdf

with pikepdf.open("report.pdf") as pdf:
    with pdf.open_outline() as outline:
        outline.root.extend([
            pikepdf.OutlineItem("Executive Summary", 0),
            pikepdf.OutlineItem("Methods",           1),
            pikepdf.OutlineItem("Primary Results",   2),
        ])
    pdf.save("report-bookmarked.pdf")
```

## Figure Rules (within reports)

Beyond the universal rules in `01_figures_01_standards.md`:

- **Compact layout.** 2–4 figures per page in a grid; not one figure per
  page. Reports must be skimmable.
- **Preserve aspect ratio.** Read original PNG dimensions with PIL before
  embedding; never stretch or distort. Compute `fig_height = page_width *
  (h/w)` per image.
- **Shared axes for comparisons.** When two panels compare conditions
  (treatment vs control, pre vs post, etc.), use `sharex=True, sharey=True`
  and remove redundant tick labels from inner panels.
- **Aligned labels.** `fig.align_ylabels()` and `fig.align_xlabels()` for
  multi-row layouts.
- **Numbered captions** (`Figure N: caption`) on every panel.

### Aspect-preserving embedding (matplotlib + PdfPages)

```python
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from PIL import Image
import glob

PAGE_WIDTH_IN = 10  # inches

with PdfPages("report-TIMESTAMP.pdf") as pdf:
    for i, png in enumerate(sorted(glob.glob("figures/*.png")), 1):
        w, h = Image.open(png).size
        fig_height = PAGE_WIDTH_IN * (h / w)

        fig, ax = plt.subplots(figsize=(PAGE_WIDTH_IN, fig_height))
        ax.imshow(mpimg.imread(png))
        ax.set_title(f"Figure {i}: {captions[png]}", fontsize=12, pad=10)
        ax.axis("off")
        fig.tight_layout()
        pdf.savefig(fig, dpi=100)  # cap DPI for size; see below
        plt.close(fig)
```

## PDF Size Management

Target: **under 10 MB** for email delivery (most providers reject >25 MB,
some <10 MB). If the PDF exceeds the target:

1. **Lower image DPI** at save time: `fig.savefig(..., dpi=100)` (default
   is often 300+).
2. **Compress with ghostscript:**
   ```bash
   gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 \
      -dPDFSETTINGS=/ebook -o output.pdf input.pdf
   ```
   `/ebook` is a good default; `/screen` for aggressive compression at the
   cost of figure crispness.
3. **Split** into `report-part1.pdf`, `report-part2.pdf` if still too
   large. Mention the split in the email body.

## Delivery: Email Rules

Every delivery email MUST include:

1. **PDF attachment** (the report itself — never just inline PNGs).
2. **Issue-tracker URL** in the body, linking to the tracking issue
   (e.g. `https://github.com/<org>/<repo>/issues/<n>`).
3. **Summary** of key findings in the email body (mirrors the executive
   summary section).
4. **Timestamp** in the subject line.
5. **File path** on the source machine, for collaborators with shared
   filesystem access.

Subject format:

```
[<Project>] <Analysis> Report YYYY-MM-DD — <one-line key finding>
```

```python
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

msg = MIMEMultipart()
msg["Subject"] = f"[{project}] {analysis} Report {date} — {summary}"
msg["From"] = from_addr
msg["To"]   = to_addr

body = f"""\
{project} {analysis} Report

Tracking issue: {issue_url}

Key findings:
- {finding_1}
- {finding_2}

Report on <host>: {report_path}
"""
msg.attach(MIMEText(body, "plain"))

with open(report_path, "rb") as fh:
    part = MIMEBase("application", "pdf")
    part.set_payload(fh.read())
encoders.encode_base64(part)
part.add_header("Content-Disposition", f'attachment; filename="{report_path.name}"')
msg.attach(part)

with smtplib.SMTP("localhost", 25) as server:
    server.sendmail(from_addr, [to_addr], msg.as_string())
```

Check `report_path.stat().st_size < 10 * 1024 * 1024` before attaching;
fall through to size-management above on failure.

## Tracking: Issue Comment

After successful delivery, comment on the tracking issue so the
delivery history lives next to the analysis spec:

```bash
gh issue comment <n> --repo <org>/<repo> --body "$(cat <<EOF
Report delivered: $(basename "$report_path")
Path: $report_path
Size: $(du -h "$report_path" | cut -f1)
Email: sent (or: failed — <reason>)
EOF
)"
```

The issue thread becomes the canonical delivery log: every report PDF is
discoverable from the analysis ticket, and failures are visible to
everyone watching the issue.

## See also

- [01_figures_01_standards.md](01_figures_01_standards.md) — figure-level
  comparison and layout rules.
- [02_research-project_07_config-and-parameters.md](02_research-project_07_config-and-parameters.md)
  — `@stx.session` entry-point pattern for the report-generation script.
