#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``ci-watch`` cron job — poll sac-agent repos for CI red, dispatch A2A.

Ports ``scripts/ci-watch.sh`` (lives in scitex-lead) to Python so it can
be installed via ``scitex-dev cron install ci-watch``. Behaviour matches
the bash prototype:

  * Iterate the agent → repo map (see ``AGENTS_TO_REPOS`` below).
  * For each repo, ask ``gh`` for the last 12 develop-branch runs and
    take the latest one per workflow name. Workflows whose latest run is
    ``failure`` are "red".
  * Red workflows → dispatch a fix-forward turn via ``sac agents send``.

When ``--dry-run`` is set, no ``sac agents send`` is fired — the would-be
prompt is printed instead. This is what the cron operator uses to verify
the loop without firing A2A turns (e.g. while the lead's Claude
credentials need re-rsync to Spartan).

The module exposes its key seams (``gh_runner``, ``sac_runner``) as
keyword arguments on every function so tests can pass real fakes
instead of monkey-patching ``subprocess``.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

# ---------------------------------------------------------------------------
# Agent → owned repo map
# ---------------------------------------------------------------------------
# Edit this in-place when a new sac agent joins the fleet. Move to a
# config file when the list grows past ~10 entries (the bash prototype's
# threshold).
AGENTS_TO_REPOS: Mapping[str, str] = {
    "proj-scitex-stats": "ywatanabe1989/scitex-stats",
    "proj-scitex-types": "ywatanabe1989/scitex-types",
    "proj-scitex-dict": "ywatanabe1989/scitex-dict",
    "proj-scitex-str": "ywatanabe1989/scitex-str",
    "proj-scitex-datetime": "ywatanabe1989/scitex-datetime",
}

# The fix-forward prompt dispatched to the responsible agent. Ported
# verbatim from scripts/ci-watch.sh — keep the agent-facing wording
# consistent so the agent's behaviour is identical regardless of which
# loop fired the turn (cron vs. on-demand).
FIX_PROMPT_TEMPLATE = """\
CI red on `{repo}` develop. The following workflow(s) report failure on the latest run:

{reds}

Investigate the root cause:
  1. `gh -R {repo} run list --branch develop --limit 5` to see recent runs.
  2. For each failing workflow, `gh -R {repo} run view <id> --log-failed` (or grep ERRO / FAILED in the logs).
  3. Pull develop, fix the root cause, commit on a fix branch, push, open a PR (`gh pr create --base develop`), and merge after CI confirms green.

If the failure is a pre-existing issue out of your scope (e.g. credentials missing on the runner), reply BLOCKED with a one-line reason. Otherwise reply with the PR URL on completion."""


@dataclass(frozen=True)
class AgentResult:
    """Per-agent outcome of one ci-watch pass."""

    agent: str
    repo: str
    red_workflows: tuple[str, ...]
    dispatched: bool
    dispatch_output: str
    error: str | None = None
    # Per-pass todo bookkeeping: the (workflow, sha) identities that
    # were filed into scitex-todo on this round, and the identities
    # that were already on file (idempotent skip). Both empty when
    # scitex-todo is unavailable (fail-open) or when there were no
    # red workflows to file in the first place.
    todos_filed: tuple[str, ...] = ()
    todos_already_open: tuple[str, ...] = ()

    def is_red(self) -> bool:
        return bool(self.red_workflows)


@dataclass(frozen=True)
class FailingRun:
    """One workflow whose latest develop run is ``failure``.

    Carries the identity tuple (``workflow``, ``run_id``, ``head_sha``)
    that the scitex-todo hook uses as its idempotency key — same
    (workflow, head_sha) re-detected on a later cron round must NOT
    create a duplicate todo. ``run_id`` is fetched alongside so the
    todo can link the operator at the failing run's GitHub Actions
    page directly.
    """

    workflow: str
    run_id: int
    head_sha: str


# ---------------------------------------------------------------------------
# gh layer
# ---------------------------------------------------------------------------


