import asyncio
import csv
import json
import ssl
import websockets

# ---- USER SETTINGS ----
HA_URL = "ws://192.168.0.115:8123/api/websocket"  # or wss://<your-host>/api/websocket
TOKEN_PATH = "token.txt"
NODES_OUT = "nodes.csv"
EDGES_OUT = "edges.csv"
# In HA 2026.1.x, neighbors are included in the zha/devices payload.
# -----------------------

def load_token(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()

class HAWS:
    def __init__(self, url, token):
        self.url = url
        self.token = token
        self._id = 1
        self.ws = None

    async def connect(self):
        ssl_context = None
        if self.url.startswith("wss://"):
            ssl_context = ssl.create_default_context()
        self.ws = await websockets.connect(self.url, ssl=ssl_context)
        msg = json.loads(await self.ws.recv())
        assert msg.get("type") == "auth_required", msg
        await self.ws.send(json.dumps({"type": "auth", "access_token": self.token}))
        msg = json.loads(await self.ws.recv())
        assert msg.get("type") == "auth_ok", msg

    async def call(self, payload):
        payload = dict(payload)
        payload["id"] = self._id
        self._id += 1
        await self.ws.send(json.dumps(payload))
        while True:
            resp = json.loads(await self.ws.recv())
            if resp.get("id") == payload["id"]:
                if not resp.get("success"):
                    raise RuntimeError(resp)
                return resp.get("result")

    async def close(self):
        if self.ws:
            await self.ws.close()

async def main():
    token = load_token(TOKEN_PATH)
    ha = HAWS(HA_URL, token)
    await ha.connect()

    # Optional: device/area registry for HA-friendly names
    try:
        device_registry = await ha.call({"type": "config/device_registry/list"})
    except RuntimeError as e:
        print("WARN: device registry unavailable:", e)
        device_registry = []
    try:
        area_registry = await ha.call({"type": "config/area_registry/list"})
    except RuntimeError as e:
        print("WARN: area registry unavailable:", e)
        area_registry = []

    area_id_to_name = {a.get("id"): a.get("name") for a in area_registry}
    # Map IEEE -> device registry entry
    ieee_to_devreg = {}
    for dev in device_registry:
        for ident in dev.get("identifiers", []):
            # identifiers are tuples like ["zha", "00:11:22:..."]
            if isinstance(ident, (list, tuple)) and len(ident) == 2:
                domain, ident_value = ident
                if domain == "zha":
                    ieee_to_devreg[ident_value] = dev

    # 1) list devices
    # NOTE: In many HA versions, ZHA websocket commands are:
    # - "zha/devices"
    # - "zha/device/neighbors"
    # If your HA errors, see notes below to discover the exact command names.
    devices = await ha.call({"type": "zha/devices"})

    # Build node rows
    node_rows = []
    # Map IEEE -> friendly name/id
    ieee_to_name = {}

    for d in devices:
        ieee = d.get("ieee")
        zha_name = d.get("name") or d.get("user_given_name") or ieee
        devreg = ieee_to_devreg.get(ieee, {})
        ha_name = devreg.get("name_by_user") or devreg.get("name") or devreg.get("name_by_device")
        ieee_to_name[ieee] = ha_name or zha_name

        ha_area_id = devreg.get("area_id") or d.get("area_id")
        ha_area_name = area_id_to_name.get(ha_area_id)

        node_rows.append({
            "id": ieee,
            "label": ha_name or zha_name,
            "zha_name": zha_name,
            "ha_name": ha_name,
            "ha_name_by_user": devreg.get("name_by_user"),
            "ha_name_by_device": devreg.get("name_by_device"),
            "ha_device_id": devreg.get("id"),
            "nwk": d.get("nwk"),
            "manufacturer": d.get("manufacturer"),
            "model": d.get("model"),
            "quirk_applied": d.get("quirk_applied"),
            "available": d.get("available"),
            "device_type": d.get("device_type"),   # router/end_device/coordinator (often present)
            "last_seen": d.get("last_seen"),
            "area_id": ha_area_id,
            "ha_area_name": ha_area_name,
        })

    # 2) neighbors -> edges (included per-device in zha/devices)
    edge_rows = []
    for d in devices:
        ieee = d.get("ieee")
        neighbors = d.get("neighbors") or []
        # Expected neighbor entry fields (vary by HA version):
        # ieee, nwk, lqi, rssi, relationship, depth, device_type
        for n in neighbors or []:
            tgt_ieee = n.get("ieee")
            if not tgt_ieee:
                continue
            edge_rows.append({
                "source": ieee,
                "target": tgt_ieee,
                "lqi": n.get("lqi", ""),
                "rssi": n.get("rssi", ""),
                "relationship": n.get("relationship", ""),
                "depth": n.get("depth", ""),
                "neighbor_device_type": n.get("device_type", ""),
            })

    await ha.close()

    # Write nodes.csv
    node_fields = list({k for r in node_rows for k in r.keys()})
    node_fields = ["id", "label"] + [f for f in node_fields if f not in ("id", "label")]
    with open(NODES_OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=node_fields)
        w.writeheader()
        w.writerows(node_rows)

    # Write edges.csv
    edge_fields = list({k for r in edge_rows for k in r.keys()})
    edge_fields = ["source", "target"] + [f for f in edge_fields if f not in ("source", "target")]
    with open(EDGES_OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=edge_fields)
        w.writeheader()
        w.writerows(edge_rows)

    print("Wrote:", NODES_OUT, EDGES_OUT)

if __name__ == "__main__":
    asyncio.run(main())
