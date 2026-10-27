# F.O.G.O. — Ferramenta Onisciente de Gestão e Operações

Central de operações de mobilidade para Marília, Assis e Cândido Mota, no desafio PROMETHEUS. O sistema cataloga equipamentos e agentes, mostra o que precisa de decisão agora e antecipa a pressão do dia com um índice explicável e uma regressão linear (Machine Learning) sobre o histórico.

Os dados são sintéticos e reprodutíveis. O mapa de ruas usa os tiles do OpenStreetMap e precisa de internet. O resto funciona na máquina.

## Como executar

Requisito: Python 3.10 ou superior. Nenhuma instalação extra.

No Windows, dê dois cliques em `iniciar.bat`, ou na pasta do projeto:

```bat
py -3 server.py
```

A central abre em `http://127.0.0.1:8080`. Encerre com Ctrl+C.

Para conferir a previsão sem subir a interface:

```bat
py -3 server.py --check
```

## O que a central faz

A tela principal é a visão geral: mapa, o que está acontecendo agora e a fila do que pede ação. Cada número do painel Agora abre a lista já filtrada. Dali dá para abrir uma ocorrência, ver as equipes próximas, confirmar a atribuição, desenhar a rota e acompanhar chegada, atendimento e encerramento.

O mapa começa na operação de demonstração (Marília, Assis e Cândido Mota). A busca territorial localiza uma UF ou um município; fora dessa operação o mapa só mostra o lugar, sem inventar ocorrência ou agente. A busca de outros municípios usa o Nominatim (OpenStreetMap) quando há internet, e o resultado fica em cache.

A primeira tela pede usuário e senha. Os atalhos entram nas contas de demonstração; a senha delas é `demonstracao`. O administrador cria as outras contas em Acessos, com perfil e grupo. A sessão fica na memória do processo: reiniciar o servidor pede o login de novo. O servidor recusa despacho, cadastro e restauração quando o perfil não permite. Um gestor municipal de Marília não altera equipamento de Assis. O operador da CCO vê a central, a fila, as ordens, as rotas, as ocorrências, os alertas, os agentes e a frota. Previsão, equipamentos e os painéis de gestão ficam com supervisor, gestor e administrador.

Apagar `data/store.json` recria a cidade-piloto. `data/access.json` guarda usuários e auditoria, sem as senhas em texto.

## Supabase e Vercel

Este projeto não é Next.js. Os comandos `npm install @supabase/supabase-js` e `npx shadcn@latest add @supabase/supabase-client-nextjs` não entram aqui. A central fala com o Supabase pela biblioteca padrão do Python.

No `.env`, ou nas variáveis da Vercel, use `SUPABASE_URL` e `SUPABASE_ANON_KEY`. A chave publicável (`NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`) também é aceita nesse segundo nome. `GET /api/supabase` diz se o projeto respondeu. A service role ainda não foi cadastrada: sem ela o cadastro continua em arquivo e não é gravado nas tabelas do Supabase.

Na Vercel o build copia `static/` para `public/` e a API sobe em `api/index.py`. Cadastre também `FOGO_ENV=production` e `FOGO_DATA=/tmp/fogo`. A pasta `/tmp` some quando a função esfria, e a sessão fica na memória do processo. Para o cadastro sobreviver na nuvem, falta a service role e as tabelas.

## Onde está a lógica

- `model.py` — cadastro, validação, histórico de 90 dias, alertas, previsão, despacho e rotas
- `ops_orders.py` — ordem de serviço, SLA e PDF
- `ops_vehicles.py` e `routing.py` — frota e percurso pelas vias (OSRM)
- `assistant.py` — chat local e, se houver chave, redação via Anthropic ou OpenAI
- `access.py` — perfis, sessão, escopo territorial e auditoria
- `server.py` — HTTP, SSE, ViaCEP e gravação em `data/store.json`
- `static/` — central de operações

O inventário de demonstração tem os tipos pedidos (radar, câmera, balança, veículo autônomo, cancela, táxi/mototáxi/escolar, totem, patinete, moto e viaturas) e mais de 15 agentes em Marília, Assis e Cândido Mota. Apagar `data/store.json` e subir de novo recria esse conjunto.

## Previsões

