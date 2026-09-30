"""Voz (opcional, não testada). STT local com faster-whisper, TTS com edge-tts.
Uso: texto = listen_once(5); await speak("Olá, senhor.")"""


def listen_once(seconds: int = 5, model_size: str = "small") -> str:
    import sounddevice as sd
    from faster_whisper import WhisperModel
    rate = 16000
    audio = sd.rec(int(seconds * rate), samplerate=rate, channels=1, dtype="float32")
    sd.wait()
    model = WhisperModel(model_size, compute_type="int8")
    segs, _ = model.transcribe(audio.flatten(), language="pt")
    return " ".join(s.text for s in segs).strip()


async def speak(text: str, voice: str = "pt-BR-AntonioNeural", out: str = "reply.mp3"):
    import edge_tts
    await edge_tts.Communicate(text, voice).save(out)
    return out
