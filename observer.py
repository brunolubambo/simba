"""Observador proativo: captura a tela do PC, só analisa quando ela muda de verdade,
usa um modelo barato para decidir se vale sugerir algo e manda a sugestão para PC e celular."""
import asyncio, hashlib, json, os, re, time
from datetime import datetime
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock
from .config import WORKSPACE, DATA, PROMPTS

ACTIVITY = DATA / "activity.md"
SCREENS = WORKSPACE / ".screens"


class Observer:
    def __init__(self, hub):
        self.hub = hub
        self.available = os.getenv("OBSERVER_ENABLED", "true").lower() == "true"   # há tela para observar?
        self.enabled = self.available
        self.model = os.getenv("OBSERVER_MODEL", "claude-haiku-4-5-20251001")
        self.interval = int(os.getenv("OBSERVER_INTERVAL_S", "20"))
        self.cooldown = int(os.getenv("OBSERVER_COOLDOWN_S", "180"))
        self.min_conf = float(os.getenv("OBSERVER_MIN_CONFIDENCE", "0.7"))
        self.quiet = os.getenv("OBSERVER_QUIET_HOURS", "")
        self.last_sig = None
        self.last_suggest = 0.0
        self.recent_titles: list[str] = []

    # ---------- regras baratas (sem modelo) ----------
    def in_quiet_hours(self, hour: int | None = None) -> bool:
        if not self.quiet:
            return False
        a, b = (int(x) for x in self.quiet.split("-"))
        h = datetime.now().hour if hour is None else hour
        return (a <= h < b) if a < b else (h >= a or h < b)

    @staticmethod
    def signature(rgb: bytes, buckets: int = 64) -> list[int]:
        """Assinatura grosseira da tela: média por faixa. Ignora mudanças mínimas (cursor, relógio)."""
        n = max(1, len(rgb) // buckets)
        return [sum(rgb[i * n:(i + 1) * n:97]) // max(1, len(rgb[i * n:(i + 1) * n:97])) for i in range(buckets)]

    @staticmethod
    def changed(a, b, threshold: int = 6) -> bool:
        if a is None:
            return True
        diff = sum(1 for x, y in zip(a, b) if abs(x - y) > 8)
        return diff >= threshold

    @staticmethod
    def parse(text: str) -> dict | None:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None

    def log_activity(self, line: str):
        with ACTIVITY.open("a", encoding="utf-8") as f:
            f.write(f"- {datetime.now():%Y-%m-%d %H:%M} {line}\n")
        lines = ACTIVITY.read_text(encoding="utf-8").splitlines()[-300:]
        ACTIVITY.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def recent_activity(self, n: int = 15) -> str:
        return "\n".join(ACTIVITY.read_text(encoding="utf-8").splitlines()[-n:]) if ACTIVITY.exists() else "(sem registro)"

    # ---------- captura e análise ----------
    def capture(self):
        import mss, mss.tools
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[1])
            return shot

    async def analyze(self, path: str) -> dict | None:
        prompt = (f"Registro recente:\n{self.recent_activity()}\n\n"
                  f"Sugestões já feitas (não repita): {self.recent_titles[-5:]}\n\n"
                  f"Leia a captura em {path} com a ferramenta Read e responda com o JSON.")
        opts = ClaudeAgentOptions(system_prompt=(PROMPTS / "observer.md").read_text(encoding="utf-8"), model=self.model,
                                  tools=["Read"], allowed_tools=["Read"], max_turns=3, cwd=str(WORKSPACE))
        out = []
        async for msg in query(prompt=prompt, options=opts):
            if isinstance(msg, AssistantMessage):
                out += [b.text for b in msg.content if isinstance(b, TextBlock)]
        return self.parse("\n".join(out))

    async def tick(self):
        if not self.available or not self.enabled or self.in_quiet_hours() or not self.hub.clients:
            return
        shot = await asyncio.to_thread(self.capture)
        sig = self.signature(shot.rgb)
        if not self.changed(self.last_sig, sig):
            return
        self.last_sig = sig
        SCREENS.mkdir(parents=True, exist_ok=True)
        path = SCREENS / f"obs_{int(time.time())}.png"
        import mss.tools
        mss.tools.to_png(shot.rgb, shot.size, output=str(path))
        try:
            r = await self.analyze(str(path))
        finally:
            path.unlink(missing_ok=True)   # privacidade: não guarda capturas
        if not r:
            return
        self.log_activity(r.get("atividade", "?"))
        await self.hub.broadcast({"type": "activity", "text": r.get("atividade", "")})
        ok = (r.get("sugerir") and float(r.get("confianca", 0)) >= self.min_conf
              and time.time() - self.last_suggest >= self.cooldown and r.get("acao"))
        if ok:
            self.last_suggest = time.time()
            self.recent_titles.append(r.get("titulo", ""))
            await self.hub.suggest({k: r.get(k) for k in ("titulo", "motivo", "acao", "confianca")})

    async def run(self):
        while True:
            try:
                await self.tick()
            except Exception as e:
                await self.hub.broadcast({"type": "error", "text": f"Observador: {e}"})
                await asyncio.sleep(60)
            await asyncio.sleep(self.interval)
