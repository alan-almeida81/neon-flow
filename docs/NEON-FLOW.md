# Neon Flow — console dos agentes via Maestri Wire

Visualização servida por `python -m neon_flow serve` em `http://127.0.0.1:8770/`. O mapa é somente leitura: não foca terminal e não altera fila, Trello ou rotinas. A única escrita é o texto que o operador digita no terminal completo de um agente, enviado como prompt pelo Maestri Wire.

## Linguagem visual

Console cyberpunk inspirado em kits de painéis HUD (colchetes nos cantos, abas de título, anéis de medição, listas numeradas e grade). As ligações são trilhas de placa de circuito: segmentos retos com curvas de 90° e chanfros de 45°, com anéis (pads) nas pontas. Cada conexão é um feixe de 1 a 4 fios paralelos (fixo por conexão) que já **nasce no módulo de origem** e segue junto até o destino. Cada feixe sai por pads próprios e tem barramento e corredor reservados. Os corredores desviam de módulos, notas e corredores já ocupados, então nenhuma trilha passa sobre um objeto ou sobre outra trilha. As notas ficam numa coluna à direita, com um canal de corredores à esquerda. No modo TODOS, as rotas do Orquestrador sobem até um barramento acima dos títulos das etapas e descem pelos corredores; os terminais de controle são alcançados por trilhas no flanco esquerdo da coluna. Para telas largas, o espaçamento foi reduzido (colunas 270, equipes 175), o ao vivo segue o desenho do operador (Orquestrador na linha do meio, Vigia acima, Integrador abaixo, Lumen à esquerda e Concierge à direita; cada equipe é uma coluna mais à direita, com Prisma em cima, Forja na linha do Orquestrador e Sentinela embaixo; colunas e módulos fora de uso somem; outros terminais e notas ativas empilham-se junto ao Lumen, ligados por corredores da borda esquerda do Orquestrador; as equipes são alcançadas por um barramento entre a linha de cima e a do meio e por corredores antes de cada coluna, entrando pelo lado esquerdo do módulo; nenhuma trilha é reta: as ligações diretas fazem um desvio de 45° antes do destino; o rótulo etapa · equipe fica logo acima do canto direito do módulo, e o espaçamento é o mínimo que reserva rótulo e ferramentas), a visão geral ao vivo enquadra só o que está em cena com o maior zoom que cabe (até 3,2×; no TODOS, até 2,2×) e cada módulo mostra até 2 ferramentas fora do foco (8 no foco). Uma conexão que fica ativa nasce apagada (cinza) e se energiza da origem ao destino em todos os fios ao mesmo tempo. Cada circuito ativo recebe uma cor própria, livre na paleta e nunca vermelha, e seus fios compartilham essa cor. A cor é liberada quando a conexão volta a ficar ociosa.

Paleta: amarelo, ciano, verde e rosa (botão **TEMA**: Neon, Synthwave, Matriz, Azul HUD, Gelo, Ultravioleta; a escolha fica no navegador). **Vermelho é reservado a falhas**: estados interrompido/falha, aviso de erro e Wire offline. Cores de terminal vermelhas no Maestri aparecem em rosa.

### Identidade por papel

Todos os módulos mantêm o mesmo retângulo de ocupação (as trilhas continuam válidas), mas cada papel tem silhueta, ícone e assinatura próprios. O **ícone fica no centro do anel** para reconhecer o papel sem ler; a cor do ícone é o estado (ciano com brilho = executando, verde = concluído, vermelho = falha/interrupção, amarelo = atenção, apagado = ocioso). Estilo cyberpunk: traços angulares, fantasmas ciano/rosa (aberração cromática) e rasgo de glitch na mudança de estado. Auxiliares usam marcas genéricas por tipo de CLI (`</>` Codex, estrela Claude, `>_` demais), sem logotipos.

| Papel | Silhueta | Ícone | Assinatura |
|---|---|---|---|
| Orquestrador | Deck de comando, cantos cortados e entalhes laterais | Coroa | Antena; uma barra por conexão Maestri **ativa** do terminal e contagem `N LINKS` |
| Consultor (Lumen) | Cápsula | Olho angular | Arcos laterais; violeta em modo TEACH/LEARN |
| Vigia | Cortes diagonais profundos | Colchetes de mira | Linha de varredura contínua |
| Triagem | Boca de admissão no flanco esquerdo | Funil | Boca acende ao executar |
| Análise | Prisma com ponta à esquerda | Prisma com feixe | Feixe de luz entrando na ponta |
| Implementação | Bloco pesado com pé escalonado | Martelo | Aletas de calor que brilham ao executar |
| Revisão | Escudo de base afunilada | Escudo com ✔ | — |
| Integração | Carcaça de conector | Junção (merge) | Pinos na base, acesos ao executar |
| Auxiliar | Chanfro simples | Marca da CLI | — |

