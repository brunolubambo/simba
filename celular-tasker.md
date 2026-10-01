# SIMBA no Galaxy A33 pelo Tasker

O servidor manda um comando pelo Firebase (FCM). O Tasker executa e **confirma**. Sem essa confirmação o SIMBA diz que não fez.

Aparelho: Samsung Galaxy A33 5G, Android 16, One UI 8.

Três ações: alarme, abrir um app, tirar foto. Compromisso de agenda continua no Google (`agenda_criar`), não no Tasker.

## 1. Firebase no Railway

1. Abra [Firebase Console](https://console.firebase.google.com), crie um projeto (ou use um que já exista).
2. Definições do projeto → Contas de serviço → **Gerar nova chave privada**. Baixa um JSON.
3. No Railway → o serviço do SIMBA → Variables, crie:
   - `FCM_SERVICE_ACCOUNT` = o JSON inteiro, numa linha
   - `CELULAR_FCM_TOKEN` = o token do passo 2 (ainda vai copiar)
   - `CELULAR_TOKEN` = um código só para o Tasker (se ficar vazio, o SIMBA usa o mesmo `SIMBA_TOKEN` do site)
4. `FCM_PROJECT_ID` é opcional: se o JSON tiver `project_id`, o SIMBA lê sozinho.
5. Não cole esses valores no chat nem no Git.

Publique a branch `celular-tasker` no Railway **depois** de revisar. O deploy automático está desligado.

## 2. Token FCM no Tasker

1. Instale o **Tasker** (versão 6 ou mais nova) e abra uma vez, com internet.
2. Menu (três pontos) → **Preferências** → **MISC** (Diversos).
3. Copie o **FCM Token** / Registration ID. Cole em `CELULAR_FCM_TOKEN` no Railway.
4. Se o campo não aparecer: atualize o Tasker e confirme que o telefone tem a Play Store / Play Services.

O SIMBA envia um campo `task` igual a `SimbaComando`. O Tasker 6+ **dispara essa tarefa sozinho**; não é obrigatório criar um perfil. Se a sua versão não disparar, crie um perfil Evento → Sistema → FCM (ou o nome equivalente) → tarefa `SimbaComando`.

## 3. Variáveis globais no Tasker

Variável → Variável Global:

- `%SimbaUrl` = `https://SEU-SERVICO.up.railway.app` (sem barra no fim)
- `%SimbaCelToken` = o mesmo valor de `CELULAR_TOKEN` (ou o `SIMBA_TOKEN`, se você não criou o outro)

## 4. Tarefa `SimbaComando`

Crie a tarefa com **exatamente** esse nome. Marque **Manter o dispositivo acordado** / Keep Device Awake, se existir.

Em cada ação de rede, ligue **Continuar a tarefa após erro** para conseguir avisar o SIMBA que falhou.

Os campos que chegam no push: `%acao`, `%hora`, `%etiqueta`, `%app`, `%camera`, `%cmd`.

### 4.1 Avisar o SIMBA (reutilize)

Crie uma tarefa pequena `SimbaResultado` com uma ação:

- Rede → **Pedido HTTP**
  - Método: POST
  - URL: `%SimbaUrl/celular/resultado?token=%SimbaCelToken`
  - Tipo de corpo: JSON
  - Corpo:

```json
{"id":"%cmd","ok":"%ok","detalhe":"%detalhe"}
```

  - Tempo limite: 15 segundos

Antes de chamá-la, defina `%ok` e `%detalhe`.

### 4.2 Alarme (`%acao` ~ `alarme`)

1. Se `%acao` ~ `alarme`
2. Variável → Divisão de Variável: `%hora` no separador `:`
   - `%hora1` = hora, `%hora2` = minuto
3. Alerta (ou Relógio) → **Definir alarme** / Set Alarm
   - Horas: `%hora1`
   - Minutos: `%hora2`
   - Etiqueta: `%etiqueta`
   - Se existir “saltar interface” / Skip UI, ligue
4. `%ok` = `true` e chame `SimbaResultado`
5. Se a ação de alarme falhar: `%ok` = `false`, `%detalhe` = `nao criou o alarme`

Permissão: Definições → Aplicações → Tasker → Permissões especiais → **Alarmes e lembretes**.

### 4.3 Abrir app (`%acao` ~ `abrir_app`)

1. Senão se `%acao` ~ `abrir_app`
2. App → **Abrir aplicação** / Launch App
   - Campo do app: pressione longo → variável `%app`
3. `%ok` = `true` e chame `SimbaResultado`
4. Se falhar: `%ok` = `false`, `%detalhe` = `app nao encontrado`

Use o nome como na gaveta: `WhatsApp`, `Gmail`, `Relógio`.

### 4.4 Foto (`%acao` ~ `foto`)

1. Senão se `%acao` ~ `foto`
2. Se `%camera` ~ `frontal` → use a câmara da frente; senão a traseira
3. Média → **Tirar foto** / Take Photo
   - Ficheiro: `Tasker/simba_%cmd.jpg` (memória interna)
   - Inserir na galeria: desligado, se puder
4. Rede → Pedido HTTP
   - Método: POST
   - URL: `%SimbaUrl/celular/foto?token=%SimbaCelToken&id=%cmd`
   - Ficheiro: o caminho da foto (o campo File do Tasker)
   - **Não** ponha Content-Type à mão; o Tasker manda multipart
   - Tempo limite: 30 segundos
5. Se o HTTP da foto falhar: `%ok` = `false`, `%detalhe` = `nao enviou a foto`, chame `SimbaResultado`

Permissão: Câmara. Na primeira foto o Android pede; aceite.

**Não** use o `POST /upload` do site: aquele dispara uma conversa nova. Foto do Tasker vai só em `/celular/foto`.

### 4.5 Ação desconhecida

Senão: `%ok` = `false`, `%detalhe` = `acao desconhecida`, `SimbaResultado`.

## 5. Bateria no One UI 8 (obrigatório neste A33)

O Samsung mata o Tasker em segundo plano. Sem estes passos o comando “foi enviado” e o SIMBA diz que o celular não confirmou.

1. Definições → **Bateria e cuidados com o dispositivo** → **Bateria**
2. **Limites de utilização em segundo plano**
   - Tire o Tasker de hibernação / suspensão profunda
   - Ponha o Tasker em **Aplicações nunca em hibernação**
3. Definições → Aplicações → Tasker → **Bateria** → **Sem restrições** (não otimizar)
4. Na mesma ficha do Tasker: ligue **Permitir atividade em segundo plano**
5. Desligue, para o Tasker, **Colocar aplicações não utilizadas em hibernação**
6. Abra os Recentes, toque no ícone do Tasker, **Bloquear este aplicativo** (cadeado)
7. Tasker → menu → Mais → Definições Android → isentar da otimização de bateria, se ainda pedir
8. Reinicie o telefone uma vez e abra o Tasker, para o One UI gravar a isenção

Permissões extra que costumam faltar neste modelo:

- Aparecer sobre outros aplicativos (alarme / abrir app com o ecrã bloqueado)
- Alterar definições do sistema
- Notificações do Tasker ligadas
- Dados móveis e Wi‑Fi irrestritos para o Tasker, se o One UI mostrar essa opção

## 6. Teste

Com o telefone ligado, desbloqueado na primeira vez:

- “Simba, cria um alarme às 07:30 com o nome academia”
- “Abre o Gmail no celular”
- “Tira uma foto com a câmera traseira” (pede aprovação na tela / Telegram)

Se o SIMBA responder que o celular não confirmou: o push saiu e o Tasker não devolveu. Volte à secção 5. Se o Firebase recusar, o token FCM do Tasker mudou — copie de novo.

## 7. O que o SIMBA não faz neste corte

Não apaga evento pelo Tasker, não manda SMS, não liga. Isso exigiria aprovação extra e não está na lista fechada. Agenda continua no Google.
