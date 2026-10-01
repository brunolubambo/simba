"""Agente local do PC pessoal: puxa comandos do SIMBA por HTTPS de saída.

Corre como o utilizador, sem admin, sem porta de entrada. Só Documentos e Ambiente de trabalho
(mais PC_ALLOW_DIRS). Nunca o PC da CODATA.

  python -m simba.pc_agent
  python -m simba.pc_agent off
  python -m simba.pc_agent on
  python -m simba.pc_agent self-test

Variáveis locais (.env, sem valores no git): SIMBA_URL, PC_TOKEN (ou SIMBA_TOKEN),
PC_ALLOW_DIRS, PC_ENABLED, PC_KILL_FILE."""
from __future__ import annotations
import json, os, ssl, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path

try:
    from . import pc as pcmod
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from simba import pc as pcmod  # type: ignore

POLL = float(os.getenv("PC_POLL_S", "1.5"))
LER_MAX = 512 * 1024
LISTA_MAX = 400
BUSCA_MAX = 40
SAIDA_MAX = 80_000
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
APPS = {
    "bloco_de_notas": "notepad.exe",
    "notepad": "notepad.exe",
    "explorador": "explorer.exe",
    "explorer": "explorer.exe",
    "calculadora": "calc.exe",
    "calc": "calc.exe",
}
TEXTO = {".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm", ".ini", ".cfg", ".log",
         ".py", ".toml", ".yml", ".yaml", ".rst", ".tex", ".css"}


def _ssl():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _bool(nome: str, padrao: str = "true") -> bool:
    return os.getenv(nome, padrao).lower() in ("1", "true", "yes", "on")


def kill_file() -> Path:
    bruto = os.getenv("PC_KILL_FILE", "").strip()
    return Path(bruto) if bruto else Path.home() / ".simba-pc.off"


def _pasta_conhecida(csidl: int) -> Path | None:
    if os.name != "nt":
        return None
    import ctypes
    buf = ctypes.create_unicode_buffer(260)
    if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) != 0 or not buf.value:
        return None
    return Path(buf.value)


def raizes() -> list[Path]:
    docs = _pasta_conhecida(5) or Path.home() / "Documents"
    if not docs.is_dir():
        alt = Path.home() / "Documentos"
        if alt.is_dir():
            docs = alt
    desk = _pasta_conhecida(16) or Path.home() / "Desktop"
    if not desk.is_dir():
        for n in ("Área de Trabalho", "Desktop"):
            alt = Path.home() / n
            if alt.is_dir():
                desk = alt
                break
    out = [docs, desk]
    extra = os.getenv("PC_ALLOW_DIRS", "").strip()
    for raw in extra.replace("|", ";").split(";"):
        s = raw.strip().strip('"')
        if not s:
            continue
        p = Path(s)
        if not p.is_absolute() or ".." in p.parts:
            log("allow", s, False, "PC_ALLOW_DIRS recusado")
            continue
        if len(p.resolve().parts) < 2:
            log("allow", s, False, "raiz de disco recusada")
            continue
        n = str(p).replace("/", "\\").lower()
        if pcmod.SISTEMA.match(n.lstrip("\\")):
            log("allow", s, False, "pasta de sistema recusada")
            continue
        out.append(p)
    vistos: list[Path] = []
    for p in out:
        chave = os.path.normcase(str(p))
        if any(os.path.normcase(str(x)) == chave for x in vistos):
            continue
        vistos.append(p)
    return vistos


def _real(p: Path) -> Path:
    return Path(os.path.realpath(p))


def _dentro(alvo: Path, bases: list[Path]) -> bool:
    try:
        a = _real(alvo) if alvo.exists() else alvo.resolve()
    except Exception:
        return False
    for b in bases:
        try:
            br = _real(b) if b.exists() else b.resolve()
            a.relative_to(br)
            return True
        except (ValueError, OSError):
            continue
    return False


def _final_handle(fd: int) -> Path | None:
    if os.name != "nt":
        try:
            return Path(os.path.realpath(f"/dev/fd/{fd}"))
        except Exception:
            return None
    import ctypes, msvcrt
    GetFinalPathNameByHandleW = ctypes.windll.kernel32.GetFinalPathNameByHandleW
    GetFinalPathNameByHandleW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_uint]
    GetFinalPathNameByHandleW.restype = ctypes.c_uint
    buf = ctypes.create_unicode_buffer(32768)
    h = msvcrt.get_osfhandle(fd)
    n = GetFinalPathNameByHandleW(h, buf, 32768, 0)
    if not n:
        return None
    s = buf.value
    if s.startswith("\\\\?\\"):
        s = s[4:]
        if s.startswith("UNC\\"):
            s = "\\\\" + s[4:]
    return Path(s)


def _dentro_real(real: Path, raiz: Path) -> bool:
    try:
        real.relative_to(raiz)
        return True
    except ValueError:
        return False


