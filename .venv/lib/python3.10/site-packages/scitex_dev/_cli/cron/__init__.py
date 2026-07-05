"""``scitex-dev cron …`` — ecosystem-wide managed-cron CLI.

The cron CLI consolidates cross-package scheduled tasks behind a single
operator surface. Managed lines are tagged with ``# scitex-dev cron:
<name>`` so install / remove operations are unambiguous and unrelated
crontab entries are preserved verbatim.

Verbs:
  * ``list``     — registry vs. installed view
  * ``install``  — materialise a registered job into crontab (idempotent)
  * ``remove``   — strip the managed line for a registered job
  * ``status``   — last-run / next-run hints per job
  * ``exec``     — execute a job's body (the verb cron itself invokes)
"""

from __future__ import annotations

from ._cmd import register_cron_commands

__all__ = ["register_cron_commands"]
