# Redesign do HUD do SIMBA: holograma realista (Three.js + shaders)

Você vai refazer **apenas a camada visual do HUD** do SIMBA (a tela principal do painel/PWA). Hoje ela parece falsa. Quero um holograma com profundidade e luz reais, no estilo das duas referências que vou anexar:

- **Referência A (SIMBA calado / idle):** esfera wireframe azul perfeita, flutuando sobre uma plataforma circular de anéis.
- **Referência B (SIMBA falando):** a mesma esfera, agora deformada de forma orgânica pelo som, com degradê azul → violeta → magenta, um halo fino em volta e a plataforma mais ativa.

## 0. Antes de mexer em qualquer coisa

1. Crie uma branch `hud-holograma-realista`.
2. Localize os arquivos do front do painel (HTML/JS/CSS da tela com o texto "Diga 'ei, Simba'") e descubra:
   - como o front já sabe o estado do assistente (ouvindo, pensando, falando). Provavelmente via WebSocket do hub (`simba/hub.py` / `simba/server.py`) ou por eventos do reconhecimento de voz e do áudio da resposta;
   - como o áudio da resposta (TTS) é tocado (elemento `<audio>`, `Audio()`, Web Audio etc.);
   - se existe bundler (Vite etc.) ou se é JS puro servido pelo FastAPI, e como o service worker do PWA faz cache dos arquivos.
3. **Me mostre o plano (arquivos que serão alterados, dependências novas, como vai ligar os estados) e espere minha aprovação antes de editar.**
4. Não altere backend, rotas, autenticação, agentes nem a lógica de voz. Só a camada visual e a ligação dos estados com ela.

## 1. Por que o HUD atual parece falso (o que corrigir)

- A esfera é uma grade uniforme, sem profundidade: parece uma bola de discoteca. Falta transparência, brilho na borda (fresnel) e a grade do lado de trás visível, mais fraca.
- A plataforma é achatada e "desenhada"; falta luz real saindo dela.
- As scanlines horizontais são fortes demais e denunciam um efeito de filtro.
- Não há partículas, feixe de luz nem bloom de verdade. O brilho parece só uma sombra azul em volta.
- Nada reage ao som: a esfera não tem vida.

## 2. Stack

- Three.js (WebGL), com `EffectComposer` + `UnrealBloomPass` + `OutputPass`.
- Se o projeto não tem bundler: baixe o Three.js como arquivo local em `static/vendor/` e use import map/ES modules. **Não use CDN**, porque o PWA precisa funcionar offline e com cache do service worker. Inclua esses arquivos no cache do service worker.
- Um único `<canvas>` em tela cheia atrás de toda a interface. O texto, o chip de sugestão e a barra de digitação continuam em HTML por cima, exatamente como hoje.

## 3. Composição da cena

**Câmera:** perspectiva (FOV ~35°), levemente acima, olhando um pouco para baixo (~15–20°). É isso que dá o formato elíptico da plataforma.

**Esfera (centro-superior da tela):**
- Diâmetro ≈ 34–38% da altura da viewport no desktop; ≈ 62% da largura no celular em pé.
- `SphereGeometry(1, 128, 96)` com `ShaderMaterial` próprio: transparente, blending aditivo, `depthWrite: false`, `side: DoubleSide`.
- Grade desenhada no fragment shader a partir do UV: ~72 meridianos × ~48 paralelos, linha fina (~1px, use `fwidth` para manter a espessura constante em qualquer zoom). As linhas convergem nos polos, como na Referência A.
- **Fresnel:** borda bem mais brilhante que o centro. É o que dá volume.
- **Face de trás:** visível com ~30–35% da intensidade da frente, para dar transparência.
- Miolo quase vazio, só com um leve brilho interno azul (radial, bem suave).
- Pequena variação de brilho por linha (ruído baixo) para não parecer uniforme.