def _componentes_ok(alvo: Path, bases: list[Path]) -> None:
    """Percorre da raiz allowlist até ao alvo. Não começa em C:\\ (isso recusaria tudo)."""
    bases_r = []
    for b in bases:
        try:
            bases_r.append(_real(b) if b.exists() else b.resolve())
        except OSError:
            continue
    if not bases_r:
        raise ValueError("nenhuma pasta permitida existe neste PC")
    try:
        check = _real(alvo) if alvo.exists() else alvo.resolve()
    except OSError as e:
        raise ValueError("caminho recusado") from e
    raiz = next((br for br in bases_r if _dentro_real(check, br)), None)
    if raiz is None:
        pai = alvo.parent
        try:
            pai_r = _real(pai) if pai.exists() else pai.resolve()
        except OSError:
            pai_r = pai
        raiz = next((br for br in bases_r if _dentro_real(pai_r, br)), None)
    if raiz is None:
        raise ValueError("fora das pastas permitidas (Documentos e Ambiente de trabalho)")
    try:
        rel = check.relative_to(raiz)
    except ValueError:
        raise ValueError("caminho recusado (junction ou atalho para fora)")
    acc = raiz
    for parte in rel.parts:
        if parte in ("..", ".", ""):
            raise ValueError("caminho recusado (..)")
        acc = acc / parte
        if not acc.exists():
            continue
        if not _dentro_real(_real(acc), raiz):
            raise ValueError("caminho recusado (junction ou atalho para fora)")


def aliases() -> dict[str, Path]:
    r = raizes()
    docs, desk = r[0], r[1]
    return {
        "documentos": docs, "documents": docs, "docs": docs,
        "desktop": desk, "ambiente de trabalho": desk, "area de trabalho": desk,
        "área de trabalho": desk,
    }


def resolver(pedido: str, *, escrever: bool = False) -> Path:
    s = pcmod.caminho_sintaxe_ok(pedido)
    pcmod._segredo(s)
    bases = raizes()
    chave = s.replace("\\", "/").strip("/").lower()
    if chave in aliases():
        p = aliases()[chave]
        if not _dentro(p, bases):
            raise ValueError("fora das pastas permitidas")
        return _real(p) if p.exists() else p
    p = Path(s)
    if not p.is_absolute():
        candidatos = []
        for b in bases:
            c = (b / s).resolve()
            candidatos.append(c)
            if not escrever and c.exists() and _dentro(c, bases):
                _componentes_ok(c, bases)
                return _real(c)
        p = candidatos[1] if len(candidatos) > 1 else candidatos[0]  # Desktop por omissão
        if not _dentro(p if p.exists() else p.parent, bases):
            raise ValueError("fora das pastas permitidas (Documentos e Ambiente de trabalho)")
        _componentes_ok(p.parent if not p.exists() else p, bases)
        return p
    pai = p.parent if not p.exists() else p
    if not pai.exists() and escrever:
        # criar só se o ancestral existente estiver na allowlist
        anc = p.parent
        while not anc.exists() and anc != anc.parent:
            anc = anc.parent
        if not _dentro(anc, bases):
            raise ValueError("fora das pastas permitidas")
    elif not _dentro(pai, bases):
        raise ValueError("fora das pastas permitidas (Documentos e Ambiente de trabalho)")
    _componentes_ok(p.parent if not p.exists() else p, bases)
    return _real(p) if p.exists() else p.resolve()


