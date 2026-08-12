# Filtros, ordenação e exportação Excel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir o seletor fixo "30/60/90/180 dias" por um filtro de data global (De/Até, com atalhos nomeados) que afeta Visão Geral, Exames e Financeiro; adicionar ordenação por coluna e exportação para Excel nas tabelas de Exames, Por exame e Eventos.

**Architecture:** Backend generaliza o filtro de "últimos N dias" (relativo) para um intervalo absoluto `data_de`/`data_ate`, aplicado nos dois endpoints de dados (`/api/dados`, `/api/recebimentos`). Front-end ganha um único controle de período no cabeçalho, um helper de ordenação reutilizado pelas três tabelas, e um endpoint novo (`/api/exportar`, `openpyxl`) que recebe as linhas já filtradas/ordenadas do navegador e devolve um `.xlsx`.

**Tech Stack:** Python stdlib + `openpyxl` (já é dependência do projeto). Sem biblioteca JS nova.

## Global Constraints

- Sem dependências novas: nenhuma lib JS nova; `openpyxl` já está em `requirements.txt`.
- O filtro de data é global (não por aba): Visão Geral, Exames e Financeiro (cartões, gráfico, Por exame, Eventos, Sem pagamento) respeitam o mesmo intervalo.
- `data_de` inclui o dia inteiro a partir de `00:00:00`; `data_ate` inclui o dia inteiro até `23:59:59` (evita excluir mensagens do último dia por causa do horário).
- Eventos financeiros sem data conhecida (`data: None`) nunca são excluídos pelo filtro de data (não dá pra julgar).
- Exportação sempre inclui todas as linhas que batem com os filtros ativos da tabela, não só as visíveis na tela (sem o corte de exibição usado só por performance de renderização).
- Testes não fazem chamada de rede real; seguem o padrão `pytest` + `monkeypatch` já usado no projeto.
- Design de referência: `docs/superpowers/specs/2026-08-12-filtros-ordenacao-exportacao-design.md`.

---

### Task 1: `rotina_pendencias.analisar` passa a aceitar intervalo de datas

**Files:**
- Modify: `rotina_pendencias.py`
- Modify: `tests/test_rotina_pendencias.py`

**Interfaces:**
- Produces: `analisar(cache: dict, data_de: str | None = None, data_ate: str | None = None) -> dict`. O retorno ganha as chaves `"data_de"` e `"data_ate"` (ecoando o que foi recebido) no lugar da antiga chave `"dias"`.
- Consumes (inalterado): `cache_email.mensagens(cache, pasta)`.

- [ ] **Step 1: Atualizar os testes existentes para a nova assinatura (devem falhar: assinatura antiga)**

Em `tests/test_rotina_pendencias.py`, trocar as 4 chamadas `rp.analisar(cache, dias=30)` (em `test_exame_sem_laudo_e_pendente`, `test_exame_com_laudo_enviado_e_retornado`, `test_baixa_manual_remove_de_pendentes`, `test_buracos_de_numeracao_prefixo_dedicado`) por `rp.analisar(cache)`, sem filtro: deve continuar incluindo essas mensagens (todas recebidas há poucos dias).

Substituir a função `test_dias_filtra_exames_e_enviados_fora_da_janela` inteira por três testes novos:

```python
def test_filtro_de_data_exclui_exames_e_enviados_fora_do_intervalo(monkeypatch):
    monkeypatch.setattr(rp, "carregar_baixas", lambda: {})
    cache = _cache_com_mensagens(
        inbox={"m1": {"assunto": "Exame", "de": "contato@ids.med.br",
                      "recebido": _iso(40), "conversa": "c1",
                      "anexos": ["ED9-00159 MARIA SILVA.dmw"], "corpo_texto": ""}},
        sentitems={"s1": {"assunto": "RE: Exame", "recebido": _iso(35),
                          "conversa": "c1", "anexos": ["ED9-00159.pdf"]}},
    )
    data_de = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    dados = rp.analisar(cache, data_de=data_de)
    assert dados["contagens"]["recebidos"] == 0
    assert dados["pendentes"] == [] and dados["retornados"] == []


def test_filtro_data_ate_inclui_o_dia_inteiro(monkeypatch):
    monkeypatch.setattr(rp, "carregar_baixas", lambda: {})
    hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cache = _cache_com_mensagens(inbox={
        "m1": {"assunto": "Exame", "de": "contato@ids.med.br",
               "recebido": hoje + "T23:00:00Z", "conversa": "c1",
               "anexos": ["ED9-00159 MARIA SILVA.dmw"], "corpo_texto": ""},
    })
    dados = rp.analisar(cache, data_ate=hoje)
    assert dados["contagens"]["recebidos"] == 1


def test_retorna_data_de_e_data_ate_no_resultado(monkeypatch):
    monkeypatch.setattr(rp, "carregar_baixas", lambda: {})
    cache = _cache_com_mensagens()
    dados = rp.analisar(cache, data_de="2026-01-01", data_ate="2026-12-31")
    assert dados["data_de"] == "2026-01-01"
    assert dados["data_ate"] == "2026-12-31"
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `pytest tests/test_rotina_pendencias.py -v`
Expected: FAIL com `TypeError: analisar() got an unexpected keyword argument 'dias'` nos testes ainda não atualizados, ou `KeyError: 'data_de'`/asserções de contagem erradas nos novos, já que a implementação ainda usa `dias`.

- [ ] **Step 3: Reescrever `analisar()` em `rotina_pendencias.py`**

Substituir a assinatura e a montagem do corte de data (do início da função até o comentário `# ---- conciliacao ----`, ou seja, as seções "recebidos" e "enviados"):

