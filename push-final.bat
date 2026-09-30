@echo off
REM SIMBA - Push Final (execute no seu PC)

echo.
echo 🚀 SIMBA - Push para GitHub
echo.

git config user.email "brunolubambo@gmail.com"
git config user.name "Bruno Lubambo"

git init
git add .
git commit -m "SIMBA: assistente pessoal com 18 agentes, voz, tela e memória" 2>nul

git remote remove origin 2>nul
git remote add origin https://brunolubambo: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@github.com/brunolubambo/simba.git

git branch -M main
git push -u origin main

if errorlevel 1 (
  echo.
  echo ❌ Erro no push
  echo Tente: git push -u origin main
) else (
  echo.
  echo ✅ Push concluído!
  echo https://github.com/brunolubambo/simba
)

pause
