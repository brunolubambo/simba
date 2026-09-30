#!/bin/bash

# SIMBA - Push com Token (execute no seu PC)

echo "🚀 SIMBA - Push para GitHub..."

cd "$(dirname "$0")" || exit

git config user.email "brunolubambo@gmail.com"
git config user.name "Bruno Lubambo"

git init
git add .
git commit -m "SIMBA: assistente pessoal com 18 agentes, voz, tela e memória" 2>/dev/null

git remote remove origin 2>/dev/null
git remote add origin https://brunolubambo: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@github.com/brunolubambo/simba.git

git branch -M main
git push -u origin main

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Push concluído!"
    echo "https://github.com/brunolubambo/simba"
else
    echo "❌ Erro - tente manualmente:"
    echo "git push -u origin main"
fi

# Limpar token da história
history -c