**Plataforma (abaixo da esfera), em camadas, cada uma com rotação própria:**
1. Anel externo de ticks finos (~120 marcas, alternando curtas e longas).
2. Faixa grossa segmentada (~24 blocos, larguras e brilhos variados, com intervalos entre eles).
3. Círculo fino contínuo com 4 pequenos entalhes brilhantes.
4. Anel tracejado (~72 traços).
5. Arcos parciais (3 a 4 arcos de ~90–140°) girando no sentido contrário.
6. Centro: disco de luz radial, de onde nasce o feixe.

Desenhe cada camada em `CanvasTexture` gerada por código (ou SVG rasterizado) e aplique em planos deitados (rotação ~ -85° em X), material aditivo emissivo. Velocidades bem diferentes e sentidos alternados. Adicione uma "poça de luz" suave no chão ao redor da plataforma (gradiente radial largo, baixa opacidade). Nada de reflexo real, só essa poça.

**Feixe de luz:** cone/cilindro transparente entre a plataforma e a base da esfera, com gradiente vertical (forte embaixo, some em cima) e estrias verticais finas que sobem devagar. Opacidade baixa, blending aditivo.

**Partículas:** 150–200 pontos (`Points`) subindo do disco central até a base da esfera. Tamanho 1–3 px, fade com a altura, leve espiral. Posições e velocidades aleatórias.

**Fundo:** gradiente radial azul-marinho muito escuro (`#020812` nas bordas → `#041A33` perto da esfera), vinheta, granulação de filme a ~3% de opacidade, e manchas desfocadas e escuras ao fundo para sugerir um ambiente (como na Referência B). **Reduza as scanlines ao mínimo (quase imperceptíveis) ou remova.**

**Ícones de status opcionais** (como na Referência B, cantos superiores, bem discretos): "conexão" (ligado ao estado real do WebSocket) e "saúde do sistema" (ligado a um ping simples, se já existir). Se exigir backend novo, deixe de fora.

## 4. Estados (o coração do trabalho)

Crie uma máquina de estados no front: `idle`, `listening`, `thinking`, `speaking`. Todas as transições usam interpolação suave (lerp/damping, 400–800 ms). Nada de saltos.

| | idle (calado) | listening | thinking | speaking |
|---|---|---|---|---|
| Forma da esfera | esfera perfeita | esfera perfeita | esfera perfeita | deformada por ruído, guiada pelo áudio |
| Movimento | rotação lenta em Y (~0,05 rad/s) + "respiração" de escala ±1,5% a cada ~4 s | igual, um pouco mais viva | rotação mais rápida; brilho pulsando | rotação lenta + ondulação contínua |
| Cor | monocromática azul-ciano | azul-ciano mais claro | azul com pulsos de ciano | degradê azul → violeta → magenta |
| Plataforma | anéis girando devagar | anéis aceleram e o anel externo se expande levemente | anéis aceleram bastante | anéis pulsam no ritmo da voz |
| Partículas | poucas, lentas | um pouco mais | rápidas, em espiral | muitas, espalhadas, parte delas magenta |
| Halo em volta | invisível | invisível | fino, tênue | visível (veja abaixo) |
| Bloom | moderado | moderado+ | moderado+ | forte |
| Texto | `DIGA "EI, SIMBA"` | `OUVINDO…` | `PENSANDO…` | `FALANDO…` |

**Deformação (speaking), no vertex shader:**
- `displacement = simplexNoise3D(normal * freq + time * speed) * amp`, com duas oitavas: uma grande e lenta (bossas amplas, como na Referência B) e uma média.
- `amp` vai de 0 a ~0,18 (em unidades do raio), proporcional ao nível do áudio. `freq` ~1,2–2,0, `speed` ~0,4.
- A grade fica mais densa e fina na parte deformada, como na Referência B (use um valor de densidade que aumenta com `amp`).
- Recalcule a normal aproximada por diferenças finitas (2 amostras extras de ruído), para o fresnel continuar correto na superfície deformada.
- **Cor no speaking:** misture azul `#2F6BFF` → violeta `#8A3CFF` → magenta `#FF3DD0` com base na normal e na direção de uma luz lateral (lado inferior direito mais magenta) e na intensidade do deslocamento. O topo e a parte voltada para a câmera ficam mais azuis.

