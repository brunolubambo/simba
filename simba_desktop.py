"""SIMBA no Windows: servidor local oculto, janela nativa e bandeja.

Escuta só em 127.0.0.1. Fechar a janela esconde; Sair na bandeja encerra tudo.
Segredos ficam no .env, nunca neste arquivo.
"""
from __future__ import annotations

import argparse
import ctypes
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from ctypes import wintypes
from logging.handlers import RotatingFileHandler
from pathlib import Path

HOST = "127.0.0.1"
DEFAULT_PORT = 8787
MUTEX_NAME = "Local\\SIMBA.Desktop"
SHOW_EVENT = "Local\\SIMBA.Desktop.Show"
ERROR_ALREADY_EXISTS = 183
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
ROOT = Path(__file__).resolve().parent
LOG_PATH = ROOT / "data" / "logs" / "desktop.log"
ICO_PATH = ROOT / "data" / "simba.ico"
WEBVIEW_DIR = ROOT / "data" / "webview2"
EDGE_PROFILE = ROOT / "data" / "edge-profile"

log = logging.getLogger("simba.desktop")
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.OpenEventW.restype = wintypes.HANDLE
kernel32.SetEvent.argtypes = [wintypes.HANDLE]
kernel32.SetEvent.restype = wintypes.BOOL
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
WINDOW_BG = "#020812"


class App:
    def __init__(self) -> None:
        self.quitting = False
        self.shut = False
        self.oculto = False
        self.muted = False
        self.mode = ""
        self.port = DEFAULT_PORT
        self.url = f"http://{HOST}:{DEFAULT_PORT}/"
        self.window = None
        self.icon = None
        self.server: Server | None = None
        self.edge: subprocess.Popen | None = None
        self.mutex = None
        self.show_event = None
        self.saved = None
        self.done = threading.Event()
        self.keep: list = []
        self.webview_retried = False
        self.reloaded = False
        self.want_taskbar_hidden = False


app = App()


class SafeStream(logging.StreamHandler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
        except Exception:
            pass


def setup_log() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log.setLevel(logging.INFO)
    log.propagate = False
    if log.handlers:
        return
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file = RotatingFileHandler(LOG_PATH, maxBytes=1_048_576, backupCount=3, encoding="utf-8")
    file.setFormatter(fmt)
    log.addHandler(file)
    stream = SafeStream(sys.stderr)
    stream.setFormatter(fmt)
    log.addHandler(stream)


def claim() -> str:
    """'owner' se esta instância ficou com a trava, 'busy' se outra já roda, 'error' se a trava falhou."""
    ctypes.set_last_error(0)
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    err = ctypes.get_last_error()
    if not handle:
        log.error("não consegui criar a trava de instância única")
        return "error"
    if err == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return "busy"
    app.mutex = handle
    event = kernel32.CreateEventW(None, False, False, SHOW_EVENT)
    if not event:
        log.error("não consegui criar o aviso para mostrar a janela")
        return "error"
    app.show_event = event
    threading.Thread(target=_wait_show, name="simba-show", daemon=True).start()
    return "owner"


def signal_show() -> None:
    for _ in range(30):
        handle = kernel32.OpenEventW(0x0002, False, SHOW_EVENT)
        if handle:
            kernel32.SetEvent(handle)
            kernel32.CloseHandle(handle)
            break
        time.sleep(0.1)
    time.sleep(0.6)
    hwnd = user32.FindWindowW(None, "SIMBA")
    if hwnd:
        foreground(hwnd)


def _wait_show() -> None:
    while not app.done.is_set():
        result = kernel32.WaitForSingleObject(app.show_event, 500)
        if result == 0 and not app.quitting:
            reveal("outra instância")


def foreground(hwnd) -> None:
    if not hwnd:
        return
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)
    user32.ShowWindow(hwnd, 5)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)


def load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ROOT / ".env")


def read_port() -> int:
    raw = (os.environ.get("SIMBA_PORT") or str(DEFAULT_PORT)).strip()
    try:
        port = int(raw)
    except ValueError:
        log.warning("SIMBA_PORT inválida; usando %s", DEFAULT_PORT)
        return DEFAULT_PORT
    if not 1 <= port <= 65535:
        log.warning("SIMBA_PORT fora de 1–65535; usando %s", DEFAULT_PORT)
        return DEFAULT_PORT
    return port


