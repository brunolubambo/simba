"""Central de dispositivos: PC e celular conectados ao mesmo Simba.
Tudo que o Simba emite vai para todos; a primeira resposta a uma aprovação vale."""
import asyncio, json, os, uuid
from fastapi import WebSocket
from .config import DATA

SUBS = DATA / "push_subscriptions.json"


class Hub:
    def __init__(self):
        self.clients: dict[WebSocket, str] = {}
        self.pending: dict[str, asyncio.Future] = {}
        self.suggestions: dict[str, dict] = {}
        self.on_suggest = None          # modo automático: o servidor executa a sugestão sozinho

    def add(self, ws: WebSocket, device: str):
        self.clients[ws] = device

    def remove(self, ws: WebSocket):
        self.clients.pop(ws, None)

    def devices(self) -> list[str]:
        return list(self.clients.values())

    async def broadcast(self, ev: dict, push: bool = False):
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_json(ev)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.remove(ws)
        if push:
            try:
                await asyncio.to_thread(send_push, ev)
            except Exception:
                pass

    async def approve(self, prompt: str, timeout: float = 300) -> bool:
        """Pede aprovação a todos os dispositivos. Sem resposta = negado."""
        aid = uuid.uuid4().hex[:8]
        fut = asyncio.get_running_loop().create_future()
        self.pending[aid] = fut
        await self.broadcast({"type": "approval", "id": aid, "prompt": prompt}, push=True)
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            return False
        finally:
            self.pending.pop(aid, None)
            await self.broadcast({"type": "approval_closed", "id": aid})

    def resolve(self, aid: str, ok: bool):
        fut = self.pending.get(aid)
        if fut and not fut.done():
            fut.set_result(bool(ok))

    def has_push(self) -> bool:
        return bool(load_subs())

    async def suggest(self, s: dict) -> str:
        sid = uuid.uuid4().hex[:8]
        auto = self.on_suggest is not None
        if not auto:
            self.suggestions[sid] = s
        await self.broadcast({"type": "suggestion", "id": sid, "auto": auto, **s}, push=True)
        if auto:
            await self.on_suggest(s)
        return sid


# ---------- Web Push (chaves geradas sozinhas na 1ª execução) ----------
def vapid() -> tuple[str, str]:
    """(caminho da chave privada, chave pública em base64url)."""
    import base64
    from py_vapid import Vapid01
    from cryptography.hazmat.primitives import serialization
    pem = DATA / "vapid_private.pem"
    if not pem.exists():
        v = Vapid01()
        v.generate_keys()
        v.save_key(str(pem))
    v = Vapid01.from_file(str(pem))
    raw = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return str(pem), base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def load_subs() -> list:
    return json.loads(SUBS.read_text()) if SUBS.exists() else []


def save_sub(sub: dict):
    subs = [s for s in load_subs() if s.get("endpoint") != sub.get("endpoint")]
    subs.append(sub)
    SUBS.write_text(json.dumps(subs))


def send_push(ev: dict):
    subs = load_subs()
    if not subs:
        return
    try:
        from pywebpush import webpush, WebPushException
        key = vapid()[0]
    except ImportError:
        return
    title = ev.get("titulo") or "SIMBA precisa da sua aprovação"
    body = ev.get("motivo") or ev.get("prompt", "")
    keep = []
    for sub in subs:
        try:
            webpush(sub, json.dumps({"title": title, "body": body[:180]}),
                    vapid_private_key=key, vapid_claims={"sub": os.getenv("VAPID_EMAIL", "mailto:simba@example.com")}, ttl=3600)
            keep.append(sub)
        except WebPushException as e:
            if getattr(e.response, "status_code", 0) not in (404, 410):   # 404/410: celular desinscrito
                keep.append(sub)
        except Exception:
            keep.append(sub)            # falha de rede: tenta de novo na próxima
    SUBS.write_text(json.dumps(keep))