```python
def analisar(cache, data_de=None, data_ate=None):
    """Roda a conciliacao sobre as mensagens ja sincronizadas no cache
    local (cache_email.py). Nao faz nenhuma chamada de rede.

    data_de/data_ate: intervalo absoluto ('AAAA-MM-DD', cada ponta
    opcional). Sem nenhum dos dois, considera todo o cache. data_de cobre
    o dia inteiro a partir de 00:00; data_ate cobre o dia inteiro ate
    23:59:59 (senao mensagens do ultimo dia recebidas a tarde ficariam de
    fora)."""
    agora = datetime.now(timezone.utc)
    cutoff_de = f"{data_de}T00:00:00Z" if data_de else None
    cutoff_ate = f"{data_ate}T23:59:59Z" if data_ate else None

    # ---- recebidos: exames (.dmw) ----
    exames = {}
    for pasta in PASTAS_RECEBIDOS:
        for m in cache_email.mensagens(cache, pasta).values():
            if cutoff_de and m["recebido"] < cutoff_de:
                continue
            if cutoff_ate and m["recebido"] > cutoff_ate:
                continue
            achados = codigos_de_anexos(m["anexos"], (".DMW",))
            if not achados:
                continue
            # nomes de anexos entram no texto: fotos tipo
            # "HELENA MARIA - CCQ-11504.png" carregam nome + codigo
            texto = texto_plano(m) + " | " + " | ".join(m["anexos"])
            prazo_msg = extrair_prazo(texto, m["recebido"])
            for codigo, nome_arq in achados:
                # nome pode estar no proprio arquivo: "0RC-04973 FULANA.dmw"
                sobra = re.sub(r"(?i)\.dmw$", "", nome_arq)
                sobra = re.sub(RE_CODIGO, "", sobra).strip(" -_")
                nome = limpar_nome(sobra) if len(sobra.split()) >= 2 else None
                if not nome:
                    nome = limpar_nome(nome_no_texto(texto, codigo))
                if not nome:
                    nome = limpar_nome(nome_antes_do_codigo(texto, codigo))
                if not nome and len(achados) == 1:
                    nome = limpar_nome(nome_avulso(texto))
                atual = exames.get(codigo)
                if atual is None or m["recebido"] < atual["recebido"]:
                    rem = (m.get("de") or "?").lower()
                    exames[codigo] = {
                        "codigo": codigo,
                        "nome": nome or (atual or {}).get("nome"),
                        "fonte": rem,
                        "recebido": m["recebido"],
                        "conversa": m.get("conversa"),
                        "pasta": pasta,
                        "prazo": prazo_msg or (atual or {}).get("prazo"),
                        "empresa": empresa_de(rem, codigo),
                    }
                elif nome and not atual.get("nome"):
                    atual["nome"] = nome

    # ---- enviados: laudos (.pdf) e conversas respondidas ----
    enviados = [m for m in cache_email.mensagens(cache, "sentitems").values()
                if (not cutoff_de or m["recebido"] >= cutoff_de)
                and (not cutoff_ate or m["recebido"] <= cutoff_ate)]
    codigos_enviados = {}
    conversas_respondidas = defaultdict(list)
    for m in enviados:
        if m.get("conversa"):
            conversas_respondidas[m["conversa"]].append(m["recebido"])
        for codigo, _ in codigos_de_anexos(m["anexos"], (".PDF",)):
            d = codigos_enviados.get(codigo)
            if d is None or m["recebido"] > d:
                codigos_enviados[codigo] = m["recebido"]
```

(O resto do corpo da função, da linha `# ---- conciliacao ----` até o `return {...}`, não muda: só a montagem de `exames`/`enviados` acima dele mudou.)

Substituir o `return` final:

```python
    return {
        "gerado_em": agora.astimezone().strftime("%d/%m/%Y %H:%M"),
        "data_de": data_de,
        "data_ate": data_ate,
        "contagens": {
            "recebidos": len(exames),
            "retornados": len(retornados),
            "pendentes": len(pendentes),
            "atrasados": sum(1 for e in pendentes if e["atrasado"]),
            "provaveis": len(provaveis),
            "avisos": len(avisos),
            "baixados": len(baixados),
        },
        "pendentes": pendentes,
        "provaveis": provaveis,
        "avisos": avisos,
        "baixados": baixados,
        "retornados": retornados,
        "status": {"ultimo": ultimo, "fontes": fontes, "empresas": empresas},
        "buracos": sorted(buracos),
    }
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `pytest tests/test_rotina_pendencias.py -v`
Expected: PASS (7 testes: 4 ajustados + 3 novos)

- [ ] **Step 5: Atualizar `relatorio_texto()` para o novo formato de período**

Adicionar, antes de `relatorio_texto` (logo após `_fmt_hora`):

```python
def _fmt_data_br(iso_data):
    p = iso_data.split("-")
    return f"{p[2]}/{p[1]}/{p[0]}"


def _periodo_texto(data_de, data_ate):
    if not data_de and not data_ate:
        return "todo o periodo"
    if data_de and data_ate:
        return f"{_fmt_data_br(data_de)} a {_fmt_data_br(data_ate)}"
    if data_de:
        return f"a partir de {_fmt_data_br(data_de)}"
    return f"ate {_fmt_data_br(data_ate)}"
```

Em `relatorio_texto`, substituir:

```python
    w(f"CONCILIACAO DE EXAMES MAPA - ultimos {dados['dias']} dias "
      f"({dados['gerado_em']})")
```

por:

```python
    w(f"CONCILIACAO DE EXAMES MAPA - "
      f"{_periodo_texto(dados['data_de'], dados['data_ate'])} "
      f"({dados['gerado_em']})")
```

- [ ] **Step 6: Atualizar `main()` (CLI) para o novo parâmetro**

Substituir:

```python
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=30)
    ap.add_argument("--listar-retornados", action="store_true")
    ap.add_argument("--salvar-historico", action="store_true",
                    help="salva copia datada em relatorios\\")
    args = ap.parse_args()

    cache = cache_email.carregar_cache()
    while True:
        progresso = cache_email.sincronizar_um_passo(
            outlook_auth.get_access_token(), cache)
        if not progresso:
            break
        print(f"Sincronizando: {progresso['pasta']} {progresso['mes']}...")

    dados = analisar(cache, args.dias)
    relatorio = relatorio_texto(dados, args.listar_retornados)
```

por:

```python
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=None,
                    help="considera so os ultimos N dias (padrao: tudo)")
    ap.add_argument("--listar-retornados", action="store_true")
    ap.add_argument("--salvar-historico", action="store_true",
                    help="salva copia datada em relatorios\\")
    args = ap.parse_args()

    cache = cache_email.carregar_cache()
    while True:
        progresso = cache_email.sincronizar_um_passo(
            outlook_auth.get_access_token(), cache)
        if not progresso:
            break
        print(f"Sincronizando: {progresso['pasta']} {progresso['mes']}...")

    data_de = None
    if args.dias is not None:
        data_de = (datetime.now(timezone.utc) -
                   timedelta(days=args.dias)).strftime("%Y-%m-%d")
    dados = analisar(cache, data_de)
    relatorio = relatorio_texto(dados, args.listar_retornados)
```

Também atualizar a linha `Uso:` no docstring do módulo (topo do arquivo):

```
Uso:  py rotina_pendencias.py [--dias N] [--listar-retornados] [--salvar-historico]
      (--dias omitido considera todo o historico do cache)
```

- [ ] **Step 7: Rodar toda a suíte e confirmar que nada quebrou**

Run: `pytest -q`
Expected: PASS em todos os testes (87 pré-existentes, com os 4 ajustados e 3 novos de `test_rotina_pendencias.py` substituindo os 5 antigos: 87 - 5 + 7 = 89 no total)

- [ ] **Step 8: Commit**

```bash
git add rotina_pendencias.py tests/test_rotina_pendencias.py
git commit -m "rotina_pendencias.analisar aceita intervalo de datas em vez de dias relativos"
```

---

### Task 2: `eventos.recebimentos` ganha filtro de data

**Files:**
- Modify: `eventos.py`
- Modify: `tests/test_eventos.py`

**Interfaces:**
- Produces: `recebimentos(pastas: tuple | None = None, data_de: str | None = None, data_ate: str | None = None) -> dict` (mesmo formato de retorno de antes).
- Produces (privada): `_dentro_do_periodo(data: str | None, data_de: str | None, data_ate: str | None) -> bool`.

- [ ] **Step 1: Escrever o teste de filtro (deve falhar: parâmetros não existem)**

Adicionar a `tests/test_eventos.py`, próximo de `test_agregacoes`:

```python
def test_recebimentos_filtra_por_data_de_ate(monkeypatch):
    evs = [
        _ev(paciente="Ana", data="2026-01-10"),
        _ev(paciente="Bia", data="2026-03-15"),
        _ev(paciente="Carla", data=None),
    ]
    monkeypatch.setattr(ev, "coletar_eventos", lambda pastas=None: evs)
    monkeypatch.setattr(ev, "_exames_realizados", lambda pastas=None: [])
    import ler_repasses as lr
    monkeypatch.setattr(lr, "financeiro", lambda pastas=None: {"empresas": {}})
    r = ev.recebimentos(data_de="2026-02-01", data_ate="2026-04-01")
    pacientes = {e["paciente"] for e in r["eventos"]}
    assert pacientes == {"Bia", "Carla"}