### Medidores (anel do módulo)

O anel fino em volta do ícone mede um dado real do papel; a leitura curta fica sob o anel e o texto completo em **MEDIDOR** na datashard. Quando o terminal executa, um ponto orbita o anel.

| Papel | Medidor | Fonte | Sob o anel |
|---|---|---|---|
| Orquestrador, Vigia, auxiliar com rotina | Relógio de rotina: enche até o próximo disparo; tracejado = pausada; pontos = rotinas do terminal | `routines` (`every`, `lastFiredAt`, `enabled`) | tempo até o disparo ou `||` |
| Orquestrador sem rotina | Matriz de conexões: um segmento por conexão do canvas, aceso se ativa | `connections` | ativas/total |
| Triagem | Fila de triagem: verde = triados, amarelo = a triar | Trello (`shelves`) | `N a triar` |
| Análise, Implementação, Revisão | Pipeline da equipe: análise, implementação, revisão e PR; o segmento do próprio papel é mais grosso; verde = pronto/aprovado, vermelho = rejeitado, ciano = etapa em curso | `laneRuns` da equipe | — (estado no ícone e na etiqueta) |
| Integração | Barramento de PRs: um segmento por equipe, cheio com PR, vermelho se a execução falhou | `laneRuns` | `N PR` |
| Consultor e demais | Recência: cheio = agora, vazio = 1 dia; violeta em modo TEACH/LEARN | `lastActiveAt`, modo | tempo desde a atividade ou modo |

