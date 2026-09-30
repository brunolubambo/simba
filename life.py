"""Dados do dia a dia num SQLite local (data/simba.db): lembretes, finanças, treinos e estudos."""
import calendar, sqlite3
from datetime import datetime, timedelta
from claude_agent_sdk import tool, create_sdk_mcp_server
from .config import DATA, now
from .toolkit import schema, safe

DB = DATA / "simba.db"


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.executescript("""
    CREATE TABLE IF NOT EXISTS lembretes(id INTEGER PRIMARY KEY, texto TEXT, quando TEXT, repetir TEXT DEFAULT 'nao', feito INT DEFAULT 0);
    CREATE TABLE IF NOT EXISTS financas(id INTEGER PRIMARY KEY, data TEXT, tipo TEXT, valor REAL, categoria TEXT, descricao TEXT, conta TEXT);
    CREATE TABLE IF NOT EXISTS treinos(id INTEGER PRIMARY KEY, data TEXT, exercicio TEXT, series INT, reps INT, carga REAL, obs TEXT);
    CREATE TABLE IF NOT EXISTS estudos(id INTEGER PRIMARY KEY, data TEXT, assunto TEXT, minutos INT, notas TEXT);
    """)
    return c


def _date(s: str | None) -> str:
    return (s or now().date().isoformat())[:10]


def _dt(s: str) -> str:
    return datetime.fromisoformat(s).isoformat(timespec="minutes")


# ---------- lembretes ----------
def advance(quando: str, repetir: str) -> str | None:
    d = datetime.fromisoformat(quando)
    if repetir == "diario":
        d += timedelta(days=1)
    elif repetir == "dias_uteis":
        d += timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
    elif repetir == "semanal":
        d += timedelta(weeks=1)
    elif repetir == "mensal":
        m = d.month % 12 + 1
        y = d.year + (d.month == 12)
        d = d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))
    else:
        return None
    return d.isoformat(timespec="minutes")


def due(at: datetime | None = None) -> list[dict]:
    at = (at or now()).isoformat(timespec="minutes")
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM lembretes WHERE feito=0 AND quando<=? ORDER BY quando", (at,))]


def fired(rid: int):
    """Chamado quando o lembrete dispara: repete ou marca como feito."""
    with db() as c:
        r = c.execute("SELECT * FROM lembretes WHERE id=?", (rid,)).fetchone()
        if not r:
            return
        nxt = advance(r["quando"], r["repetir"])
        if nxt:
            c.execute("UPDATE lembretes SET quando=? WHERE id=?", (nxt, rid))
        else:
            c.execute("UPDATE lembretes SET feito=1 WHERE id=?", (rid,))


def snooze(rid: int, minutes: int = 10):
    with db() as c:
        r = c.execute("SELECT * FROM lembretes WHERE id=?", (rid,)).fetchone()
        if r:
            c.execute("INSERT INTO lembretes(texto,quando) VALUES(?,?)",
                      (r["texto"], (now() + timedelta(minutes=minutes)).isoformat(timespec="minutes")))


@tool("lembrete_criar", "Cria lembrete que chega como notificação no celular e no PC.",
      schema({"texto": ("string", "o que lembrar"), "quando": ("string", "AAAA-MM-DDTHH:MM, hora local")},
             {"repetir": ("string", "nao | diario | dias_uteis | semanal | mensal")}))
@safe
def lembrete_criar(a):
    rep = a.get("repetir", "nao")
    if rep not in ("nao", "diario", "dias_uteis", "semanal", "mensal"):
        raise ValueError("repetir inválido")
    with db() as c:
        cur = c.execute("INSERT INTO lembretes(texto,quando,repetir) VALUES(?,?,?)", (a["texto"], _dt(a["quando"]), rep))
    return f"Lembrete #{cur.lastrowid}: '{a['texto']}' em {_dt(a['quando'])}" + ("" if rep == "nao" else f", repete {rep}")


@tool("lembrete_listar", "Lista lembretes pendentes.", schema({}))
@safe
def lembrete_listar(a):
    with db() as c:
        rows = c.execute("SELECT * FROM lembretes WHERE feito=0 ORDER BY quando").fetchall()
    return "\n".join(f"#{r['id']} {r['quando']} | {r['texto']}" + ("" if r["repetir"] == "nao" else f" ({r['repetir']})")
                     for r in rows) or "Nenhum lembrete pendente."


@tool("lembrete_concluir", "Conclui ou cancela um lembrete (inclusive os que repetem).", schema({"id": ("integer", "id")}))
@safe
def lembrete_concluir(a):
    with db() as c:
        c.execute("UPDATE lembretes SET feito=1 WHERE id=?", (int(a["id"]),))
    return "Concluído."


# ---------- finanças ----------
@tool("financa_registrar", "Registra despesa ou receita.",
      schema({"tipo": ("string", "despesa | receita"), "valor": ("number", "valor em reais"),
              "categoria": ("string", "ex.: mercado, transporte, moradia, lazer, saúde, salário")},
             {"descricao": ("string", "detalhe"), "data": ("string", "AAAA-MM-DD, padrão hoje"),
              "conta": ("string", "cartão/banco, opcional")}))