def test_recebimentos_sem_filtro_mantem_comportamento_atual(monkeypatch):
    evs = [_ev(paciente="Ana", data="2020-01-01"), _ev(paciente="Bia", data="2030-01-01")]
    monkeypatch.setattr(ev, "coletar_eventos", lambda pastas=None: evs)
    monkeypatch.setattr(ev, "_exames_realizados", lambda pastas=None: [])
    import ler_repasses as lr
    monkeypatch.setattr(lr, "financeiro", lambda pastas=None: {"empresas": {}})
    r = ev.recebimentos()
    assert {e["paciente"] for e in r["eventos"]} == {"Ana", "Bia"}
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `pytest tests/test_eventos.py -v -k recebimentos_filtra`
Expected: FAIL com `TypeError: recebimentos() got an unexpected keyword argument 'data_de'`

- [ ] **Step 3: Adicionar o filtro em `eventos.py`**

Adicionar, logo antes de `def recebimentos(...)`:

```python
def _dentro_do_periodo(data, data_de, data_ate):
    """True se `data` (AAAA-MM-DD ou None) esta dentro do intervalo. Uma
    data desconhecida (None) nunca e excluida pelo filtro."""
    if not data:
        return True
    if data_de and data < data_de:
        return False
    if data_ate and data > data_ate:
        return False
    return True
```

Alterar a assinatura e o início de `recebimentos`:

```python
def recebimentos(pastas=None, data_de=None, data_ate=None):
    """Estrutura completa pro GET /api/recebimentos.

    data_de/data_ate: intervalo absoluto ('AAAA-MM-DD', cada ponta
    opcional), aplicado antes de qualquer agregacao."""
    from datetime import datetime as _dt
    import ler_repasses as lr
    evs = coletar_eventos(pastas)
    evs = [e for e in evs if _dentro_do_periodo(e["data"], data_de, data_ate)]
```

(o resto do corpo de `recebimentos` que usa `evs` continua igual, já que agora opera sobre a lista filtrada).

Na seção "sem pagamento", substituir:

```python
    sem_pagamento = []
    for ex in _exames_realizados(pastas):
```

por:

```python
    sem_pagamento = []
    realizados = [ex for ex in _exames_realizados(pastas)
                  if _dentro_do_periodo(ex["data"], data_de, data_ate)]
    for ex in realizados:
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `pytest tests/test_eventos.py -v`
Expected: PASS em todos os testes de `test_eventos.py` (os pré-existentes continuam passando sem alteração, já que chamam `recebimentos()` sem argumentos de data, que tem o mesmo efeito de antes)

- [ ] **Step 5: Rodar toda a suíte**

Run: `pytest -q`
Expected: PASS em todos

- [ ] **Step 6: Commit**

```bash
git add eventos.py tests/test_eventos.py
git commit -m "eventos.recebimentos aceita filtro de intervalo de datas"
```

---

### Task 3: Módulo novo `exportar_excel.py`

**Files:**
- Create: `exportar_excel.py`
- Create: `tests/test_exportar_excel.py`

**Interfaces:**
- Produces: `gerar(payload: dict) -> tuple[bytes, str]`. `payload` tem o formato `{"titulo": str, "colunas": [{"chave": str, "rotulo": str, "tipo": "texto"|"numero"|"data"}], "linhas": [dict]}`. Devolve `(conteudo_xlsx, nome_do_arquivo)`.

- [ ] **Step 1: Escrever os testes (devem falhar: módulo não existe)**

Criar `tests/test_exportar_excel.py`:

```python
import io
from datetime import datetime

import openpyxl

import exportar_excel as ee


def test_gerar_cria_cabecalho_e_linhas():
    payload = {
        "titulo": "Exames",
        "colunas": [
            {"chave": "codigo", "rotulo": "Código", "tipo": "texto"},
            {"chave": "qtd", "rotulo": "Qtd", "tipo": "numero"},
        ],
        "linhas": [
            {"codigo": "ED9-00159", "qtd": 3},
            {"codigo": "0RC-00042", "qtd": 1},
        ],
    }
    conteudo, nome_arquivo = ee.gerar(payload)
    assert nome_arquivo.startswith("Exames_")
    assert nome_arquivo.endswith(".xlsx")

    wb = openpyxl.load_workbook(io.BytesIO(conteudo))
    ws = wb.active
    assert [c.value for c in ws[1]] == ["Código", "Qtd"]
    assert [c.value for c in ws[2]] == ["ED9-00159", 3]
    assert [c.value for c in ws[3]] == ["0RC-00042", 1]


def test_gerar_coluna_numero_vira_float_de_verdade():
    payload = {
        "titulo": "Por exame",
        "colunas": [{"chave": "valor", "rotulo": "Valor", "tipo": "numero"}],
        "linhas": [{"valor": "123.45"}],
    }
    conteudo, _ = ee.gerar(payload)
    wb = openpyxl.load_workbook(io.BytesIO(conteudo))
    valor = wb.active.cell(row=2, column=1).value
    assert valor == 123.45
    assert isinstance(valor, float)


def test_gerar_coluna_data_vira_data_de_verdade():
    payload = {
        "titulo": "Eventos",
        "colunas": [{"chave": "recebido", "rotulo": "Recebido", "tipo": "data"}],
        "linhas": [{"recebido": "2026-08-01T10:00:00Z"}],
    }
    conteudo, _ = ee.gerar(payload)
    wb = openpyxl.load_workbook(io.BytesIO(conteudo))
    celula = wb.active.cell(row=2, column=1)
    assert celula.value == datetime(2026, 8, 1, 10, 0, 0)
    assert celula.number_format == "DD/MM/YYYY"


def test_gerar_valor_ausente_vira_celula_vazia():
    payload = {
        "titulo": "Exames",
        "colunas": [{"chave": "prazo", "rotulo": "Prazo", "tipo": "data"}],
        "linhas": [{"prazo": None}],
    }
    conteudo, _ = ee.gerar(payload)
    wb = openpyxl.load_workbook(io.BytesIO(conteudo))
    assert wb.active.cell(row=2, column=1).value is None


def test_nome_arquivo_sanitiza_titulo_com_espacos():
    payload = {"titulo": "Por exame", "colunas": [], "linhas": []}
    _, nome_arquivo = ee.gerar(payload)
    assert nome_arquivo.startswith("Por_exame_")
    assert " " not in nome_arquivo
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `pytest tests/test_exportar_excel.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'exportar_excel'`

- [ ] **Step 3: Criar `exportar_excel.py`**

