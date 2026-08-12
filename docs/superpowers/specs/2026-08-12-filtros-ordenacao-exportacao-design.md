# Filtros, ordenação e exportação Excel: design

## Objetivo

O painel tem hoje filtros parciais (busca/empresa/status/pagamento só na
aba Exames; busca/exame/força só em "Sem pagamento identificado") e nenhuma
ordenação por coluna em lugar nenhum: as tabelas ficam sempre na ordem
fixa em que o backend devolve. Também não existe nenhuma forma de exportar
uma tabela para conferir/compartilhar fora do painel. O seletor "período"
no cabeçalho (30/60/90/180 dias) mistura duas coisas que deveriam ser
separadas: por quanto tempo o backend olha pra trás, e o que a tela mostra.
Essa segunda parte nunca foi um filtro de verdade, é uma janela fixa
sem controle fino.

Este design:
- Generaliza o filtro de "últimos N dias" para um intervalo `de`/`até`
  controlável, aplicado de forma **global** (não por aba): Visão Geral,
  Exames e Financeiro respeitam o mesmo filtro.
- Adiciona ordenação por coluna (clique no cabeçalho) nas duas tabelas de
  análise do Financeiro (Por exame, Eventos) e na tabela de Exames.
- Adiciona exportação para Excel (`.xlsx`) nas mesmas três tabelas.

**Fora de escopo:** filtro de data ou ordenação nas listas de triagem da
Visão Geral (Atrasados/Aguardando prazo continuam sem filtro próprio,
só respeitam o filtro de data global), na seção de investigação "Sem
pagamento identificado" (mantém os filtros que já tem: busca/exame/força),
e nos cartões de Importações (não são tabelas de dados, são status de
arquivo).

## Filtro de data global

### Backend

`rotina_pendencias.analisar(cache, data_de=None, data_ate=None)` substitui
`analisar(cache, dias=30)`: em vez de um corte relativo (`agora - dias`),
filtra `exames`/`enviados` por um intervalo absoluto
(`data_de <= recebido <= data_ate`, cada ponta opcional: `None` significa
sem limite daquele lado). A lógica de filtro em si não muda, só o cálculo
do intervalo. O retorno perde a chave `"dias"`.

`eventos.recebimentos(pastas=None, data_de=None, data_ate=None)` ganha o
mesmo filtro, aplicado à lista de eventos (`evs`) **antes** de qualquer
agregação (`totais`, `por_mes`, `por_exame`, `cobertura`, `sem_pagamento`).
Hoje essa função soma tudo, sem filtro nenhum: esse é o único lugar do
backend onde o filtro de data está sendo adicionado de verdade, não só
generalizado.

Motivo de filtrar as agregações no servidor em vez de no navegador: os
totais e o gráfico mensal do Financeiro são somas. Se o filtro fosse só de
exibição no front-end (esconder linhas depois de já somadas), os totais
mostrados ficariam errados. A alternativa seria reimplementar a soma em
JavaScript, duplicando a lógica de agregação que já existe em
`eventos.recebimentos()`, pior que estender a função Python que já faz
isso.

`GET /api/dados` e `GET /api/recebimentos` passam a aceitar `?de=&ate=`
(formato `AAAA-MM-DD`, cada um opcional) em vez de `/api/dados` aceitar
`?dias=`.

### Frontend

Um único controle no cabeçalho, no lugar do `<select id="dias">` atual: um
`<select>` de opções nomeadas, com "Personalizado…" revelando dois campos
de data (De/Até):

- Últimos 7 dias
- Últimos 30 dias
- Últimos 90 dias (padrão ao abrir o painel)
- Últimos 3 meses
- Este mês
- Mês passado
- Este ano
- Ano passado
- Tudo
- Personalizado… (mostra os campos De/Até)

