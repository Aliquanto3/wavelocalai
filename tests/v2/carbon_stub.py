"""Double de `OfflineEmissionsTracker` pour les tests : aucune mesure matérielle, aucun réseau.

`StubTracker` rend 1,8 mg et 0,001 Wh par défaut ; `Tracker.configure` règle une panne, une valeur
ou un délai, et `Tracker.running` / `peak` comptent les trackers simultanés (un seul à la fois).
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from typing import Any


class Probe:
    """État partagé des trackers d'un test : constructions, simultanéité, réglages."""

    def __init__(self) -> None:
        self.kwargs: list[dict[str, Any]] = []
        self.running = 0
        self.peak = 0
        self.started = 0
        self.stopped = 0
        self.emissions_kg = 1.8e-6  # 1,8 mg
        self.energy_kwh = 1e-6  # 0,001 Wh
        self.start_error: Exception | None = None
        self.stop_error: Exception | None = None
        self.start_delay_s = 0.0
        self.no_data = False
        self._lock = threading.Lock()

    def tracker_class(self):
        probe = self

        class StubTracker:
            def __init__(self, **kwargs: Any) -> None:
                probe.kwargs.append(kwargs)
                self.final_emissions_data: Any = None

            def start(self) -> None:
                if probe.start_error is not None:
                    raise probe.start_error
                time.sleep(probe.start_delay_s)
                with probe._lock:
                    probe.running += 1
                    probe.started += 1
                    probe.peak = max(probe.peak, probe.running)

            def stop(self) -> float:
                with probe._lock:
                    probe.running -= 1
                    probe.stopped += 1
                if probe.stop_error is not None:
                    raise probe.stop_error
                if not probe.no_data:
                    self.final_emissions_data = SimpleNamespace(
                        energy_consumed=probe.energy_kwh, emissions=probe.emissions_kg
                    )
                return probe.emissions_kg

        return StubTracker

    def loader(self):
        return lambda: self.tracker_class()