```python
# -*- coding: utf-8 -*-
"""Gera arquivos .xlsx a partir de colunas/linhas ja filtradas e
ordenadas pelo front-end, para o endpoint POST /api/exportar."""

import io
import re
from datetime import datetime

import openpyxl
from openpyxl.styles import Font

_RE_INVALIDO_NOME_ARQUIVO = re.compile(r"[^A-Za-z0-9_\-]+")
_RE_INVALIDO_TITULO_ABA = re.compile(r'[\[\]:*?/\\]')


def _nome_arquivo(titulo):
    limpo = _RE_INVALIDO_NOME_ARQUIVO.sub("_", titulo or "planilha").strip("_")
    hoje = datetime.now().strftime("%Y-%m-%d")
    return f"{limpo or 'planilha'}_{hoje}.xlsx"


def _valor_celula(bruto, tipo):
    if bruto is None:
        return None
    if tipo == "numero":
        try:
            return float(bruto)
        except (TypeError, ValueError):
            return None
    if tipo == "data":
        try:
            return datetime.fromisoformat(
                str(bruto).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return str(bruto)
    return str(bruto)


def gerar(payload):
    """(bytes_do_xlsx, nome_do_arquivo) a partir de
    {"titulo": str, "colunas": [{"chave", "rotulo", "tipo"}], "linhas": [dict]}."""
    titulo = payload.get("titulo") or "Planilha"
    colunas = payload.get("colunas") or []
    linhas = payload.get("linhas") or []

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = (_RE_INVALIDO_TITULO_ABA.sub("_", titulo) or "Planilha")[:31]

    for j, col in enumerate(colunas, start=1):
        celula = ws.cell(row=1, column=j, value=col.get("rotulo", ""))
        celula.font = Font(bold=True)

    for i, linha in enumerate(linhas, start=2):
        for j, col in enumerate(colunas, start=1):
            valor = _valor_celula(linha.get(col.get("chave")),
                                  col.get("tipo", "texto"))
            celula = ws.cell(row=i, column=j, value=valor)
            if col.get("tipo") == "data" and isinstance(valor, datetime):
                celula.number_format = "DD/MM/YYYY"

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue(), _nome_arquivo(titulo)
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `pytest tests/test_exportar_excel.py -v`
Expected: PASS (5 testes)

- [ ] **Step 5: Commit**

```bash
git add exportar_excel.py tests/test_exportar_excel.py
git commit -m "Adiciona modulo de geracao de planilhas Excel para exportacao"
```

---

### Task 4: Filtro de data nos endpoints existentes e endpoint de exportação (`painel.py`)

**Files:**
- Modify: `painel.py`
- Modify: `tests/test_painel_api.py`

**Interfaces:**
- Consumes: `rotina_pendencias.analisar(cache, data_de, data_ate)` (Task 1), `eventos.recebimentos(pastas=None, data_de=None, data_ate=None)` (Task 2), `exportar_excel.gerar(payload)` (Task 3).
- Produces: `GET /api/dados?de=&ate=`, `GET /api/recebimentos?de=&ate=`, `POST /api/exportar` (recebe o JSON de `exportar_excel.gerar`, devolve o `.xlsx`).

- [ ] **Step 1: Atualizar `/api/dados` para `de`/`ate`**

Substituir:

```python
            elif rota.path == "/api/dados":
                dias = int(parse_qs(rota.query).get("dias", ["30"])[0])
                dias = max(1, min(dias, 365))
                try:
                    token = outlook_auth.get_access_token("silencioso")
                except outlook_auth.AuthExpirada as e:
                    self._json({"precisa_login": True, "mensagem": str(e)})
                    return
                with TRAVA:
                    cache = cache_email.carregar_cache()
                    progresso = cache_email.sincronizar_um_passo(token, cache)
                    if progresso:
                        self._json({"sincronizando": progresso})
                        return
                    try:
                        import baixar_repasses
                        baixar_repasses.varrer(token)
                    except Exception:
                        pass  # sem repasses novos nao pode travar o painel
                    dados = rotina_pendencias.analisar(cache, dias)
                try:
                    import cruzar_pagamentos
                    dados["pagamentos_orfaos"] = (
                        cruzar_pagamentos.anotar_pagamentos(dados))
                except Exception:
                    dados["pagamentos_orfaos"] = []
                salvar_historico(dados)
                self._json(dados)

            elif rota.path == "/api/recebimentos":
                import eventos
                self._json(eventos.recebimentos())
```

por:

```python
            elif rota.path == "/api/dados":
                qs = parse_qs(rota.query)
                data_de = qs.get("de", [""])[0] or None
                data_ate = qs.get("ate", [""])[0] or None
                try:
                    token = outlook_auth.get_access_token("silencioso")
                except outlook_auth.AuthExpirada as e:
                    self._json({"precisa_login": True, "mensagem": str(e)})
                    return
                with TRAVA:
                    cache = cache_email.carregar_cache()
                    progresso = cache_email.sincronizar_um_passo(token, cache)
                    if progresso:
                        self._json({"sincronizando": progresso})
                        return
                    try:
                        import baixar_repasses
                        baixar_repasses.varrer(token)
                    except Exception:
                        pass  # sem repasses novos nao pode travar o painel
                    dados = rotina_pendencias.analisar(cache, data_de, data_ate)
                try:
                    import cruzar_pagamentos
                    dados["pagamentos_orfaos"] = (
                        cruzar_pagamentos.anotar_pagamentos(dados))
                except Exception:
                    dados["pagamentos_orfaos"] = []
                salvar_historico(dados)
                self._json(dados)

            elif rota.path == "/api/recebimentos":
                qs = parse_qs(rota.query)
                data_de = qs.get("de", [""])[0] or None
                data_ate = qs.get("ate", [""])[0] or None
                import eventos
                self._json(eventos.recebimentos(data_de=data_de, data_ate=data_ate))
```

- [ ] **Step 2: Adicionar o endpoint `POST /api/exportar`**

Em `do_POST`, substituir:

```python
            elif rota.path == "/api/baixa":
                tam = int(self.headers.get("Content-Length", "0"))
                corpo = json.loads(self.rfile.read(tam).decode("utf-8"))
                cod = rotina_pendencias.registrar_baixa(
                    corpo.get("codigo", ""), corpo.get("motivo", ""))
                self._json({"ok": True, "codigo": cod})
            else:
                self._json({"erro": "rota desconhecida"}, 404)
```

por:

```python
            elif rota.path == "/api/baixa":
                tam = int(self.headers.get("Content-Length", "0"))
                corpo = json.loads(self.rfile.read(tam).decode("utf-8"))
                cod = rotina_pendencias.registrar_baixa(
                    corpo.get("codigo", ""), corpo.get("motivo", ""))
                self._json({"ok": True, "codigo": cod})
            elif rota.path == "/api/exportar":
                tam = int(self.headers.get("Content-Length", "0"))
                corpo = json.loads(self.rfile.read(tam).decode("utf-8"))
                import exportar_excel
                conteudo, nome_arquivo = exportar_excel.gerar(corpo)
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet")
                self.send_header(
                    "Content-Disposition",
                    f'attachment; filename="{nome_arquivo}"')
                self.send_header("Content-Length", str(len(conteudo)))
                self.end_headers()
                self.wfile.write(conteudo)
            else:
                self._json({"erro": "rota desconhecida"}, 404)
```

- [ ] **Step 3: Escrever os testes HTTP (devem falhar: rotas ainda não aceitam os novos parâmetros/não existem)**

Adicionar a `tests/test_painel_api.py`:

```python
def test_api_recebimentos_aceita_filtro_de_data():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), painel.Handler)
    porta = servidor.server_address[1]
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{porta}/api/recebimentos"
                "?de=2026-01-01&ate=2026-12-31", timeout=30) as resp:
            dados = json.loads(resp.read())
        assert set(dados.keys()) == {"totais", "por_mes", "por_exame",
                                     "eventos", "sem_pagamento", "cobertura",
                                     "documentos"}
    finally:
        servidor.shutdown()
        thread.join(timeout=5)