@safe
def financa_registrar(a):
    if a["tipo"] not in ("despesa", "receita"):
        raise ValueError("tipo deve ser despesa ou receita")
    with db() as c:
        c.execute("INSERT INTO financas(data,tipo,valor,categoria,descricao,conta) VALUES(?,?,?,?,?,?)",
                  (_date(a.get("data")), a["tipo"], float(a["valor"]), a["categoria"].lower(),
                   a.get("descricao", ""), a.get("conta", "")))
    return f"{a['tipo'].capitalize()} de R$ {float(a['valor']):.2f} em {a['categoria']} registrada."


def finance_summary(de: str, ate: str) -> str:
    with db() as c:
        rows = c.execute("SELECT tipo, categoria, SUM(valor) t, COUNT(*) n FROM financas WHERE data BETWEEN ? AND ? "
                         "GROUP BY tipo, categoria ORDER BY tipo, t DESC", (de, ate)).fetchall()
    if not rows:
        return f"Sem lançamentos entre {de} e {ate}."
    rec = sum(r["t"] for r in rows if r["tipo"] == "receita")
    des = sum(r["t"] for r in rows if r["tipo"] == "despesa")
    lines = [f"{de} a {ate}: receitas R$ {rec:.2f} | despesas R$ {des:.2f} | saldo R$ {rec - des:.2f}"]
    lines += [f"  {r['tipo']:8} {r['categoria']:15} R$ {r['t']:.2f} ({r['n']}x)" for r in rows]
    return "\n".join(lines)


@tool("financa_resumo", "Resumo por categoria num período (padrão: mês atual).",
      schema({}, {"de": ("string", "AAAA-MM-DD"), "ate": ("string", "AAAA-MM-DD")}))
@safe
def financa_resumo(a):
    hoje = now().date()
    return finance_summary(a.get("de") or hoje.replace(day=1).isoformat(), a.get("ate") or hoje.isoformat())


# ---------- treinos ----------
@tool("treino_registrar", "Registra um exercício feito.",
      schema({"exercicio": ("string", "nome"), "series": ("integer", "séries"), "reps": ("integer", "repetições")},
             {"carga": ("number", "kg"), "obs": ("string", "observação"), "data": ("string", "AAAA-MM-DD")}))
@safe
def treino_registrar(a):
    with db() as c:
        c.execute("INSERT INTO treinos(data,exercicio,series,reps,carga,obs) VALUES(?,?,?,?,?,?)",
                  (_date(a.get("data")), a["exercicio"].lower(), int(a["series"]), int(a["reps"]),
                   float(a.get("carga", 0) or 0), a.get("obs", "")))
    return "Treino registrado."


@tool("treino_historico", "Histórico de treinos (filtra por exercício).",
      schema({}, {"exercicio": ("string", "nome"), "dias": ("integer", "padrão 30")}))
@safe
def treino_historico(a):
    since = (now().date() - timedelta(days=int(a.get("dias", 30)))).isoformat()
    q, p = "SELECT * FROM treinos WHERE data>=?", [since]
    if a.get("exercicio"):
        q += " AND exercicio LIKE ?"; p.append(f"%{a['exercicio'].lower()}%")
    with db() as c:
        rows = c.execute(q + " ORDER BY data DESC, id DESC LIMIT 100", p).fetchall()
    return "\n".join(f"{r['data']} {r['exercicio']}: {r['series']}x{r['reps']}" + (f" @ {r['carga']:g} kg" if r["carga"] else "")
                     + (f" ({r['obs']})" if r["obs"] else "") for r in rows) or "Sem treinos no período."


# ---------- estudos ----------
@tool("estudo_registrar", "Registra sessão de estudo (idiomas, cursos, leitura técnica).",
      schema({"assunto": ("string", "ex.: francês, inglês, UX"), "minutos": ("integer", "duração")},
             {"notas": ("string", "o que foi visto, erros comuns"), "data": ("string", "AAAA-MM-DD")}))
@safe
def estudo_registrar(a):
    with db() as c:
        c.execute("INSERT INTO estudos(data,assunto,minutos,notas) VALUES(?,?,?,?)",
                  (_date(a.get("data")), a["assunto"].lower(), int(a["minutos"]), a.get("notas", "")))
    return "Estudo registrado."


@tool("estudo_historico", "Histórico e total de estudo.", schema({}, {"assunto": ("string", "filtro"), "dias": ("integer", "padrão 30")}))
@safe
def estudo_historico(a):
    since = (now().date() - timedelta(days=int(a.get("dias", 30)))).isoformat()
    q, p = "SELECT * FROM estudos WHERE data>=?", [since]
    if a.get("assunto"):
        q += " AND assunto LIKE ?"; p.append(f"%{a['assunto'].lower()}%")
    with db() as c:
        rows = c.execute(q + " ORDER BY data DESC", p).fetchall()
    total = sum(r["minutos"] for r in rows)
    return f"Total: {total} min em {len(rows)} sessões\n" + "\n".join(
        f"{r['data']} {r['assunto']} {r['minutos']} min" + (f": {r['notas']}" if r["notas"] else "") for r in rows[:50])


LEMBRETES = [lembrete_criar, lembrete_listar, lembrete_concluir]
FINANCAS = [financa_registrar, financa_resumo]
TREINOS = [treino_registrar, treino_historico]
ESTUDOS = [estudo_registrar, estudo_historico]
life_server = create_sdk_mcp_server(name="vida", version="1.0.0", tools=LEMBRETES + FINANCAS + TREINOS + ESTUDOS)


def names(tools):
    return [f"mcp__vida__{t.name}" for t in tools]
