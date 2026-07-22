"""Calibracion: graba la linea base de cada nodo con la casa VACIA (o quieta).

Escucha el trafico CSI real durante --seconds y guarda media/desviacion del
motion_score de cada nodo en server/calibration.json. El detector usa esos
valores para calcular el z-score.

Uso (con la casa vacia o todo el mundo quieto):
    python calibrate.py --seconds 60
"""

import argparse
import json
import socket
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "server"))
import csi_packet  # noqa: E402
from features import NodeFeatureExtractor  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5566)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument(
        "--out", default=str(Path(__file__).parent.parent / "server" / "calibration.json")
    )
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.host, args.port))
    sock.settimeout(1.0)

    extractors: dict[int, NodeFeatureExtractor] = {}
    scores: dict[int, list[float]] = {}
    deadline = time.time() + args.seconds

    print(f"Grabando linea base durante {args.seconds}s... NO te muevas por la casa.")
    while time.time() < deadline:
        try:
            data, _ = sock.recvfrom(2048)
        except socket.timeout:
            continue
        pkt = csi_packet.parse(data)
        if pkt is None:
            continue
        ext = extractors.setdefault(pkt.node_id, NodeFeatureExtractor())
        ext.add(pkt.amplitudes)
        score = ext.motion_score()
        if score is not None:
            scores.setdefault(pkt.node_id, []).append(score)

    if not scores:
        print("No se recibio CSI de ningun nodo. ¿Estan encendidos los ESP32?")
        return

    calibration = {}
    for node_id, values in sorted(scores.items()):
        arr = np.array(values)
        calibration[str(node_id)] = {"mean": float(arr.mean()), "std": float(arr.std())}
        print(f"  nodo {node_id}: mean={arr.mean():.4f} std={arr.std():.4f} ({len(values)} muestras)")

    Path(args.out).write_text(json.dumps(calibration, indent=2))
    print(f"Calibracion guardada en {args.out}")


if __name__ == "__main__":
    main()
