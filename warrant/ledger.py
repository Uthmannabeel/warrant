"""The trust ledger — Warrant's earned track record.

Every loop records a prediction and its real-world outcome. The per-action-class hit-rate
is what gates autonomy: an action class may act autonomously only while its hit-rate stays
at/above the configured threshold. This is the heart of "earning the right to act".
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import config

LEDGER_PATH = Path(config.ledger_path)


def wilson_lower_bound(successes: int, n: int, z: float = 1.96) -> float:
    """Lower bound of the Wilson score interval (95% by default).

    This is what makes "earned trust" statistically honest: 1/1 successes yields ~0.21, not
    1.0, so a single lucky outcome can NOT graduate an action to autonomous. Confidence only
    climbs with a sustained track record.
    """
    if n == 0:
        return 0.0
    phat = successes / n
    denom = 1 + z * z / n
    centre = phat + z * z / (2 * n)
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n)
    return max(0.0, (centre - margin) / denom)


@dataclass
class Outcome:
    action_class: str          # e.g. "restart_connection_pool"
    target: str                # what was acted on
    predicted: str             # the falsifiable prediction, human-readable
    correct: bool              # did reality stay inside the forecast band?
    timestamp: str             # ISO-8601, stamped by the caller (no clock in this module)
    confidence: float = 0.5    # the agent's STATED confidence (0..1) in this prediction -> calibration
    kind: str = "production"   # "exam" (proving ground) or "production" (live system)
    fingerprint: str = ""      # brain fingerprint at decision time -> drift detection
    note: str = ""


class Ledger:
    def __init__(self, path: Path = LEDGER_PATH) -> None:
        self.path = path
        self._records: list[Outcome] = self._load()

    def _load(self) -> list[Outcome]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [Outcome(**r) for r in data]

    def _save(self) -> None:
        self.path.write_text(
            json.dumps([asdict(r) for r in self._records], indent=2), encoding="utf-8"
        )

    def record(self, outcome: Outcome) -> None:
        self._records.append(outcome)
        self._save()

    def records(self, action_class: str | None = None) -> list[Outcome]:
        """All recorded outcomes, optionally filtered to one action class (chronological)."""
        if action_class is None:
            return list(self._records)
        return [r for r in self._records if r.action_class == action_class]

    def action_classes(self) -> list[str]:
        """Every action class that has at least one recorded outcome (stable order)."""
        seen: list[str] = []
        for r in self._records:
            if r.action_class not in seen:
                seen.append(r.action_class)
        return seen

    def reset(self) -> None:
        """Wipe the track record — used for a clean demo run, not in real operation."""
        self._records = []
        if self.path.exists():
            self.path.unlink()

    def _counts(self, action_class: str) -> tuple[int, int]:
        relevant = [r for r in self._records if r.action_class == action_class]
        return sum(1 for r in relevant if r.correct), len(relevant)

    def hit_rate(self, action_class: str) -> float | None:
        """Raw fraction of correct predictions, or None if never tried (display only)."""
        successes, n = self._counts(action_class)
        return None if n == 0 else successes / n

    def confidence(self, action_class: str) -> float:
        """Statistically honest trust: Wilson lower bound over the action's track record."""
        successes, n = self._counts(action_class)
        return wilson_lower_bound(successes, n)

    def sample_size(self, action_class: str) -> int:
        return self._counts(action_class)[1]

    def may_act_autonomously(self, action_class: str) -> bool:
        """Autonomy is EARNED: an action runs autonomously only once its Wilson-lower-bound
        confidence clears the threshold AND it has a minimum track record. A single success
        is never enough."""
        successes, n = self._counts(action_class)
        if n < config.autonomy_min_samples:
            return False  # not enough evidence yet -> human-in-the-loop
        return wilson_lower_bound(successes, n) >= config.autonomy_threshold
