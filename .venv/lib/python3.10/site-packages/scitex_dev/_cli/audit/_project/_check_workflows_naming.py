"""PS-164 — `.github/workflows/` filename + structure convention.

Spec: `_skills/general/02_package/12_workflows-naming.md`.

Three sub-checks (all severity W during adoption):

1. Vague filename — file basename is in the denylist (docs.yml, test.yml,
   lint.yml, ci.yml, build.yml, release.yml, publish.yml, audit.yml,
   quality.yml, sync.yml, integration.yml).
2. Multi-concern workflow — `jobs:` block has >1 entry whose IDs do not
   share a common stem (heuristic: longest-common-prefix across all job
   IDs is <3 characters AND no shared word).
3. `name:` field obviously mismatches the filename (Jaccard of tokenised
   filename-stem vs. tokenised `name:` slug is < 0.2).

`cla.yml` is exempt — the CLA Assistant GitHub App pins that filename.
"""

from __future__ import annotations

import re
from pathlib import Path

# Filenames that the CLA Assistant action pins. Never flagged.
_EXEMPT_FILENAMES = frozenset({"cla.yml", "cla.yaml"})

# Generic filenames the convention forbids.
_VAGUE_FILENAMES = frozenset(
    {
        "docs.yml",
        "test.yml",
        "tests.yml",
        "lint.yml",
        "ci.yml",
        "build.yml",
        "release.yml",
        "publish.yml",
        "audit.yml",
        "quality.yml",
        "sync.yml",
        "integration.yml",
    }
)

# Match a top-level `name:` field (first line at column 0 starting `name:`).
_RE_TOP_NAME = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)

# Match a `jobs:` block start and individual job IDs (2-space indent).
_RE_JOBS_BLOCK = re.compile(r"^jobs:\s*$", re.MULTILINE)
_RE_JOB_ID = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$", re.MULTILINE)


def _tokenise(s: str) -> set[str]:
    """Lowercase tokens split on non-alphanumerics."""
    return {t for t in re.split(r"[^a-z0-9]+", s.lower()) if t}


def _job_ids(text: str) -> list[str]:
    """Return all top-level job IDs inside the `jobs:` block.

    Heuristic — only counts 2-space-indented identifiers that appear
    after the first `jobs:` line. Robust enough for the canonical
    GitHub Actions style; YAML pathological cases (tab indentation,
    flow style) are rare in our ecosystem and would just under-report.
    """
    m = _RE_JOBS_BLOCK.search(text)
    if not m:
        return []
    after = text[m.end() :]
    return _RE_JOB_ID.findall(after)


def _share_stem(job_ids: list[str], filename_stem: str = "") -> bool:
    """True iff the job IDs plausibly share a common purpose.

    Heuristic:
      (a) longest common prefix >= 3 chars, OR
      (b) at least one tokenised word common to all IDs, OR
      (c) every job ID appears as a token in the filename stem
          (e.g. `pypi-publish-and-github-release-on-tag.yml` with jobs
          `build`/`publish`/`release` — the filename itself declares the
          pipeline, so the multi-job structure is intentional).
    """
    if len(job_ids) <= 1:
        return True
    # (a) Longest common prefix
    lcp = job_ids[0]
    for j in job_ids[1:]:
        i = 0
        while i < len(lcp) and i < len(j) and lcp[i] == j[i]:
            i += 1
        lcp = lcp[:i]
        if not lcp:
            break
    if len(lcp) >= 3:
        return True
    # (b) Shared word in all IDs
    token_sets = [_tokenise(j) for j in job_ids]
    common = set.intersection(*token_sets) if token_sets else set()
    if common:
        return True
    # (c) Filename declares the pipeline that the jobs implement.
    if filename_stem:
        fname_tokens = _tokenise(filename_stem)
        if all(_tokenise(j) <= fname_tokens for j in job_ids):
            return True
        # (c') Release-pipeline shape: a "publish"/"release"-named file
        # whose jobs are recognised pipeline steps (build → publish →
        # release / github-release) is intentional. Allow this when the
        # filename mentions publish/release AND every job is in the
        # canonical pipeline-step vocabulary.
        _PIPELINE_STEPS = {
            "build",
            "publish",
            "release",
            "tag",
            "upload",
            "verify",
            "sign",
            "github-release",
            "github_release",
            "githubrelease",
        }
        if ({"publish", "release"} & fname_tokens) and all(
            j.lower() in _PIPELINE_STEPS for j in job_ids
        ):
            return True
    return False


def _name_field_matches_filename(filename_stem: str, name_field: str) -> bool:
    """Loose match: only flag obvious mismatches.

    Acceptable (no violation) if EITHER:
      - `name:` field has <2 tokens (people legitimately use short labels
        like `Test`, `Docs` — the file name already carries the detail), OR
      - at least one token overlaps between filename-stem and name-field, OR
      - the name-field as a single lowercase string is a substring of the
        filename stem (e.g. name=`pytest` vs file=`pytest-matrix-…`).

    Only fires when the name-field is multi-word AND has zero overlap
    with the filename — a clear sign of drift (e.g. file=`docs.yml`,
    name=`Publish to PyPI`).
    """
    a = _tokenise(filename_stem)
    b = _tokenise(name_field)
    if not a or not b:
        return True
    if len(b) < 2:
        return True
    if a & b:
        return True
    flat = name_field.lower().replace(" ", "")
    if flat and flat in filename_stem.lower():
        return True
    return False


def check_ps164_workflow_naming(repo: Path, violation_cls: type, out: list) -> None:
    """Append PS-164 violations for `.github/workflows/`.

    Three independent sub-checks; each fires once per offending file.
    """
    wf_dir = repo / ".github" / "workflows"
    if not wf_dir.is_dir():
        return

    for path in sorted(wf_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix not in {".yml", ".yaml"}:
            continue
        if path.name in _EXEMPT_FILENAMES:
            continue

        rel = str(path.relative_to(repo))

        # (1) Vague filename
        if path.name in _VAGUE_FILENAMES:
            out.append(
                violation_cls(
                    "PS-164",
                    rel,
                    (
                        f"workflow filename `{path.name}` is too generic — "
                        "rename to describe what runs and where (e.g. "
                        "`pytest-on-ubuntu-py3-11-3-12-3-13.yml`, "
                        "`rtd-build-on-ubuntu-latest.yml`). See "
                        "_skills/general/02_package/12_workflows-naming.md."
                    ),
                )
            )

        # Read content for (2) and (3)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # (2) Multi-concern workflow
        job_ids = _job_ids(text)
        if len(job_ids) > 1 and not _share_stem(job_ids, path.stem):
            out.append(
                violation_cls(
                    "PS-164",
                    rel,
                    (
                        f"workflow has {len(job_ids)} jobs with unrelated "
                        f"IDs ({', '.join(job_ids)}) — split into one file "
                        "per check. See "
                        "_skills/general/02_package/12_workflows-naming.md."
                    ),
                )
            )

        # (3) name: mismatches filename
        m = _RE_TOP_NAME.search(text)
        if m:
            name_field = m.group(1).strip().strip("\"'")
            if not _name_field_matches_filename(path.stem, name_field):
                out.append(
                    violation_cls(
                        "PS-164",
                        rel,
                        (
                            f"workflow `name:` field ({name_field!r}) does "
                            f"not match filename stem ({path.stem!r}). "
                            "Align the two so branch-protection check names "
                            "remain greppable."
                        ),
                    )
                )
