"""Perfil do usuário em um lugar só: padrões, sobrescritos por data/perfil.json (se existir).

Usado pelo código novo (modo conversa). Exemplo de data/perfil.json:
{"nome_usuario": "Bruno", "idioma_nativo": "pt-BR", "fuso": "America/Fortaleza", "nome_tutor": "Simba"}
"""
import json
import os

from .config import DATA

PADRAO = {
    "nome_usuario": "",
    "idioma_nativo": "pt-BR",
    "fuso": os.getenv("SIMBA_TZ", "America/Fortaleza"),
    "nome_tutor": "Simba",
}


def carregar() -> dict:
    perfil = dict(PADRAO)
    arquivo = DATA / "perfil.json"
    try:
        extra = json.loads(arquivo.read_text(encoding="utf-8"))
        if isinstance(extra, dict):
            perfil.update({k: v for k, v in extra.items() if k in PADRAO and isinstance(v, str) and v.strip()})
    except (OSError, ValueError):
        pass
    return perfil
