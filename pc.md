# SIMBA no PC pessoal

O SIMBA no Railway **não** lê o disco deste Windows. Um agente local, a correr **como o seu utilizador** (sem administrador), puxa o comando por HTTPS e confirma. Sem porta de entrada. Sem Tailscale.

Só **este** PC pessoal Windows 11. **Nunca** o PC da CODATA.

Lista fechada: `listar`, `ler`, `buscar` (livres, só nas pastas permitidas); `escrever`, `abrir`, `terminal`, `desligar` (pedem aprovação). Apagar, instalar, config do sistema, senhas/chaves e comando livre estão **proibidos** — o SIMBA pede para fazer à mão.

## 1. No Railway

Variables (só os **nomes**; os valores ficam no painel, nunca no git nem no chat):

- `PC_ENABLED` — `true` liga a ferramenta; `false` desliga e o agente sai no próximo ciclo
- `PC_TOKEN` — token só do agente; se vazio, usa `SIMBA_TOKEN`
- `PC_TIMEOUT_S` — espera pela confirmação (padrão 30)
- `PC_ALLOW_DIRS` — opcional; eco da política. Quem aplica a allowlist é o agente local

Faça o deploy **deste ramo** (`agente-pc`). Não misture com o ramo do celular.

## 2. Neste PC

No `.env` local (já está no `.gitignore`) ou nas variáveis do utilizador Windows:

- `SIMBA_URL` — origem HTTPS do SIMBA (sem barra no fim)
- `PC_TOKEN` — o mesmo tipo de segredo definido no Railway (ou `SIMBA_TOKEN`)
- `PC_ALLOW_DIRS` — pastas extra **absolutas**, separadas por `;` (vazio = só Documentos e Ambiente de trabalho)
- `PC_ENABLED` — `false` pára o agente
- `PC_KILL_FILE` — opcional; se o ficheiro existir, o agente sai. Padrão: `%USERPROFILE%\.simba-pc.off`

Na pasta pai do repositório (`simba-casa`):

```
python -m simba.pc_agent
```

Deixe essa janela aberta. Sem o processo a correr, o SIMBA não executa nada neste computador.

```
python -m simba.pc_agent off
python -m simba.pc_agent on
python -m simba.pc_agent self-test
```

`off` cria o ficheiro do kill switch; `on` apaga-o e liga. Ctrl+C também pára.

## 3. Pastas permitidas

Predefinição: Documentos e Ambiente de trabalho deste utilizador. Nada de `C:\`, Perfil completo, nem pastas de trabalho.

Caminhos com `..`, UNC, junctions/symlinks para fora, `.env`, chaves e executáveis são recusados.

## 4. Teste (só neste PC pessoal)

Pasta de teste no Ambiente de trabalho, por exemplo `Desktop\simba-pc-teste`. Com o agente a ouvir:

- “Lista a pasta de teste” — sem perguntar
- “Cria ola.txt nessa pasta” — cartão de aprovação com o caminho; SIM cria, NÃO não cria
- “Abre o Bloco de notas” — aprovação, depois a janela
- `git status` num repositório **dentro** da allowlist — aprovação com o comando exacto
- Pedir `..\..\Windows` ou `C:\Windows` — recusa
- “Apaga isto” / “instala aquilo” / “corre este PowerShell” — o SIMBA recusa
- Kill: `python -m simba.pc_agent off`, ou criar o ficheiro sentinela, ou `PC_ENABLED=false`

Se o agente estiver parado, o SIMBA diz que o PC **não** confirmou. Não inventa que executou.

## 5. O que isto não faz

Não controla o PC da CODATA. Não altera Google, Telegram nem voz. Não abre porta. Não corre comando livre.
