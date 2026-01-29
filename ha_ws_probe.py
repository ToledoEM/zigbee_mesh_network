import asyncio
import json
import ssl

import websockets

HA_URL = "ws://192.168.0.115:8123/api/websocket"
TOKEN_PATH = "token.txt"
OUT_FILE = "ws_probe_results.json"


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

    results = {"success": {}, "errors": {}}

    candidates = [
        ("zha/devices", {}),
        ("zha/device/neighbors", {"ieee": None}),
        ("zha/configuration", {}),
        ("zha/network", {}),
        ("zha/network/scan", {}),
    ]

    devices = None
    try:
        devices = await ha.call({"type": "zha/devices"})
        results["success"]["zha/devices"] = devices
    except RuntimeError as exc:
        results["errors"]["zha/devices"] = exc.args[0] if exc.args else {"error": "unknown"}

    for cmd, extra in candidates:
        if cmd == "zha/devices":
            continue
        payload = {"type": cmd}
        payload.update(extra)
        try:
            if cmd == "zha/device/neighbors":
                if not devices:
                    raise RuntimeError({"error": {"code": "no_devices"}})
                sample_ieee = devices[0].get("ieee")
                payload["ieee"] = sample_ieee
            results["success"][cmd] = await ha.call(payload)
        except RuntimeError as exc:
            results["errors"][cmd] = exc.args[0] if exc.args else {"error": "unknown"}

    await ha.close()

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
