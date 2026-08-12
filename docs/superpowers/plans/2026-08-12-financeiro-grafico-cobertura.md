# Financeiro: gráfico, contagens e cobertura de documentos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolver os três problemas de legibilidade restantes na aba Financeiro do painel MAPA: gráfico "Recebido por mês" ilegível, contagens sem separador de milhar, e falta de um indicador visual de documentos faltando por empresa/mês.

**Architecture:** Mudanças isoladas em `painel.html` (único arquivo de frontend do projeto, sem build step, vanilla JS). Task 1 é CSS mais uma substituição mecânica de expressões JS. Task 2 adiciona uma seção nova com lógica JS nova (cálculo de cobertura por mês a partir de dado que já existe em `rec.por_mes`) e um donut SVG desenhado à mão, sem biblioteca externa.

**Tech Stack:** HTML/CSS/JS embutidos em `painel.html`. SVG nativo pro donut. `Node.js` (já disponível no ambiente de desenvolvimento) usado só pra verificação manual da lógica JS nova antes de aplicar no arquivo, já que o projeto não tem test runner de JS (o `pytest` do projeto cobre só o backend Python).

## Global Constraints

- Sem framework ou biblioteca JS externa: tudo em vanilla JS dentro de `painel.html`, seguindo o padrão do resto do projeto.
- Sem mudança de contrato em `/api/dados` ou `/api/recebimentos`: as mudanças deste plano são inteiramente de frontend.
- Sem mudança em `ler_repasses.py`, `cruzar_pagamentos.py`, nem na nota de texto `cobertura_pagamentos` já existente (Visão Geral).
- Toda contagem inteira **derivada de dados** (não constantes fixas de limite de exibição, como o `LIMITE = 800` de Exames ou o `500` do corte de Eventos) usa o helper `num(n)` (baseado em `toLocaleString("pt-BR")`), no mesmo espírito de como `brl()` já formata moeda.
- Nenhuma destas mudanças toca em código Python: `py -m pytest -q` deve continuar passando com a mesma contagem de testes do baseline, em toda task.
- O donut de cobertura de documentos (Task 2) segue o filtro de período global (`periodoAtivo()`), recalculando junto com o resto da aba Financeiro quando o filtro muda.

---

### Task 1: Gráfico mais largo e separador de milhar nas contagens

**Files:**
- Modify: `painel.html`

**Interfaces:**
- Produces: `function num(n)` (novo helper, ao lado de `brl()`). Não é consumido pela Task 2 (percentuais de cobertura vão de 0 a 100, nunca precisam de separador de milhar).

- [ ] **Step 1: Aumentar a largura das colunas do gráfico mensal**

Em `painel.html`, localizar a regra CSS `.gb-col` (dentro do bloco de estilos, perto de `.grafico-barras`):

```css
  .gb-col { flex: 1; min-width: 42px; display: flex; flex-direction: column;
    align-items: center; gap: 4px; }
```

Trocar `min-width: 42px` por `min-width: 90px` (espaço suficiente pro rótulo `brl(totalMes)` completo, ex. "R$ 12.345,67", não quebrar linha nem esbarrar na coluna vizinha):

```css
  .gb-col { flex: 1; min-width: 90px; display: flex; flex-direction: column;
    align-items: center; gap: 4px; }
```

`.grafico-barras` já tem `overflow-x: auto` (linha visível no mesmo bloco), então quando os meses não couberem mais na largura da tela o próprio container já rola horizontalmente. Não precisa adicionar nada além da troca do `min-width`.

- [ ] **Step 2: Escrever e rodar a verificação do helper `num()`**

Criar um arquivo temporário na raiz do worktree, `_verificar_num.js` (não deve ser commitado: apagar ao final da task), com:

```js
function num(n) {
  return (n || 0).toLocaleString("pt-BR");
}
const casos = [
  [7, "7"],
  [0, "0"],
  [1234, "1.234"],
  [123456, "123.456"],
  [null, "0"],
  [undefined, "0"],
];
let falhou = false;
for (const [entrada, esperado] of casos) {
  const saida = num(entrada);
  if (saida !== esperado) {
    console.log("FALHOU: num(" + entrada + ") = '" + saida + "', esperado '" + esperado + "'");
    falhou = true;
  }
}
console.log(falhou ? "FALHOU" : "OK: todos os casos passaram");
```

