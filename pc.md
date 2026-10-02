# SIMBA no PC pessoal

O SIMBA no Railway **não** lê o disco deste Windows. Um agente local, a correr **como o seu utilizador** (sem administrador), puxa o comando por HTTPS e confirma. Sem porta de entrada. Sem Tailscale.

Só **este** PC pessoal Windows 11. **Nunca** o PC da CODATA.

Lista fechada: `listar`, `ler`, `buscar` (livres, só nas pastas permitidas); `escrever`, `abrir`, `terminal`, `desligar` (pedem aprovação). Apagar, instalar, config do sistema, senhas/chaves e comando livre estão **proibidos** — o SIMBA pede para fazer à mão.

## 1. No Railway

Variables (só os **nomes**; os valores ficam no painel, nunca no git nem no chat):

- `PC_ENABLED` — só o valor exato `true` liga a ferramenta. Qualquer outra coisa (ou ausente) mantém desligado
- `PC_TOKEN` — token só do agente. Obrigatório, mínimo 32 caracteres e **diferente** do `SIMBA_TOKEN`. Sem ele o servidor recusa o agente e o agente não inicia
- `PC_TIMEOUT_S` — espera pela confirmação (padrão 30)
- `PC_ALLOW_DIRS` — opcional; eco da política. Quem aplica a allowlist é o agente local

O código do agente está no mesmo ramo do celular (`celular-tasker`) e sobe com o mesmo deploy do servidor.

Gerar o token (no PowerShell do seu PC; o valor aparece só na tela, copie direto para o Railway e para o `.env`, sem colar em chat):

```
-join ((48..57)+(65..90)+(97..122) | Get-Random -Count 48 | % {[char]$_})
```

## 2. Neste PC

No `.env` local (já está no `.gitignore`) ou nas variáveis do utilizador Windows:

- `SIMBA_URL` — origem HTTPS do SIMBA (sem barra no fim)
- `PC_TOKEN` — o mesmo valor definido no Railway (nunca o `SIMBA_TOKEN`)
- `PC_ALLOW_DIRS` — pastas extra **absolutas**, separadas por `;` (vazio = só `Desktop\simba-pc`, criada sozinha)
- `PC_ENABLED` — `false` pára o agente
- `PC_KILL_FILE` — opcional; se o ficheiro existir, o agente sai. Padrão: `%USERPROFILE%\.simba-pc.off`

Na pasta pai do repositório (`simba-casa`):

```
python -m simba.pc_agent
```

Deixe essa janela aberta. Sem o processo a correr, o SIMBA não executa nada neste computador.

```
python -m simba.pc_agent self-test   # rode antes de ligar: tudo tem de dizer recusou/ok
python -m simba.pc_agent off
python -m simba.pc_agent on
python -m simba.pc_agent self-test
```

`off` cria o ficheiro do kill switch; `on` apaga-o e liga. Ctrl+C também pára.

## 3. Pastas permitidas

Predefinição: só `Desktop\simba-pc`. Nada de Documentos inteiro, `C:\`, Perfil completo, nem pastas de trabalho. Nunca `data\` do SIMBA, `.git`, `.ssh`, `AppData` nem JSON com token/credencial no nome.

Caminhos com `..`, UNC, junctions/symlinks para fora, `.env` e chaves são recusados. Escrever e abrir só aceitam `.txt .md .csv .json .pdf .png .jpg .docx .xlsx`. Ao substituir um ficheiro existente, o anterior fica ao lado como `.bak`.

## 4. Teste (só neste PC pessoal)

Pasta de teste dentro de `Desktop\simba-pc`, por exemplo `Desktop\simba-pc\teste`. Com o agente a ouvir:

- “Lista a pasta de teste” — sem perguntar
- “Cria ola.txt nessa pasta” — cartão de aprovação com o caminho; SIM cria, NÃO não cria
- “Abre o Bloco de notas” — aprovação, depois a janela
- `git status` num repositório **dentro** da allowlist — aprovação com o comando exacto
- Pedir `..\..\Windows` ou `C:\Windows` — recusa
- “Apaga isto” / “instala aquilo” / “corre este PowerShell” — o SIMBA recusa
- Pedir para criar `a.py` ou ler algo em `data\google` — recusa
- Kill: `python -m simba.pc_agent off`, ou criar o ficheiro sentinela, ou `PC_ENABLED=false`

Se o agente estiver parado, o SIMBA diz que o PC **não** confirmou. Não inventa que executou.

## 5. O que isto não faz

Não controla o PC da CODATA. Não altera Google, Telegram nem voz. Não abre porta. Não corre comando livre.