def log(acao: str, alvo: str, ok: bool, nota: str = ""):
    alvo_s = str(alvo).replace("\n", " ")[:180]
    linha = f"[pc] {acao}: {'ok' if ok else 'erro'} {alvo_s}"
    if nota and not ok:
        linha += f" ({nota[:80]})"
    print(linha, flush=True)
    try:
        p = Path.home() / ".simba-pc.log"
        with p.open("a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + linha + "\n")
    except OSError:
        pass


def _listar_dir(pasta: Path) -> str:
    if not pasta.is_dir():
        raise ValueError("não é uma pasta")
    itens = []
    with os.scandir(pasta) as it:
        for e in it:
            if len(itens) >= LISTA_MAX:
                itens.append("…")
                break
            try:
                marca = "/" if e.is_dir(follow_symlinks=False) else ""
            except OSError:
                marca = ""
            itens.append(e.name + marca)
    itens.sort()
    return f"{pasta}\n" + "\n".join(itens)


def _ler(path: Path) -> str:
    if not path.is_file():
        raise ValueError("não é um ficheiro")
    if path.stat().st_size > LER_MAX:
        raise ValueError("ficheiro grande demais para ler")
    fd = os.open(str(path), os.O_RDONLY)
    try:
        final = _final_handle(fd)
        if final and not _dentro(final, raizes()):
            raise ValueError("caminho recusado (saiu da allowlist)")
        data = os.read(fd, LER_MAX + 1)
    finally:
        os.close(fd)
    if len(data) > LER_MAX:
        raise ValueError("ficheiro grande demais para ler")
    return data.decode("utf-8", "replace")


def _escrever(path: Path, conteudo: str) -> str:
    if path.suffix.lower() in pcmod.EXEC_EXT:
        raise ValueError("não crio executáveis nem scripts")
    pcmod._segredo(str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    if not _dentro(path.parent, raizes()):
        raise ValueError("pasta-mãe fora da allowlist")
    flags = os.O_CREAT | os.O_WRONLY | os.O_TRUNC
    fd = os.open(str(path), flags, 0o644)
    try:
        final = _final_handle(fd)
        if final and not _dentro(final, raizes()):
            raise ValueError("caminho recusado (saiu da allowlist)")
        os.write(fd, conteudo.encode("utf-8"))
    finally:
        os.close(fd)
    return f"escrito {path} ({len(conteudo)} caracteres)"


def _buscar(pasta: Path, q: str) -> str:
    qn = q.lower()
    hits: list[str] = []
    for root, dirs, files in os.walk(pasta, followlinks=False):
        rp = Path(root)
        if not _dentro(rp, raizes()):
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for nome in files:
            if len(hits) >= BUSCA_MAX:
                return "\n".join(hits) + "\n…"
            p = rp / nome
            linha = None
            if qn in nome.lower():
                linha = str(p)
            elif p.suffix.lower() in TEXTO:
                try:
                    if p.stat().st_size <= LER_MAX and qn in p.read_text(encoding="utf-8", errors="ignore").lower():
                        linha = str(p)
                except OSError:
                    pass
            if linha:
                hits.append(linha)
    return "\n".join(hits) if hits else "(nada encontrado)"


def _abrir_app(nome: str, caminho: str | None) -> str:
    exe = APPS.get(nome.lower())
    extra = os.getenv("PC_APPS", "").strip()
    if not exe and extra:
        for par in extra.split(";"):
            if "=" not in par:
                continue
            k, v = par.split("=", 1)
            v = v.strip()
            if k.strip().lower() == nome.lower() and v and "\\" not in v and "/" not in v and ".." not in v:
                exe = v
                break
    if not exe:
        raise ValueError(f"app '{nome}' não está na lista")
    import shutil
    found = shutil.which(exe)
    if not found:
        raise ValueError(f"não encontrei {exe} neste PC")
    args = [found]
    if caminho:
        args.append(str(resolver(caminho)))
    subprocess.Popen(args, close_fds=True, creationflags=CREATE_NO_WINDOW)
    return f"abri {exe}"


def _abrir_ficheiro(caminho: str) -> str:
    p = resolver(caminho)
    if not p.exists():
        raise ValueError("ficheiro não existe")
    if p.suffix.lower() in pcmod.EXEC_EXT:
        raise ValueError("não abro executáveis da pasta; use um app da lista")
    os.startfile(p)  # type: ignore[attr-defined]
    return f"abri {p}"


def _terminal(cmd: str, cwd: str | None) -> str:
    if cmd == "processos":
        r = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=20,
                           creationflags=CREATE_NO_WINDOW)
        out = (r.stdout or r.stderr or "")[:SAIDA_MAX]
        if r.returncode:
            raise ValueError(out or "tasklist falhou")
        return out or "(vazio)"
    if cmd == "git_status":
        if not cwd:
            raise ValueError("git_status precisa de cwd")
        pasta = resolver(cwd)
        if not pasta.is_dir():
            raise ValueError("cwd não é pasta")
        r = subprocess.run(["git", "status"], cwd=str(pasta), capture_output=True, text=True,
                           timeout=20, creationflags=CREATE_NO_WINDOW)
        out = (r.stdout or r.stderr or "")[:SAIDA_MAX]
        if r.returncode:
            raise ValueError(out or "git status falhou")
        return out or "(vazio)"
    raise ValueError("comando recusado")


def executar(dados: dict) -> str:
    acao = dados.get("acao")
    if acao == "desligar":
        kill_file().write_text("off\n", encoding="utf-8")
        return "desligado"
    if acao == "listar":
        pasta = dados.get("pasta")
        if not pasta:
            blocos = []
            for r in raizes():
                if r.exists():
                    blocos.append(_listar_dir(r))
            return "\n\n".join(blocos) or "(pastas permitidas vazias ou inexistentes)"
        return _listar_dir(resolver(pasta))
    if acao == "ler":
        return _ler(resolver(dados.get("caminho", "")))[: pcmod.LER_MAX]
    if acao == "buscar":
        pasta = dados.get("pasta")
        q = str(dados.get("q") or "")
        if pasta:
            return _buscar(resolver(pasta), q)
        partes = [_buscar(r, q) for r in raizes() if r.exists()]
        texto = "\n".join(p for p in partes if p and p != "(nada encontrado)")
        return texto or "(nada encontrado)"
    if acao == "escrever":
        return _escrever(resolver(dados.get("caminho", ""), escrever=True), str(dados.get("conteudo") or ""))
    if acao == "abrir":
        if dados.get("app"):
            return _abrir_app(str(dados["app"]), dados.get("caminho"))
        return _abrir_ficheiro(str(dados.get("caminho") or ""))
    if acao == "terminal":
        return _terminal(str(dados.get("cmd") or ""), dados.get("cwd"))
    raise ValueError(f"ação '{acao}' recusada")


def _headers() -> dict:
    token = os.getenv("PC_TOKEN", "").strip() or os.getenv("SIMBA_TOKEN", "").strip()
    if not token:
        raise SystemExit("defina PC_TOKEN ou SIMBA_TOKEN no .env (sem pôr o valor no git)")
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _url() -> str:
    u = os.getenv("SIMBA_URL", "").strip().rstrip("/")
    if not u.startswith("https://") and not u.startswith("http://localhost") and not u.startswith("http://127.0.0.1"):
        raise SystemExit("defina SIMBA_URL com https:// (ou http://localhost para teste)")
    return u


def _pedido(metodo: str, caminho: str, corpo: dict | None = None) -> tuple[int, bytes]:
    data = None if corpo is None else json.dumps(corpo, ensure_ascii=False).encode()
    req = urllib.request.Request(_url() + caminho, data=data, method=metodo, headers=_headers())
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=25, context=_ssl()) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() if e.fp else b""