def test_api_exportar_devolve_xlsx():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), painel.Handler)
    porta = servidor.server_address[1]
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    try:
        payload = json.dumps({
            "titulo": "Exames",
            "colunas": [{"chave": "codigo", "rotulo": "Código", "tipo": "texto"}],
            "linhas": [{"codigo": "ED9-00159"}],
        }).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{porta}/api/exportar", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            assert resp.headers["Content-Type"] == (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet")
            assert "Exames_" in resp.headers["Content-Disposition"]
            conteudo = resp.read()
        import io as _io
        import openpyxl as _openpyxl
        wb = _openpyxl.load_workbook(_io.BytesIO(conteudo))
        assert wb.active.cell(row=1, column=1).value == "Código"
    finally:
        servidor.shutdown()
        thread.join(timeout=5)
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `pytest tests/test_painel_api.py -v`
Expected: PASS em todos (os pré-existentes continuam passando; os 2 novos passam)

- [ ] **Step 5: Rodar toda a suíte**

Run: `pytest -q`
Expected: PASS em todos

- [ ] **Step 6: Commit**

```bash
git add painel.py tests/test_painel_api.py
git commit -m "painel.py: filtro de data em /api/dados e /api/recebimentos, novo endpoint /api/exportar"
```

---

### Task 5: Controle de período global (`painel.html`)

**Files:**
- Modify: `painel.html`

**Interfaces:**
- Consumes: `GET /api/dados?de=&ate=`, `GET /api/recebimentos?de=&ate=` (Task 4). Campos `dados.data_de`/`dados.data_ate` no lugar de `dados.dias`.
- Produces: `periodoAtivo() -> {de: string, ate: string}`, usada só dentro desta task (`carregar()`/`carregarRecebimentos()`). A exportação (Task 7) não recalcula período: reaproveita `dados`/`rec`, que já chegam filtrados pelo período ativo.

- [ ] **Step 1: Substituir o seletor de período no cabeçalho**

Substituir:

```html
  <label style="color:#fff">Período
    <select id="dias">
      <option value="30" selected>30 dias</option>
      <option value="60">60 dias</option>
      <option value="90">90 dias</option>
      <option value="180">180 dias</option>
    </select>
  </label>
```

por:

```html
  <label style="color:#fff">Período
    <select id="periodo-preset" onchange="mudouPresetPeriodo()">
      <option value="7">Últimos 7 dias</option>
      <option value="30">Últimos 30 dias</option>
      <option value="90" selected>Últimos 90 dias</option>
      <option value="3m">Últimos 3 meses</option>
      <option value="mes-atual">Este mês</option>
      <option value="mes-passado">Mês passado</option>
      <option value="ano-atual">Este ano</option>
      <option value="ano-passado">Ano passado</option>
      <option value="tudo">Tudo</option>
      <option value="personalizado">Personalizado…</option>
    </select>
  </label>
  <span id="periodo-personalizado" class="oculto">
    <input type="date" id="periodo-de"> a
    <input type="date" id="periodo-ate">
  </span>
```

- [ ] **Step 2: Adicionar as funções de cálculo de período**

No `<script>`, logo após a declaração `let dados = null;`, adicionar:

```javascript
function calcularPeriodo(preset) {
  const hoje = new Date();
  const iso = d => d.toISOString().slice(0, 10);
  const diasAtras = n => { const d = new Date(hoje); d.setDate(d.getDate() - n); return iso(d); };
  if (preset === "7") return {de: diasAtras(7), ate: iso(hoje)};
  if (preset === "30") return {de: diasAtras(30), ate: iso(hoje)};
  if (preset === "90") return {de: diasAtras(90), ate: iso(hoje)};
  if (preset === "3m") {
    const d = new Date(hoje); d.setMonth(d.getMonth() - 3);
    return {de: iso(d), ate: iso(hoje)};
  }
  if (preset === "mes-atual") {
    return {de: iso(new Date(hoje.getFullYear(), hoje.getMonth(), 1)), ate: iso(hoje)};
  }
  if (preset === "mes-passado") {
    const primeiro = new Date(hoje.getFullYear(), hoje.getMonth() - 1, 1);
    const ultimo = new Date(hoje.getFullYear(), hoje.getMonth(), 0);
    return {de: iso(primeiro), ate: iso(ultimo)};
  }
  if (preset === "ano-atual") {
    return {de: iso(new Date(hoje.getFullYear(), 0, 1)), ate: iso(hoje)};
  }
  if (preset === "ano-passado") {
    return {de: iso(new Date(hoje.getFullYear() - 1, 0, 1)),
            ate: iso(new Date(hoje.getFullYear() - 1, 11, 31))};
  }
  if (preset === "tudo") return {de: "", ate: ""};
  return null;  // "personalizado": usa os campos de data diretamente
}

function periodoAtivo() {
  const preset = document.getElementById("periodo-preset").value;
  if (preset === "personalizado") {
    return {
      de: document.getElementById("periodo-de").value,
      ate: document.getElementById("periodo-ate").value,
    };
  }
  return calcularPeriodo(preset);
}

function mudouPresetPeriodo() {
  const preset = document.getElementById("periodo-preset").value;
  document.getElementById("periodo-personalizado")
    .classList.toggle("oculto", preset !== "personalizado");
  if (preset !== "personalizado") {
    carregar();
  }
}

function formatarPeriodoAtivo(dataDe, dataAte) {
  if (!dataDe && !dataAte) return "Todo o período";
  if (dataDe && dataAte) return dataBrAno(dataDe) + " a " + dataBrAno(dataAte);
  if (dataDe) return "A partir de " + dataBrAno(dataDe);
  return "Até " + dataBrAno(dataAte);
}
```

- [ ] **Step 3: Ligar os campos de data personalizados ao recarregamento**

Depois do bloco existente:

```javascript
for (const id of ["f-busca", "f-empresa", "f-status", "f-pag"]) {
  document.getElementById(id).addEventListener("input", renderExames);
}
```

adicionar:

```javascript
for (const id of ["periodo-de", "periodo-ate"]) {
  document.getElementById(id).addEventListener("change", carregar);
}
```

- [ ] **Step 4: Atualizar `carregar()` e `carregarRecebimentos()` para usar `periodoAtivo()`**

Substituir:

```javascript
async function carregar() {
  const btn = document.getElementById("btn-atualizar");
  const btnDocs = document.getElementById("btn-atualizar-docs");
  btn.disabled = true;
  btnDocs.disabled = true;
  mostrar("carregando");
  document.getElementById("carregando-status").innerHTML = "&nbsp;";
  try {
    const dias = document.getElementById("dias").value;
    let d;
    while (true) {
      const r = await fetch("/api/dados?dias=" + dias);
      d = await r.json();
      if (d.precisa_login) { await telaLogin(); return; }
      if (d.erro) throw new Error(d.erro);
      if (!d.sincronizando) break;
      document.getElementById("carregando-status").textContent =
        "Lendo histórico: " + formatMes(d.sincronizando.mes) +
        " (" + d.sincronizando.pasta + ")…";
    }
    dados = d;
    render();
    carregarRecebimentos();
    carregarImportacoes();
    mostrar("conteudo");
  } catch (e) {
```