Rodar: `node _verificar_num.js`
Esperado: `OK: todos os casos passaram`. Este script já contém a implementação final de `num()`: como não dá pra importar `painel.html` (não é um módulo) dentro de um script Node, a verificação roda numa cópia isolada da função primeiro, e o Step 3 cola essa mesma implementação, já validada, dentro de `painel.html`.

- [ ] **Step 3: Adicionar o helper `num()` em `painel.html`**

Logo depois da função `brl()` (por volta da linha 446-449):

```js
function brl(v) {
  if (v == null) return "";
  return v.toLocaleString("pt-BR", {style: "currency", currency: "BRL"});
}
```

Adicionar logo abaixo:

```js
function brl(v) {
  if (v == null) return "";
  return v.toLocaleString("pt-BR", {style: "currency", currency: "BRL"});
}
function num(n) {
  return (n || 0).toLocaleString("pt-BR");
}
```

- [ ] **Step 4: Aplicar `num()` nos cards do topo (função `render()`)**

Trocar (por volta das linhas 802-818):

```js
  document.getElementById("cards").innerHTML =
    "<div class='card vermelho'><div class='num'>" + atrasados.length +
      "</div><div class='rot'>Atrasados</div></div>" +
    "<div class='card azul'><div class='num'>" + noPrazo.length +
      "</div><div class='rot'>Aguardando prazo</div></div>" +
    "<div class='card verde'><div class='num'>" + c.retornados +
      "</div><div class='rot'>Laudos enviados</div></div>" +
    "<div class='card verde'><div class='num'>" + pagos +
      "</div><div class='rot'>Pagamentos confirmados</div></div>" +
    "<div class='card ambar' style='cursor:pointer' onclick='verFaltando()'" +
      " title='Laudos dentro do período que os demonstrativos ja pagam, " +
      "mas sem registro neles. Clique para ver a lista'><div class='num'>" +
      emFalta + "</div><div class='rot'>Sem registro de pagamento</div></div>" +
    "<div class='card ambar'><div class='num'>" + (c.provaveis + c.avisos) +
      "</div><div class='rot'>Para conferir</div></div>" +
    "<div class='card cinza'><div class='num'>" + c.recebidos +
      "</div><div class='rot'>Recebidos no período</div></div>";
```

Por:

```js
  document.getElementById("cards").innerHTML =
    "<div class='card vermelho'><div class='num'>" + num(atrasados.length) +
      "</div><div class='rot'>Atrasados</div></div>" +
    "<div class='card azul'><div class='num'>" + num(noPrazo.length) +
      "</div><div class='rot'>Aguardando prazo</div></div>" +
    "<div class='card verde'><div class='num'>" + num(c.retornados) +
      "</div><div class='rot'>Laudos enviados</div></div>" +
    "<div class='card verde'><div class='num'>" + num(pagos) +
      "</div><div class='rot'>Pagamentos confirmados</div></div>" +
    "<div class='card ambar' style='cursor:pointer' onclick='verFaltando()'" +
      " title='Laudos dentro do período que os demonstrativos ja pagam, " +
      "mas sem registro neles. Clique para ver a lista'><div class='num'>" +
      num(emFalta) + "</div><div class='rot'>Sem registro de pagamento</div></div>" +
    "<div class='card ambar'><div class='num'>" + num(c.provaveis + c.avisos) +
      "</div><div class='rot'>Para conferir</div></div>" +
    "<div class='card cinza'><div class='num'>" + num(c.recebidos) +
      "</div><div class='rot'>Recebidos no período</div></div>";
```

- [ ] **Step 5: Aplicar `num()` na contagem de exames filtrados (função `renderExames()`)**

Trocar (por volta da linha 715-716):

```js
  document.getElementById("f-contagem").textContent =
    lista.length + " exame" + (lista.length === 1 ? "" : "s");
```

Por:

```js
  document.getElementById("f-contagem").textContent =
    num(lista.length) + " exame" + (lista.length === 1 ? "" : "s");
```

