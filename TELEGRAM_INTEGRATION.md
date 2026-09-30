# 🤖 Integração Telegram no SIMBA

A integração com Telegram agora está completa! O SIMBA pode receber mensagens via Telegram, processar pedidos e enviar notificações.

## ✅ O que foi implementado

### 1. **Módulo Telegram** (`telegram.py`)
- Bot do Telegram com suporte a polling (não precisa de webhook)
- Handlers para comandos: `/start`, `/help`
- Processamento de mensagens de texto
- Registro automático de usuários
- Envio de notificações para um ou todos os usuários

### 2. **Atualizações no `server.py`**
- Inicialização do Telegram no lifespan da aplicação
- Integração com o pipeline de processamento existente
- Endpoints HTTP para gerenciamento do Telegram

### 3. **Dependência adicionada** (`requirements.txt`)
- `python-telegram-bot[all]>=20.0` para bot assíncrono

## 🚀 Como usar

### Pré-requisitos
- ✅ Token do Telegram Bot criado (você já fez isso)
- ✅ Variável `TELEGRAM_BOT_TOKEN` configurada no Railway

### Fluxo de funcionamento

```
Usuário → Telegram → Bot recebe mensagem
                        ↓
                  Handler processa
                        ↓
                  Callback: run_and_broadcast()
                        ↓
                  SIMBA processa pedido
                        ↓
                  Resposta enviada de volta ao Telegram
```

### Comandos disponíveis

- `/start` - Iniciar conversa (registra o usuário)
- `/help` - Ver comandos disponíveis
- Qualquer mensagem de texto é processada pelo SIMBA

## 📡 Endpoints HTTP

### 1. Enviar notificação para todos os usuários
```bash
curl -X POST https://seu-app.railway.app/telegram/notify \
  -H "Content-Type: application/json" \
  -d '{"text": "Notificação importante!"}' \
  -G --data-urlencode "token=SEU_TOKEN"
```

### 2. Listar usuários registrados
```bash
curl https://seu-app.railway.app/telegram/users?token=SEU_TOKEN
```

### 3. Enviar mensagem para um chat específico
```bash
curl -X POST https://seu-app.railway.app/telegram/send \
  -H "Content-Type: application/json" \
  -d '{"chat_id": 123456789, "text": "Mensagem privada"}' \
  -G --data-urlencode "token=SEU_TOKEN"
```

### 4. Ver status no painel
```bash
curl https://seu-app.railway.app/painel?token=SEU_TOKEN
```

Agora inclui informações sobre Telegram:
```json
{
  "telegram": {
    "users": 2,
    "token_set": true
  },
  ...
}
```

## 📝 Como funciona o ciclo completo

### Recebendo mensagens

1. Usuário envia mensagem no Telegram
2. Bot recebe via polling (verifica a cada segundo)
3. Handler `_handle_message` é acionado
4. Callback `on_message` é chamado
5. `run_and_broadcast()` processa com o SIMBA
6. Resposta é enviada de volta ao Telegram

### Enviando notificações

1. SIMBA gera um evento notificável (aprovação, conclusão, alerta)
2. Chamadas automáticas a `send_telegram_notification()`
3. Mensagem é entregue a todos os usuários registrados

### Gerenciando usuários

- Usuários são automaticamente registrados no primeiro `/start`
- Dados armazenados em `data/telegram_users.json`
- Formato: `{chat_id: {name, username, first_seen}}`

## 🔧 Troubleshooting

### "TELEGRAM_BOT_TOKEN não configurado"
- Verifique se a variável está definida no Railway
- Reinicie a aplicação após adicionar

### Bot não responde
- Verifique se o bot está no Telegram (procure por seu username)
- Envie `/start` para registrar
- Verifique os logs no Railway

### Mensagens não chegam
- Confirme que o token é válido (não copie com espaços)
- Verifique se o chat_id está correto
- Leia os logs de erro do Railway

## 📊 Estrutura de dados

### `telegram_users.json`
```json
{
  "123456789": {
    "name": "Bruno",
    "username": "bruno_user",
    "first_seen": "2026-09-30 14:30:45"
  },
  "987654321": {
    "name": "Maria",
    "username": "maria_user",
    "first_seen": "2026-09-30 15:00:00"
  }
}
```

## ✨ Próximos passos opcionais

1. **Webhook em vez de polling**: Para desempenho em produção, configure webhook ao invés de polling
2. **Grupos do Telegram**: Estender para permitir chats em grupo
3. **Inline buttons**: Adicionar botões interativos nas respostas
4. **Media sharing**: Suporte para envio de imagens/arquivos

## 🧪 Para testar

1. Faça push das mudanças
2. Aguarde redeploy no Railway
3. Abra o Telegram e procure seu bot
4. Envie `/start`
5. Envie uma mensagem teste
6. Verifique a resposta

---

**Status**: ✅ Integração completa e pronta para usar!
Você pode começar a enviar mensagens ao seu bot no Telegram agora.
