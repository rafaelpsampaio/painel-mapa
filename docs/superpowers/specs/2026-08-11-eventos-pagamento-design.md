# Eventos de pagamento e Financeiro centrado em exame — design

## Objetivo

O painel cresceu sem um modelo de dados central: cada parser devolve um
formato próprio, a aba Financeiro soma totais por documento, a aba Análises
cruza por convênio (Hapvida, Amil...), e a investigação de "exame feito e
não pago" ficou espalhada e difícil de usar. O que a usuária precisa:

- Saber quanto recebeu: total, por mês, por pagador (IDS × Unimed ×
  CardioPro), por tipo de exame; nº de exames e nº de consultas.
- Investigar caso a caso: achar rapidamente quem fez exame e não recebeu
  pagamento, com evidência suficiente pra decidir se cobra.
- IDS e Unimed como eixos centrais. O convênio por trás de um pagamento da
  IDS (Hapvida, Amil, Intermédica...) é detalhe de drill-down, nunca eixo
  de agregação.

Este design introduz um modelo único ("evento de pagamento"), um parser novo
para o 4º formato de documento encontrado, uma aba Financeiro redesenhada
(absorvendo a aba Análises, que deixa de existir) e botões separados de
atualização (email × documentos).

## Modelo de dados: evento de pagamento

Nova função em `ler_repasses.py` que varre as pastas de demonstrativos e
devolve uma lista única e deduplicada de eventos:

```python
{
    "pagador": "IDS" | "Unimed" | "CardioPro",
    "exame": <nome canônico, ver taxonomia>,
    "paciente": str,
    "data": "AAAA-MM-DD",          # data do exame/procedimento (competência)
    "valor": float | None,          # None quando a fonte não informa valor
    "convenio": str | None,         # detalhe (só IDS informa); nunca eixo
    "tipo": "pago" | "faturado",   # faturado = só a planilha CardioPro
    "documento": <nome do arquivo de origem>,
}
```

### Fontes que alimentam eventos

1. **IDS · Listagem de Repasse** (já parseado hoje): linhas por paciente dos
   setores MAPA (`itens_ids`) e não-MAPA (`itens_ids_setores`), unificadas.
   Valor por linha; convênio extraído do sufixo do nome quando reconhecido.
2. **IDS · Relatório de Repasses Médicos** (parser NOVO): formato encontrado
   em 4 arquivos reais hoje classificados como "não identificado".
   Assinatura no texto: "Relatório de Repasses Médicos" + "Repasse Médico -
   Resumido". Linhas da seção "Procedimentos (Valor Fixo)":
   `Data Paciente Procedimento Vlr.Repasse Requis. Convênio Qt`
   (ex.: `07/01/2025 ODAIL JOSE DENDEVITE TESTE ERGOMETRICO MIBI 98,83
   5282691 UNIMED 1`). Traz exame nominal, valor, requisição e convênio por
   paciente. Entra também em `NOMES_AMIGAVEIS` e na cadeia `_tentar_parsers`
   pra aba Importações.
3. **Unimed · Demonstrativo**: hoje só extraímos itens do código 20102038
   (MAPA). Passa a extrair itens de todos os códigos da tabela
   `SERVICOS_UNIMED`, incluindo consultas (10101012, 99910073), ECG, Holter
   e avaliação de marca-passo.
4. **CardioPro · Planilha de repasse**: linhas por paciente como hoje
   (`itens_cardiopro`), sem valor. Entram como candidatos a pagamento de
   menor prioridade (ver regra abaixo).

### Regra de pagador (possibilidades cruzadas)

Não há trilho fixo "fonte X recebe do pagador Y" nem lista fechada de
combinações permitidas. Casos reais conhecidos: Unimed paga exame feito na
IDS; CardioPro paga exame da CardioPro; e outros cruzamentos podem existir.
O casamento realizado × pago aceita **qualquer pagador** para qualquer
fonte de exame; a regra é só de **prioridade**, não de exclusividade:

1. Demonstrativo da **IDS** (dinheiro real, com valor).
2. Demonstrativo da **Unimed** (dinheiro real, com valor).
3. Planilha da **CardioPro** (evidência de repasse, sem valor).

Um mesmo exame que aparece em mais de uma fonte conta **uma vez**, pela
fonte de maior prioridade. Isso evita a dupla contagem
planilha-CardioPro + demonstrativo-Unimed do mesmo exame. Onde a planilha
for a única evidência, o evento entra com `pagador: "CardioPro"`,
`tipo: "faturado"` e `valor: None`.

Consequência explícita nos totais: o total em reais soma apenas eventos com
valor (IDS + Unimed). Eventos CardioPro contam em quantidade e aparecem como
"sem valor informado", nunca com valor inventado.

