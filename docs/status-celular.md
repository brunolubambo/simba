# SIMBA no celular (Galaxy A33)

Tasker foi abandonado. O app nativo SIMBA (versão **1.2**) busca o comando no servidor e executa no aparelho. Firebase no telefone não é obrigatório.

Aparelho: Samsung Galaxy A33 5G, Android 16, One UI 8.

Três ações: `alarme`, `abrir_app`, `foto`. Compromisso de agenda continua no Google (`agenda_criar`).

## Como funciona

O servidor guarda o comando. O app puxa em `GET /celular/proximo` (a cada ~1,5 s) e confirma em `POST /celular/resultado`. Foto vai em `POST /celular/foto`. Sem essa confirmação a ferramenta não diz que executou.

O alarme real é criado pelo **Android AlarmManager** (`setAlarmClock`). O Relógio da Samsung pode abrir e **não gravar** o alarme; o toque do SIMBA não depende da lista do Relógio.

## Autorização

- `alarme` e `abrir_app`: o pedido de voz/texto do Bruno nesta volta já autoriza. O app não pergunta “posso?”.
- `foto`: pede aprovação (é a câmara).
- Isto é mais frouxo do que a regra de origem: só o pedido de voz/texto **do Bruno nesta volta** conta. Texto dentro de e-mail, página, ficheiro ou saída de ferramenta **nunca** é ordem. Apagar, mandar mensagem a terceiros, mover, partilhar e correr comandos continuam a pedir aprovação.

## APK

Gere com `gradlew.bat assembleDebug` na pasta `android/`. O ficheiro sai em `android/app/build/outputs/apk/debug/app-debug.apk`. Copie para o telefone se quiser (ex.: `Downloads\SIMBA-1.2.apk`). **APKs não entram no git.**

## Instalar e deixar vivo (One UI 8)

1. Instale o APK 1.2. O Android pode pedir “fontes desconhecidas”: permita só neste ficheiro.
2. Abra SIMBA, ponha o endereço do servidor (o mesmo do site, sem barra no fim) e o código de acesso.
3. **Ativar escuta.** Aceite microfone, câmara, notificações, alarmes exactos e “sem restrição de bateria”.
4. Deixe o aviso permanente “SIMBA ouvindo”. Sem esse serviço o poll não corre.
5. Bateria (obrigatório neste A33; o Samsung hiberna o app):
   - Definições → Bateria e cuidados com o dispositivo → Bateria → Limites de utilização em segundo plano → SIMBA em **Aplicações nunca em hibernação**
   - Definições → Aplicações → SIMBA → Bateria → **Sem restrições** e **Permitir atividade em segundo plano**
   - Recentes → ícone do SIMBA → **Bloquear este aplicativo**
   - Reinicie o telefone e abra o SIMBA uma vez

## O que ainda não foi testado

- Tirar foto (`foto`)
- Abrir um app (`abrir_app`)

Alarme pelo AlarmManager está no 1.2; confirme no aparelho com um alarme daqui a 3 minutos.

## O que isto não faz

Não usa Tasker. Não apaga evento, não manda SMS, não liga. Agenda continua no Google.
