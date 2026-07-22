"""Fusiona los estados de los nodos en un mapa habitacion/planta -> ocupacion."""

from detector import MOTION, PRESENCE, OFFLINE


class Localizer:
    def __init__(self, config: dict):
        self.node_map: dict[int, dict] = {
            int(nid): info for nid, info in config.get("nodes", {}).items()
        }

    def rooms(self, node_states: dict) -> dict:
        result: dict[str, dict] = {}
        for nid, info in self.node_map.items():
            room = info["room"]
            floor = info["floor"]
            ns = node_states.get(nid)
            entry = result.setdefault(
                room,
                {"floor": floor, "state": OFFLINE, "zscore": 0.0, "nodes": []},
            )
            if ns is None:
                entry["nodes"].append({"node_id": nid, "state": OFFLINE, "zscore": 0.0})
                continue
            entry["nodes"].append(
                {"node_id": nid, "state": ns.state, "zscore": round(ns.zscore, 2)}
            )
            # El estado mas "activo" de los nodos de la habitacion manda
            rank = {MOTION: 3, PRESENCE: 2, "vacio": 1, OFFLINE: 0}
            if rank.get(ns.state, 0) >= rank.get(entry["state"], 0):
                entry["state"] = ns.state
                entry["zscore"] = round(ns.zscore, 2)
        return result

    def summary(self, rooms: dict) -> dict:
        occupied = [r for r, v in rooms.items() if v["state"] in (MOTION, PRESENCE)]
        floors: dict[int, list[str]] = {}
        for room, v in rooms.items():
            floors.setdefault(v["floor"], []).append(room)
        return {
            "occupied_rooms": occupied,
            "floors": {str(f): sorted(rs) for f, rs in sorted(floors.items())},
        }