Cada opção nomeada (exceto "Personalizado" e "Tudo") calcula `de`/`ate` em
JavaScript a partir da data de hoje (ex.: "Mês passado" = primeiro ao
último dia do mês anterior). "Tudo" manda os dois parâmetros vazios.
Selecionar uma opção nomeada dispara `carregar()` e `carregarRecebimentos()`
na hora; em "Personalizado", cada mudança num dos dois campos de data
dispara os dois de novo (mesmo padrão `oninput` que os filtros
busca/empresa/status/pagamento já usam hoje). Esses filtros existentes da
aba Exames continuam exatamente como estão, filtrando no navegador por
cima do conjunto que o backend já devolve filtrado pela data. O subtítulo do cabeçalho troca
"Últimos N dias · atualizado em..." por algo que reflita o intervalo ativo
(ex.: "01/06 a 12/08 · atualizado em...", ou "Todo o período · atualizado
em..." quando for "Tudo").

Esse filtro afeta, sem exceção: cartões e listas da Visão Geral (Atrasados,
Aguardando prazo, Retornados, status da caixa, buracos de numeração),
tabela de Exames, cartões/gráfico mensal/tabela Por exame/lista de Eventos
do Financeiro, e "Sem pagamento identificado" (via `dados`/`rec` filtrados
que já chegam prontos do backend).

## Ordenação por coluna

Aplica-se a três tabelas: Exames (aba Exames), Por exame e Eventos
(drill-down) na aba Financeiro.

Um helper JS único faz a ordenação:

```js
function ordenarLista(lista, campo, direcao, tipo) {
  const sinal = direcao === "asc" ? 1 : -1;
  return lista.slice().sort((a, b) => {
    let va = a[campo], vb = b[campo];
    if (tipo === "numero") return sinal * ((va || 0) - (vb || 0));
    if (tipo === "data") return sinal * (va || "").localeCompare(vb || "");
    return sinal * (va || "").toString().localeCompare((vb || "").toString(), "pt-BR");
  });
}
```

Cada tabela define suas colunas uma vez (`{chave, rotulo, tipo}`), e essa
mesma definição alimenta tanto o cabeçalho clicável quanto a exportação
(seção seguinte). Exemplo (Exames): `codigo` (texto), `nome` (texto),
`empresa` (texto), `recebido` (data), `prazo` (data), `status` (texto),
`retornado_em` (data).

Cabeçalho clicável: clique ordena por aquela coluna (asc); clique de novo
na mesma coluna inverte a direção; uma seta (▲/▼) no cabeçalho mostra a
coluna e direção ativas. Cada tabela guarda seu próprio estado
(`{campo, direcao}`), com o valor inicial igual ao comportamento de hoje
(Exames: `recebido` desc; Por exame: `qtd` desc; Eventos: `data` desc).

## Exportação para Excel

Novo endpoint `POST /api/exportar`: recebe
`{"titulo": "Exames", "colunas": [{"chave": "codigo", "rotulo": "Código", "tipo": "texto"}, ...], "linhas": [{...}]}`
e devolve um arquivo `.xlsx` (`Content-Type:
application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`,
`Content-Disposition: attachment; filename="<Título>_<AAAA-MM-DD>.xlsx"`).
Implementado com `openpyxl` (já é dependência do projeto: hoje só lê
planilhas da CardioPro em `ler_repasses.py`/`eventos.py`; passa a também
escrever). Cabeçalho da planilha vem de `colunas[].rotulo`; cada linha
grava `linhas[i][coluna.chave]` na ordem das colunas.

Os valores em `linhas` são **crus**, não formatados para exibição
(`1234.56`, não `"R$ 1.234,56"`; `"2026-08-01T10:00:00Z"`, não `"01/08"`).
O `tipo` da coluna (o mesmo usado na ordenação) diz ao servidor como
escrever a célula: `numero` vira célula numérica de verdade (soma no
Excel), `data` vira célula de data com formato `dd/mm/aaaa` (parseada do
ISO), `texto` vira string simples.

Botão "Exportar Excel" nas três tabelas (junto da barra de filtros).
Exporta a lista **filtrada e ordenada** que está na tela, mas sem o corte
de exibição: a tabela de Exames corta em 800 linhas e Eventos em 500 só
por performance de renderização; a exportação leva tudo que bate com os
filtros ativos (busca, empresa, status, pagamento, data), não só o que
está visível na tela.

## Testes

Seguindo o padrão do projeto (`pytest` + `monkeypatch`, sem chamada de
rede real):

- `rotina_pendencias.analisar(cache, data_de=..., data_ate=...)`: filtro
  por intervalo absoluto (ambas as pontas, só uma ponta, ou nenhuma,
  equivalente a "Tudo") produz o mesmo conjunto que o filtro por `dias`
  produzia no caso equivalente.
- `eventos.recebimentos(data_de=..., data_ate=...)`: agregações (`totais`,
  `por_mes`, `por_exame`) refletem só os eventos dentro do intervalo;
  sem intervalo, soma tudo (comportamento de hoje).
- Endpoint `/api/exportar`: dado um payload de colunas/linhas com os três
  tipos (texto/número/data), a planilha gerada tem o cabeçalho certo, os
  tipos de célula certos (verificável reabrindo o `.xlsx` com
  `openpyxl.load_workbook`), e o nome de arquivo esperado no
  `Content-Disposition`.

## Fora de escopo

- Filtro de data ou ordenação nas listas de triagem da Visão Geral, em
  "Sem pagamento identificado", ou nos cartões de Importações.
- Qualquer outro formato de exportação (CSV, PDF).
- Salvar/lembrar o filtro de data escolhido entre sessões (sempre volta
  pro padrão "Últimos 90 dias" ao reabrir o painel).
