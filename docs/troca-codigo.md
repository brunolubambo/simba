# Trocar o código de acesso sem queda

O HUD e o WebSocket entram com `SIMBA_TOKEN`. O celular entra com `CELULAR_TOKEN` ou, se esse estiver vazio, com o mesmo `SIMBA_TOKEN`.

`SIMBA_TOKEN_ANTERIOR` é opcional. Ausente ou vazio, nada muda: só o código atual vale. Preenchido, o servidor aceita o código atual **ou** o antigo, com comparação segura, e continua recusando valor vazio. Assim dá para atualizar os clientes sem um intervalo em que o código novo ainda não chegou e o antigo já foi recusado.

`PC_TOKEN` e o webhook do Telegram ficam fora dessa janela.

O log de acesso continua ligado. O valor depois de `token=` sai como `token=***`.

## Passo a passo

Nas variáveis do servidor (no Railway, Variables), sem colar o código em chat, log ou documento:

1. Grave o código que está em uso agora em `SIMBA_TOKEN_ANTERIOR` e o código novo em `SIMBA_TOKEN`. Faça o deploy. O processo sobe de novo já aceitando os dois.
2. Atualize o código no HUD, no desktop e no celular.
3. Apague `SIMBA_TOKEN_ANTERIOR` e faça o deploy outra vez. A partir daí só o código novo entra.