(o segundo `lista.length` fica cru: é só a comparação `=== 1` pra decidir plural, não é exibido.)

- [ ] **Step 6: Aplicar `num()` no resumo "Por empresa" e na tabela de fontes (função `render()`)**

Trocar (por volta das linhas 853-864):

```js
  if (st.empresas && st.empresas.length) {
    stHtml += "<p style='margin:8px 0 4px'><b>Por empresa:</b> " +
      st.empresas.map(e => esc(e.empresa) + ": " + e.exames + " mapas (" +
        e.pendentes + " pend.)").join(" · ") + "</p>";
  }
  stHtml += "<table><tr><th>Fonte</th><th>Exames</th><th>Último envio</th></tr>" +
    st.fontes.map(f =>
      "<tr><td>" + esc(f.fonte) + "</td><td>" + f.exames + "</td><td>" +
      dataBr(f.ultimo) +
      (f.dias_sem_enviar >= 7 ? " <span class='alerta'>sem enviar há " +
        f.dias_sem_enviar + " dias</span>" : "") +
      "</td></tr>").join("") + "</table>";
```

Por:

```js
  if (st.empresas && st.empresas.length) {
    stHtml += "<p style='margin:8px 0 4px'><b>Por empresa:</b> " +
      st.empresas.map(e => esc(e.empresa) + ": " + num(e.exames) + " mapas (" +
        num(e.pendentes) + " pend.)").join(" · ") + "</p>";
  }
  stHtml += "<table><tr><th>Fonte</th><th>Exames</th><th>Último envio</th></tr>" +
    st.fontes.map(f =>
      "<tr><td>" + esc(f.fonte) + "</td><td>" + num(f.exames) + "</td><td>" +
      dataBr(f.ultimo) +
      (f.dias_sem_enviar >= 7 ? " <span class='alerta'>sem enviar há " +
        num(f.dias_sem_enviar) + " dias</span>" : "") +
      "</td></tr>").join("") + "</table>";
```

- [ ] **Step 7: Aplicar `num()` nos contadores de "Provavelmente laudados", "Respondidos sem laudo", "Numeração pulada" e "Baixados manualmente" (função `render()`)**

Trocar cada uma das quatro linhas de contagem (por volta das linhas 868-893):

```js
      dados.provaveis.length + ")</summary><div class='corpo'>" +
```
```js
      dados.avisos.length + ")</summary><div class='corpo'>" +
```
```js
      dados.buracos.length + ")</summary><div class='corpo'>" +
```
```js
      dados.baixados.length + ")</summary><div class='corpo'><table>" +
```

Por (respectivamente):

```js
      num(dados.provaveis.length) + ")</summary><div class='corpo'>" +
```
```js
      num(dados.avisos.length) + ")</summary><div class='corpo'>" +
```
```js
      num(dados.buracos.length) + ")</summary><div class='corpo'>" +
```
```js
      num(dados.baixados.length) + ")</summary><div class='corpo'><table>" +
```

As condições `if (dados.provaveis.length)` etc. que controlam se o bloco aparece continuam cruas (são checagens de verdadeiro/falso, não exibição).

- [ ] **Step 8: Aplicar `num()` no contador de "Pagamentos sem exame correspondente" (função `render()`)**

Trocar (por volta da linha 904-905):

```js
      "<details><summary>Pagamentos sem exame correspondente (" +
      dados.pagamentos_orfaos.length + ")</summary><div class='corpo'>" +
```

Por:

```js
      "<details><summary>Pagamentos sem exame correspondente (" +
      num(dados.pagamentos_orfaos.length) + ")</summary><div class='corpo'>" +
```

- [ ] **Step 9: Aplicar `num()` nos cards de recebimento por pagador (função `renderCardsRecebimentos()`)**

Trocar (por volta das linhas 1239-1250):

