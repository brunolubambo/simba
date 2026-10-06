# SIMBA no PC

O app de desktop sobe o servidor só em `127.0.0.1` e abre o mesmo HUD numa janela nativa. Fechar a janela esconde: rotinas, Telegram e voz continuam. Sair, na bandeja, encerra tudo.

A voz desta branch é a de sempre: reconhecimento do WebView2 e fala do servidor (edge-tts). `voice.py` tem faster-whisper opcional, sem ligação com o HUD. Piper não está nesta branch.

## Instalar

No `.venv` do projeto, que já tem o `requirements.txt` do servidor:

```
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
```

Isso instala `pywebview`, `pystray` e `pillow`. Esses pacotes ficam em `requirements-desktop.txt`. O Railway usa só `requirements.txt`.

O token, as chaves e o bot continuam no `.env`. Nenhum script grava segredo.

## Testar

```
.\.venv\Scripts\pythonw.exe simba_desktop.py
```

A porta é `SIMBA_PORT` no `.env`. Sem essa variável, usa `8787`. O servidor escuta apenas em `127.0.0.1`.

A bandeja tem Abrir SIMBA, Silenciar/Ativar microfone, Reiniciar servidor e Sair. Fechar a janela deixa o processo e o servidor vivos. Um segundo arranque só traz a janela de volta.

Para subir já escondido, como no logon:

```
.\.venv\Scripts\pythonw.exe simba_desktop.py --oculto
```

O microfone fica permitido no perfil do WebView2 (`data/webview2`), sem pedir de novo. A janela usa o fundo escuro do HUD. Se o WebView2 não abrir, o motivo fica em `data/logs/desktop.log`. Sem o Microsoft Edge instalado, o app não tenta `Edge --app`.

## Início automático

Sem administrador. Na pasta do projeto:

```
powershell -ExecutionPolicy Bypass -File .\instalar-autostart.ps1
```

Cria ou atualiza a tarefa **SIMBA**: ao fazer logon, o `pythonw` do `.venv` roda `simba_desktop.py --oculto`, sem console. Se o processo falhar, o Agendador tenta de novo.

Atalho na pasta Inicializar, em vez da tarefa:

```
powershell -ExecutionPolicy Bypass -File .\instalar-autostart.ps1 -Atalho
```

Para tirar a tarefa e o atalho:

```
powershell -ExecutionPolicy Bypass -File .\desinstalar-autostart.ps1
```

Os dois scripts podem rodar de novo e dizem o que criaram ou o que já não existia.

## Logs

`data/logs/desktop.log`. Gira ao passar de 1 MB e guarda 3 arquivos antigos. O processo do servidor nasce com `PYTHONUTF8=1`.
