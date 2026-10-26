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

## Uso de IA

A interface e a lógica foram construídas com auxílio do Grok 4.7, no Cursor. O índice e o risco de equipamento são estatística explicável. O chat usa Anthropic ou OpenAI somente se a chave existir; sem chave, roda local. Não há chave gravada no código.