### Deduplicação em dois níveis

1. **Documento** (já existe, commit `9e1aed9`): mesmo conteúdo interpretado,
   nomes de arquivo diferentes → conta um.
2. **Evento** (novo): chave `(pagador, exame, paciente normalizado, data)`.
   Necessário porque os relatórios da IDS se sobrepõem no tempo (um relatório
   impresso em julho reimprime linhas desde janeiro) e demonstrativos
   Unimed/CardioPro repetem linhas do mesmo exame. Reimpressão e reenvio
   nunca duplicam evento, mesmo entre documentos diferentes.

O dedup usa `rotina_pendencias.normalizar()` no nome do paciente, como o
cruzamento atual já faz.

Os dois níveis acima são por chave exata, dentro do mesmo pagador. O caso
entre pagadores diferentes (mesmo exame na planilha CardioPro e no
demonstrativo Unimed) não é dedup por chave: é resolvido pela regra de
prioridade da seção anterior, usando o casamento aproximado por nome +
janela de datas (`casa_nome`, ±10 dias), porque as fontes grafam o nome de
formas diferentes.

## Taxonomia canônica de exame

| Canônico | Fontes que mapeiam pra ele |
|---|---|
| MAPA | setor "MAPA" (IDS), código 20102038 (Unimed/CardioPro) |
| Teste Ergométrico | setor "TESTE ERGOMETRICO", procedimento homônimo |
| Teste Ergométrico MIBI | setor "TESTE ERGOMETRICO MIBI", procedimento homônimo |
| Laudo Stress Farmacológico | setor "HONORARIO MEDICO" (IDS), procedimento homônimo |
| Eletrocardiograma | setores "ECG"/"ELETROCARDIOGRAMA", código 40101010 |
| Consulta | códigos 10101012 e 99910073 (Unimed) |
| Holter | código 20102020 (Unimed) |
| Aval. marca-passo | código 20101201 (Unimed) |

Consultas existem apenas na Unimed (confirmado com o usuário). O modelo fica
aberto: um procedimento fora da tabela entra com o nome que veio no
documento, sem quebrar nada.

## API (`painel.py`)

- **`GET /api/recebimentos`** (novo): substitui `/api/financeiro` e
  `/api/realizados_fornecedor`. Devolve:
  - `totais`: recebido em reais, nº exames, nº consultas, por pagador.
  - `por_mes`: lista de meses com quebra por pagador e por exame.
  - `por_exame`: quantidade e valor por exame canônico.
  - `eventos`: a lista completa (é o que permite drill-down no front sem
    outra chamada; volume atual ~poucos milhares de linhas, ok em JSON).
  - `documentos`: a lista de documentos por empresa (o que hoje vem de
    `/api/financeiro`), para a seção de documentos recebidos.
  - `sem_pagamento`: lista de investigação (ver seção própria).
- Os endpoints antigos `/api/financeiro` e `/api/realizados_fornecedor` são
  removidos junto com o front que os consumia (não há outro consumidor).
- **`GET /api/dados`** ganha parâmetro `?email=0`: pula a varredura da caixa
  (auth + `baixar_repasses.varrer` + `rotina_pendencias.analisar`) e devolve
  apenas o que dá pra recalcular das pastas. É o que alimenta o botão
  "Atualizar documentos".

## Atualização separada (email × documentos)

Dois botões no cabeçalho, no lugar do "Atualizar" único:

- **Atualizar email**: fluxo completo de hoje (varre caixa, baixa
  demonstrativos novos, refaz conciliação MAPA e recarrega tudo). Lento
  (~1 min), usado quando se espera coisa nova no email.
- **Atualizar documentos**: relê só as pastas (local + `repasses/`) e refaz
  `/api/recebimentos` e `/api/importacoes`. Rápido (segundos, com o cache de
  PDF existente). Usado após salvar arquivos na pasta local.

A abertura do painel continua fazendo o ciclo completo automaticamente,
como hoje.

## Aba Financeiro única (Análises deixa de existir)

Estrutura de cima pra baixo:

1. **Cartões de totais**: Total recebido (R$) · Exames pagos (nº) ·
   Consultas (nº) · um cartão por pagador (IDS, Unimed, CardioPro) com
   quantidade e valor.
2. **Recebido por mês**: gráfico de barras empilhadas, alternável entre
   quebra "por pagador" e "por exame" (segmentado como o da aba Análises
   atual). Mês pela data do exame (competência). Clique numa barra ou fatia
   abre o drill-down.
3. **Por exame**: tabela com uma linha por exame canônico (quantidade,
   valor, valor médio). Linha clicável → drill-down.