def _default_gh_runner(args: list[str]) -> subprocess.CompletedProcess:
    """Real ``gh`` invocation. Tests pass their own fake."""
    return subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def red_runs_for(
    repo: str,
    *,
    gh_runner: Callable[[list[str]], subprocess.CompletedProcess] | None = None,
) -> list[FailingRun]:
    """Return one :class:`FailingRun` per workflow whose latest develop run is ``failure``.

    Parses the JSON output of

        gh -R <repo> run list --branch develop --limit 12 \
            --json conclusion,workflowName,databaseId,headSha

    Only the most recent run per workflow is considered — ``gh`` returns
    runs newest-first, so the first occurrence of each ``workflowName``
    wins. Pure helper; no side-effects.

    The ``headSha`` field is needed downstream by
    :func:`_create_todo_if_new` for its idempotency key (a re-poll on
    the same failing SHA must NOT spawn a duplicate todo). ``databaseId``
    becomes ``run_id`` so the todo can link straight to the failing
    run's logs page.

    Raises ``RuntimeError`` if ``gh`` exits non-zero — the cron job
    swallows the error per-repo so one bad repo doesn't kill the loop.
    """
    run = gh_runner or _default_gh_runner
    args = [
        "-R",
        repo,
        "run",
        "list",
        "--branch",
        "develop",
        "--limit",
        "12",
        "--json",
        "conclusion,workflowName,databaseId,headSha",
    ]
    r = run(args)
    if r.returncode != 0:
        raise RuntimeError(
            f"`gh {' '.join(args)}` failed (rc={r.returncode}): "
            f"{(r.stderr or r.stdout).strip()}"
        )
    try:
        data = json.loads(r.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gh returned non-JSON for {repo}: {exc}") from exc

    seen: set[str] = set()
    reds: list[FailingRun] = []
    for entry in data:
        name = entry.get("workflowName")
        if not name or name in seen:
            continue
        seen.add(name)
        if entry.get("conclusion") == "failure":
            reds.append(
                FailingRun(
                    workflow=name,
                    run_id=int(entry.get("databaseId") or 0),
                    head_sha=str(entry.get("headSha") or ""),
                )
            )
    return reds


def red_workflows_for(
    repo: str,
    *,
    gh_runner: Callable[[list[str]], subprocess.CompletedProcess] | None = None,
) -> list[str]:
    """Return the workflow names whose latest develop run is ``failure``.

    Thin name-only wrapper around :func:`red_runs_for`, preserved as the
    historical wire shape (``list[str]``) so existing callers and tests
    keep working unchanged after the rich-tuple refactor that lets the
    scitex-todo hook see ``head_sha`` / ``run_id``.
    """
    return [r.workflow for r in red_runs_for(repo, gh_runner=gh_runner)]


# ---------------------------------------------------------------------------
# scitex-todo creation layer (CI-fail → todo)
# ---------------------------------------------------------------------------
#
# When ci-watch spots a red workflow, we ALSO file a scitex-todo entry so
# the failure surfaces on the agent's board, not just in the dispatched
# fix-forward turn. Design notes:
#
#   * scitex-todo is a SOFT dependency. We lazy-import inside
#     :func:`_resolve_todo_api`; an ``ImportError`` (CI sandbox without
#     scitex-todo, fresh editable install, etc.) degrades to no-op, never
#     blocks the dispatch loop. Same fail-open spirit as the busy-probe.
#
#   * Idempotency: the (repo, workflow, head_sha) tuple is hashed into a
#     stable task id (see :func:`_todo_task_id_for`). A subsequent cron
#     round on the SAME failing SHA reuses the id; scitex-todo's
#     ``add_task`` raises ``TaskValidationError`` with the message
#     ``"duplicate task id ..."`` which we catch and treat as "already
#     filed" — no duplicate todos. proj-scitex-todo confirmed the
#     ``"duplicate task id"`` substring is stable (see ``_model.py:368``
#     in scitex-todo; if it ever shifts they grep our hook for sync).
#     No dedicated exit code exists yet (CLI uses click's catch-all
#     exit 1), so a substring match against the exception message is
#     the available identity signal.
#
#   * Mapping to scitex-todo's schema (proj-scitex-todo a2a, 2026-06-09):
#       - kind="task" (NOT "bug" — bug is not in VALID_KINDS; we prefix
#         the title with [CI-FAIL] instead so the operator can grep).
#       - status="pending"
#       - assignee=<owning sac agent>
#       - project=<repo basename>
#       - pr_url=<GitHub Actions run URL> (no --url flag exists; pr_url
#         is the closest free-form URL field)
#       - note=<markdown block with workflow / SHA / run URL>
#
#   * Auto-close on red→green recovery is intentionally OUT of scope
#     for v1 (lead 2026-06-09). Tracked as a follow-up.


@dataclass(frozen=True)
class _TodoApi:
    """Bundle of scitex-todo entry points needed by the hook.

    Lets tests substitute a hand-rolled fake (PA-306 / STX-NM*) for the
    `add_task` callable + the `validation_error_cls` type without
    `unittest.mock` or `monkeypatch`.
    """

    add_task: Callable[..., Any]
    validation_error_cls: type
    store_path: Path | None


def _resolve_todo_api(
    store_path: Path | None = None,
) -> _TodoApi | None:
    """Lazy-import scitex-todo. Returns ``None`` if not installed.

    Caller treats ``None`` as "scitex-todo unavailable → skip todo
    creation, keep going" (fail-open). This keeps scitex-todo a soft
    dependency: ci-watch's core (red detection + sac dispatch) works
    even on hosts that don't have scitex-todo installed.
    """
    try:
        from scitex_todo._paths import resolve_tasks_path
        from scitex_todo._store import (
            TaskValidationError,
            add_task,
        )
    except Exception:  # stx-allow: fallback (reason: scitex-todo is a soft dep)
        return None
    resolved = store_path if store_path is not None else resolve_tasks_path(None)
    return _TodoApi(
        add_task=add_task,
        validation_error_cls=TaskValidationError,
        store_path=resolved,
    )


_TODO_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _todo_task_id_for(repo: str, workflow: str, head_sha: str) -> str:
    """Stable id for the (repo, workflow, head_sha) tuple.

    Format: ``ci-fail-{repo-basename}-{workflow-slug}-{sha[:8]}``. Same
    failing SHA + workflow → same id → idempotent ``add_task`` (we catch
    ``TaskValidationError("duplicate task id ...")`` upstream). The
    workflow name is lowercased and stripped to ``[a-z0-9-]`` so spaces
    and matrix-row qualifiers (``pytest-matrix-on-ubuntu-py3.12``)
    round-trip safely through scitex-todo's id validation.
    """
    repo_slug = repo.split("/")[-1]
    workflow_slug = _TODO_SLUG_RE.sub("-", workflow.lower()).strip("-")
    short_sha = head_sha[:8] if head_sha else "nosha"
    return f"ci-fail-{repo_slug}-{workflow_slug}-{short_sha}"


def _create_todo_if_new(
    *,
    agent: str,
    repo: str,
    failing_run: FailingRun,
    todo_api: _TodoApi | None = None,
) -> bool:
    """File a CI-fail todo via the scitex-todo Python API.

    Returns ``True`` if a new todo was created, ``False`` if the
    (repo, workflow, head_sha) tuple was already on file (idempotent
    skip) OR scitex-todo is not importable (fail-open). Any other
    ``TaskValidationError`` (real schema breakage) re-raises.

    The substring match against ``"duplicate task id"`` is the
    identity signal proj-scitex-todo's CLI exposes today; if they ever
    add a dedicated exit code / exception subclass, swap this for the
    typed check. The string is hard-coded in scitex-todo's
    ``_model._validate_tasks`` (proj-scitex-todo a2a confirmed
    stability and committed to grep on rename).
    """
    api = todo_api if todo_api is not None else _resolve_todo_api()
    if api is None:
        return False
    task_id = _todo_task_id_for(repo, failing_run.workflow, failing_run.head_sha)
    project = repo.split("/")[-1]
    short_sha = failing_run.head_sha[:8] if failing_run.head_sha else "nosha"
    title = f"[CI-FAIL] {project} / {failing_run.workflow} @ {short_sha}"
    run_url = (
        f"https://github.com/{repo}/actions/runs/{failing_run.run_id}"
        if failing_run.run_id
        else ""
    )
    note = (
        f"Workflow: `{failing_run.workflow}`\n"
        f"SHA: `{failing_run.head_sha}`\n"
        f"Run: {run_url}"
    )
    try:
        api.add_task(
            api.store_path,
            id=task_id,
            title=title,
            status="pending",
            kind="task",
            project=project,
            assignee=agent,
            pr_url=run_url,
            note=note,
        )
        return True
    except api.validation_error_cls as exc:
        if "duplicate task id" in str(exc):
            return False
        raise


# ---------------------------------------------------------------------------
# sac dispatch layer
# ---------------------------------------------------------------------------


def _default_sac_runner(
    args: list[str],
    *,
    input_text: str,
) -> subprocess.CompletedProcess:
    """Real ``sac`` invocation. Tests pass their own fake."""
    return subprocess.run(
        ["sac", *args],
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


# ---------------------------------------------------------------------------
# sac sidecar busy probe
# ---------------------------------------------------------------------------
#
# The cron job dispatches via ``sac agents send``, which has a hard 120 s
# server-side timeout. When an agent is mid-turn from a previous round,
# the new send blocks for the full 120 s before failing — and the next
# agent's send is delayed in turn. Three busy agents = 6 minutes lost,
# and the 10-minute cron interval starts to overflow.
#
# sac's A2A sidecar exposes a non-spec observability route at
# ``/agents/<name>/_active`` returning ``{"tasks": [...]}``. We probe it
# before each ``dispatch_fix_turn`` and skip the agent if any task is
# active. The check is fail-open: any HTTP / parse / timeout error
# returns False (treat as not-busy) — under-skipping is recoverable
# (one wasted 120 s send), over-skipping silently mutes the watcher.

# Short on purpose. The endpoint is in-process on the sidecar and
# returns instantly when reachable; a long wait defeats the whole point
# of probing before the 120 s send.
_BUSY_PROBE_TIMEOUT_S = 5.0


def _default_http_runner(url: str, timeout: float) -> tuple[int, bytes]:
    """Real ``urllib`` GET. Tests pass their own fake.

    Returns ``(status_code, body_bytes)``. Raises on transport failure
    (connection refused, timeout, etc.) — :func:`_is_agent_busy`
    catches everything and reports not-busy.
    """
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.getcode(), resp.read()


def _is_agent_busy(
    host: str,
    a2a_port: int,
    agent: str,
    *,
    http_runner: Callable[[str, float], tuple[int, bytes]] | None = None,
) -> bool:
    """True iff the sac sidecar's /_active route reports any tasks for ``agent``.

    Endpoint: ``http://{host}:{a2a_port}/agents/{agent}/_active``.

    Response shape: ``{"tasks": [{"id", "state", "last_event_at"}, ...]}``.
    Non-empty ``tasks`` → busy.

    Fail-open contract: on any request failure (timeout, 404, non-200,
    JSON parse error, missing ``tasks`` key, runner exception of any
    kind) return ``False``. Better to over-dispatch (and eat one 120 s
    sac-send timeout) than silently skip every round because the probe
    is misconfigured.
    """
    runner = http_runner or _default_http_runner
    url = f"http://{host}:{a2a_port}/agents/{agent}/_active"
    try:
        status, body = runner(url, _BUSY_PROBE_TIMEOUT_S)
    except Exception:  # stx-allow: fallback (reason: fail-open per docstring)
        return False
    if status != 200:
        return False
    try:
        data = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        return False
    return len(tasks) > 0


# ---------------------------------------------------------------------------
# state.db resolution — agent → (host, a2a_port)
# ---------------------------------------------------------------------------


def _resolve_agent_endpoint(
    agent: str,
    *,
    sac_runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> tuple[str, int] | None:
    """Return ``(host, a2a_port)`` for ``agent``'s live state.db row, or None.

    Uses ``sac db query --table=instances --where=... --json``. None is
    returned when the agent has no live row, no a2a_port, or sac db
    fails — the caller treats None as "can't probe, assume not busy"
    (fail-open, consistent with :func:`_is_agent_busy`).
    """
    runner = sac_runner or _default_sac_runner
    where = f"name='{agent}' AND ended_at IS NULL"
    args = [
        "db",
        "query",
        "--table",
        "instances",
        "--where",
        where,
        "--json",
        "--limit",
        "1",
    ]
    try:
        r = runner(args, input_text="")
    except Exception:  # stx-allow: fallback (reason: probe fail-open)
        return None
    if r.returncode != 0:
        return None
    try:
        rows = json.loads(r.stdout or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(rows, list) or not rows:
        return None
    row = rows[0]
    if not isinstance(row, dict):
        return None
    host = row.get("host")
    port = row.get("a2a_port")
    if not isinstance(host, str) or not host:
        return None
    if not isinstance(port, int) or port <= 0:
        return None
    return host, port


def build_fix_prompt(repo: str, reds: list[str]) -> str:
    """Return the agent-facing fix prompt for a red repo."""
    body = "\n".join(reds)
    return FIX_PROMPT_TEMPLATE.format(repo=repo, reds=body)


def dispatch_fix_turn(
    agent: str,
    repo: str,
    reds: list[str],
    *,
    sac_runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> str:
    """Fire ``sac agents send <agent> <prompt>``. Returns combined output."""
    runner = sac_runner or _default_sac_runner
    prompt = build_fix_prompt(repo, reds)
    # Keep the same call shape as the bash prototype: prompt as a single
    # positional argument. sac's send command treats arg as the message
    # body. We don't pipe via stdin so quoting stays simple.
    r = runner(["agents", "send", agent, prompt], input_text="")
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        raise RuntimeError(
            f"sac agents send {agent!r} failed (rc={r.returncode}): {out.strip()}"
        )
    return out


# ---------------------------------------------------------------------------
# Top-level pass
# ---------------------------------------------------------------------------


def run_once(
    *,
    only_agent: str | None = None,
    agents_to_repos: Mapping[str, str] | None = None,
    dry_run: bool = False,
    gh_runner: Callable[[list[str]], subprocess.CompletedProcess] | None = None,
    sac_runner: Callable[..., subprocess.CompletedProcess] | None = None,
    todo_api: _TodoApi | None = None,
    out=None,
) -> list[AgentResult]:
    """Run one ci-watch pass over every (or the named) agent.

    Returns a list of ``AgentResult`` so callers (and tests) can inspect
    what happened. Prints progress to ``out`` (default ``sys.stdout``) in
    the same human-readable format as the bash prototype.

    The ``todo_api`` seam lets tests pass a hand-rolled fake to verify
    the CI-fail → scitex-todo bookkeeping without importing scitex-todo
    at all (PA-306 / STX-NM* — no ``unittest.mock``). In production
    callers leave it ``None`` so :func:`_resolve_todo_api` lazy-imports
    scitex-todo on first need; if scitex-todo is not installed the hook
    short-circuits to no-op and the rest of the loop is unaffected.
    """
    if out is None:
        out = sys.stdout
    table = agents_to_repos if agents_to_repos is not None else AGENTS_TO_REPOS

    results: list[AgentResult] = []
    for agent in sorted(table):
        if only_agent and agent != only_agent:
            continue
        repo = table[agent]
        print(f"=== {agent} <- {repo} ===", file=out)
        try:
            reds = red_runs_for(repo, gh_runner=gh_runner)
        except RuntimeError as exc:
            print(f"  error: {exc}", file=out)
            results.append(
                AgentResult(
                    agent=agent,
                    repo=repo,
                    red_workflows=(),
                    dispatched=False,
                    dispatch_output="",
                    error=str(exc),
                )
            )
            continue

        red_names = [r.workflow for r in reds]

        if not reds:
            print("  all green", file=out)
            results.append(
                AgentResult(
                    agent=agent,
                    repo=repo,
                    red_workflows=(),
                    dispatched=False,
                    dispatch_output="",
                )
            )
            continue

        print("  red workflows:", file=out)
        for r in reds:
            print(f"    - {r.workflow}", file=out)

        # CI-fail → scitex-todo. Fail-open so a scitex-todo glitch never
        # blocks the sac dispatch / fix-forward turn below. We file the
        # todo even in dry-run + agent-busy paths because the todo is
        # the *durable* record of the failure; the sac dispatch is the
        # *live* nudge. Either being skipped doesn't excuse the other.
        todos_filed: list[str] = []
        todos_already_open: list[str] = []
        for failing_run in reds:
            try:
                created = _create_todo_if_new(
                    agent=agent,
                    repo=repo,
                    failing_run=failing_run,
                    todo_api=todo_api,
                )
            except Exception as exc:  # stx-allow: fallback (reason: todo hook fail-open)
                # Surface a one-line diagnostic so the operator notices
                # if scitex-todo starts rejecting every call, but keep
                # the loop alive.
                print(f"  todo-hook: {failing_run.workflow}: {exc}", file=out)
                continue
            task_id = _todo_task_id_for(
                repo, failing_run.workflow, failing_run.head_sha
            )
            if created:
                todos_filed.append(task_id)
                print(f"  todo: filed {task_id}", file=out)
            else:
                todos_already_open.append(task_id)

        if dry_run:
            prompt = build_fix_prompt(repo, red_names)
            print(
                f"  [dry-run] would dispatch to {agent}:",
                file=out,
            )
            for line in prompt.splitlines():
                print(f"    | {line}", file=out)
            results.append(
                AgentResult(
                    agent=agent,
                    repo=repo,
                    red_workflows=tuple(red_names),
                    dispatched=False,
                    dispatch_output=prompt,
                    todos_filed=tuple(todos_filed),
                    todos_already_open=tuple(todos_already_open),
                )
            )
            continue

        # Skip when the agent has active work — prevents the 120s
        # sac-send timeout from cascading and overflowing the 10-min
        # cron interval. Endpoint and lookup are both fail-open so a
        # broken probe degrades to over-dispatch, not silent muting.
        endpoint = _resolve_agent_endpoint(agent, sac_runner=sac_runner)
        if endpoint is not None:
            host, port = endpoint
            if _is_agent_busy(host, port, agent):
                print(f"  skip: {agent} has active task(s)", file=out)
                results.append(
                    AgentResult(
                        agent=agent,
                        repo=repo,
                        red_workflows=tuple(red_names),
                        dispatched=False,
                        dispatch_output="",
                        todos_filed=tuple(todos_filed),
                        todos_already_open=tuple(todos_already_open),
                    )
                )
                continue

        print(f"  dispatching fix turn to {agent} ...", file=out)
        try:
            output = dispatch_fix_turn(agent, repo, red_names, sac_runner=sac_runner)
        except RuntimeError as exc:
            print(f"  error: {exc}", file=out)
            results.append(
                AgentResult(
                    agent=agent,
                    repo=repo,
                    red_workflows=tuple(red_names),
                    dispatched=False,
                    dispatch_output="",
                    error=str(exc),
                    todos_filed=tuple(todos_filed),
                    todos_already_open=tuple(todos_already_open),
                )
            )
            continue

        for line in output.splitlines()[-3:]:
            print(f"    {line}", file=out)
        results.append(
            AgentResult(
                agent=agent,
                repo=repo,
                red_workflows=tuple(red_names),
                dispatched=True,
                dispatch_output=output,
                todos_filed=tuple(todos_filed),
                todos_already_open=tuple(todos_already_open),
            )
        )

    return results


# EOF
