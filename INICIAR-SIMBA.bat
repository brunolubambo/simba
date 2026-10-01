@echo off
setlocal EnableDelayedExpansion
title SIMBA - local
cd /d "%~dp0"
echo.
echo  ================================
echo   SIMBA - preparando e iniciando
echo  ================================
echo.

rem --- a pasta precisa se chamar simba (e o nome do pacote Python) ---
for %%I in ("%~dp0.") do set "PKG=%%~nxI"
if /i not "%PKG%"=="simba" goto :nomepasta

rem --- 1. Python 3.10 ou mais novo ---
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=python"
if not defined PY goto :sempython

rem --- 2. Ambiente do Python (.venv), so na primeira vez ---
if not exist ".venv\Scripts\python.exe" (
  echo Criando o ambiente do Python, so na primeira vez...
  %PY% -m venv .venv || goto :erro
)
echo Instalando e conferindo as dependencias. Na primeira vez demora alguns minutos...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :erro

rem --- 3. Arquivo .env com o codigo de acesso do app ---
if exist ".env" goto :iniciar
echo.
echo Primeira vez neste computador: vou criar o arquivo .env.
echo Use o mesmo codigo de acesso que voce digita no app do SIMBA.
echo Se nao lembrar: Railway, aba Variables, variavel SIMBA_TOKEN.
set /p "CODIGO=Codigo de acesso do SIMBA: "
echo.
echo Chave da Anthropic, para ele conseguir responder. Opcional: Enter para pular.
echo Fica no Railway, aba Variables, variavel ANTHROPIC_API_KEY.
set /p "CHAVE=ANTHROPIC_API_KEY: "
> ".env" echo(SIMBA_TOKEN=!CODIGO!
>> ".env" echo(OBSERVER_ENABLED=false
>> ".env" echo(BROWSER_ENABLED=false
if defined CHAVE >> ".env" echo(ANTHROPIC_API_KEY=!CHAVE!
echo Arquivo .env criado.

:iniciar
echo.
echo SIMBA ligado em http://127.0.0.1:8000
echo Para desligar, feche esta janela.
echo.
start "" /min cmd /c "ping -n 6 127.0.0.1 >nul & explorer http://127.0.0.1:8000"
cd ..
"%~dp0.venv\Scripts\python.exe" -m uvicorn simba.server:app --host 127.0.0.1 --port 8000
goto :fim

:nomepasta
echo A pasta deste arquivo precisa se chamar simba (agora se chama %PKG%).
echo Renomeie a pasta para simba e rode de novo.
goto :fim

:sempython
echo Nao encontrei o Python 3.10 ou mais novo neste computador.
echo Vou abrir o site oficial: instale marcando a opcao "Add python.exe to PATH"
echo e depois rode este arquivo de novo.
start "" https://www.python.org/downloads/
goto :fim

:erro
echo.
echo Algo deu errado acima. Tire um print desta janela e mande para o Claude.
goto :fim

:fim
echo.
pause
