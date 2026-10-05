"""Voz no PC: escuta com o faster-whisper já carregado e fala com o Piper (Cadu).

O navegador manda o áudio do microfone (PC ou celular) pelo WebSocket /ear.
Um limiar de volume corta a frase ~0,4 s depois do silêncio — sem esperar o
reconhecimento do Chrome, e sem gravar 5 s fixos. A palavra de ativação
continua sendo "ei, Simba", lida no texto.

Se o faster-whisper não estiver instalado, /ear responde "off" e o app volta
para o microfone do navegador. Se o Piper não estiver instalado, a fala segue
no edge-tts. Na Railway os dois ficam de fora de propósito.

  pip install faster-whisper piper-tts
"""
import io, os, threading, urllib.request, wave
from pathlib import Path
from .config import DATA

STT_MODEL = os.getenv("SIMBA_STT_MODEL", "base")
FRAME = 480                    # 30 ms em 16 kHz
FRAME_BYTES = FRAME * 2
RATE = 16000
PIPER_ONNX = "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/cadu/medium/pt_BR-cadu-medium.onnx"
PIPER_JSON = PIPER_ONNX + ".json"

_model = None
_piper = None
_lock = threading.Lock()
_piper_lock = threading.Lock()


def installed() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def ensure_model() -> bool:
    """Carrega o Whisper uma vez. As frases seguintes não pagam a abertura."""
    global _model
    if _model is not None:
        return True
    if not installed():
        return False
    with _lock:
        if _model is not None:
            return True
        try:
            from faster_whisper import WhisperModel
            threads = min(8, os.cpu_count() or 4)
            print(f"[voz] carregando escuta ({STT_MODEL})")
            _model = WhisperModel(STT_MODEL, device="cpu", compute_type="int8", cpu_threads=threads, num_workers=1)
            print(f"[voz] escuta local pronta ({STT_MODEL})")
            return True
        except Exception as e:
            print(f"[voz] escuta local indisponível: {e}")
            return False


def _junk(text: str) -> bool:
    n = " ".join(text.lower().replace(",", " ").replace(".", " ").split())
    if len(n) < 2:
        return True
    return n.startswith("legendas") or "inscreva-se" in n or n.startswith("obrigado por assistir")


def transcribe(pcm: bytes) -> str:
    if _model is None and not ensure_model():
        return ""
    import numpy as np
    audio = np.frombuffer(pcm, dtype=np.int16).astype("float32") / 32768.0
    if audio.size < RATE // 4:
        return ""
    with _lock:
        segments, _info = _model.transcribe(
            audio, language="pt", beam_size=1, best_of=1, temperature=0,
            condition_on_previous_text=False, vad_filter=False, without_timestamps=True,
            initial_prompt="Ei, Simba.",
        )
        parts = []
        for seg in segments:
            if seg.no_speech_prob is not None and seg.no_speech_prob > 0.6:
                continue
            parts.append(seg.text)
    text = " ".join(parts).strip()
    return "" if _junk(text) else text


def _rms(frame: bytes) -> float:
    import array
    samples = array.array("h")
    samples.frombytes(frame)
    if not samples:
        return 0.0
    acc = 0
    for s in samples:
        acc += s * s
    return (acc / len(samples)) ** 0.5 / 32768.0


