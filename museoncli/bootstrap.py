"""Upgrade before importing domain dependencies, whose DLLs Windows locks in use."""

from __future__ import annotations

import json
import sys

from museoncli.updates import ensure_latest


def main() -> None:
    try:
        update = ensure_latest(sys.argv[1:])
    except (Exception, KeyboardInterrupt) as exc:
        interrupted = isinstance(exc, KeyboardInterrupt)
        code = "interrupted" if interrupted else "cli_update_failed"
        message = "interrupted" if interrupted else str(exc)
        print(
            json.dumps(
                {
                    "ok": False,
                    "command": None,
                    "reason": code,
                    "detail": message,
                    "error": {"code": code, "message": message, "retryable": interrupted},
                }
            )
        )
        raise SystemExit(130 if interrupted else 1) from None

    from museoncli.main import main as run

    run(update=update)