```js
  let h = cardRec("Total recebido", brl(t.valor), null,
                  "mostrarEventos('Todos os eventos', function(e){return true})");
  h += cardRec("Exames pagos/faturados", t.exames, null,
               "mostrarEventos('Exames pagos', function(e){return e.exame !== 'Consulta'})");
  h += cardRec("Consultas", t.consultas, null,
               "mostrarEventos('Consultas', function(e){return e.exame === 'Consulta'})");
  for (const nome of ["IDS", "Unimed", "CardioPro"]) {
    const p = t.por_pagador[nome];
    if (!p) continue;
    h += cardRec(nome, p.qtd, valorAgregado(p.valor),
                 "mostrarEventos('" + nome + "', function(e){return e.pagador === '" +
                 nome + "'})");
  }
```

Por:

```js
  let h = cardRec("Total recebido", brl(t.valor), null,
                  "mostrarEventos('Todos os eventos', function(e){return true})");
  h += cardRec("Exames pagos/faturados", num(t.exames), null,
               "mostrarEventos('Exames pagos', function(e){return e.exame !== 'Consulta'})");
  h += cardRec("Consultas", num(t.consultas), null,
               "mostrarEventos('Consultas', function(e){return e.exame === 'Consulta'})");
  for (const nome of ["IDS", "Unimed", "CardioPro"]) {
    const p = t.por_pagador[nome];
    if (!p) continue;
    h += cardRec(nome, num(p.qtd), valorAgregado(p.valor),
                 "mostrarEventos('" + nome + "', function(e){return e.pagador === '" +
                 nome + "'})");
  }
```

- [ ] **Step 10: Aplicar `num()` na tabela "Por exame" (função `renderPorExame()`)**

Trocar (por volta da linha 1274-1276):

```js
  const linhas = lista.map(x =>
    "<tr style='cursor:pointer' onclick=\"mostrarEventosPorExame('" + x.exame + "')\">" +
    "<td>" + esc(x.exame) + "</td><td class='num'>" + x.qtd + "</td>" +
```

Por:

```js
  const linhas = lista.map(x =>
    "<tr style='cursor:pointer' onclick=\"mostrarEventosPorExame('" + x.exame + "')\">" +
    "<td>" + esc(x.exame) + "</td><td class='num'>" + num(x.qtd) + "</td>" +
```

- [ ] **Step 11: Aplicar `num()` no detalhe de cada documento financeiro (função `detalheDocumentoFin()`)**

Trocar (por volta das linhas 1005-1021):

```js
  if (doc.meses) {
    h += "<table><tr><th>Mês</th><th>ECG</th><th>MAPA</th></tr>" +
      doc.meses.map(m => "<tr><td>" + esc(m.mes) + "</td><td>" +
        m.ecg + "</td><td>" + m.mapa + "</td></tr>").join("") + "</table>";
  } else {
    h += "<table><tr><th>Tipo</th>" +
      (doc.linhas.some(l => l.detalhe) ? "<th>Unidade</th>" : "") +
      "<th>Qtd</th><th>Valor</th></tr>" +
      doc.linhas.map(l => "<tr><td>" + esc(l.tipo) + "</td>" +
        (doc.linhas.some(x => x.detalhe)
          ? "<td>" + esc(l.detalhe || "") + "</td>" : "") +
        "<td>" + l.qtd + "</td><td>" + brlSeguro(l.valor) + "</td></tr>")
        .join("") + "</table>";
  }
  if (doc.executantes) {
    h += "<p class='nota' style='margin-top:8px'>" + doc.executantes.map(e =>
      esc(e.nome) + ": " + e.servicos + " serviços (" + brlSeguro(e.valor) +
      ")").join(" · ") + "</p>";
```

Por:

```js
  if (doc.meses) {
    h += "<table><tr><th>Mês</th><th>ECG</th><th>MAPA</th></tr>" +
      doc.meses.map(m => "<tr><td>" + esc(m.mes) + "</td><td>" +
        num(m.ecg) + "</td><td>" + num(m.mapa) + "</td></tr>").join("") + "</table>";
  } else {
    h += "<table><tr><th>Tipo</th>" +
      (doc.linhas.some(l => l.detalhe) ? "<th>Unidade</th>" : "") +
      "<th>Qtd</th><th>Valor</th></tr>" +
      doc.linhas.map(l => "<tr><td>" + esc(l.tipo) + "</td>" +
        (doc.linhas.some(x => x.detalhe)
          ? "<td>" + esc(l.detalhe || "") + "</td>" : "") +
        "<td>" + num(l.qtd) + "</td><td>" + brlSeguro(l.valor) + "</td></tr>")
        .join("") + "</table>";
  }
  if (doc.executantes) {
    h += "<p class='nota' style='margin-top:8px'>" + doc.executantes.map(e =>
      esc(e.nome) + ": " + num(e.servicos) + " serviços (" + brlSeguro(e.valor) +
      ")").join(" · ") + "</p>";
```

