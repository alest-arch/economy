"""Simulador: genera trafico CSI sintetico de varios nodos y lo envia por UDP.

Permite probar todo el pipeline (servidor + dashboard) sin tener ESP32 todavia.
Simula una persona que va cambiando de habitacion cada pocos segundos.

Uso:
    python simulate.py [--server 127.0.0.1] [--port 5566]
"""

import argparse
import math
import random
import socket
import struct
import time

HEADER = struct.Struct("<HBBIbBH")
MAGIC = 0xC51D
N_SUBCARRIERS = 64
RATE_HZ = 50

# Debe coincidir con server/config.yaml
NODES = {1: "salon", 2: "cocina", 3: "dormitorio-1", 4: "dormitorio-2"}

# Guion: (segundos, habitacion con persona o None)
SCRIPT = [
    (8, None),
    (10, "salon"),
    (8, "cocina"),
    (6, None),
    (10, "dormitorio-1"),
    (8, "dormitorio-2"),
]


def make_packet(node_id: int, seq: int, active: bool, t: float) -> bytes:
    amplitudes = []
    for k in range(N_SUBCARRIERS):
        base = 40 + 15 * math.sin(k / 7.0)
        noise = random.gauss(0, 0.8)
        if active:
            # Una persona moviendose modula el multipath: oscilacion lenta + ruido fuerte
            noise += 8 * math.sin(2 * math.pi * 1.5 * t + k) + random.gauss(0, 4)
        amplitudes.append(base + noise)

    iq = bytearray()
    for a in amplitudes:
        phase = random.uniform(0, 2 * math.pi)
        i = max(-127, min(127, int(a * math.sin(phase))))
        r = max(-127, min(127, int(a * math.cos(phase))))
        iq += struct.pack("<bb", i, r)

    hdr = HEADER.pack(MAGIC, 1, node_id, seq, -55 + random.randint(-3, 3), 6, len(iq))
    return hdr + bytes(iq)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5566)
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    seqs = dict.fromkeys(NODES, 0)
    t0 = time.time()

    print(f"Enviando CSI simulado a {args.server}:{args.port} (Ctrl+C para parar)")
    while True:
        for duration, person_room in SCRIPT:
            label = person_room or "nadie"
            print(f"  -> persona en: {label} ({duration}s)")
            end = time.time() + duration
            while time.time() < end:
                t = time.time() - t0
                for node_id, room in NODES.items():
                    pkt = make_packet(node_id, seqs[node_id], room == person_room, t)
                    seqs[node_id] += 1
                    sock.sendto(pkt, (args.server, args.port))
                time.sleep(1.0 / RATE_HZ)


if __name__ == "__main__":
    main()
