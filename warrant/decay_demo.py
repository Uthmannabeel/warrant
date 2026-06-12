"""Trust decay — a license rots unless renewed by fresh evidence.

A track record earned a year ago should not, by itself, justify autonomy today: the system,
the traffic, and the failure modes have all moved on. Warrant time-weights evidence with a
configurable half-life, so confidence quietly erodes as a license goes unused — and the action
falls back to human-in-the-loop until someone renews it with fresh, graded outcomes.

This is a pure, self-contained illustration (no sandbox, no network): it builds one clean track
record, then certifies it as if more and more time had passed.

    python -m warrant.decay_demo
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from .certification import certify
from .config import config
from .ledger import Ledger, Outcome

ACTION = "restart_connection_pool"
FP = "soar-playbook:rules@7"


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    # An in-memory ledger (never written to disk) with a solid, freshly-earned track record.
    ledger = Ledger.__new__(Ledger)
    ledger.path = None  # type: ignore[assignment]
    ledger._records = []  # type: ignore[attr-defined]
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(8):
        ledger._records.append(Outcome(  # type: ignore[attr-defined]
            action_class=ACTION, target="connection_pool",
            predicted="error_rate returns below the control limit", correct=True,
            timestamp=_iso(t0 + timedelta(minutes=i)), confidence=0.85,
            kind="production", fingerprint=FP, note="earned",
        ))

    print("=" * 72)
    print(" TRUST DECAY — a license rots unless renewed by fresh evidence")
    print("=" * 72)
    print(f" action class : {ACTION}")
    print(f" track record : 8/8 correct, earned on {t0.date()}")
    print(f" half-life    : {config.trust_halflife_days:.0f} days "
          f"(WARRANT_TRUST_HALFLIFE_DAYS)\n")
    print(f" {'days since last evidence':>26} | {'confidence':>10} | status")
    print(" " + "-" * 70)

    for days in (0, 15, 30, 60, 120, 240):
        now = _iso(t0 + timedelta(minutes=8) + timedelta(days=days))
        lic = certify(ledger, ACTION, current_fingerprint=FP, now_iso=now)
        flag = "" if lic.status == "LICENSED" else "  <- rotted to human-in-the-loop"
        print(f" {days:>22}d   | {lic.confidence:>10.2f} | {lic.status}{flag}")

    print("\n A year-old success is not a licence to act today. Renew, or step back.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