4. **Sem pagamento identificado** (a lista de investigação, ver abaixo).
5. **Documentos recebidos**: a lista atual por empresa, colapsada
   (`<details>`), no fim.

**Drill-down universal**: qualquer número clicável abre um bloco de
transações (padrão do `bloco-transacoes-fin` atual): lista de eventos com
paciente, exame, data, valor, pagador, convênio (quando houver) e documento
de origem, com busca por nome. Um único componente reutilizado por
cartões, barras e tabela.

A aba Análises sai do menu e seu código (donuts por fornecedor, estimativas
por participação média) é removido. A estimativa "pedido/laudado por
participação média do fornecedor" morre sem substituto: era exatamente o
tipo de número inventado que confundia.

## Investigação "Sem pagamento identificado"

Bloco em formato de lista de trabalho, não de gráfico:

- **Uma linha por caso**: paciente, exame, data, fonte da evidência de
  realização, dias de espera, e uma etiqueta de força da suspeita:
  - **"Período já pago e não veio"** (suspeita forte): o pagador esperado já
    emitiu demonstrativo cobrindo a data do exame e o caso não estava lá.
  - **"Aguardando faturamento"** (fraca): nenhum demonstrativo cobre a data
    ainda; provavelmente atraso normal.
- Ordenação: suspeitas fortes primeiro, depois por idade (mais antigo
  primeiro). Filtros: exame, pagador esperado, período; busca por nome.
- Clique no caso → detalhe: onde ele aparece como realizado (documento/
  email), quais demonstrativos cobrem o período em que ele deveria estar, e
  botão de baixa manual (reaproveita o fluxo de `baixas.txt`).

### Fontes de "realizado" (a cobertura é desigual e o painel diz isso)

- **MAPA**: email (fluxo atual da `rotina_pendencias`), cobertura contínua.
- **Demais exames IDS**: "IDS · Listagem de Exames/Laudos", que chega
  esporadicamente. Sem listagem cobrindo o período, o painel não sabe o que
  foi feito; o bloco mostra a janela de cobertura de cada fonte pra deixar
  o limite claro.
- **CardioPro**: a planilha é a evidência de produção; exame na planilha sem
  pagamento Unimed/CardioPro correspondente entra na lista.

O cruzamento realizado × pago usa o casamento por nome aproximado + janela
de datas já existente (`casa_nome`, ±10 dias), agora contra a lista única
de eventos em vez de três coletas paralelas.

## Migração interna

- `cruzar_pagamentos.py` passa a consumir a lista de eventos (elimina as
  coletas paralelas `coletar_itens`/`coletar_itens_setores` e a matriz
  `COMPAT`, substituída pela regra de prioridade).
- `financeiro()` e `agregar_por_mes_fornecedor()` são substituídas pela
  agregação de eventos; a conciliação MAPA da aba Exames continua igual,
  apenas casando contra eventos.
- A regra de repetição de exame (mesmo paciente, ≤15 dias, um pagamento) e
  as baixas manuais continuam valendo.

## Testes

- Parser novo (Relatório de Repasses Médicos) testado contra os 3 PDFs
  reais legíveis (o 4º tem texto vazio, vira caso de teste de "não
  identificado").
- Extração Unimed ampliada testada contra demonstrativo real, conferindo
  contagens por código contra o próprio PDF.
- Dedup de eventos: teste com dois documentos sobrepostos reais (relatório
  reimpresso) confirmando que o total não duplica.
- Agregações (`por_mes`, `por_exame`, `totais`) com fixtures pequenas e
  determinísticas.
- Regra de prioridade: exame presente na planilha CardioPro e no
  demonstrativo Unimed conta uma vez, pela Unimed.

## Fora de escopo

- Fluxo de email/login, aba Visão geral, aba Exames (além do ponto de
  integração do cruzamento) e baixas manuais.
- Qualquer agregação por convênio (fica só como detalhe de drill-down).
- OCR pra PDFs sem texto extraível (ex.: o arquivo com texto vazio); eles
  continuam aparecendo como "não identificado" na aba Importações.

## Desvios aceitos na implementação

- A planilha CardioPro não alimenta a lista "Sem pagamento identificado":
  ela só entra como evidência de pagamento/faturamento. Um exame que
  aparece só na planilha, sem pagamento IDS/Unimed casado, vira um evento
  "faturado" visível nos cartões e na lista de eventos, não um caso de
  investigação.
- Os filtros implementados no bloco de investigação são exame, força da
  suspeita e busca por nome. Pagador esperado e período ficaram de fora
  desta rodada.
- A cobertura forte/fraca compara mês a mês (granularidade mensal), não
  dia a dia: um pagamento registrado no mês cobre qualquer exame
  realizado no mesmo mês, mesmo que a data exata não bata.
