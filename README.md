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

Acessos ficam no menu. A sessão inicial é o operador da CCO. A senha das contas de demonstração é `demonstracao`. O servidor recusa despacho, cadastro e restauração quando o perfil não permite. Um gestor municipal de Marília não altera equipamento de Assis.

Apagar `data/store.json` recria a cidade-piloto. `data/access.json` guarda usuários e auditoria, sem as senhas em texto.

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

## Uso de IA

A interface e a lógica foram construídas com auxílio do Grok 4.7, no Cursor. O índice, o risco de equipamento, a ordem das rotas e a inteligência operacional são estatística e regras explicáveis. O chat usa Anthropic ou OpenAI somente se a chave existir; sem chave, roda local. Não há chave gravada no código.
