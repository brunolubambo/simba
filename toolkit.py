import asyncio, functools, traceback


def schema(required: dict, optional: dict | None = None) -> dict:
    """required/optional: {nome: (tipo_json, descrição)}"""
    props = {k: {"type": t, "description": d} for k, (t, d) in {**required, **(optional or {})}.items()}
    return {"type": "object", "properties": props, "required": list(required)}


def ok(text: str) -> dict:
    return {"content": [{"type": "text", "text": text or "(vazio)"}]}


def err(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "is_error": True}


def safe(fn):
    """Roda a função síncrona numa thread e transforma exceções em erro legível para o agente."""
    @functools.wraps(fn)
    async def wrapper(args):
        try:
            return ok(await asyncio.to_thread(fn, args))
        except Exception as e:
            return err(f"{type(e).__name__}: {e}")
    return wrapper
