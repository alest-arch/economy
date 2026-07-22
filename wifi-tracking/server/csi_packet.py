"""Parseo del paquete UDP binario que envian los nodos ESP32 (ver firmware/src/main.c)."""

import struct
from dataclasses import dataclass

import numpy as np

MAGIC = 0xC51D
HEADER = struct.Struct("<HBBIbBH")  # magic, version, node_id, seq, rssi, channel, csi_len


@dataclass
class CsiPacket:
    node_id: int
    seq: int
    rssi: int
    channel: int
    amplitudes: np.ndarray  # amplitud por subportadora


def parse(data: bytes) -> CsiPacket | None:
    if len(data) < HEADER.size:
        return None
    magic, version, node_id, seq, rssi, channel, csi_len = HEADER.unpack_from(data)
    if magic != MAGIC or version != 1:
        return None
    raw = data[HEADER.size : HEADER.size + csi_len]
    if len(raw) < csi_len or csi_len < 4:
        return None

    iq = np.frombuffer(raw, dtype=np.int8).astype(np.float32)
    if iq.size % 2:
        iq = iq[:-1]
    # El ESP32 entrega pares [imag, real] por subportadora
    imag, real = iq[0::2], iq[1::2]
    amplitudes = np.sqrt(real**2 + imag**2)
    return CsiPacket(node_id, seq, rssi, channel, amplitudes)
