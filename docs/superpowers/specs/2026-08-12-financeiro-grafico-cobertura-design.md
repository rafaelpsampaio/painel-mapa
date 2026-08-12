# Financeiro: gráfico, contagens e cobertura de documentos: design

## Objetivo

Três problemas de legibilidade na aba Financeiro, sem relação de
dependência entre si:

1. O gráfico "Recebido por mês" fica ilegível com vários meses: cada
   coluna tem só 42-56px de largura, mas o rótulo embaixo mostra mês +
   valor completo em R$ (ex.: "R$ 12.345,67"), que não cabe e esbarra na
   coluna vizinha.
2. Contagens simples (não monetárias) não têm separador de milhar. `brl()`
   já formata moeda corretamente com `toLocaleString("pt-BR")`; contagens
   cruas (`qtd`, `.length`) são concatenadas direto como número.
3. Não existe uma forma visual de identificar documentos faltando por
   empresa/mês. Hoje só existe uma nota de texto
   (`dados.cobertura_pagamentos`, "Pagamentos já cobrem exames de: Unimed
   01/01 a 15/08...") que descreve outra coisa: a janela de datas de
   exame que os demonstrativos já pagaram, não presença/ausência de
   documento por mês.

**Fora de escopo:** qualquer mudança no parser de documentos
(`ler_repasses.py`), no cruzamento de pagamentos
(`cruzar_pagamentos.py`), ou na nota de texto `cobertura_pagamentos`
existente (Visão Geral): ela continua como está, é um conceito
diferente do que este design endereça.

## 1. Gráfico "Recebido por mês"

Muda só o CSS/layout; a lógica de dados (fatias empilhadas por
pagador/exame, cores estáveis por série, clique abre o drill-down do mês)
não muda.

- `.gb-col` (hoje `min-width: 42px`) passa para uma largura mínima em
  torno de 80-90px, suficiente pro rótulo de valor completo
  (`brl(totalMes)`) não quebrar linha nem esbarrar na coluna vizinha. O
  valor exato de largura é ajustado visualmente durante a implementação
  (testar com um valor alto tipo "R$ 99.999,99" pra garantir que cabe).
- `#grafico-meses` ganha um container com `overflow-x: auto` (ou a
  própria `.grafico-barras` recebe isso), então quando o período
  filtrado tiver muitos meses o usuário rola horizontalmente em vez de
  ver tudo espremido.
- Nenhuma mudança nos dados que chegam do backend (`rec.por_mes`
  continua igual).

## 2. Separador de milhar em contagens

Novo helper, ao lado de `brl()`:

```js
function num(n) {
  return (n || 0).toLocaleString("pt-BR");
}
```

Aplicado em todo lugar do `painel.html` que hoje concatena uma contagem
crua em vez de um valor monetário. Levantamento feito nesta sessão (a
lista exata de linhas é confirmada durante a implementação, já que o
arquivo pode ter mudado):

- Cards do topo (`render()`): Atrasados, Aguardando prazo, Laudos
  enviados, Pagamentos confirmados, Sem registro de pagamento, Para
  conferir, Recebidos no período.
- Cards de recebimento por pagador (`renderCardsRecebimentos()`): Exames
  pagos/faturados, Consultas, e a quantidade de cada pagador
  (IDS/Unimed/CardioPro).
- Tabela "Por exame" (`renderPorExame()`): coluna Qtd.
- Aba Financeiro → Documentos: contagem de documentos por empresa no
  cabeçalho do `<details>` ("Documentos · Unimed (N)"), quantidade de
  itens em cada documento ("N itens"), e as contagens de linha dentro do
  detalhe de cada documento (ECG/MAPA da CardioPro, quantidade por tipo
  de procedimento).

Critério pra decidir se um número cru entra nessa lista: é uma
contagem de itens (não um valor em R$, que já usa `brl()`, nem um índice
de posição, nem parte de uma data). Não precisa de separador em números
que nunca passam de 3 dígitos por natureza (ex.: dias de espera de um
exame individual), mas aplicar o helper ali também não quebra nada: o
`toLocaleString` de um número pequeno simplesmente não insere separador.
Pra manter consistência sem ter que julgar caso a caso, o helper é
aplicado a toda contagem inteira exibida, pequena ou grande.

## 3. Cobertura de documentos por empresa (donut)

### De onde vem o dado

Duas fontes possíveis foram avaliadas:

- **Datas dos documentos** (`emitido_em`/`periodo` em
  `ler_repasses.financeiro()`): descartada. O formato é inconsistente
  entre tipos de documento (`periodo` é `AAAAMM` na Unimed, mas uma
  string de intervalo `"dd/mm/aaaa a dd/mm/aaaa"` no Relatório de
  Repasses da IDS), e a planilha da CardioPro não guarda ano nenhum na
  aba (só "Jan", "Fev"...): o ano de cada aba só existe hoje dentro das
  datas por linha que `eventos.itens_cardiopro()` já extrai célula a
  célula.
- **Eventos já processados** (`rec.por_mes`, o mesmo dado que alimenta o
  gráfico do item 1): usada. Todo evento em `por_mes` já tem uma data
  completa e correta (dia/mês/ano), incluindo os da CardioPro. "Esse mês
  teve pelo menos um evento de pagamento dessa empresa?" fica uma
  pergunta direta sobre um dado que já existe, sem tocar no parser de
  documentos nem duplicar lógica de extração de data.

### Cálculo (frontend, a partir de `rec.por_mes` já filtrado)

```js
function mesesCobertura(periodo) {
  // primeiro mes: inicio do filtro ativo, ou o mes mais antigo com
  // dado em rec.por_mes quando o filtro for "Tudo" (sem data_de)
  const primeiro = periodo.de
    ? periodo.de.slice(0, 7)
    : (rec.por_mes[0] ? rec.por_mes[0].mes : null);
  if (!primeiro) return [];
  const hoje = new Date();
  const mesAtual = hoje.getFullYear() + "-" + String(hoje.getMonth() + 1).padStart(2, "0");
  // ultimo mes: fim do filtro ativo, mas nunca alem do mes corrente
  const ultimoFiltro = periodo.ate ? periodo.ate.slice(0, 7) : mesAtual;
  const ultimo = ultimoFiltro < mesAtual ? ultimoFiltro : mesAtual;
  const meses = [];
  let [ano, mes] = primeiro.split("-").map(Number);
  const [anoFim, mesFim] = ultimo.split("-").map(Number);
  while (ano < anoFim || (ano === anoFim && mes <= mesFim)) {
    meses.push(`${ano}-${String(mes).padStart(2, "0")}`);
    mes++;
    if (mes > 12) { mes = 1; ano++; }
  }
  return meses;
}

function coberturaEmpresa(nome, meses) {
  const porMes = new Map(rec.por_mes.map(m => [m.mes, m]));
  const faltando = meses.filter(ym => !(porMes.get(ym)?.por_pagador?.[nome]));
  const cobertos = meses.length - faltando.length;
  return { pct: meses.length ? Math.round(100 * cobertos / meses.length) : 0, faltando };
}
```

Se `meses.length === 0` (filtro sem nenhum dado antes, caso raro), a
empresa mostra "Sem dados no período" em vez de um donut.

### Visual

Nova seção "Cobertura de documentos", posicionada acima da lista de
documentos existente (`#sec-documentos-fin`), com um donut por empresa
(IDS / Unimed / CardioPro), lado a lado. Cada donut:

- SVG puro (sem biblioteca), um círculo de fundo cinza-claro e um arco
  colorido representando a % de cobertura (`stroke-dasharray` sobre a
  circunferência), com a % escrita no centro.
- Nome da empresa acima ou abaixo do donut.
- Texto fixo logo abaixo: `"Faltou: Dez/25, Nov/25"` (usa `formatMes()`,
  já existente, pra formatar cada mês da lista `faltando`) ou
  `"Cobertura completa"` quando `faltando` estiver vazio.
- Sem interação (sem clique/hover pra detalhe): a lista de meses
  faltando já fica visível direto, sem precisar de drill-down.

Segue o filtro de período global (mesmo `periodoAtivo()`/`rec` que
alimenta o resto da aba Financeiro): trocar o filtro recalcula os
donuts junto com o resto.

## Testes

Seguindo o padrão do projeto:

- `num(n)`: formata milhares corretamente (`1234` → `"1.234"`), não
  quebra em números pequenos (`7` → `"7"`) nem em `0`/`null`/`undefined`.
- `mesesCobertura`/`coberturaEmpresa`: dado um `rec.por_mes` de teste,
  calculam a lista de meses no intervalo certo (respeitando `de`/`ate`,
  incluindo o caso sem `de` e o caso onde `ate` é no futuro), e a % e
  lista de faltando corretas por empresa.
- Não há mudança de contrato em nenhum endpoint do backend
  (`/api/dados`, `/api/recebimentos`): os três itens deste design são
  puramente de frontend, então não precisam de teste `pytest` novo além
  dos já existentes continuarem passando.

## Fora de escopo

- Qualquer mudança em `ler_repasses.py`, `cruzar_pagamentos.py`, ou na
  nota de texto `cobertura_pagamentos` já existente.
- Interatividade nos donuts (clique pra detalhe, filtro por clicar numa
  fatia).
- Abreviar valores monetários (ex.: "R$ 12,3 mil"): o gráfico mensal
  continua mostrando o valor completo, só com mais espaço.
- Persistir/lembrar escolhas desta tela entre sessões.