Cada previsão na tela diz o que está sendo estimado, os dados usados e a ação.

- **Índice de pressão (0–100).** Média do histórico sintético de 90 dias da região, no mesmo dia da semana e na mesma hora, com peso igual para as quatro ocorrências mais recentes desse recorte. Sensores fora aumentam o índice. A escala não entra no número: aparece como déficit ao lado.
- **Reforço de agentes.** Compara a pressão prevista com a capacidade de cerca de 0,85 ocorrência por hora por agente da escala. A frase sai no formato da região e da janela.
- **Risco de equipamento.** Soma pontos por situação atual, manutenção vencida ou nos próximos 7 dias e idade acima de 7 anos. Não é um modelo treinado.
- **Anomalia.** A janela de 3 horas comparada com a média e o desvio do mesmo recorte. É o presente fora do padrão, não uma previsão.
- **Disponibilidade.** Série dos últimos dias do histórico mais a situação atual do cadastro.
- **Chuva.** O exercício “E se chover forte” aplica fator 1,25 sobre a média da hora e não altera o cadastro. O clima ao vivo do Open-Meteo só entra se a consulta responder; sem rede, o sistema segue sem esse fator.

## Ordem de serviço

Mau funcionamento, furto e manutenção vencida abrem OS sozinhos. Dá para abrir manualmente no quadro. O SLA é 4 h, 24 h, 72 h ou 7 dias. A atribuição sugere o agente em atividade mais próximo, pela distância haversine. Concluir a OS devolve o equipamento a operacional e marca a próxima revisão para 90 dias, exceto quando o caso é furto. O PDF sai do próprio quadro.

## Chat

O botão Chat, ou a tecla `/`, abre o painel. Sem `ANTHROPIC_API_KEY` e sem `OPENAI_API_KEY`, as respostas vêm de regras locais. Com uma das chaves no ambiente, o texto final pode ser reescrito pelo modelo, sempre a partir dos fatos já calculados. Abrir OS pelo chat pede confirmação. As chaves ficam só em variável de ambiente. Veja `.env.example`.

## Roteirização

A rota do dia lê as OS abertas e três equipes (Sampaio, Centro e Assis). A ordem usa inserção mais barata, vizinho mais próximo e 2-opt, em `optimizer.py`. OS crítica entra primeiro. Radar e balança só vão para equipe com essa habilidade. Cada equipe leva no máximo 6 paradas e 8 horas, com 30 minutos de execução e volta à base.

A comparação “rota ingênua” reparte as OS na ordem de abertura, sem olhar o mapa. O desenho pede a geometria ao OSRM (`/route` e `/table`). Se não responder em 3 segundos, a tela marca **estimativa aproximada** e usa 30 km/h em linha reta — esse traço não é uma rua. No pico (7h–9h e 17h–19h) o tempo é multiplicado por 1,35. Chuva do Open-Meteo, se responder, soma 25%. Não há trânsito ao vivo.

Complexidade prática O(n²) por equipe. Serve para dezenas de paradas, não para centenas. Moto e caminhão continuam no perfil de automóvel do OSRM.

## Inteligência operacional

| Dor | Solução | Conta | Limite |
| --- | --- | --- | --- |
| Equipamento “ok” que não registra | Zumbi se dois intervalos ficam abaixo de 20% do baseline da hora | Taxa do tipo × pico | Baseline sintético, não um log bruto de 90 dias por equipamento |
| Várias falhas do mesmo nó | OS-mãe e uma equipe | 3 falhas ou 60% do nó em 10 min; confiança = percentual do nó | A janela da demonstração é o instante do cenário |
| Alerta solto | Fila de até 7 ações com custo de esperar | registros/hora × horas × peso da via | Peso 1,4 só em Sampaio Vidal |
| Sair sem kit | Casos parecidos por tipo, fornecedor e firmware | Soma de campos iguais | Não é modelo treinado |
| Viagem só para preventiva | Carona se o desvio cabe em 8 min | Haversine a 30 km/h | Não usa o trânsito real |
| Sensor cego | Grade e posto que cobre mais pontos | Guloso | Não é área geográfica oficial |
| Agente parado em zona 4 ou 5 | Check-in e alerta ao supervisor | 20 min parado, 2 min sem resposta | Demonstração confirma o silêncio na hora. Em produção, localização de agente exige base legal (LGPD) |
| Contrato ruim | Ranking pelo SLA `contrato_sla_horas` | Média de horas das OS concluídas | Amostra sintética |