por:

```javascript
async function carregar() {
  const btn = document.getElementById("btn-atualizar");
  const btnDocs = document.getElementById("btn-atualizar-docs");
  btn.disabled = true;
  btnDocs.disabled = true;
  mostrar("carregando");
  document.getElementById("carregando-status").innerHTML = "&nbsp;";
  try {
    const periodo = periodoAtivo();
    const qs = new URLSearchParams();
    if (periodo.de) qs.set("de", periodo.de);
    if (periodo.ate) qs.set("ate", periodo.ate);
    let d;
    while (true) {
      const r = await fetch("/api/dados?" + qs.toString());
      d = await r.json();
      if (d.precisa_login) { await telaLogin(); return; }
      if (d.erro) throw new Error(d.erro);
      if (!d.sincronizando) break;
      document.getElementById("carregando-status").textContent =
        "Lendo histórico: " + formatMes(d.sincronizando.mes) +
        " (" + d.sincronizando.pasta + ")…";
    }
    dados = d;
    render();
    carregarRecebimentos();
    carregarImportacoes();
    mostrar("conteudo");
  } catch (e) {
```

Substituir o início de `carregarRecebimentos()`:

```javascript
async function carregarRecebimentos() {
  try {
    rec = await (await fetch("/api/recebimentos")).json();
  } catch (e) {
```

por:

```javascript
async function carregarRecebimentos() {
  try {
    const periodo = periodoAtivo();
    const qs = new URLSearchParams();
    if (periodo.de) qs.set("de", periodo.de);
    if (periodo.ate) qs.set("ate", periodo.ate);
    rec = await (await fetch("/api/recebimentos?" + qs.toString())).json();
  } catch (e) {
```

- [ ] **Step 5: Atualizar o subtítulo em `render()`**

Substituir:

```javascript
  document.getElementById("subtitulo").textContent =
    "Últimos " + dados.dias + " dias · atualizado em " + dados.gerado_em +
    " · email ativo ✓";
```

por:

```javascript
  document.getElementById("subtitulo").textContent =
    formatarPeriodoAtivo(dados.data_de, dados.data_ate) +
    " · atualizado em " + dados.gerado_em + " · email ativo ✓";
```

- [ ] **Step 6: Verificar bem-formação e rodar a suíte Python**

Não há teste automatizado de JavaScript neste projeto. Confirmar visualmente que o HTML/JS editado está bem-formado (tags/chaves/aspas balanceadas) e rodar:

Run: `pytest -q`
Expected: PASS em todos (este passo não toca nenhum arquivo `.py`, então a contagem de testes não muda)

- [ ] **Step 7: Commit**

```bash
git add painel.html
git commit -m "painel.html: substitui seletor de periodo fixo por filtro de data global"
```

---

### Task 6: Ordenação por coluna nas tabelas de Exames, Por exame e Eventos

**Files:**
- Modify: `painel.html`

**Interfaces:**
- Produces: `ordenarLista(lista, campo, direcao, tipo) -> array`, `alternarOrdenacao(estado, campo)`, `cabecalhoOrdenavel(colunas, estado, onClickFn) -> string`, `tipoDaColuna(colunas, campo) -> string`, `COLUNAS_EXAMES`, `COLUNAS_POR_EXAME`, `COLUNAS_EVENTOS`, `listaExamesFiltrada() -> array`, `listaEventosFiltrada() -> array`. Essas últimas duas e as três constantes `COLUNAS_*` são consumidas pela Task 7 (exportação).

- [ ] **Step 1: Adicionar os helpers compartilhados de ordenação**

No `<script>`, logo após a função `normJs`, adicionar:

```javascript
function ordenarLista(lista, campo, direcao, tipo) {
  const sinal = direcao === "asc" ? 1 : -1;
  return lista.slice().sort((a, b) => {
    let va = a[campo], vb = b[campo];
    if (tipo === "numero") return sinal * ((va || 0) - (vb || 0));
    if (tipo === "data") return sinal * (va || "").localeCompare(vb || "");
    return sinal * (va || "").toString().localeCompare((vb || "").toString(), "pt-BR");
  });
}

function alternarOrdenacao(estado, campo) {
  if (estado.campo === campo) {
    estado.direcao = estado.direcao === "asc" ? "desc" : "asc";
  } else {
    estado.campo = campo;
    estado.direcao = "asc";
  }
}

function tipoDaColuna(colunas, campo) {
  const c = colunas.find(c => c.chave === campo);
  return c ? c.tipo : "texto";
}

function cabecalhoOrdenavel(colunas, estado, onClickFn) {
  return colunas.map(c => {
    const ativo = estado.campo === c.chave;
    const seta = ativo ? (estado.direcao === "asc" ? " ▲" : " ▼") : "";
    return "<th style='cursor:pointer' onclick='" + onClickFn + "(\"" +
      c.chave + "\")'>" + esc(c.rotulo) + seta + "</th>";
  }).join("");
}
```

- [ ] **Step 2: Ordenação na tabela de Exames**

Logo antes de `function renderExames() {`, adicionar:

```javascript
const COLUNAS_EXAMES = [
  {chave: "codigo", rotulo: "Código", tipo: "texto"},
  {chave: "nome", rotulo: "Paciente", tipo: "texto"},
  {chave: "empresa", rotulo: "Empresa", tipo: "texto"},
  {chave: "recebido", rotulo: "Recebido", tipo: "data"},
  {chave: "prazo", rotulo: "Prazo", tipo: "data"},
  {chave: "status", rotulo: "Status", tipo: "texto"},
  {chave: "retornado_em", rotulo: "Laudo", tipo: "data"},
];
let ordExames = {campo: "recebido", direcao: "desc"};

function ordenarExamesPor(campo) {
  alternarOrdenacao(ordExames, campo);
  renderExames();
}

function listaExamesFiltrada() {
  const busca = normJs(document.getElementById("f-busca").value.trim());
  const emp = document.getElementById("f-empresa").value;
  const st = document.getElementById("f-status").value;
  const pg = document.getElementById("f-pag").value;
  let lista = todosExames();
  if (emp) lista = lista.filter(e => e.empresa === emp);
  if (st) lista = lista.filter(e => e.status === st);
  if (pg === "pago") lista = lista.filter(e => e.pagamento);
  if (pg === "faltando")
    lista = lista.filter(e => e.pagamento_esperado && !e.pagamento);
  if (pg === "nao") lista = lista.filter(e => !e.pagamento);
  if (busca) lista = lista.filter(e =>
    normJs((e.nome || "") + " " + e.codigo).includes(busca));
  return lista;
}
```

Dentro de `renderExames()`, substituir:

```javascript
  const busca = normJs(document.getElementById("f-busca").value.trim());
  const emp = document.getElementById("f-empresa").value;
  const st = document.getElementById("f-status").value;
  const pg = document.getElementById("f-pag").value;
  let lista = todosExames();
  if (emp) lista = lista.filter(e => e.empresa === emp);
  if (st) lista = lista.filter(e => e.status === st);
  if (pg === "pago") lista = lista.filter(e => e.pagamento);
  if (pg === "faltando")
    lista = lista.filter(e => e.pagamento_esperado && !e.pagamento);
  if (pg === "nao") lista = lista.filter(e => !e.pagamento);
  if (busca) lista = lista.filter(e =>
    normJs((e.nome || "") + " " + e.codigo).includes(busca));

  document.getElementById("f-contagem").textContent =
```

