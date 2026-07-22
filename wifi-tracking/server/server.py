"""Servidor central: recibe CSI por UDP, detecta ocupacion y sirve el dashboard.

Uso:
    python server.py [--config config.yaml]
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

import uvicorn
import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

import csi_packet
from detector import Detector
from features import NodeFeatureExtractor
from localizer import Localizer

BASE_DIR = Path(__file__).parent


class Engine:
    def __init__(self, config: dict):
        self.config = config
        det = config.get("detection", {})
        self.window_seconds = det.get("window_seconds", 2.0)
        self.min_packets = det.get("min_packets", 20)
        self.extractors: dict[int, NodeFeatureExtractor] = {}
        self.detector = Detector(config, BASE_DIR / config.get("calibration_file", "calibration.json"))
        self.localizer = Localizer(config)
        self.packet_count = 0

    def ingest(self, data: bytes) -> None:
        pkt = csi_packet.parse(data)
        if pkt is None:
            return
        self.packet_count += 1
        ext = self.extractors.setdefault(
            pkt.node_id,
            NodeFeatureExtractor(self.window_seconds, self.min_packets),
        )
        ext.add(pkt.amplitudes)

    def snapshot(self) -> dict:
        now = time.time()
        for nid, ext in self.extractors.items():
            score = ext.motion_score() if now - ext.last_packet_time < 3.0 else None
            self.detector.update(nid, score, now)
        rooms = self.localizer.rooms(self.detector.states)
        return {
            "ts": now,
            "packets": self.packet_count,
            "rooms": rooms,
            "summary": self.localizer.summary(rooms),
        }


class UdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, engine: Engine):
        self.engine = engine

    def datagram_received(self, data: bytes, addr) -> None:
        self.engine.ingest(data)


def build_app(engine: Engine) -> FastAPI:
    app = FastAPI(title="wifi-person-tracking")
    clients: set[WebSocket] = set()

    @app.get("/")
    async def index():
        return FileResponse(BASE_DIR / "static" / "index.html")

    @app.get("/api/state")
    async def state():
        return engine.snapshot()

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        clients.add(websocket)
        try:
            while True:
                await websocket.send_text(json.dumps(engine.snapshot()))
                await asyncio.sleep(0.5)
        except WebSocketDisconnect:
            pass
        finally:
            clients.discard(websocket)

    return app


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(BASE_DIR / "config.yaml"))
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text())
    engine = Engine(config)

    listen = config.get("listen", {})
    loop = asyncio.get_running_loop()
    await loop.create_datagram_endpoint(
        lambda: UdpProtocol(engine),
        local_addr=(listen.get("host", "0.0.0.0"), listen.get("port", 5566)),
    )
    print(f"[csi] escuchando UDP en {listen.get('host')}:{listen.get('port')}")

    dash = config.get("dashboard", {})
    server = uvicorn.Server(
        uvicorn.Config(
            build_app(engine),
            host=dash.get("host", "0.0.0.0"),
            port=dash.get("port", 8080),
            log_level="warning",
        )
    )
    print(f"[web] dashboard en http://localhost:{dash.get('port', 8080)}")
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