- [ ] **Step 12: Aplicar `num()` no resumo de arquivos importados (função `renderSecaoImportacoes()`)**

Trocar (por volta das linhas 1071-1074):

```js
  resumoEl.textContent = secao.arquivos.length + " arquivo" +
    (secao.arquivos.length === 1 ? "" : "s") +
    (naoId ? " · " + naoId + " não identificado" + (naoId === 1 ? "" : "s") : "") +
    (erro ? " · " + erro + " com erro" : "");
```

Por:

```js
  resumoEl.textContent = num(secao.arquivos.length) + " arquivo" +
    (secao.arquivos.length === 1 ? "" : "s") +
    (naoId ? " · " + num(naoId) + " não identificado" + (naoId === 1 ? "" : "s") : "") +
    (erro ? " · " + num(erro) + " com erro" : "");
```

- [ ] **Step 13: Aplicar `num()` no resumo de "Sem pagamento identificado" (função `renderSemPagamento()`)**

Trocar (por volta das linhas 1202-1204):

```js
  const fortes = casos.filter(c => c.forca === "forte").length;
  document.getElementById("sp-contagem").textContent =
    visiveis.length + " caso(s) · " + fortes + " forte(s)";
```

Por:

```js
  const fortes = casos.filter(c => c.forca === "forte").length;
  document.getElementById("sp-contagem").textContent =
    num(visiveis.length) + " caso(s) · " + num(fortes) + " forte(s)";
```

- [ ] **Step 14: Aplicar `num()` na lista de documentos financeiros por empresa (função `renderDocumentosFin()`)**

Trocar (por volta das linhas 1346-1355):

```js
    listas += "<section class='bloco'><details><summary><h2 style='display:inline'>" +
      "Documentos · " + esc(nome) + " (" + docsOrdenados.length +
      ")</h2></summary><div class='doc-fin-lista'>" +
      docsOrdenados.map(doc => {
        const r = resumoDocumentoFin(doc);
        return "<details><summary>" +
          "<span class='doc-data'>" + esc(dataDocumentoFin(doc)) + "</span>" +
          "<span class='doc-tipo'>" + esc(doc.tipo_amigavel || TIPO_AMIGAVEL_FIN[nome]) + "</span>" +
          "<span class='doc-num'>" + r.qtd + " itens" +
```

Por:

```js
    listas += "<section class='bloco'><details><summary><h2 style='display:inline'>" +
      "Documentos · " + esc(nome) + " (" + num(docsOrdenados.length) +
      ")</h2></summary><div class='doc-fin-lista'>" +
      docsOrdenados.map(doc => {
        const r = resumoDocumentoFin(doc);
        return "<details><summary>" +
          "<span class='doc-data'>" + esc(dataDocumentoFin(doc)) + "</span>" +
          "<span class='doc-tipo'>" + esc(doc.tipo_amigavel || TIPO_AMIGAVEL_FIN[nome]) + "</span>" +
          "<span class='doc-num'>" + num(r.qtd) + " itens" +
```

- [ ] **Step 15: Aplicar `num()` no título do drill-down de eventos e no aviso de corte da tabela de Eventos**

Trocar (função `mostrarEventos()`, por volta da linha 1289-1290):

```js
  document.getElementById("eventos-titulo").textContent =
    titulo + " (" + eventosVisiveis.length + ")";
```

Por:

```js
  document.getElementById("eventos-titulo").textContent =
    titulo + " (" + num(eventosVisiveis.length) + ")";
```

Trocar (função `renderEventosFiltrados()`, por volta da linha 1332-1333):

```js
    (lista.length > 500 ? "<p class='nota'>Mostrando 500 de " + lista.length +
     "; use a busca pra refinar.</p>" : "");
```

