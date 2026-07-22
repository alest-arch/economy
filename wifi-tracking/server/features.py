"""Extraccion de caracteristicas de movimiento a partir del stream CSI de un nodo.

La idea fisica: con la habitacion vacia el canal WiFi es estable y la amplitud
de cada subportadora apenas varia. Un cuerpo moviendose altera el multipath y
dispara la varianza temporal de las amplitudes. La metrica usada es el
coeficiente de variacion medio entre subportadoras dentro de una ventana
deslizante, robusto frente a cambios de ganancia (AGC) porque normaliza por la
media.
"""

import time
from collections import deque

import numpy as np


class NodeFeatureExtractor:
    def __init__(self, window_seconds: float = 2.0, min_packets: int = 20):
        self.window_seconds = window_seconds
        self.min_packets = min_packets
        self._window: deque[tuple[float, np.ndarray]] = deque()
        self._n_subcarriers: int | None = None
        self.last_packet_time: float = 0.0

    def add(self, amplitudes: np.ndarray, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        self.last_packet_time = now

        if self._n_subcarriers is None:
            self._n_subcarriers = len(amplitudes)
        elif len(amplitudes) != self._n_subcarriers:
            # Trama de otro formato (p.ej. solo LLTF): descartar para no mezclar
            return

        self._window.append((now, amplitudes))
        cutoff = now - self.window_seconds
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()

    def motion_score(self) -> float | None:
        """Coeficiente de variacion medio de las subportadoras en la ventana."""
        if len(self._window) < self.min_packets:
            return None
        matrix = np.stack([a for _, a in self._window])  # (tiempo, subportadoras)
        mean = matrix.mean(axis=0)
        std = matrix.std(axis=0)
        valid = mean > 1e-3
        if not valid.any():
            return None
        cv = std[valid] / mean[valid]
        return float(cv.mean())

    def packet_rate(self) -> float:
        if len(self._window) < 2:
            return 0.0
        span = self._window[-1][0] - self._window[0][0]
        return len(self._window) / span if span > 0 else 0.0