def pythonw() -> str:
    exe = Path(sys.executable)
    if exe.name.lower() == "python.exe":
        sibling = exe.with_name("pythonw.exe")
        if sibling.is_file():
            return str(sibling)
    return str(exe)


def server_env() -> dict:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    parent = str(ROOT.parent)
    previous = env.get("PYTHONPATH")
    env["PYTHONPATH"] = parent if not previous else parent + os.pathsep + previous
    return env


def log_utf8(python: str, env: dict) -> None:
    exe = python
    if exe.lower().endswith("pythonw.exe"):
        alternate = str(Path(exe).with_name("python.exe"))
        if Path(alternate).is_file():
            exe = alternate
    try:
        done = subprocess.run(
            [exe, "-c", "import os; print(os.environ.get('PYTHONUTF8', ''))"],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            timeout=30,
        )
        log.info("subprocesso com PYTHONUTF8=%s", (done.stdout or "").strip() or "?")
    except Exception:
        log.exception("não conferi PYTHONUTF8")


def process_alive(pid: int) -> bool:
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    kernel32.CloseHandle(handle)
    return True


def is_python(pid: int) -> bool:
    try:
        done = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            timeout=10,
        )
    except Exception:
        return False
    name = (done.stdout or "").lower()
    return "pythonw.exe" in name or "python.exe" in name


def listener_pid(port: int) -> int | None:
    try:
        done = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            timeout=8,
        )
    except Exception:
        return None
    for line in (done.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[1] == f"127.0.0.1:{port}" and parts[3] == "LISTENING":
            try:
                return int(parts[4])
            except ValueError:
                return None
    return None


def kill_process(proc: subprocess.Popen | None, pid: int | None) -> None:
    if proc is not None and proc.poll() is None:
        pid = proc.pid
        proc.terminate()
        try:
            proc.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            pass
    if not pid or pid == os.getpid() or not process_alive(pid):
        return
    if not is_python(pid):
        log.warning("não encerrei o pid %s porque não é o Python do SIMBA", pid)
        return
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True,
        creationflags=CREATE_NO_WINDOW,
    )


def _safe_line(line: str) -> str:
    line = line.rstrip()
    if len(line) > 400:
        line = line[:400] + "…"
    lowered = line.lower()
    if "token=" in lowered or "bot_token" in lowered or "api_key" in lowered:
        return "[linha omitida]"
    return line