Por:

```js
    (lista.length > 500 ? "<p class='nota'>Mostrando 500 de " + num(lista.length) +
     "; use a busca pra refinar.</p>" : "");
```

- [ ] **Step 16: Rodar a suíte de testes Python e apagar o script de verificação**

Rodar: `py -m pytest -q`
Esperado: mesma contagem de testes do baseline (nenhum arquivo Python foi tocado nesta task).

Apagar `_verificar_num.js` (arquivo temporário do Step 2, não deve ser commitado).

- [ ] **Step 17: Commit**

```bash
git add painel.html
git commit -m "painel.html: gráfico mensal mais largo e separador de milhar nas contagens"
```

---

### Task 2: Cobertura de documentos por empresa (donut)

**Files:**
- Modify: `painel.html`

**Interfaces:**
- Consumes: `rec.por_mes` (já existente, cada item `{mes: "AAAA-MM", por_pagador: {NOME: {qtd, valor}}, por_exame: {...}}`), `periodoAtivo()` (já existente, retorna `{de, ate}` em `"AAAA-MM-DD"` ou string vazia), `formatMes(ym)` (já existente, `"AAAA-MM"` → `"Mês/AA"`), `esc()` (já existente).
- Produces: `mesesCobertura(periodo)`, `coberturaEmpresa(nome, meses)`, `svgDonut(pct, cor)`, `renderCobertura()`. Nenhuma é consumida fora desta task.

- [ ] **Step 1: Escrever e rodar a verificação de `mesesCobertura`/`coberturaEmpresa` num script Node isolado**

Criar um arquivo temporário na raiz do worktree, `_verificar_cobertura.js` (não deve ser commitado: apagar ao final da task), com:

```js
function mesesCobertura(periodo, rec) {
  const primeiro = periodo.de
    ? periodo.de.slice(0, 7)
    : (rec.por_mes[0] ? rec.por_mes[0].mes : null);
  if (!primeiro) return [];
  const hoje = new Date();
  const mesAtual = hoje.getFullYear() + "-" + String(hoje.getMonth() + 1).padStart(2, "0");
  const ultimoFiltro = periodo.ate ? periodo.ate.slice(0, 7) : mesAtual;
  const ultimo = ultimoFiltro < mesAtual ? ultimoFiltro : mesAtual;
  const meses = [];
  let [ano, mes] = primeiro.split("-").map(Number);
  const [anoFim, mesFim] = ultimo.split("-").map(Number);
  while (ano < anoFim || (ano === anoFim && mes <= mesFim)) {
    meses.push(ano + "-" + String(mes).padStart(2, "0"));
    mes++;
    if (mes > 12) { mes = 1; ano++; }
  }
  return meses;
}

function coberturaEmpresa(nome, meses, rec) {
  const porMes = new Map(rec.por_mes.map(m => [m.mes, m]));
  const faltando = meses.filter(ym => !(porMes.get(ym) && porMes.get(ym).por_pagador[nome]));
  const cobertos = meses.length - faltando.length;
  return { pct: meses.length ? Math.round(100 * cobertos / meses.length) : 0, faltando };
}

let falhou = false;
function checar(desc, real, esperado) {
  const ok = JSON.stringify(real) === JSON.stringify(esperado);
  console.log((ok ? "OK: " : "FALHOU: ") + desc +
    (ok ? "" : " -> obtido " + JSON.stringify(real) + ", esperado " + JSON.stringify(esperado)));
  if (!ok) falhou = true;
}

checar("meses no intervalo 2025-06 a 2025-09 (totalmente no passado)",
  mesesCobertura({de: "2025-06-01", ate: "2025-09-15"}, {por_mes: []}),
  ["2025-06", "2025-07", "2025-08", "2025-09"]);

const hoje = new Date();
const mesAtual = hoje.getFullYear() + "-" + String(hoje.getMonth() + 1).padStart(2, "0");
const resultado2 = mesesCobertura({de: "2025-01-01", ate: ""}, {por_mes: []});
checar("ultimo mes cai no mes atual quando 'ate' nao e informado",
  resultado2[resultado2.length - 1], mesAtual);

checar("sem 'de', usa o mes mais antigo de rec.por_mes",
  mesesCobertura({de: "", ate: "2025-03-31"}, {por_mes: [{mes: "2025-01"}, {mes: "2025-02"}]}),
  ["2025-01", "2025-02", "2025-03"]);

checar("sem 'de' e sem por_mes, retorna lista vazia",
  mesesCobertura({de: "", ate: ""}, {por_mes: []}), []);

const recTeste = {por_mes: [
  {mes: "2025-06", por_pagador: {Unimed: {qtd: 2}}},
  {mes: "2025-07", por_pagador: {IDS: {qtd: 1}}},
  {mes: "2025-08", por_pagador: {Unimed: {qtd: 3}}},
]};
checar("cobertura Unimed no intervalo jun-ago/2025 (falta julho)",
  coberturaEmpresa("Unimed", ["2025-06", "2025-07", "2025-08"], recTeste),
  {pct: 67, faltando: ["2025-07"]});

checar("cobertura completa quando todo mes tem evento",
  coberturaEmpresa("IDS", ["2025-07"], recTeste),
  {pct: 100, faltando: []});

console.log(falhou ? "FALHOU" : "OK: todos os casos passaram");
```