O cenário “Rodar cenário de demonstração”, na tela Inteligência, percorre esses passos em cerca de 3 minutos.

## Decisões de UX

A pessoa na central precisa ver, em poucos segundos, o que exige atenção. O menu principal tem nove destinos: Central, O que fazer agora, Ordens de serviço, Rotas, Equipamentos, Agentes, Previsões, Impacto e Configurações. O restante continua em Mais, para não esconder telas que já existiam.

A barra superior concentra a saúde da cidade, a busca (também em Ctrl+K), o sino de alertas críticos, o modo crise, o tema e o usuário. A paleta de comandos acha equipamento, agente, OS, bairro e tela. A tecla ? lista os atalhos. O primeiro acesso mostra um tour de cinco passos, que pode ser pulado.

As cores de situação são as mesmas em badge, mapa e tabela: verde operacional, amarelo atenção, laranja suspeito, vermelho crítico, azul em manutenção, roxo não instalado, cinza desativado. O texto acompanha a cor. A fonte é Segoe UI, no próprio sistema, para a central abrir sem baixar fonte da internet. O corpo tem 14 px e os botões, no mínimo 40 px.

Na Central, cinco indicadores ficam no topo e o que fazer agora fica na coluna direita. O quadro de OS aceita arrastar o card de estágio. O formulário de equipamento está em Identificação, Situação e Localização.

## Valor para a gestão

Os números desta camada são estimativas com premissas em `value_settings` no cadastro. Apagar `data/store.json` recria os campos que faltarem, sem mudar o esquema.

| Dor | Solução | Método | Dados | Limitação |
| --- | --- | --- | --- | --- |
| O gestor não vê o custo do mês | Painel Financeiro | Soma de mão de obra, peças e deslocamento; perda = horas parado × custo/hora do tipo e da via | OS encerradas e `horas_parada_mes` | Meses sem OS usam série de demonstração, marcada na tela |
| Aferição vencida passa batido | Lista 30/15/7 dias e OS automática | Data `validade_afericao` comparada com hoje | Radar e balança, órgão no cadastro | O prazo legal precisa ser confirmado com a legislação e o órgão. A autuação é simulada |
| OS concluída sem o técnico no local | Check-in, fotos e tempo mínimo | Haversine contra o raio configurável | Check-in, nomes das fotos e início da OS | Foto é o nome do arquivo, não o binário. Sem prova, a OS fecha como conclusão suspeita |
| Não se sabe quantas equipes bastam | Simulador de 1 a 15 equipes | Eventos discretos: chegada exponencial e atendimento na média das OS | Histórico de abertura; se a amostra for curta, usa 3,0 por hora | Um turno de 8 h. SLA é a espera até o início, não o SLA contratual da OS |
| A dica se perde no fechamento | Campo de uma frase e busca por modelo | Sobreposição de tipo e palavras | `dica_do_tecnico` | Não é um modelo treinado |
| Preventiva no horário errado | Aviso de vizinho fora ou pico | Mesma região fora, outra preventiva aberta, ou 7h–9h e 17h–19h | Situação do equipamento e a hora | A sugestão anda de hora em hora, sem o trânsito real |
| O histórico pode ser alterado | Cadeia SHA-256 e PDF | Cada registro inclui o hash do anterior | `ledger` no cadastro | A cadeia guarda os eventos novos. O log antigo de acesso continua separado |
| Relatório sob encomenda | `/docs`, webhook HMAC e frases no chat | Palavras-chave locais; o webhook assina o corpo | OS, contratos e a simulação | Sem chave de IA o chat não reescreve o relatório |

A tela Valor entregue soma rota poupada, multa contratual identificada e o risco de aferição. Está escrito na tela que são estimativas.

## Uso de IA

A interface e a lógica foram construídas com auxílio do Grok 4.7, no Cursor. O índice, o risco de equipamento, a ordem das rotas e a inteligência operacional são estatística e regras explicáveis. O chat usa Anthropic ou OpenAI somente se a chave existir; sem chave, roda local. Não há chave gravada no código.