**Halo (speaking):** arco fino de ~270° em volta da esfera (raio ~1,35 × o da esfera), inclinado ~20°, com degradê ciano → magenta e pontas que afinam (alfa por ângulo). Brilha e gira devagar. Entra com fade ao começar a falar e sai ao terminar.

**Cores base (idle):**
- núcleo `#0A1F3D`, azul profundo `#0B5CFF`, ciano `#38C8FF`, realce `#BFF3FF`.

**Bloom:** idle strength ~0,9; speaking ~1,4; radius ~0,6; threshold baixo (~0,1). Faça a transição de strength suave também.

## 5. Ligação com o áudio

- **Falando:** conecte a saída do TTS a um `AnalyserNode` (`createMediaElementSource` no `<audio>`, ou o nó que já existir). Calcule RMS suavizado (attack rápido ~60 ms, release lento ~250 ms) e 3 bandas (grave/médio/agudo). Grave → amplitude da deformação; médio → pulso dos anéis; agudo → brilho das partículas.
- **Ouvindo:** `AnalyserNode` no microfone (só leitura, não altere a captura de voz atual) para reagir de leve ao volume da minha voz.
- **Fallback:** se não for possível pegar o áudio (ex.: limitação do navegador/iOS), gere um envelope de amplitude simulado (ruído suave, 0,3–0,8) enquanto o estado for `speaking`. O visual nunca pode ficar parado enquanto ele fala.
- Quando o estado volta para idle, a amplitude decai com suavidade até zero (nunca corte seco).

## 6. Layout e HTML por cima do canvas (manter)

- Rótulo de estado centralizado logo abaixo da plataforma (mesma fonte atual, ciano, caixa alta, espaçamento de letras).
- Chip de sugestão ("› Que dia é hoje") logo abaixo.
- Campo de texto na base: `Diga "ei, Simba" ou digite aqui`.
- Responsivo: no celular em pé a esfera fica maior em relação à tela e a plataforma segue abaixo dela, sem cortar. Teste 360×800, 390×844, 768×1024 e 1440×900.

## 7. Desempenho (roda no celular Android como PWA)

- `renderer.setPixelRatio(Math.min(devicePixelRatio, 2))`.
- Bloom em meia resolução.
- Pausar o render quando a aba/app estiver oculto (`visibilitychange`) e reduzir para ~30 fps se o FPS médio cair abaixo de 40 por 3 s.
- Modo leve automático (sem bloom, menos partículas, esfera 64×48) se o dispositivo for fraco ou o FPS continuar baixo.
- Alvo: 60 fps no desktop e ≥ 45 fps num Android intermediário.

## 8. Acessibilidade

- O rótulo de estado fica numa região `aria-live="polite"` para leitores de tela.
- `prefers-reduced-motion`: desativar deformação e partículas, manter só pulso suave de brilho.
- Contraste do texto ≥ 4.5:1 sobre o fundo (WCAG AA). Teste com o bloom ligado.
- O canvas é decorativo: `aria-hidden="true"`.

## 9. Critérios de aceite

- [ ] No idle, a tela se parece com a Referência A: esfera transparente com borda brilhante, grade fina, feixe e partículas, plataforma com anéis em perspectiva.
- [ ] Falando, a tela se parece com a Referência B: esfera deformada pelo som, degradê azul-violeta-magenta, halo em volta, anéis pulsando.
- [ ] Transições entre estados são suaves, sem saltos.
- [ ] A deformação acompanha o volume real da voz do SIMBA (ou o fallback simulado).
- [ ] Nenhuma lógica de voz, WebSocket ou backend foi quebrada.
- [ ] Funciona como PWA instalado, inclusive offline (Three.js em cache).
- [ ] ≥ 45 fps no celular; modo leve ativa sozinho quando necessário.
- [ ] Sem erros no console; textos legíveis (AA).

## 10. Entrega

1. Commits pequenos na branch `hud-holograma-realista`: primeiro cena estática (esfera + plataforma + feixe), depois estados, depois áudio, depois desempenho/acessibilidade.
2. Depois de cada etapa, me diga como testar localmente e o que devo ver.
3. Não faça merge nem push para a `main`. Eu reviso antes (o deploy no Railway é manual).