class Server:
    def __init__(self, port: int) -> None:
        self.port = port
        self.python = pythonw()
        self.env = server_env()
        self.proc: subprocess.Popen | None = None
        self.adopted_pid: int | None = None
        self.lock = threading.Lock()
        self.stop_flag = threading.Event()
        self.stopped = False
        self.intentional = False
        self.gave_up = False
        self.crashes: list[float] = []
        self.generation = 0

    def _health(self) -> bool:
        try:
            with urllib.request.urlopen(f"http://{HOST}:{self.port}/health", timeout=1.5) as resp:
                return resp.status == 200 and b"ok" in resp.read(300)
        except Exception:
            return False

    def _spawn_locked(self) -> None:
        if self.stopped:
            return
        if ROOT.name != "simba":
            log.error("a pasta do projeto precisa se chamar simba (está %s)", ROOT.name)
        cmd = [
            self.python,
            "-m",
            "uvicorn",
            "simba.server:app",
            "--host",
            HOST,
            "--port",
            str(self.port),
            "--no-access-log",
        ]
        log.info("subindo servidor em %s:%s com PYTHONUTF8=1", HOST, self.port)
        try:
            self.proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT.parent),
                env=self.env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except Exception:
            log.exception("não subi o servidor")
            self.proc = None
            return
        self.adopted_pid = None
        threading.Thread(target=self._pump, args=(self.proc,), name="simba-server-log", daemon=True).start()
        log.info("processo do servidor: pid %s", self.proc.pid)

    def _pump(self, proc: subprocess.Popen) -> None:
        stream = proc.stdout
        if stream is None:
            return
        for line in stream:
            text = _safe_line(line)
            if text:
                log.info("servidor | %s", text)

    def _budget(self) -> bool:
        now = time.monotonic()
        self.crashes = [item for item in self.crashes if now - item < 600]
        if len(self.crashes) >= 5:
            return False
        self.crashes.append(now)
        return True

    def start(self) -> None:
        log_utf8(self.python, self.env)
        with self.lock:
            if self._health():
                self.adopted_pid = listener_pid(self.port)
                log.info("servidor SIMBA já respondia em %s:%s (pid %s)", HOST, self.port, self.adopted_pid)
                return
            self._spawn_locked()

    def watch(self) -> None:
        threading.Thread(target=self._loop, name="simba-watch", daemon=True).start()

    def _loop(self) -> None:
        while not self.stop_flag.wait(2):
            code = None
            gen = 0
            with self.lock:
                if self.stopped or self.intentional or self.gave_up:
                    continue
                if self.proc is not None:
                    code = self.proc.poll()
                    if code is None:
                        continue
                    self.proc = None
                    gen = self.generation
                elif self.adopted_pid:
                    if process_alive(self.adopted_pid):
                        continue
                    code = "sumiu"
                    self.adopted_pid = None
                    gen = self.generation
                else:
                    continue
            self._recover(code, gen)

    def _recover(self, code, gen: int) -> None:
        if self._health():
            pid = listener_pid(self.port)
            with self.lock:
                if gen != self.generation or self.stopped:
                    return
                self.adopted_pid = pid
            log.info("servidor ainda responde em %s:%s (pid %s)", HOST, self.port, pid)
            return
        with self.lock:
            if gen != self.generation or self.stopped or self.intentional or self.gave_up:
                return
            if not self._budget():
                self.gave_up = True
                log.error(
                    "servidor caiu 5 vezes em 10 minutos; não reinicio sozinho. "
                    "Use Reiniciar servidor na bandeja."
                )
                return
            log.warning(
                "servidor encerrou (%s); reiniciando (%s/5 em 10 minutos)",
                code,
                len(self.crashes),
            )
            self._spawn_locked()

    def wait_ready(self, timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if app.done.is_set():
                return False
            if self._health():
                return True
            time.sleep(0.4)
        return False

    def restart(self) -> None:
        log.info("reinício pedido pela bandeja")
        with self.lock:
            self.generation += 1
            self.intentional = True
            self.gave_up = False
            self.crashes.clear()
            proc = self.proc
            pid = self.adopted_pid
            self.proc = None
            self.adopted_pid = None
        kill_process(proc, pid)
        with self.lock:
            self.intentional = False
            if not self.stopped:
                self._spawn_locked()

    def stop(self) -> None:
        with self.lock:
            if self.stopped:
                return
            self.stopped = True
            self.intentional = True
            self.generation += 1
            proc = self.proc
            pid = self.adopted_pid
            self.proc = None
            self.adopted_pid = None
        self.stop_flag.set()
        kill_process(proc, pid)
        log.info("servidor encerrado")


def _color(value: str | None, opacity: float):
    if not value or value.strip() == "none":
        return None
    raw = value.strip()
    if len(raw) == 7 and raw.startswith("#"):
        red = int(raw[1:3], 16)
        green = int(raw[3:5], 16)
        blue = int(raw[5:7], 16)
        alpha = max(0, min(255, round(255 * opacity)))
        return red, green, blue, alpha
    return None


def _draw_svg(size: int):
    from PIL import Image, ImageDraw

    tree = ET.parse(ROOT / "pwa" / "icon.svg")
    root = tree.getroot()
    box = (root.get("viewBox") or "0 0 512 512").split()
    width = float(box[2]) if len(box) >= 4 else 512.0
    height = float(box[3]) if len(box) >= 4 else 512.0
    big = size * 4
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    scale = big / width

    def px(value: str, fallback: float = 0.0) -> float:
        return float(value or fallback) * scale

    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        opacity = float(el.get("opacity") or 1)
        if tag == "rect":
            fill = _color(el.get("fill"), opacity)
            if not fill:
                continue
            x = px(el.get("x") or "0")
            y = px(el.get("y") or "0")
            w = px(el.get("width") or str(width))
            h = px(el.get("height") or str(height))
            draw.rectangle([x, y, x + w, y + h], fill=fill)
        elif tag == "circle":
            cx = px(el.get("cx") or "0")
            cy = px(el.get("cy") or "0")
            radius = px(el.get("r") or "0")
            fill = _color(el.get("fill"), opacity)
            outline = _color(el.get("stroke"), opacity)
            stroke = max(1, round(float(el.get("stroke-width") or 1) * scale))
            bounds = [cx - radius, cy - radius, cx + radius, cy + radius]
            if fill and outline:
                draw.ellipse(bounds, fill=fill, outline=outline, width=stroke)
            elif fill:
                draw.ellipse(bounds, fill=fill)
            elif outline:
                draw.ellipse(bounds, outline=outline, width=stroke)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def _fallback_icon(size: int):
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (size, size), (5, 8, 13, 255))
    draw = ImageDraw.Draw(image)
    margin = size * 0.18
    draw.ellipse([margin, margin, size - margin, size - margin], outline=(79, 209, 255, 255), width=max(1, size // 16))
    inner = size * 0.38
    draw.ellipse([inner, inner, size - inner, size - inner], fill=(79, 209, 255, 255))
    return image


def build_icon():
    from PIL import Image

    sizes = (16, 32, 48, 256)
    try:
        images = [_draw_svg(size) for size in sizes]
        log.info("ícone gerado a partir de pwa/icon.svg")
    except Exception:
        log.exception("não li pwa/icon.svg; uso um ícone simples")
        images = [_fallback_icon(size) for size in sizes]
    ICO_PATH.parent.mkdir(parents=True, exist_ok=True)
    images[-1].save(
        ICO_PATH,
        format="ICO",
        sizes=[(item.width, item.height) for item in images],
        append_images=images[:-1],
    )
    tray = images[-1].resize((64, 64), Image.Resampling.LANCZOS)
    return tray.convert("RGBA"), ICO_PATH


def webview2_installed() -> bool:
    import winreg

    keys = (
        "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        "{2CD8A007-E189-409D-A2C8-9AF4EF3C72AA}",
        "{0D50BFEC-CD6A-4F9A-964C-C7416E3ACB10}",
        "{65C35B14-6C1D-4122-AC46-7148CC9D6497}",
    )
    hives = (
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{guid}"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{guid}"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{guid}"),
    )
    for guid in keys:
        for hive, pattern in hives:
            try:
                with winreg.OpenKey(hive, pattern.format(guid=guid)) as key:
                    version, _ = winreg.QueryValueEx(key, "pv")
            except OSError:
                continue
            if version and version != "0.0.0.0":
                return True
    return False


def find_edge() -> Path | None:
    roots = [
        os.environ.get("PROGRAMFILES(X86)", ""),
        os.environ.get("PROGRAMFILES", ""),
        os.environ.get("LOCALAPPDATA", ""),
    ]
    for root in roots:
        if not root:
            continue
        candidate = Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        if candidate.is_file():
            return candidate
    return None


def install_microphone(origin: str) -> None:
    import webview.platforms.edgechromium as edgechromium
    from Microsoft.Web.WebView2.Core import CoreWebView2PermissionKind, CoreWebView2PermissionState

    original = edgechromium.EdgeChrome.on_webview_ready
    if getattr(original, "_simba_mic", False):
        return

    def on_webview_ready(self, sender, args):
        try:
            if not args.IsSuccess:
                if not app.webview_retried:
                    app.webview_retried = True
                    log.error(
                        "O WebView2 não abriu a janela: %s. Tentando criar o controlador de novo.",
                        args.InitializationException,
                    )
                    try:
                        self.webview.EnsureCoreWebView2Async(None)
                    except Exception:
                        log.exception("segunda tentativa do WebView2")
                else:
                    log.error(
                        "O WebView2 falhou de novo (%s). A janela fica sem o HUD. "
                        "O Microsoft Edge não está instalado neste PC, só o WebView2 Runtime, "
                        "então não há o modo Edge --app.",
                        args.InitializationException,
                    )
                return original(self, sender, args)
            if args.IsSuccess:
                core = sender.CoreWebView2

                def on_permission(_sender, perm):
                    try:
                        if perm.PermissionKind != CoreWebView2PermissionKind.Microphone:
                            return
                        perm.State = CoreWebView2PermissionState.Allow
                        try:
                            perm.SavesInProfile = True
                        except Exception:
                            pass
                        try:
                            perm.Handled = True
                        except Exception:
                            pass
                    except Exception:
                        log.exception("permissão do microfone")

                app.keep.append(on_permission)
                core.PermissionRequested += on_permission
                try:
                    core.Profile.SetPermissionStateAsync(
                        CoreWebView2PermissionKind.Microphone,
                        origin,
                        CoreWebView2PermissionState.Allow,
                    )
                except Exception:
                    log.exception("perfil do microfone")
                log.info("microfone do WebView2 permitido de forma persistente")
                if app.want_taskbar_hidden:
                    _ui(self.form, lambda: taskbar_button(self.form, False))
        except Exception:
            log.exception("não preparei o microfone")
        return original(self, sender, args)

    on_webview_ready._simba_mic = True
    edgechromium.EdgeChrome.on_webview_ready = on_webview_ready


def _ui(form, fn) -> None:
    if form.InvokeRequired:
        from System import Action

        delegate = Action(fn)
        app.keep.append(delegate)
        form.Invoke(delegate)
    else:
        fn()


def webview_alive(form) -> bool:
    ctl = getattr(form, "webview", None)
    if ctl is None:
        return False
    try:
        return ctl.CoreWebView2 is not None
    except Exception:
        return False


def taskbar_button(form, show: bool) -> None:
    """Tira ou devolve o botão da barra sem recriar o HWND.

    ShowInTaskbar recria a janela e aborta o WebView2 com E_ABORT (0x80004004).
    """
    hwnd = int(form.Handle.ToInt64())
    style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    if show:
        style = (style | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
    else:
        style = (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)
    user32.SetWindowPos(
        hwnd,
        None,
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
    )


def conceal_form(form, remember: bool) -> None:
    import System.Windows.Forms as WinForms
    from System.Drawing import Point

    if remember and form.Location.X > -16000:
        app.saved = (form.Location.X, form.Location.Y, form.WindowState)
    app.want_taskbar_hidden = True
    if form.WindowState != WinForms.FormWindowState.Normal:
        form.WindowState = WinForms.FormWindowState.Normal
    form.Location = Point(-30000, -30000)
    if webview_alive(form):
        taskbar_button(form, False)


def reveal_form(form) -> None:
    import System.Windows.Forms as WinForms
    from System.Drawing import Point

    on_screen = form.Location.X > -16000
    app.want_taskbar_hidden = False
    if webview_alive(form):
        taskbar_button(form, True)
    if on_screen:
        if form.WindowState == WinForms.FormWindowState.Minimized:
            form.WindowState = WinForms.FormWindowState.Normal
        if not form.Visible:
            form.Show()
        form.Activate()
        try:
            foreground(int(form.Handle.ToInt64()))
        except Exception:
            pass
        return
    saved = app.saved
    form.WindowState = WinForms.FormWindowState.Normal
    if saved:
        x, y, state = saved
        form.Location = Point(int(x), int(y))
        if state == WinForms.FormWindowState.Maximized:
            form.WindowState = WinForms.FormWindowState.Maximized
    else:
        area = WinForms.Screen.PrimaryScreen.WorkingArea
        form.Location = Point(
            int(area.X + max(0, (area.Width - form.Width) // 2)),
            int(area.Y + max(0, (area.Height - form.Height) // 2)),
        )
    if not form.Visible:
        form.Show()
    kick_webview(form)
    form.Activate()
    try:
        hwnd = int(form.Handle.ToInt64())
    except Exception:
        hwnd = 0
    if hwnd:
        foreground(hwnd)


def reveal(origin: str) -> None:
    if app.quitting:
        return
    log.info("mostrar janela (%s)", origin)
    if app.mode == "edge":
        if app.edge is None or app.edge.poll() is not None:
            app.edge = launch_edge(False)
        hwnd = user32.FindWindowW(None, "SIMBA")
        if hwnd:
            foreground(hwnd)
        return
    window = app.window
    if window is None:
        return
    form = getattr(window, "native", None)
    if form is None:
        try:
            window.show()
            window.restore()
        except Exception:
            log.exception("mostrar janela")
        return
    try:
        _ui(form, lambda: reveal_form(form))
    except Exception:
        log.exception("mostrar janela")


def kick_webview(form) -> None:
    """O WebView2 nasce com tamanho zero se a janela foi criada minimizada."""
    import System.Windows.Forms as WinForms

    ctl = getattr(form, "webview", None)
    if ctl is None:
        return
    if ctl.Width >= 50 and ctl.Height >= 50:
        return
    ctl.Dock = WinForms.DockStyle.Fill
    ctl.Bounds = form.ClientRectangle
    form.PerformLayout()


def on_restored() -> None:
    """Sair da minimização não reabre o log; só devolve o tamanho do WebView2."""
    if app.oculto:
        return
    form = getattr(app.window, "native", None) if app.window is not None else None
    if form is None:
        return
    try:
        _ui(form, lambda: kick_webview(form))
    except Exception:
        log.exception("ajustar WebView2")


def on_shown() -> None:
    form = getattr(app.window, "native", None) if app.window is not None else None
    if app.oculto and form is not None:
        try:
            _ui(form, lambda: conceal_form(form, False))
        except Exception:
            log.exception("início oculto")
        log.info("início oculto: servidor e bandeja no ar, janela escondida")
        return
    if form is not None:
        def show_normal():
            import System.Windows.Forms as WinForms
            if form.WindowState == WinForms.FormWindowState.Minimized:
                form.WindowState = WinForms.FormWindowState.Normal
            form.Show()
            kick_webview(form)
            form.Activate()
        try:
            _ui(form, show_normal)
        except Exception:
            log.exception("mostrar janela inicial")
    log.info("janela aberta")


def on_closing():
    if app.quitting:
        return None
    window = app.window
    form = getattr(window, "native", None) if window is not None else None
    if form is None:
        return False
    from System import Action

    def later():
        try:
            conceal_form(form, True)
            log.info("janela escondida; servidor continua")
        except Exception:
            log.exception("esconder janela")

    delegate = Action(later)
    app.keep.append(delegate)
    try:
        form.BeginInvoke(delegate)
    except Exception:
        log.exception("esconder janela")
    return False


def page_has_content() -> bool:
    window = app.window
    if window is None:
        return False
    try:
        count = window.evaluate_js("(document.body && (document.body.innerText || '').trim().length) || 0")
    except Exception:
        log.exception("não conferi se a página abriu")
        return True
    try:
        return int(count or 0) > 0
    except (TypeError, ValueError):
        return bool(count)


def reload_if_empty() -> None:
    time.sleep(0.8)
    if app.quitting or app.reloaded or app.window is None:
        return
    if page_has_content():
        return
    app.reloaded = True
    log.warning("a página abriu vazia; recarregando uma vez")
    try:
        app.window.load_url(app.url)
    except Exception:
        log.exception("recarregar página")


def on_loaded() -> None:
    log.info("HUD carregado")
    form = getattr(app.window, "native", None) if app.window is not None else None
    if form is not None:
        try:
            _ui(form, lambda: kick_webview(form))
        except Exception:
            log.exception("ajustar WebView2")
    threading.Thread(target=reload_if_empty, name="simba-reload", daemon=True).start()
    if not app.muted or app.window is None:
        return
    try:
        app.window.evaluate_js("window.simbaSetListen&&window.simbaSetListen(false)")
    except Exception:
        log.exception("reaplicar microfone silenciado")


def launch_edge(oculto: bool) -> subprocess.Popen:
    exe = find_edge()
    if exe is None:
        raise RuntimeError("Edge não encontrado")
    EDGE_PROFILE.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(exe),
        f"--app={app.url}",
        f"--user-data-dir={EDGE_PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "--use-fake-ui-for-media-stream",
    ]
    if oculto:
        cmd.extend(["--window-position=-30000,-30000", "--window-size=1280,800"])
    log.info("modo de janela: Edge --app (perfil separado)")
    return subprocess.Popen(cmd, cwd=str(ROOT), creationflags=CREATE_NO_WINDOW)


def run_webview(ico: Path) -> None:
    import webview

    app.mode = "webview"
    log.info("modo de janela: pywebview (WebView2)")
    WEBVIEW_DIR.mkdir(parents=True, exist_ok=True)
    install_microphone(f"http://{HOST}:{app.port}")
    window = webview.create_window(
        "SIMBA",
        app.url,
        width=1280,
        height=800,
        x=-30000 if app.oculto else None,
        y=-30000 if app.oculto else None,
        min_size=(960, 640),
        background_color=WINDOW_BG,
        text_select=True,
        confirm_close=False,
    )
    app.window = window
    window.events.shown += on_shown
    window.events.restored += on_restored
    window.events.closing += on_closing
    window.events.loaded += on_loaded
    webview.start(
        gui="edgechromium",
        private_mode=False,
        storage_path=str(WEBVIEW_DIR),
        icon=str(ico) if ico.is_file() else None,
    )


def run_edge() -> None:
    app.mode = "edge"
    app.edge = launch_edge(app.oculto)
    if app.oculto:
        log.info("início oculto: servidor e bandeja no ar")
    announced = False
    while not app.done.wait(0.4):
        proc = app.edge
        if proc is not None and proc.poll() is not None:
            if not announced:
                log.info("janela Edge fechada; servidor continua")
                announced = True
            app.edge = None
        elif proc is not None:
            announced = False


def start_tray(image) -> None:
    import pystray

    def on_open(icon, item):
        reveal("bandeja")

    def on_mic(icon, item):
        app.muted = not app.muted
        flag = "false" if app.muted else "true"
        label = "silenciado" if app.muted else "ativo"
        window = app.window
        if window is None:
            log.info("microfone %s", label)
            return
        try:
            window.evaluate_js(f"window.simbaSetListen&&window.simbaSetListen({flag})")
            log.info("microfone %s", label)
        except Exception:
            log.exception("microfone")

    def on_restart(icon, item):
        if app.server is None:
            return
        threading.Thread(target=app.server.restart, name="simba-restart", daemon=True).start()

    def mic_text(item):
        return "Ativar microfone" if app.muted else "Silenciar microfone"

    menu = pystray.Menu(
        pystray.MenuItem("Abrir SIMBA", on_open, default=True),
        pystray.MenuItem(mic_text, on_mic),
        pystray.MenuItem("Reiniciar servidor", on_restart),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Sair", quit_app),
    )
    icon = pystray.Icon("simba", image, "SIMBA", menu)
    app.icon = icon
    icon.run_detached()
    log.info("bandeja no ar")


def quit_app(icon=None, item=None) -> None:
    if app.quitting:
        return
    log.info("encerrando pelo menu Sair")
    app.quitting = True
    app.done.set()
    if app.server is not None:
        app.server.stop()
    if app.edge is not None and app.edge.poll() is None:
        kill_process(app.edge, app.edge.pid)
        app.edge = None
    window = app.window
    if window is not None:
        try:
            window.destroy()
        except Exception:
            log.exception("fechar janela")
    if app.icon is not None:
        try:
            app.icon.stop()
        except Exception:
            pass


def shutdown() -> None:
    if app.shut:
        return
    app.shut = True
    app.quitting = True
    app.done.set()
    if app.server is not None:
        app.server.stop()
    if app.edge is not None and app.edge.poll() is None:
        kill_process(app.edge, app.edge.pid)
    if app.icon is not None:
        try:
            app.icon.stop()
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    if os.name != "nt":
        print("O SIMBA desktop roda no Windows.")
        return 1
    parser = argparse.ArgumentParser(description="SIMBA no PC")
    parser.add_argument("--oculto", action="store_true", help="sobe com a janela escondida")
    args = parser.parse_args(argv)
    setup_log()
    owned = claim()
    if owned == "busy":
        log.info("já estava em execução; pedi para trazer a janela")
        signal_show()
        return 0
    if owned == "error":
        return 1
    log.info("SIMBA desktop iniciando (pid %s)", os.getpid())
    try:
        load_env()
        app.oculto = args.oculto
        app.port = read_port()
        app.url = f"http://{HOST}:{app.port}/"
        app.server = Server(app.port)
        app.server.start()
        app.server.watch()
        image, ico = build_icon()
        start_tray(image)
        ready = app.server.wait_ready(45)
        if ready:
            log.info("servidor respondendo em http://%s:%s/", HOST, app.port)
        else:
            log.warning("servidor ainda não respondeu; a janela abre mesmo assim")
        if app.done.is_set():
            return 0
        if webview2_installed():
            try:
                run_webview(ico)
                return 0
            except Exception:
                log.exception("pywebview falhou ao abrir a janela")
        else:
            log.error("WebView2 Runtime não encontrado")
        if find_edge() is None:
            log.error(
                "A janela não abriu. O WebView2 falhou e o Microsoft Edge não está instalado neste computador. "
                "Só existe o WebView2 Runtime, então o modo Edge --app não funciona aqui. O servidor continua na bandeja."
            )
            app.done.wait()
            return 0
        try:
            run_edge()
        except Exception:
            log.exception("não abri o Edge")
        return 0
    finally:
        shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
