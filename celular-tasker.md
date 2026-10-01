# SIMBA no Galaxy A33 — sem Tasker

O Tasker é pago. **Não precisa dele.** O app Android do SIMBA (de graça, neste repositório) busca o comando no servidor e confirma. Firebase no telefone também não é obrigatório.

Aparelho: Samsung Galaxy A33 5G, Android 16, One UI 8.

Três ações: alarme, abrir um app, tirar foto. Compromisso de agenda continua no Google (`agenda_criar`).

## 1. No Railway

A ferramenta já liga com `CELULAR_APP=true` (padrão). Não precisa de `FCM_SERVICE_ACCOUNT` nem de token do Firebase.

O app usa o **mesmo código de acesso** do site (`SIMBA_TOKEN`). Se quiser um código só para o celular, crie `CELULAR_TOKEN` no Railway e use esse no app.

## 2. Instalar o app no A33

1. Gere o APK debug (no PC, pasta `android/`):

```
gradlew.bat assembleDebug
```

O arquivo sai em `android/app/build/outputs/apk/debug/app-debug.apk`.

2. Passe o APK para o telefone (USB, Drive, etc.) e instale. O Android pode avisar “fontes desconhecidas”: permita só para este arquivo.
3. Abra **SIMBA**.
4. Endereço do servidor: `https://authentic-friendship-production-0dac.up.railway.app` (sem barra no fim).
5. Código de acesso: o mesmo do site (não envie no chat).
6. **Ativar escuta.** Aceite microfone, câmara, notificações e “sem restrição de bateria”.
7. Deixe o aviso permanente “SIMBA ouvindo”. Sem esse serviço o comando não é puxado.

## 3. Bateria no One UI 8 (obrigatório neste A33)

O Samsung mata apps em segundo plano. Sem isto o SIMBA diz que o celular não confirmou.

1. Definições → **Bateria e cuidados com o dispositivo** → **Bateria** → **Limites de utilização em segundo plano**
2. Ponha o **SIMBA** em **Aplicações nunca em hibernação**
3. Definições → Aplicações → SIMBA → **Bateria** → **Sem restrições**
4. Ligue **Permitir atividade em segundo plano**
5. Recentes → ícone do SIMBA → **Bloquear este aplicativo**
6. Reinicie o telefone e abra o SIMBA uma vez

## 4. Teste

Com o app ouvindo e o A33 ligado:

- “Simba, cria um alarme às 07:30 com o nome academia”
- “Abre o Gmail no celular”
- “Tira uma foto com a câmera traseira” (pede aprovação)

Se não confirmar: o app não está em primeiro/segundo plano, ou a bateria hibernou. Volte à secção 3.

## 5. O que isto não faz

Não usa Tasker. Não apaga evento, não manda SMS, não liga. Agenda continua no Google.