def self_test() -> int:
    print("raízes:", ", ".join(str(p) for p in raizes()))
    falhas = 0
    for mau in (r"..\..\Windows\win.ini", r"C:\Windows\System32\cmd.exe",
                r"\\servidor\c$", r"C:\Users\Windows 11\Desktop\a:stream"):
        try:
            resolver(mau)
            print("FALHOU (devia recusar):", mau)
            falhas += 1
        except ValueError:
            print("recusou:", mau)
    for r in raizes():
        if r.exists():
            resolver(str(r))
            print("aceitou raiz:", r)
            break
    print("kill file:", kill_file())
    return 1 if falhas else 0


def loop():
    if os.name != "nt":
        raise SystemExit("este agente só corre no Windows pessoal")
    if not _bool("PC_ENABLED", "true"):
        raise SystemExit("PC_ENABLED=false — agente parado")
    kf = kill_file()
    if kf.exists():
        raise SystemExit(f"kill switch activo ({kf}). Apague o ficheiro ou rode: python -m simba.pc_agent on")
    print(f"SIMBA PC agente a ouvir {_url()} (Ctrl+C para parar)", flush=True)
    while True:
        if not _bool("PC_ENABLED", "true") or kf.exists():
            print("[pc] desligado", flush=True)
            return
        try:
            code, raw = _pedido("GET", "/pc/proximo")
        except Exception as e:
            print(f"[pc] rede: {type(e).__name__}", flush=True)
            time.sleep(5)
            continue
        if code == 204:
            time.sleep(POLL)
            continue
        if code == 401:
            print("[pc] token recusado", flush=True)
            time.sleep(8)
            continue
        if code != 200:
            print(f"[pc] HTTP {code}", flush=True)
            time.sleep(4)
            continue
        try:
            dados = json.loads(raw.decode())
        except Exception:
            time.sleep(POLL)
            continue
        cmd = str(dados.get("id") or "")
        acao = str(dados.get("acao") or "")
        try:
            detalhe = executar(dados)
            ok = True
        except Exception as e:
            detalhe = str(e)[:500]
            ok = False
        log(acao, dados.get("caminho") or dados.get("pasta") or dados.get("cwd") or dados.get("app") or acao, ok,
            "" if ok else detalhe)
        try:
            _pedido("POST", "/pc/resultado", {"id": cmd, "ok": ok, "detalhe": detalhe[:SAIDA_MAX]})
        except Exception as e:
            print(f"[pc] resultado: {type(e).__name__}", flush=True)
        if acao == "desligar":
            return


def main(argv: list[str] | None = None):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    args = list(sys.argv[1:] if argv is None else argv)
    kf = kill_file()
    if args[:1] == ["off"]:
        kf.write_text("off\n", encoding="utf-8")
        print("kill switch ligado:", kf)
        return 0
    if args[:1] == ["on"]:
        if kf.exists():
            kf.unlink()
        print("kill switch desligado")
        if args[1:] == ["--stay"]:
            return 0
        # continua e liga o loop
    if args[:1] == ["self-test"]:
        return self_test()
    try:
        loop()
    except KeyboardInterrupt:
        print("\n[pc] parado")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