por:

```javascript
  let lista = listaExamesFiltrada();
  lista = ordenarLista(lista, ordExames.campo, ordExames.direcao,
    tipoDaColuna(COLUNAS_EXAMES, ordExames.campo));

  document.getElementById("f-contagem").textContent =
```

Substituir a montagem do `<table>` (mantendo tudo mais abaixo igual):

```javascript
  document.getElementById("tabela-exames").innerHTML =
    "<table><tr><th>Código</th><th>Paciente</th><th>Empresa</th>" +
    "<th>Recebido</th><th>Prazo</th><th>Status</th><th>Laudo</th>" +
    "<th>Pagamento</th><th></th></tr>" + linhas + "</table>" +
```

por:

```javascript
  document.getElementById("tabela-exames").innerHTML =
    "<table><tr>" + cabecalhoOrdenavel(COLUNAS_EXAMES, ordExames, "ordenarExamesPor") +
    "<th>Pagamento</th><th></th></tr>" + linhas + "</table>" +
```

- [ ] **Step 3: Ordenação na tabela Por exame (Financeiro)**

Substituir a função inteira:

```javascript
function renderPorExame() {
  const linhas = rec.por_exame.map((x, i) =>
    "<tr style='cursor:pointer' onclick=\"mostrarEventosPorExame(" + i + ")\">" +
    "<td>" + esc(x.exame) + "</td><td class='num'>" + x.qtd + "</td>" +
    "<td class='num'>" + valorAgregado(x.valor) +
    "</td><td class='num'>" +
    (x.valor > 0 && x.qtd ? brl(x.valor / x.qtd) : "") + "</td></tr>").join("");
  document.getElementById("tabela-por-exame").innerHTML =
    "<table><thead><tr><th>Exame</th><th class='num'>Qtd</th>" +
    "<th class='num'>Valor</th><th class='num'>Médio</th></tr></thead>" +
    "<tbody>" + linhas + "</tbody></table>";
}
```

por:

```javascript
const COLUNAS_POR_EXAME = [
  {chave: "exame", rotulo: "Exame", tipo: "texto"},
  {chave: "qtd", rotulo: "Qtd", tipo: "numero"},
  {chave: "valor", rotulo: "Valor", tipo: "numero"},
];
let ordPorExame = {campo: "qtd", direcao: "desc"};

function ordenarPorExamePor(campo) {
  alternarOrdenacao(ordPorExame, campo);
  renderPorExame();
}

function mostrarEventosPorExame(exame) {
  mostrarEventos(exame, function(e) { return e.exame === exame; });
}

function renderPorExame() {
  const lista = ordenarLista(rec.por_exame, ordPorExame.campo, ordPorExame.direcao,
    tipoDaColuna(COLUNAS_POR_EXAME, ordPorExame.campo));
  const linhas = lista.map(x =>
    "<tr style='cursor:pointer' onclick=\"mostrarEventosPorExame('" + x.exame + "')\">" +
    "<td>" + esc(x.exame) + "</td><td class='num'>" + x.qtd + "</td>" +
    "<td class='num'>" + valorAgregado(x.valor) +
    "</td><td class='num'>" +
    (x.valor > 0 && x.qtd ? brl(x.valor / x.qtd) : "") + "</td></tr>").join("");
  document.getElementById("tabela-por-exame").innerHTML =
    "<table><thead><tr>" +
    cabecalhoOrdenavel(COLUNAS_POR_EXAME, ordPorExame, "ordenarPorExamePor") +
    "<th class='num'>Médio</th></tr></thead>" +
    "<tbody>" + linhas + "</tbody></table>";
}
```

(A antiga `mostrarEventosPorExame(i)`, que recebia o índice na lista `rec.por_exame` e quebraria assim que a lista fosse reordenada na tela, é substituída por uma versão que recebe o **nome do exame** diretamente, sem depender de posição/ordem.)

- [ ] **Step 4: Ordenação na tabela de Eventos (drill-down)**

Substituir a função inteira:

```javascript
function renderEventosFiltrados() {
  const busca = normJs(document.getElementById("eventos-busca").value.trim());
  const lista = eventosVisiveis.filter(e =>
    !busca || normJs(e.paciente).includes(busca));
  const linhas = lista.slice(0, 500).map(e =>
    "<tr><td>" + esc(e.paciente) + "</td><td>" + esc(e.exame) + "</td>" +
    "<td>" + esc(dataBrAno(e.data)) + "</td><td>" + esc(e.pagador) +
    (e.convenio ? " · " + esc(e.convenio) : "") + "</td>" +
    "<td class='num'>" + (e.valor != null ? brl(e.valor)
      : (e.tipo === "faturado" ? "faturado" : "sem valor")) + "</td>" +
    "<td class='nota'>" + esc(e.documento) + "</td></tr>").join("");
  document.getElementById("eventos-corpo").innerHTML =
    "<table><thead><tr><th>Paciente</th><th>Exame</th><th>Data</th>" +
    "<th>Pagador</th><th class='num'>Valor</th><th>Documento</th></tr>" +
    "</thead><tbody>" + linhas + "</tbody></table>" +
    (lista.length > 500 ? "<p class='nota'>Mostrando 500 de " + lista.length +
     "; use a busca pra refinar.</p>" : "");
}
```

por:

```javascript
const COLUNAS_EVENTOS = [
  {chave: "paciente", rotulo: "Paciente", tipo: "texto"},
  {chave: "exame", rotulo: "Exame", tipo: "texto"},
  {chave: "data", rotulo: "Data", tipo: "data"},
  {chave: "pagador", rotulo: "Pagador", tipo: "texto"},
  {chave: "valor", rotulo: "Valor", tipo: "numero"},
];
let ordEventos = {campo: "data", direcao: "desc"};

function ordenarEventosPor(campo) {
  alternarOrdenacao(ordEventos, campo);
  renderEventosFiltrados();
}

function listaEventosFiltrada() {
  const busca = normJs(document.getElementById("eventos-busca").value.trim());
  return eventosVisiveis.filter(e => !busca || normJs(e.paciente).includes(busca));
}

function renderEventosFiltrados() {
  let lista = listaEventosFiltrada();
  lista = ordenarLista(lista, ordEventos.campo, ordEventos.direcao,
    tipoDaColuna(COLUNAS_EVENTOS, ordEventos.campo));
  const linhas = lista.slice(0, 500).map(e =>
    "<tr><td>" + esc(e.paciente) + "</td><td>" + esc(e.exame) + "</td>" +
    "<td>" + esc(dataBrAno(e.data)) + "</td><td>" + esc(e.pagador) +
    (e.convenio ? " · " + esc(e.convenio) : "") + "</td>" +
    "<td class='num'>" + (e.valor != null ? brl(e.valor)
      : (e.tipo === "faturado" ? "faturado" : "sem valor")) + "</td>" +
    "<td class='nota'>" + esc(e.documento) + "</td></tr>").join("");
  document.getElementById("eventos-corpo").innerHTML =
    "<table><thead><tr>" +
    cabecalhoOrdenavel(COLUNAS_EVENTOS, ordEventos, "ordenarEventosPor") +
    "<th>Documento</th></tr></thead><tbody>" + linhas + "</tbody></table>" +
    (lista.length > 500 ? "<p class='nota'>Mostrando 500 de " + lista.length +
     "; use a busca pra refinar.</p>" : "");
}
```