A ideia de mostrar ferramentas saindo do agente, câmera com zoom e linha do tempo veio do [agent-flow](https://github.com/patoles/agent-flow) (Apache 2.0). A forma e a mecânica são próprias, sem cópia de código, nome ou logo. Cópia local de referência: `D:\Projetos\agent-flow`.

## Cenas

| Cena | Como entrar | O que mostra |
|---|---|---|
| Ao vivo | padrão | Só quem está executando (e quem participa de uma conexão ativa), na disposição do desenho (equipes em colunas), reenquadrado automaticamente; a lista abaixo mostra os demais |
| Todos | botão **TODOS** ou clique na lista | Todas as equipes em colunas por etapa SDD; Orquestrador no topo de uma coluna de controle à esquerda; notas numa coluna à direita (layout para tela larga) |
| Setor | clique no rótulo da equipe | Zoom na linha da equipe; demais equipes esmaecidas |
| Agente | clique num módulo ou ←/→ | Zoom no módulo, até 8 ferramentas e a datashard (dados e cauda do terminal digitados na tela); **DADOS** ou Enter abre o painel lateral com texto selecionável |

A troca de cena é um voo de câmera com leve recuo no meio do trajeto, linhas de velocidade, faixas de glitch e o rótulo `ACESSANDO // NOME` com barra de progresso. Arrastar e a roda do mouse continuam livres em qualquer cena. Com movimento reduzido, a troca é imediata e sem animações.

## Leitura do console

| Elemento | Significado |
|---|---|
| Módulo com borda ciano, anel girando e varredura | Terminal ativo no Wire (`isActive`) ou turno local em execução |
| Moldura que se desenha da esquerda para a direita | Início de turno |
| Tremor (glitch) e contorno que se expande | Mudança de estado: ciano início, verde conclusão, vermelho só para interrupção/falha |
| Circuito que acende aos poucos até o destino | A ligação ficou ativa. Cada ligação tem sua cor; ao completar, pulsos percorrem a trilha |
| Trilha acesa | Conexão do canvas Maestri com `isActive`; uma cor por circuito ativo |
| Trilha apagada | Conexão do canvas existente, sem troca ativa |
| Pilha numerada âmbar sob o módulo | Ferramentas/MCP do turno, com entrada em glitch e texto digitado; ficam verdes com ✔ e somem ao sair |
| Aba amarela ATENÇÃO | `needsAttention` do Maestri |
| TRACE | Estados observados desde que a página abriu (janela de 15 min); traços âmbar = ferramentas |

Só conexões reais do canvas Maestri são desenhadas; elas mostram que a ligação existe e está ativa, não o conteúdo trocado. O TRACE e o estado de acendimento ficam só no navegador e recomeçam ao recarregar. A cauda do terminal pode estar incompleta e não comprova conclusão.

## Dados

`GET /api/flow` (`neon_flow/flow.py`) reaproveita a projeção do Pixel Office (`build_office`: estados, links e eventos de transição) e acrescenta:

- etapa SDD por nome/papel: triagem, análise, implementação, revisão, integração; os demais terminais ficam em controle (orquestrador, consultor, vigia, auxiliar);
- equipe (`floorName`) e status/progresso de cada floor do Wire;
- cauda do preview do terminal: últimas 6 linhas, sem ANSI e com no máximo 160 colunas;
- conexões do canvas (`connections`) e notas ligadas a terminais (`notes`);
- última execução da fila por equipe (`laneRuns`: lane 1/2/3 = Alfa/Beta/Gama), com card, status, etapas e PR.

Fontes e cache: snapshot do feed Wire (o do `/events`, se conectado; senão, consulta direta a cada 3 s), runtime local a cada 5 s e Trello a cada 30 s. Se o Trello falhar, o console continua e o quadro aparece como indisponível.

`?demo=1` simula o fluxo no navegador, sem consultar o Wire.

## Uplink Lumen

A consulta entre Orquestrador e Lumen tem animação própria sobre o circuito roteado (não cruza módulos). O sinal é o mesmo do Pixel Office: turno do Lumen no runtime em execução, ou concluído há menos de 20 s, e o modo da consulta.

| Modo | Quem ensina | Animação |
|---|---|---|
| TEACH | Lumen orienta o Orquestrador | Feixe dourado em hélice dupla, partículas de luz indo do Lumen ao Orquestrador, estrela de "insight" no Orquestrador e raios dourados irradiando do Lumen |
| LEARN | Orquestrador ensina ao Lumen a correção confirmada | Descarga elétrica violeta, blocos de dados indo do Orquestrador ao Lumen, anéis de absorção no Lumen e órbita tracejada que se contrai |
| Concluído | — | Rastro que esmaece em 20 s |

No modo AO VIVO aparece também o rótulo `UPLINK LUMEN // …`. Com movimento reduzido, fica só o conduto aceso.

## Estilos de ligação

- **Ligações (menu TEMA):** CIRCUITO (trilhas de placa a 90°/45°), CABO (cabos gastos e irregulares sobre as mesmas rotas, com fita, emendas, abraçadeiras, remendos e plugues; energizados com brilho, faíscas e pulsos) ou AMBOS (mistura nas mesmas rotas: ligações em circuito, em cabo ou híbridas, em que o circuito entra numa caixinha de junção com LEDs (piscam quando a ligação está ativa) e sai como cabo; a caixa só vai num trecho reto e livre, senão a ligação fica só circuito; como as rotas não se cruzam, a mistura também não). A escolha fica salva no navegador.

## Terminal completo

No detalhe do agente (clique no módulo e depois em **DADOS**, ou em **VER NO MAPA** num aviso), o botão **ABRIR TERMINAL COMPLETO** abre a tela do terminal com o mesmo fluxo que o Orbita usa:

- O servidor abre o websocket `/api/terminals/{id}/stream` do Maestri Wire (TLS com chave fixada, token do keyring) e repassa saída e geometria ao navegador por Server-Sent Events em `GET /api/terminal-stream?terminalId=…`. O token nunca chega ao navegador.
- A tela é desenhada com [xterm.js](https://github.com/xtermjs/xterm.js) 6.0.0, empacotado em `web/vendor/xterm/` (licença MIT), sem CDN. Cores ANSI, cursor e tamanho real do terminal são preservados; **AMPLIAR** ocupa a janela inteira.
- **Enviar:** o campo abaixo do terminal manda o texto como prompt (`POST /api/prompt` → `POST /api/terminals/{id}/prompt` no Wire). Ctrl+Enter envia, Enter quebra linha; o rascunho de cada agente fica guardado enquanto a página estiver aberta. O servidor só aceita o envio do próprio computador, com `Content-Type: application/json` e sem `Origin` de outro site, e o Maestri só aceita se o pareamento tiver permissão para isso.
- No `?demo=1` o terminal é simulado: digita uma sessão de exemplo e responde ao que for enviado.

## Mensagens de decisão e falha

Quando um agente pede uma decisão (`attention: true`) ou para com falha (`state: "failed"`), aparece um cartão ao lado do módulo dele, com seta apontando para o agente. O cartão acompanha a câmera (também em tela cheia), escolhe o lado que não cobre outros módulos e, se o agente estiver fora da tela, espera no canto superior direito.

- **Conteúdo:** papel, equipe, tarefa, há quanto tempo e a pergunta. A pergunta vem do campo opcional `question`; sem ele, das últimas linhas da cauda do terminal.
- **Ações:** **RESPONDER** abre o terminal completo com o cursor no campo de envio; **VER NO MAPA** foca o agente e abre o detalhe; **OCULTAR** esconde até o próximo pedido.
- **Avisos fora da página:** o título da aba mostra `(N) ⚠ decisão`; um bipe curto toca a cada pedido novo; com **AVISAR NA ÁREA DE TRABALHO**, o navegador mostra uma notificação do sistema (clicar nela abre o agente).
- Até três cartões ficam visíveis; os demais aparecem como `+N aguardando`. Pedidos de decisão vêm antes das falhas.