Rodar: `node _verificar_cobertura.js`
Esperado (script isolado, sem depender de `painel.html`): `OK: todos os casos passaram`. Se algum caso falhar, ajustar a lógica acima até todos passarem antes de colar as funções em `painel.html` no próximo passo (o script já contém a implementação final pretendida; este passo é a validação empírica dela, no espírito do que foi feito na task de filtro de datas do sub-projeto anterior).

- [ ] **Step 2: Adicionar o container HTML da nova seção**

Em `painel.html`, localizar (por volta da linha 329):

```html
    <div id="sec-documentos-fin"></div>
    <div id="sec-orfaos"></div>
```

Trocar por:

```html
    <div id="sec-cobertura-fin"></div>
    <div id="sec-documentos-fin"></div>
    <div id="sec-orfaos"></div>
```

- [ ] **Step 3: Adicionar o CSS da grade de donuts**

Logo depois da regra `.gb-rotulo` (por volta da linha 154):

```css
  .gb-rotulo { font-size: 11px; color: var(--cor-texto-fraco); }
```

Adicionar logo abaixo:

```css
  .gb-rotulo { font-size: 11px; color: var(--cor-texto-fraco); }

  .cob-grade { display: flex; flex-wrap: wrap; gap: 24px; }
  .cob-item { display: flex; flex-direction: column; align-items: center;
    gap: 6px; width: 140px; text-align: center; }
  .cob-nome { font-weight: 600; }
```

- [ ] **Step 4: Adicionar as funções de cálculo e desenho do donut**

Adicionar as três funções abaixo em `painel.html`, logo antes da função `renderDocumentosFin()` (por volta da linha 1336):