- [ ] **Step 5: Verificar bem-formação e rodar a suíte Python**

Sem teste automatizado de JavaScript. Confirmar visualmente que as chaves/aspas do HTML editado estão balanceadas, e rodar:

Run: `pytest -q`
Expected: PASS em todos (este passo não toca nenhum arquivo `.py`)

- [ ] **Step 6: Commit**

```bash
git add painel.html
git commit -m "painel.html: adiciona ordenacao por coluna em Exames, Por exame e Eventos"
```

---

### Task 7: Exportar Excel nas três tabelas

**Files:**
- Modify: `painel.html`

**Interfaces:**
- Consumes: `POST /api/exportar` (Task 4), `COLUNAS_EXAMES`/`COLUNAS_POR_EXAME`/`COLUNAS_EVENTOS`, `listaExamesFiltrada()`/`listaEventosFiltrada()`, `ordenarLista`/`tipoDaColuna`, `ordExames`/`ordPorExame`/`ordEventos` (Task 6).

- [ ] **Step 1: Adicionar os botões "Exportar Excel" nas três tabelas**

Na barra de filtros da aba Exames, substituir:

```html
      <div class="filtros">
        <input type="text" id="f-busca" placeholder="Buscar paciente ou código&hellip;">
        <select id="f-empresa"><option value="">Todas as empresas</option></select>
        <select id="f-status">
          <option value="">Todos os status</option>
          <option value="atrasado">Atrasados</option>
          <option value="no_prazo">Aguardando prazo</option>
          <option value="provavel">Conferir (nome parecido)</option>
          <option value="aviso">Conferir (respondido sem laudo)</option>
          <option value="retornado">Laudo enviado</option>
          <option value="baixado">Baixados</option>
        </select>
        <select id="f-pag">
          <option value="">Pagamento: todos</option>
          <option value="pago">Pagamento confirmado</option>
          <option value="faltando">Sem registro (período já pago)</option>
          <option value="nao">Sem pagamento (qualquer motivo)</option>
        </select>
        <span class="contagem" id="f-contagem"></span>
      </div>
```

por:

```html
      <div class="filtros">
        <input type="text" id="f-busca" placeholder="Buscar paciente ou código&hellip;">
        <select id="f-empresa"><option value="">Todas as empresas</option></select>
        <select id="f-status">
          <option value="">Todos os status</option>
          <option value="atrasado">Atrasados</option>
          <option value="no_prazo">Aguardando prazo</option>
          <option value="provavel">Conferir (nome parecido)</option>
          <option value="aviso">Conferir (respondido sem laudo)</option>
          <option value="retornado">Laudo enviado</option>
          <option value="baixado">Baixados</option>
        </select>
        <select id="f-pag">
          <option value="">Pagamento: todos</option>
          <option value="pago">Pagamento confirmado</option>
          <option value="faltando">Sem registro (período já pago)</option>
          <option value="nao">Sem pagamento (qualquer motivo)</option>
        </select>
        <span class="contagem" id="f-contagem"></span>
        <button onclick="exportarExcel('exames')">Exportar Excel</button>
      </div>
```

Na seção "Por exame", substituir:

```html
    <section class="bloco">
      <h2>Por exame</h2>
      <div id="tabela-por-exame"></div>
    </section>
```

por:

```html
    <section class="bloco">
      <h2>Por exame</h2>
      <div class="filtros" style="justify-content:flex-end">
        <button onclick="exportarExcel('por-exame')">Exportar Excel</button>
      </div>
      <div id="tabela-por-exame"></div>
    </section>
```

Na barra de filtros do bloco de Eventos, substituir:

```html
      <div class="filtros">
        <input type="text" id="eventos-busca" placeholder="Buscar paciente&hellip;"
          oninput="renderEventosFiltrados()">
      </div>
```

por:

```html
      <div class="filtros">
        <input type="text" id="eventos-busca" placeholder="Buscar paciente&hellip;"
          oninput="renderEventosFiltrados()">
        <button onclick="exportarExcel('eventos')">Exportar Excel</button>
      </div>
```

- [ ] **Step 2: Adicionar a função `exportarExcel`**

No `<script>`, logo antes da função `carregar()`, adicionar:

```javascript
async function exportarExcel(tabela) {
  let titulo, colunas, linhas;
  if (tabela === "exames") {
    titulo = "Exames";
    colunas = COLUNAS_EXAMES;
    linhas = ordenarLista(listaExamesFiltrada(), ordExames.campo, ordExames.direcao,
      tipoDaColuna(COLUNAS_EXAMES, ordExames.campo));
  } else if (tabela === "por-exame") {
    titulo = "Por exame";
    colunas = COLUNAS_POR_EXAME;
    linhas = ordenarLista(rec.por_exame, ordPorExame.campo, ordPorExame.direcao,
      tipoDaColuna(COLUNAS_POR_EXAME, ordPorExame.campo));
  } else if (tabela === "eventos") {
    titulo = "Eventos";
    colunas = COLUNAS_EVENTOS;
    linhas = ordenarLista(listaEventosFiltrada(), ordEventos.campo, ordEventos.direcao,
      tipoDaColuna(COLUNAS_EVENTOS, ordEventos.campo));
  } else {
    return;
  }
  let resp;
  try {
    resp = await fetch("/api/exportar", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({titulo, colunas, linhas}),
    });
  } catch (e) {
    alert("Não consegui gerar a planilha.");
    return;
  }
  if (!resp.ok) { alert("Não consegui gerar a planilha."); return; }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const cabecalho = resp.headers.get("Content-Disposition") || "";
  const m = cabecalho.match(/filename="([^"]+)"/);
  a.download = m ? m[1] : (titulo + ".xlsx");
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
```

- [ ] **Step 3: Verificação manual (não há teste automatizado de download de arquivo neste projeto)**

Run: `py painel.py`

No navegador, com o painel carregado:
1. Aba Exames: clicar "Exportar Excel" baixa um `.xlsx`; abrir e conferir que tem uma linha por exame visível na tela (respeitando os filtros ativos) e cabeçalhos corretos.
2. Aba Financeiro, seção "Por exame": mesma checagem.
3. Abrir um drill-down de Eventos (clicar em qualquer número clicável do Financeiro) e exportar dali.
4. Trocar a ordenação de uma coluna antes de exportar; conferir que a ordem no `.xlsx` bate com a ordem na tela.

- [ ] **Step 4: Rodar a suíte Python completa (nenhum arquivo `.py` foi tocado nesta task, mas confirma que nada mais quebrou)**

Run: `pytest -q`
Expected: PASS em todos

- [ ] **Step 5: Commit**

```bash
git add painel.html
git commit -m "painel.html: adiciona exportacao para Excel nas tabelas de Exames, Por exame e Eventos"
```

---

## Fora de escopo (ver design)

- Filtro de data ou ordenação nas listas de triagem da Visão Geral, em "Sem pagamento identificado", ou nos cartões de Importações.
- Qualquer outro formato de exportação (CSV, PDF).
- Salvar/lembrar o filtro de data escolhido entre sessões.
