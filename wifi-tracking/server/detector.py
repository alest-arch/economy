"""Deteccion de estado por nodo comparando el motion_score con la linea base calibrada."""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

EMPTY = "vacio"
PRESENCE = "presencia"
MOTION = "movimiento"
OFFLINE = "sin-datos"


@dataclass
class NodeState:
    state: str = OFFLINE
    score: float = 0.0
    zscore: float = 0.0
    last_active: float = 0.0
    baseline_mean: float = field(default=0.05)
    baseline_std: float = field(default=0.01)


class Detector:
    def __init__(self, config: dict, calibration_path: str | Path | None = None):
        det = config.get("detection", {})
        self.motion_z = det.get("motion_z_threshold", 4.0)
        self.presence_z = det.get("presence_z_threshold", 2.0)
        self.hold_seconds = det.get("hold_seconds", 5.0)
        self.states: dict[int, NodeState] = {}
        self._load_calibration(calibration_path)

    def _load_calibration(self, path: str | Path | None) -> None:
        self._calibration: dict[str, dict] = {}
        if path and Path(path).exists():
            self._calibration = json.loads(Path(path).read_text())

    def _get_state(self, node_id: int) -> NodeState:
        if node_id not in self.states:
            ns = NodeState()
            cal = self._calibration.get(str(node_id))
            if cal:
                ns.baseline_mean = cal["mean"]
                ns.baseline_std = max(cal["std"], 1e-4)
            self.states[node_id] = ns
        return self.states[node_id]

    def update(self, node_id: int, score: float | None, now: float | None = None) -> NodeState:
        now = now if now is not None else time.time()
        ns = self._get_state(node_id)

        if score is None:
            if now - ns.last_active > self.hold_seconds:
                ns.state = OFFLINE if ns.last_active == 0 else EMPTY
            return ns

        ns.score = score
        ns.zscore = (score - ns.baseline_mean) / ns.baseline_std

        if ns.zscore >= self.motion_z:
            ns.state = MOTION
            ns.last_active = now
        elif ns.zscore >= self.presence_z:
            ns.state = PRESENCE
            ns.last_active = now
        elif now - ns.last_active > self.hold_seconds:
            ns.state = EMPTY

        return ns