```js
function mesesCobertura(periodo) {
  const primeiro = periodo.de
    ? periodo.de.slice(0, 7)
    : (rec.por_mes[0] ? rec.por_mes[0].mes : null);
  if (!primeiro) return [];
  const hoje = new Date();
  const mesAtual = hoje.getFullYear() + "-" + String(hoje.getMonth() + 1).padStart(2, "0");
  const ultimoFiltro = periodo.ate ? periodo.ate.slice(0, 7) : mesAtual;
  const ultimo = ultimoFiltro < mesAtual ? ultimoFiltro : mesAtual;
  const meses = [];
  let [ano, mes] = primeiro.split("-").map(Number);
  const [anoFim, mesFim] = ultimo.split("-").map(Number);
  while (ano < anoFim || (ano === anoFim && mes <= mesFim)) {
    meses.push(ano + "-" + String(mes).padStart(2, "0"));
    mes++;
    if (mes > 12) { mes = 1; ano++; }
  }
  return meses;
}

function coberturaEmpresa(nome, meses) {
  const porMes = new Map(rec.por_mes.map(m => [m.mes, m]));
  const faltando = meses.filter(ym => !(porMes.get(ym) && porMes.get(ym).por_pagador[nome]));
  const cobertos = meses.length - faltando.length;
  return { pct: meses.length ? Math.round(100 * cobertos / meses.length) : 0, faltando };
}

function svgDonut(pct, cor) {
  const r = 40, c = 2 * Math.PI * r;
  const offset = c * (1 - pct / 100);
  return "<svg width='96' height='96' viewBox='0 0 96 96'>" +
    "<circle cx='48' cy='48' r='" + r + "' fill='none' stroke='var(--cor-borda)' stroke-width='12'/>" +
    "<circle cx='48' cy='48' r='" + r + "' fill='none' stroke='" + cor + "' stroke-width='12' " +
    "stroke-dasharray='" + c.toFixed(2) + "' stroke-dashoffset='" + offset.toFixed(2) + "' " +
    "style='transform:rotate(-90deg);transform-origin:48px 48px'/>" +
    "<text x='48' y='48' text-anchor='middle' dominant-baseline='central' " +
    "font-size='20' font-weight='700' fill='var(--cor-texto)'>" + pct + "%</text></svg>";
}

function renderCobertura() {
  const sec = document.getElementById("sec-cobertura-fin");
  const meses = mesesCobertura(periodoAtivo());
  if (!meses.length) { sec.innerHTML = ""; return; }
  const itens = ["IDS", "Unimed", "CardioPro"].map(nome => {
    const { pct, faltando } = coberturaEmpresa(nome, meses);
    const cor = pct === 100 ? "var(--cor-ok)" : pct === 0 ? "var(--cor-erro)" : "var(--cor-alerta)";
    const nota = faltando.length
      ? "Faltou: " + faltando.map(formatMes).join(", ")
      : "Cobertura completa";
    return "<div class='cob-item'>" + svgDonut(pct, cor) +
      "<div class='cob-nome'>" + esc(nome) + "</div>" +
      "<div class='nota'>" + esc(nota) + "</div></div>";
  }).join("");
  sec.innerHTML = "<section class='bloco'><h2>Cobertura de documentos</h2>" +
    "<p class='nota'>Meses, dentro do período filtrado, com pelo menos um " +
    "pagamento registrado de cada empresa.</p>" +
    "<div class='cob-grade'>" + itens + "</div></section>";
}
```

`formatMes` é definida mais abaixo no arquivo (perto de `PALETA_FORNECEDOR`), mas como é uma `function` declarada (hoisted), a ordem não importa.

- [ ] **Step 5: Chamar `renderCobertura()` a partir de `carregarRecebimentos()`**

Trocar (por volta das linhas 1097-1101):

```js
  renderCardsRecebimentos();
  renderMeses(vistaMes);
  renderPorExame();
  renderSemPagamento();
  renderDocumentosFin();
}
```

Por:

```js
  renderCardsRecebimentos();
  renderMeses(vistaMes);
  renderPorExame();
  renderSemPagamento();
  renderCobertura();
  renderDocumentosFin();
}
```

- [ ] **Step 6: Rodar a suíte de testes Python e apagar o script de verificação**

Rodar: `py -m pytest -q`
Esperado: mesma contagem de testes do baseline (nenhum arquivo Python foi tocado nesta task).

Apagar `_verificar_cobertura.js` (arquivo temporário do Step 1, não deve ser commitado).

- [ ] **Step 7: Commit**

```bash
git add painel.html
git commit -m "painel.html: adiciona cobertura de documentos por empresa (donut)"
```

## Verificação visual (fora das tasks, antes de finalizar o branch)

Nenhuma das duas tasks tem cobertura automatizada de renderização (o projeto não tem teste de UI). Antes de considerar o plano pronto, abrir o painel de verdade num navegador (`py painel.py` e acessar `http://localhost:<porta>`, ou o atalho já configurado) e conferir visualmente:

- O gráfico "Recebido por mês" com vários meses no período filtrado: os rótulos de valor não devem mais esbarrar um no outro.
- Os cards, tabelas e a nova seção "Cobertura de documentos" mostrando números de 4+ dígitos com separador de milhar.
- Os três donuts de cobertura (IDS/Unimed/CardioPro) desenhando corretamente (arco proporcional ao percentual, texto centralizado, sem overflow do SVG).