class Decoder:
    """Corta a fala quando o volume cai. Devolve ('partial'|'final', pcm)."""

    def __init__(self):
        self.pending = bytearray()
        self.pre = bytearray()
        self.utt = bytearray()
        self.speech = False
        self.hot = 0
        self.quiet = 0
        self.noise = 0.008
        self.partial_at = 0

    def feed(self, pcm: bytes) -> list[tuple[str, bytes]]:
        self.pending.extend(pcm)
        out = []
        while len(self.pending) >= FRAME_BYTES:
            frame = bytes(self.pending[:FRAME_BYTES])
            del self.pending[:FRAME_BYTES]
            level = _rms(frame)
            voiced = level > max(0.012, self.noise * 3.2)
            if not self.speech and not voiced:
                self.noise = self.noise * 0.98 + level * 0.02
            if not self.speech:
                self.pre.extend(frame)
                extra = len(self.pre) - FRAME_BYTES * 8
                if extra > 0:
                    del self.pre[:extra]
                if voiced:
                    self.hot += 1
                    if self.hot >= 4:
                        self.speech = True
                        self.utt = bytearray(self.pre)
                        self.quiet = 0
                        self.partial_at = len(self.utt)
                else:
                    self.hot = 0
                continue
            self.utt.extend(frame)
            if voiced:
                self.quiet = 0
            else:
                self.quiet += 1
            too_long = len(self.utt) >= RATE * 2 * 20
            if self.quiet >= 14 or too_long:
                tail = 0 if too_long else FRAME_BYTES * self.quiet
                audio = bytes(self.utt[:-tail] if tail and tail < len(self.utt) else self.utt)
                self._idle()
                if len(audio) >= FRAME_BYTES * 10:
                    out.append(("final", audio))
            elif len(self.utt) - self.partial_at >= RATE * 2:
                self.partial_at = len(self.utt)
                out.append(("partial", bytes(self.utt[-RATE * 2 * 8:])))
        return out

    def _idle(self):
        self.speech = False
        self.hot = 0
        self.quiet = 0
        self.utt.clear()
        self.pre.clear()
        self.partial_at = 0


def _voices() -> tuple[Path, Path]:
    folder = DATA / "voices"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "pt_BR-cadu-medium.onnx", folder / "pt_BR-cadu-medium.onnx.json"


def _download(url: str, dest: Path):
    if dest.is_file() and dest.stat().st_size > 1000:
        return
    try:
        import certifi, ssl
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ctx = None
    print(f"[voz] baixando {dest.name}")
    req = urllib.request.Request(url, headers={"User-Agent": "simba"})
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, context=ctx, timeout=180) as src, tmp.open("wb") as out:
        while True:
            block = src.read(1024 * 256)
            if not block:
                break
            out.write(block)
    tmp.replace(dest)


def piper_ready() -> bool:
    return _piper is not None


def ensure_piper() -> bool:
    global _piper
    if _piper is not None:
        return True
    try:
        from piper import PiperVoice
    except Exception:
        return False
    with _piper_lock:
        if _piper is not None:
            return True
        try:
            onnx, cfg = _voices()
            _download(PIPER_ONNX, onnx)
            _download(PIPER_JSON, cfg)
            _piper = PiperVoice.load(str(onnx), config_path=str(cfg))
            print("[voz] fala local pronta (cadu)")
            return True
        except Exception as e:
            print(f"[voz] piper indisponível, sigo no edge-tts: {e}")
            return False


def synth_piper(text: str) -> bytes | None:
    """WAV de uma frase. None se o Piper não estiver pronto ou falhar."""
    voice = _piper
    if voice is None or not (text or "").strip():
        return None
    buf = io.BytesIO()
    try:
        if hasattr(voice, "synthesize_wav"):
            with wave.open(buf, "wb") as wav:
                voice.synthesize_wav(text, wav)
            data = buf.getvalue()
            return data if len(data) > 44 else None
        chunks, rate, width, channels = [], 22050, 2, 1
        for audio in voice.synthesize(text):
            raw = getattr(audio, "audio_int16_bytes", None)
            if raw is None and isinstance(audio, (bytes, bytearray)):
                raw = bytes(audio)
            if not raw:
                continue
            chunks.append(raw)
            rate = getattr(audio, "sample_rate", rate)
            width = getattr(audio, "sample_width", width)
            channels = getattr(audio, "sample_channels", channels)
        if not chunks:
            return None
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(width)
            wav.setframerate(rate)
            wav.writeframes(b"".join(chunks))
        return buf.getvalue()
    except Exception as e:
        print(f"[voz] piper falhou: {e}")
        return None


def warm():
    """Sobe em segundo plano quando o servidor liga."""
    try:
        ensure_model()
    except Exception as e:
        print(f"[voz] {e}")
    try:
        ensure_piper()
    except Exception as e:
        print(f"[voz] {e}")
