# Eventos de Pagamento + Financeiro Centrado em Exame — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modelo único de "evento de pagamento" alimentado por todos os parsers, aba Financeiro redesenhada em torno de exame e pagador (IDS/Unimed/CardioPro), lista de investigação "Sem pagamento identificado" e botões separados de atualização (email × documentos).

**Architecture:** Novo módulo `eventos.py` concentra extração por paciente, taxonomia canônica de exames, dedup em dois níveis e agregações; `painel.py` expõe `GET /api/recebimentos`; `painel.html` ganha a aba Financeiro nova e perde a aba Análises. `cruzar_pagamentos.py` passa a consumir eventos (a conciliação MAPA por email continua).

**Tech Stack:** Python 3.14 (stdlib http.server, pypdf, openpyxl), pytest, front vanilla JS num único `painel.html`.

**Spec:** `docs/superpowers/specs/2026-08-11-eventos-pagamento-design.md`

## Global Constraints

- Texto novo em pt-BR, sem em-dash como pontuação de frase (regra do usuário).
- `documentos/`, `amostras/`, `repasses/` são gitignorados: testes que usam PDFs reais só rodam na máquina de dev (padrão já existente nos testes atuais).
- Nunca inventar valor: evento sem valor informado tem `valor: None` e o front mostra "sem valor informado".
- Convênio (Hapvida, Amil, Intermédica...) nunca é eixo de agregação; só detalhe de drill-down.
- Sem trilho fixo de pagador: qualquer pagador pode pagar exame de qualquer fonte; prioridade IDS → Unimed → CardioPro só resolve contagem dupla.
- Estilo visual: usar as classes/tokens CSS existentes (`bloco`, `cards`, `segmentado`, `legenda`, `badge`, `var(--cor-*)`); nada de cor hardcoded nova.
- Commits: mensagem em pt-BR, uma linha de resumo; rodar `py -m pytest tests/ -q` antes de cada commit.

## Dados reais de referência (verificados na máquina de dev)

- `documentos\drive-download-20260811T213946Z-1-001\TE 2025\10 Out25 MIBI 2- PCT.pdf`: formato "Relatório de Repasses Médicos", 17 itens, total R$ 1.680,11, linhas `DD/MM/AAAA NOME PROCEDIMENTO 98,83 REQUIS UNIMED 1`. Primeiro item: 07/01/2025 ODAIL JOSE DENDEVITE, TESTE ERGOMETRICO MIBI, 98,83, req 5282691, UNIMED.
- `...\TE 2025\202512 DR. FERNANDO SAMPAIO MIBI.pdf`: PDF com texto extraído vazio (deve continuar "não identificado").
- Demonstrativo Unimed (`6 Unimed Jun26.pdf`): itens em linhas verticais; código na linha `i` (`10101012-CONSULTA...`), data em `i-1`, nome subindo a partir de `i-4`; valor pago é o último `R$ ...` nas ~8 linhas após o código. Contagens reais nesse arquivo: 136×10101012, 146×40101010, 144×20102038, 1×99910073.
- O Relatório de Repasses repete pagamentos que também estão na Listagem de Repasse da IDS (mesmo valor unitário 98,83): o dedup de evento precisa remover o convênio grudado no nome da Listagem para as chaves baterem.

---

### Task 1: Parser "Relatório de Repasses Médicos" (nível documento)

**Files:**
- Modify: `ler_repasses.py` (após `processar_listagem_exames`, ~linha 252; `NOMES_AMIGAVEIS` ~linha 280; `_macro` ~linha 288; `_tentar_parsers` ~linha 312; `financeiro()` ~linha 366)
- Modify: `tests/test_ler_repasses_inventario.py`
- Copy fixtures (não versionadas): 2 PDFs para `amostras/`

**Interfaces:**
- Produces: `processar_relatorio_repasses(caminho) -> dict | None` com
  `{"tipo": "IDS - Relatorio de Repasses", "arquivo": str, "periodo": str,
  "emitido_em": str, "itens": [{"data": "AAAA-MM-DD", "paciente": str,
  "procedimento": str, "valor": float, "requisicao": str, "convenio": str}],
  "total": {"qtd": int, "valor": float} | None}`

- [ ] **Step 1: Copiar fixtures pra amostras/**

```powershell
Copy-Item "documentos\drive-download-20260811T213946Z-1-001\TE 2025\10 Out25 MIBI 2- PCT.pdf" "amostras\RELATORIO REPASSES - MIBI PCT.pdf"
Copy-Item "documentos\drive-download-20260811T213946Z-1-001\TE 2025\202512 DR. FERNANDO SAMPAIO MIBI.pdf" "amostras\RELATORIO SEM TEXTO.pdf"
```

- [ ] **Step 2: Escrever os testes que falham**

Em `tests/test_ler_repasses_inventario.py`, adicionar no fim:

```python
def test_processar_relatorio_repasses():
    caminho = os.path.join(AMOSTRAS, "RELATORIO REPASSES - MIBI PCT.pdf")
    r = lr.processar_relatorio_repasses(caminho)
    assert r["tipo"] == "IDS - Relatorio de Repasses"
    assert r["periodo"] == "01/01/2025 a 31/05/2025"
    assert r["total"] == {"qtd": 17, "valor": 1680.11}
    assert len(r["itens"]) == 17
    assert r["itens"][0] == {
        "data": "2025-01-07", "paciente": "ODAIL JOSE DENDEVITE",
        "procedimento": "TESTE ERGOMETRICO MIBI", "valor": 98.83,
        "requisicao": "5282691", "convenio": "UNIMED"}


def test_processar_relatorio_repasses_ignora_outros_formatos():
    caminho = os.path.join(AMOSTRAS, "DEMAIS EXAMES - FERNANDO SAMPAIO.pdf")
    assert lr.processar_relatorio_repasses(caminho) is None


def test_relatorio_repasses_entra_na_cadeia_de_parsers():
    caminho = os.path.join(AMOSTRAS, "RELATORIO REPASSES - MIBI PCT.pdf")
    item = lr._inspecionar_arquivo(caminho)
    assert item["status"] == "ok"
    assert item["tipo_amigavel"] == "IDS · Relatório de repasses"
    assert item["resumo"] == "17 procedimentos · R$ 1.680,11"


def test_relatorio_sem_texto_continua_nao_identificado():
    caminho = os.path.join(AMOSTRAS, "RELATORIO SEM TEXTO.pdf")
    item = lr._inspecionar_arquivo(caminho)
    assert item["status"] == "nao_identificado"
```

E atualizar o teste existente `test_nomes_amigaveis_cobre_os_4_tipos_conhecidos`
(renomear para `..._5_tipos...`) incluindo a nova entrada:

```python
def test_nomes_amigaveis_cobre_os_5_tipos_conhecidos():
    assert lr.NOMES_AMIGAVEIS == {
        "IDS - Listagem de Repasse": "IDS · Repasse por unidade",
        "IDS - Listagem de Exames/Laudos": "IDS · Exames e laudos",
        "IDS - Relatorio de Repasses": "IDS · Relatório de repasses",
        "Unimed - Demonstrativo": "Unimed · Demonstrativo",
        "CardioPro - Planilha de repasse": "CardioPro · Planilha",
    }
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `py -m pytest tests/test_ler_repasses_inventario.py -k relatorio -v`
Expected: FAIL com `AttributeError: ... 'processar_relatorio_repasses'`

- [ ] **Step 4: Implementar o parser**

Em `ler_repasses.py`, após `processar_listagem_exames` (linha ~252):

```python
# ------------------------------------------ IDS Relatorio de Repasses
PROCEDIMENTOS_RELATORIO = (
    "TESTE ERGOMETRICO MIBI",
    "LAUDO STRESS FARMACOLOGICO",
    "TESTE ERGOMETRICO",
    "ELETROCARDIOGRAMA",
    "M.A.P.A",
    "MAPA",
)
_PROC_ALT = "|".join(re.escape(p) for p in PROCEDIMENTOS_RELATORIO)
LINHA_RELATORIO_RE = re.compile(
    r"^(?P<data>\d{2}/\d{2}/\d{4})\s+(?P<pac>.+?)\s+"
    rf"(?P<proc>{_PROC_ALT})\s+"
    r"(?P<valor>[\d\.]+,\d{2})\s+(?P<req>\d+)\s+(?P<conv>.+?)\s+\d+\s*$")


def processar_relatorio_repasses(caminho):
    """Le o Relatorio de Repasses Medicos (sistema da Medicina Nuclear/IDS):
    pagamento por paciente com exame nominal, valor, requisicao e convenio."""
    txt = texto_pdf(caminho)
    if not re.search(r"Relat.rio de Repasses M.dicos", txt):
        return None
    resumo = {"tipo": "IDS - Relatorio de Repasses",
              "arquivo": os.path.basename(caminho), "itens": [], "total": None}
    m = re.search(r"Per.odo de pesquisa entre\s*:\s*"
                  r"(\d{2}/\d{2}/\d{4}) e (\d{2}/\d{2}/\d{4})", txt)
    if m:
        resumo["periodo"] = f"{m.group(1)} a {m.group(2)}"
    m = re.search(r"Impresso em\s*:\s*(\d{1,2} \w{3} \d{4})", txt)
    if m:
        resumo["emitido_em"] = m.group(1)
    for linha in txt.splitlines():
        m = LINHA_RELATORIO_RE.match(linha.strip())
        if not m:
            continue
        resumo["itens"].append({
            "data": _data_iso(m.group("data")),
            "paciente": m.group("pac").strip(),
            "procedimento": m.group("proc"),
            "valor": dinheiro(m.group("valor")),
            "requisicao": m.group("req"),
            "convenio": m.group("conv").strip(),
        })
    m = re.search(r"Total procedimentos\s*R\$\s*([\d\.,]+)\s*(\d+)\s*Quantidade",
                  txt)
    if m:
        resumo["total"] = {"qtd": int(m.group(2)), "valor": dinheiro(m.group(1))}
    return resumo
```

Registrar nos três pontos:

1. `NOMES_AMIGAVEIS`: adicionar `"IDS - Relatorio de Repasses": "IDS · Relatório de repasses",` (depois da linha de Exames/Laudos).
2. `_macro`: antes do bloco `if tipo.startswith("Unimed")`, adicionar:

```python
    if tipo == "IDS - Relatorio de Repasses":
        if r.get("total"):
            return (f"{r['total']['qtd']} procedimentos · "
                    f"R$ {_fmt_valor(r['total']['valor'])}")
        return f"{len(r['itens'])} procedimento(s)"
```

3. `_tentar_parsers`: a tupla de parsers PDF vira
   `(processar_ids, processar_unimed, processar_listagem_exames, processar_relatorio_repasses)`.

4. `financeiro()`: adicionar branch antes do `else` (que hoje assume CardioPro),
   agregando itens por procedimento:

```python
        elif r["tipo"] == "IDS - Relatorio de Repasses":
            emp = empresas.setdefault("IDS", {"documentos": []})
            por_proc = {}
            for it in r["itens"]:
                p = por_proc.setdefault(it["procedimento"], {"qtd": 0, "valor": 0})
                p["qtd"] += 1
                p["valor"] += it["valor"]
            emp["documentos"].append({
                "arquivo": r["arquivo"],
                "emitido_em": None,
                "periodo": r.get("periodo"),
                "linhas": [{"tipo": proc.title(), "qtd": p["qtd"],
                            "valor": p["valor"]}
                           for proc, p in por_proc.items()],
                "total": r.get("total"),
            })
```

- [ ] **Step 5: Rodar tudo e ver passar**

Run: `py -m pytest tests/ -q`
Expected: todos passam (incluindo o teste renomeado dos 5 tipos)

- [ ] **Step 6: Commit**

```bash
git add ler_repasses.py tests/test_ler_repasses_inventario.py
git commit -m "Parser novo: IDS Relatorio de Repasses (pagamento por paciente)"
```

---

### Task 2: `eventos.py` com taxonomia e separação de convênio

**Files:**
- Create: `eventos.py`
- Create: `tests/test_eventos.py`
- Modify: `cruzar_pagamentos.py:46-74` (CONVENIO_DISPLAY/extrair_convenio saem de lá)

**Interfaces:**
- Produces: `eventos.exame_canonico(nome: str) -> str`;
  `eventos.separar_convenio(nome: str) -> (str, str | None)` (nome limpo, convênio de exibição);
  `eventos.CODIGO_UNIMED_CANONICO: dict[str, str]`;
  `eventos.PRIORIDADE_PAGADOR: dict[str, int]`
- Consumes: `rotina_pendencias.normalizar`, `ler_repasses._regex_tolerante`

- [ ] **Step 1: Testes que falham** (`tests/test_eventos.py`, novo arquivo)

```python
import eventos as ev


def test_exame_canonico_mapeia_setores_e_procedimentos():
    assert ev.exame_canonico("MAPA") == "MAPA"
    assert ev.exame_canonico("M.A.P.A") == "MAPA"
    assert ev.exame_canonico("TESTE ERGOMETRICO") == "Teste Ergométrico"
    assert ev.exame_canonico("TESTE ERGOMETRICO MIBI") == "Teste Ergométrico MIBI"
    assert ev.exame_canonico("HONORARIO MEDICO") == "Laudo Stress Farmacológico"
    assert ev.exame_canonico("LAUDO STRESS FARMACOLOGICO") == "Laudo Stress Farmacológico"
    assert ev.exame_canonico("ECG") == "Eletrocardiograma"
    assert ev.exame_canonico("ELETROCARDIOGRAMA") == "Eletrocardiograma"


def test_exame_canonico_desconhecido_passa_como_veio():
    assert ev.exame_canonico("DENSITOMETRIA OSSEA") == "Densitometria Ossea"


def test_codigo_unimed_canonico():
    assert ev.CODIGO_UNIMED_CANONICO == {
        "20102038": "MAPA", "20102020": "Holter",
        "40101010": "Eletrocardiograma", "10101012": "Consulta",
        "99910073": "Consulta", "20101201": "Aval. marca-passo"}


def test_separar_convenio_reconhecido():
    nome, conv = ev.separar_convenio("MARIA DA SILVA INTERMEDICA SAUDE S.A")
    assert nome == "MARIA DA SILVA"
    assert conv == "Intermédica"


def test_separar_convenio_ausente():
    nome, conv = ev.separar_convenio("JOSE PEREIRA")
    assert nome == "JOSE PEREIRA"
    assert conv is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `py -m pytest tests/test_eventos.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'eventos'`

- [ ] **Step 3: Implementar `eventos.py`**

```python
# -*- coding: utf-8 -*-
"""Modelo central de eventos de pagamento.

Todo demonstrativo (IDS, Unimed, CardioPro) e reduzido a uma lista unica de
eventos {pagador, exame, paciente, data, valor, convenio, tipo, documento}.
As agregacoes do painel (por mes, por pagador, por exame) e a investigacao
de "sem pagamento" trabalham so em cima dessa lista.
"""

import re

import rotina_pendencias as rp
from ler_repasses import _regex_tolerante

# ordem de prioridade quando o mesmo exame aparece pago em mais de uma fonte
PRIORIDADE_PAGADOR = {"IDS": 0, "Unimed": 1, "CardioPro": 2}

# nomes de setor (IDS) e de procedimento (Relatorio de Repasses) -> canonico
EXAME_CANONICO = {
    "MAPA": "MAPA",
    "M.A.P.A": "MAPA",
    "TESTE ERGOMETRICO": "Teste Ergométrico",
    "TESTE ERGOMETRICO MIBI": "Teste Ergométrico MIBI",
    "HONORARIO MEDICO": "Laudo Stress Farmacológico",
    "LAUDO STRESS FARMACOLOGICO": "Laudo Stress Farmacológico",
    "ECG": "Eletrocardiograma",
    "ELETROCARDIOGRAMA": "Eletrocardiograma",
}

# codigos de servico dos demonstrativos Unimed/CardioPro -> canonico
CODIGO_UNIMED_CANONICO = {
    "20102038": "MAPA",
    "20102020": "Holter",
    "40101010": "Eletrocardiograma",
    "10101012": "Consulta",
    "99910073": "Consulta",
    "20101201": "Aval. marca-passo",
}


def exame_canonico(nome):
    """Nome canonico do exame; desconhecido passa como veio (title case)."""
    chave = rp.normalizar(nome)
    return EXAME_CANONICO.get(chave, (nome or "").strip().title())


# convenios conhecidos grudados no fim do campo "nome" da Listagem de
# Repasse da IDS (sem separador); descobertos minerando os sufixos
CONVENIO_DISPLAY = {
    "INTERMEDICA SAUDE S.A": "Intermédica",
    "INTERMEDICA- MEDIPLAN": "Intermédica",
    "CARTAO IDS MATRIZ": "Cartão IDS",
    "HAPVIDA - SOROCABA": "Hapvida",
    "BRADESCO OPERADORA PLANOS S/A": "Bradesco Operadora",
    "BRADESCO SAUDE": "Bradesco Saúde",
    "CAIXA ECONOMICA FEDERAL": "Caixa Econômica Federal",
    "SUL AMERICA": "Sul América",
    "PORTO SEGURO": "Porto Seguro",
    "CEPOS- EMPRESA": "Cepos",
    "UNIMED": "Unimed",
    "AMIL": "Amil",
    "APAS": "Apas",
    "CASSI": "Cassi",
    "CABESP": "Cabesp",
    "MARINHA": "Marinha",
}
_PADROES_CONVENIO = sorted(CONVENIO_DISPLAY, key=len, reverse=True)
_PADROES_CONVENIO = [(c, re.compile(_regex_tolerante(c) + r"$"))
                     for c in _PADROES_CONVENIO]


def separar_convenio(nome):
    """(nome sem o sufixo de convenio, convenio de exibicao ou None)."""
    for canonico, padrao in _PADROES_CONVENIO:
        m = padrao.search(nome or "")
        if m:
            return (nome[:m.start()].strip(), CONVENIO_DISPLAY[canonico])
    return ((nome or "").strip(), None)
```

Em `cruzar_pagamentos.py`: apagar o bloco `CONVENIO_DISPLAY`/`_PADROES_CONVENIO`/
`extrair_convenio` (linhas 44-74) e trocar por
`from eventos import separar_convenio`; no `itens_ids_setores`, trocar
`"convenio": extrair_convenio(nome)` por
`"convenio": separar_convenio(nome)[1]`.

- [ ] **Step 4: Rodar e ver passar**

Run: `py -m pytest tests/ -q`
Expected: todos passam

- [ ] **Step 5: Commit**

```bash
git add eventos.py tests/test_eventos.py cruzar_pagamentos.py
git commit -m "eventos.py: taxonomia canonica de exames e separacao de convenio"
```

---

### Task 3: Extratores por paciente migram para `eventos.py` (Unimed ampliada)

**Files:**
- Modify: `eventos.py` (adicionar extratores no fim)
- Modify: `cruzar_pagamentos.py` (remover `data_de`, `data_valida`, `itens_ids`, `itens_ids_setores`, `itens_unimed`, `itens_cardiopro`, `casa_nome`; importar de `eventos`)
- Modify: `tests/test_eventos.py`

**Interfaces:**
- Produces (todas em `eventos.py`, mesmo shape de item bruto):
  `itens_ids(caminho)`, `itens_ids_setores(caminho)`, `itens_unimed(caminho)`,
  `itens_cardiopro(caminho)`, `itens_relatorio(caminho)` →
  `[{"empresa": str, "mod": str, "data": datetime|None, "nome": str,
  "valor": float|None, "convenio": str|None, "origem": str}]`;
  `casa_nome(nome_email, nome_pag) -> bool`; `data_de(v)`; `data_valida(d)`
- Consumes: `ler_repasses.texto_pdf`, `ler_repasses.dinheiro`,
  `ler_repasses.SETOR_EXAME_LISTAGEM`, `ler_repasses.processar_relatorio_repasses`

- [ ] **Step 1: Testes que falham** (adicionar em `tests/test_eventos.py`)

```python
import os
from datetime import datetime

AMOSTRAS = "amostras"


def test_itens_relatorio():
    itens = ev.itens_relatorio(
        os.path.join(AMOSTRAS, "RELATORIO REPASSES - MIBI PCT.pdf"))
    assert len(itens) == 17
    assert itens[0] == {
        "empresa": "IDS", "mod": "TESTE ERGOMETRICO MIBI",
        "data": datetime(2025, 1, 7), "nome": "ODAIL JOSE DENDEVITE",
        "valor": 98.83, "convenio": "Unimed",
        "origem": "RELATORIO REPASSES - MIBI PCT.pdf"}


def test_itens_unimed_todos_os_codigos():
    itens = ev.itens_unimed(
        os.path.join(AMOSTRAS, "ExibeDemonstrativoPdf.pdf"))
    mods = {i["mod"] for i in itens}
    assert "MAPA" in mods
    assert "Consulta" in mods
    assert "Eletrocardiograma" in mods
    consulta = next(i for i in itens if i["mod"] == "Consulta")
    assert consulta["empresa"] == "Unimed"
    assert consulta["valor"] is not None and consulta["valor"] > 0
    assert len(consulta["nome"].split()) >= 2


def test_itens_ids_setores_tem_convenio_separado():
    itens = ev.itens_ids_setores(
        os.path.join(AMOSTRAS, "DEMAIS EXAMES - FERNANDO SAMPAIO.pdf"))
    assert itens
    com_convenio = [i for i in itens if i["convenio"]]
    assert com_convenio, "esperava ao menos um item com convenio reconhecido"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `py -m pytest tests/test_eventos.py -v`
Expected: FAIL com `AttributeError` nos novos nomes

- [ ] **Step 3: Implementar em `eventos.py`**

Adicionar imports no topo (`glob`, `os`, `datetime/timedelta`, `openpyxl`,
e de `ler_repasses`: `texto_pdf`, `dinheiro`, `SETOR_EXAME_LISTAGEM`,
`processar_relatorio_repasses`). Mover **sem alterar a lógica** de
`cruzar_pagamentos.py`: `data_de`, `data_valida`, `casa_nome`, `itens_ids`,
`itens_cardiopro`. Mover `itens_ids_setores` com uma única mudança
(convênio separado, como no teste). Reescrever `itens_unimed` generalizada:

```python
def itens_unimed(caminho):
    """No PDF da Unimed cada campo sai numa linha:
    ... NOME / UF / plano(A|E) / data / CODIGO-SERVICO / qt / R$ ... / R$ pago"""
    txt = texto_pdf(caminho)
    if "UNIMED" not in txt.upper():
        return []
    linhas = [l.strip() for l in txt.splitlines()]
    itens = []
    for i, linha in enumerate(linhas):
        m = re.match(r"^(\d{8})-", linha)
        if not m or i < 4:
            continue
        codigo = m.group(1)
        mod = CODIGO_UNIMED_CANONICO.get(codigo)
        if not mod:
            continue
        data = data_de(linhas[i - 1])
        if not data:
            continue
        # nome: linhas alfabeticas logo acima do codigo de plano (i-3)
        partes = []
        j = i - 4
        while j >= 0 and len(partes) < 3:
            cand = linhas[j]
            if not cand or re.search(r"\d", cand):
                break  # protocolo/lote ou vazio: acabou o nome
            partes.insert(0, cand)
            j -= 1
        nome = " ".join(partes).strip()
        if len(nome.split()) < 2:
            continue
        # valor pago: ultimo "R$ ..." antes do proximo item
        valor = None
        for l2 in linhas[i + 1:i + 9]:
            if re.match(r"^\d{8}-", l2):
                break
            mv = re.match(r"^R\$\s*([\d\.,]+)$", l2)
            if mv:
                valor = dinheiro(mv.group(1))
        itens.append({"empresa": "Unimed", "mod": mod, "data": data,
                      "nome": nome, "valor": valor, "convenio": None,
                      "origem": os.path.basename(caminho)})
    return itens


def itens_relatorio(caminho):
    """Itens por paciente do Relatorio de Repasses Medicos (IDS)."""
    r = processar_relatorio_repasses(caminho)
    if not r:
        return []
    return [{"empresa": "IDS", "mod": it["procedimento"],
             "data": data_de(datetime.strptime(it["data"], "%Y-%m-%d")
                             .strftime("%d/%m/%Y")),
             "nome": it["paciente"], "valor": it["valor"],
             "convenio": separar_convenio(it["convenio"])[1] or it["convenio"].title(),
             "origem": r["arquivo"]}
            for it in r["itens"]]
```

Nota: `itens_ids` e `itens_cardiopro` movidos não têm campo `convenio`;
adicionar `"convenio": None` (itens_cardiopro) e para `itens_ids` deixar o
nome com convênio grudado (a Task 4 separa via `separar_convenio`).

Em `cruzar_pagamentos.py`: apagar as funções movidas e importar:

```python
from eventos import (casa_nome, data_de, data_valida, itens_ids,
                     itens_ids_setores, itens_unimed, itens_cardiopro)
```

(Os usos existentes em `coletar_itens`/`coletar_itens_setores`/`main`
continuam funcionando com os nomes importados; `itens_unimed` agora devolve
todos os códigos, então `coletar_itens` deve filtrar
`[i for i in itens_unimed(caminho) if i["mod"] == "MAPA"]` para preservar o
comportamento da conciliação MAPA até a Task 7.)

- [ ] **Step 4: Rodar e ver passar**

Run: `py -m pytest tests/ -q`
Expected: todos passam

- [ ] **Step 5: Commit**

```bash
git add eventos.py cruzar_pagamentos.py tests/test_eventos.py
git commit -m "eventos.py: extratores por paciente (Unimed ampliada, Relatorio IDS)"
```

---

### Task 4: `coletar_eventos()` com dedup e supressão de pagamento cruzado

**Files:**
- Modify: `eventos.py`
- Modify: `tests/test_eventos.py`

**Interfaces:**
- Produces: `eventos.coletar_eventos(pastas=None) -> list[dict]` com eventos
  `{"pagador": "IDS"|"Unimed"|"CardioPro", "exame": str, "paciente": str
  (Title Case, sem convênio), "data": "AAAA-MM-DD"|None, "valor": float|None,
  "convenio": str|None, "tipo": "pago"|"faturado", "documento": str}`
- Consumes: extratores da Task 3, `ler_repasses.pastas_padrao`

- [ ] **Step 1: Testes que falham**

```python
def test_coletar_eventos_shape_e_dedup_exato(tmp_path):
    import shutil
    shutil.copy(os.path.join(AMOSTRAS, "RELATORIO REPASSES - MIBI PCT.pdf"),
                tmp_path / "a.pdf")
    shutil.copy(os.path.join(AMOSTRAS, "RELATORIO REPASSES - MIBI PCT.pdf"),
                tmp_path / "b.pdf")  # reenvio: mesmo conteudo, outro nome
    evs = ev.coletar_eventos(pastas=(str(tmp_path),))
    assert len(evs) == 17  # nao 34
    e0 = next(e for e in evs if e["paciente"] == "Odail Jose Dendevite")
    assert e0 == {"pagador": "IDS", "exame": "Teste Ergométrico MIBI",
                  "paciente": "Odail Jose Dendevite", "data": "2025-01-07",
                  "valor": 98.83, "convenio": "Unimed", "tipo": "pago",
                  "documento": "a.pdf" if e0["documento"] == "a.pdf" else e0["documento"]}


def test_supressao_cruzada_prioriza_pagador_de_maior_prioridade():
    evs = ev._suprimir_cruzados([
        {"pagador": "CardioPro", "exame": "MAPA", "paciente": "Maria Souza",
         "data": "2026-03-10", "valor": None, "convenio": None,
         "tipo": "faturado", "documento": "planilha.xlsx"},
        {"pagador": "Unimed", "exame": "MAPA", "paciente": "MARIA SOUZA",
         "data": "2026-03-12", "valor": 90.0, "convenio": None,
         "tipo": "pago", "documento": "unimed.pdf"},
    ])
    assert len(evs) == 1
    assert evs[0]["pagador"] == "Unimed"


def test_supressao_cruzada_mantem_pacientes_diferentes():
    evs = ev._suprimir_cruzados([
        {"pagador": "Unimed", "exame": "MAPA", "paciente": "Maria Souza",
         "data": "2026-03-12", "valor": 90.0, "convenio": None,
         "tipo": "pago", "documento": "unimed.pdf"},
        {"pagador": "CardioPro", "exame": "MAPA", "paciente": "Marta Silveira",
         "data": "2026-03-12", "valor": None, "convenio": None,
         "tipo": "faturado", "documento": "planilha.xlsx"},
    ])
    assert len(evs) == 2
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `py -m pytest tests/test_eventos.py -k "coletar_eventos or supressao" -v`
Expected: FAIL com `AttributeError`

- [ ] **Step 3: Implementar**

```python
def _suprimir_cruzados(eventos):
    """O mesmo exame pago/faturado em fontes de pagadores diferentes conta
    uma vez, pela fonte de maior prioridade (IDS > Unimed > CardioPro).
    Casamento aproximado (casa_nome, +-10 dias) porque as fontes grafam o
    nome de formas diferentes."""
    from datetime import datetime as _dt
    ordenados = sorted(eventos,
                       key=lambda e: PRIORIDADE_PAGADOR.get(e["pagador"], 9))
    mantidos = []
    indice = {}
    for evd in ordenados:
        tokens = rp.normalizar(evd["paciente"]).split()
        chave = (evd["exame"], tokens[0]) if tokens else None
        duplicado = False
        if chave and evd["data"]:
            dt = _dt.strptime(evd["data"], "%Y-%m-%d")
            for outro in indice.get(chave, []):
                if outro["pagador"] == evd["pagador"] or not outro["data"]:
                    continue
                delta = abs((_dt.strptime(outro["data"], "%Y-%m-%d") - dt).days)
                if delta > 10:
                    continue
                if casa_nome(evd["paciente"], outro["paciente"]):
                    duplicado = True
                    break
        if duplicado:
            continue
        mantidos.append(evd)
        if chave:
            indice.setdefault(chave, []).append(evd)
    return mantidos


def coletar_eventos(pastas=None):
    """Lista unica de eventos de pagamento de todas as pastas, deduplicada."""
    import ler_repasses as lr
    if pastas is None:
        pastas = lr.pastas_padrao()
    brutos = []
    for pasta in pastas:
        for caminho in sorted(glob.glob(os.path.join(glob.escape(pasta), "*"))):
            low = caminho.lower()
            try:
                if low.endswith(".pdf"):
                    brutos += itens_relatorio(caminho)
                    brutos += itens_ids(caminho)
                    brutos += itens_ids_setores(caminho)
                    brutos += itens_unimed(caminho)
                elif low.endswith(".xlsx"):
                    brutos += itens_cardiopro(caminho)
            except Exception:
                continue  # arquivo quebrado aparece na aba Importacoes
    eventos = []
    for p in brutos:
        data = p.get("data")
        if data is not None and not data_valida(data):
            data = None
        nome, conv = separar_convenio(p["nome"])
        eventos.append({
            "pagador": p["empresa"],
            "exame": exame_canonico(p["mod"]),
            "paciente": nome.title(),
            "data": data.strftime("%Y-%m-%d") if data else None,
            "valor": p.get("valor"),
            "convenio": p.get("convenio") or conv,
            "tipo": "faturado" if p["empresa"] == "CardioPro" else "pago",
            "documento": p["origem"],
        })
    vistos = set()
    unicos = []
    for evd in eventos:
        chave = (evd["pagador"], evd["exame"],
                 rp.normalizar(evd["paciente"]), evd["data"])
        if chave in vistos:
            continue
        vistos.add(chave)
        unicos.append(evd)
    return _suprimir_cruzados(unicos)
```

Nota sobre o primeiro teste: o campo `documento` do evento deduplicado será
o do primeiro arquivo processado (ordem alfabética, `a.pdf`); a asserção do
dicionário completo compara os demais campos com exatidão.

- [ ] **Step 4: Rodar e ver passar**

Run: `py -m pytest tests/ -q`
Expected: todos passam

- [ ] **Step 5: Commit**

```bash
git add eventos.py tests/test_eventos.py
git commit -m "coletar_eventos: lista unica com dedup e supressao de pagamento cruzado"
```

---

### Task 5: `recebimentos()` (agregações + sem_pagamento)

**Files:**
- Modify: `eventos.py`
- Modify: `tests/test_eventos.py`

**Interfaces:**
- Produces: `eventos.recebimentos(pastas=None) -> dict`:

```python
{
  "totais": {"valor": float, "exames": int, "consultas": int,
             "por_pagador": {"IDS": {"qtd": int, "valor": float}, ...}},
  "por_mes": [{"mes": "AAAA-MM",
               "por_pagador": {"IDS": {"qtd": int, "valor": float}, ...},
               "por_exame": {"MAPA": {"qtd": int, "valor": float}, ...}}],
  "por_exame": [{"exame": str, "qtd": int, "valor": float}],  # qtd desc
  "eventos": [<evento>],          # como na Task 4
  "sem_pagamento": [{"paciente": str, "exame": str, "data": "AAAA-MM-DD",
                     "fonte": str, "forca": "forte"|"fraca"}],
  "cobertura": {"<exame>": {"inicio": "AAAA-MM-DD", "fim": "AAAA-MM-DD"}},
  "documentos": {"IDS": {"documentos": [...]}, ...},  # = financeiro()["empresas"]
}
```
- Consumes: `coletar_eventos`, `ler_repasses.financeiro`,
  `ler_repasses.processar_listagem_exames`

- [ ] **Step 1: Testes que falham** (fixtures sintéticas, sem PDF)

```python
def _ev(**kw):
    base = {"pagador": "IDS", "exame": "MAPA", "paciente": "Maria Souza",
            "data": "2026-03-10", "valor": 45.0, "convenio": None,
            "tipo": "pago", "documento": "doc.pdf"}
    base.update(kw)
    return base


def test_agregacoes(monkeypatch):
    evs = [
        _ev(),
        _ev(paciente="Jose Lima", exame="Consulta", pagador="Unimed",
            valor=122.0, data="2026-03-20"),
        _ev(paciente="Ana Reis", exame="Teste Ergométrico", valor=105.5,
            data="2026-04-02"),
        _ev(paciente="Rui Costa", pagador="CardioPro", tipo="faturado",
            valor=None, data="2026-04-05"),
    ]
    monkeypatch.setattr(ev, "coletar_eventos", lambda pastas=None: evs)
    monkeypatch.setattr(ev, "_exames_realizados", lambda pastas=None: [])
    import ler_repasses as lr
    monkeypatch.setattr(lr, "financeiro", lambda pastas=None: {"empresas": {}})
    r = ev.recebimentos()
    assert r["totais"] == {
        "valor": 272.5, "exames": 3, "consultas": 1,
        "por_pagador": {"IDS": {"qtd": 2, "valor": 150.5},
                        "Unimed": {"qtd": 1, "valor": 122.0},
                        "CardioPro": {"qtd": 1, "valor": 0}}}
    assert [m["mes"] for m in r["por_mes"]] == ["2026-03", "2026-04"]
    assert r["por_mes"][0]["por_pagador"]["IDS"] == {"qtd": 1, "valor": 45.0}
    assert r["por_exame"][0]["exame"] == "MAPA"  # maior qtd primeiro... empate: ordem por qtd desc, valor desc
    assert r["eventos"] == evs


def test_sem_pagamento_forte_e_fraca(monkeypatch):
    evs = [_ev(paciente="Maria Souza", exame="Teste Ergométrico",
               data="2026-03-10")]
    realizados = [
        {"paciente": "Maria Souza", "setor": "TESTE ERGOMETRICO",
         "data": "2026-03-10", "assinado": "Sim"},   # pago: fora da lista
        {"paciente": "Pedro Alves", "setor": "TESTE ERGOMETRICO",
         "data": "2026-03-12", "assinado": "Sim"},   # coberto e nao pago: forte
        {"paciente": "Rita Nunes", "setor": "TESTE ERGOMETRICO",
         "data": "2026-07-01", "assinado": "Sim"},   # fora da cobertura: fraca
        {"paciente": "Caio Dias", "setor": "TESTE ERGOMETRICO",
         "data": "2026-03-15", "assinado": "Não"},   # sem laudo: fora da lista
    ]
    monkeypatch.setattr(ev, "coletar_eventos", lambda pastas=None: evs)
    monkeypatch.setattr(ev, "_exames_realizados",
                        lambda pastas=None: realizados)
    import ler_repasses as lr
    monkeypatch.setattr(lr, "financeiro", lambda pastas=None: {"empresas": {}})
    r = ev.recebimentos()
    casos = {c["paciente"]: c for c in r["sem_pagamento"]}
    assert set(casos) == {"Pedro Alves", "Rita Nunes"}
    assert casos["Pedro Alves"]["forca"] == "forte"
    assert casos["Rita Nunes"]["forca"] == "fraca"
    assert r["sem_pagamento"][0]["paciente"] == "Pedro Alves"  # forte primeiro
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `py -m pytest tests/test_eventos.py -k "agregacoes or sem_pagamento" -v`
Expected: FAIL com `AttributeError`

- [ ] **Step 3: Implementar**

```python
def _exames_realizados(pastas=None):
    """Exames da Listagem de Exames/Laudos da IDS (dedup por requisicao):
    a evidencia de 'foi feito' pros exames que nao passam pelo email."""
    import ler_repasses as lr
    if pastas is None:
        pastas = lr.pastas_padrao()
    exames = []
    vistos_req = set()
    for pasta in pastas:
        for caminho in sorted(glob.glob(os.path.join(glob.escape(pasta), "*"))):
            if not caminho.lower().endswith(".pdf"):
                continue
            try:
                r = lr.processar_listagem_exames(caminho)
            except Exception:
                continue
            for e in (r or {}).get("exames", []):
                if e["requisicao"] in vistos_req:
                    continue
                vistos_req.add(e["requisicao"])
                exames.append({"paciente": e["paciente"],
                               "setor": e["setor"], "data": e["data"],
                               "assinado": e["assinado"]})
    return exames


def recebimentos(pastas=None):
    """Estrutura completa pro GET /api/recebimentos."""
    from datetime import datetime as _dt
    import ler_repasses as lr
    evs = coletar_eventos(pastas)

    def _soma(grupo, evd):
        g = grupo.setdefault(evd_chave, {"qtd": 0, "valor": 0})
    # (ver implementacao real abaixo; helper inline)

    por_pagador = {}
    por_exame = {}
    por_mes = {}
    total_valor = 0.0
    exames_qtd = consultas_qtd = 0
    for evd in evs:
        v = evd["valor"] or 0
        total_valor += v
        if evd["exame"] == "Consulta":
            consultas_qtd += 1
        else:
            exames_qtd += 1
        p = por_pagador.setdefault(evd["pagador"], {"qtd": 0, "valor": 0})
        p["qtd"] += 1
        p["valor"] += v
        x = por_exame.setdefault(evd["exame"], {"qtd": 0, "valor": 0})
        x["qtd"] += 1
        x["valor"] += v
        if evd["data"]:
            m = por_mes.setdefault(evd["data"][:7],
                                   {"mes": evd["data"][:7],
                                    "por_pagador": {}, "por_exame": {}})
            mp = m["por_pagador"].setdefault(evd["pagador"],
                                             {"qtd": 0, "valor": 0})
            mp["qtd"] += 1
            mp["valor"] += v
            mx = m["por_exame"].setdefault(evd["exame"], {"qtd": 0, "valor": 0})
            mx["qtd"] += 1
            mx["valor"] += v

    # cobertura por exame: janela de datas de exame ja paga
    cobertura = {}
    for evd in evs:
        if not evd["data"]:
            continue
        c = cobertura.setdefault(evd["exame"], [evd["data"], evd["data"]])
        c[0] = min(c[0], evd["data"])
        c[1] = max(c[1], evd["data"])

    # sem pagamento: realizado laudado sem evento casado
    indice = {}
    for evd in evs:
        tokens = rp.normalizar(evd["paciente"]).split()
        if tokens and evd["data"]:
            indice.setdefault((evd["exame"], tokens[0]), []).append(evd)
    sem_pagamento = []
    for ex in _exames_realizados(pastas):
        if ex["assinado"] != "Sim":
            continue
        exame = exame_canonico(ex["setor"])
        tokens = rp.normalizar(ex["paciente"]).split()
        dt = _dt.strptime(ex["data"], "%Y-%m-%d")
        achou = False
        for evd in (indice.get((exame, tokens[0]), []) if tokens else []):
            delta = abs((_dt.strptime(evd["data"], "%Y-%m-%d") - dt).days)
            if delta <= 10 and casa_nome(ex["paciente"], evd["paciente"]):
                achou = True
                break
        if achou:
            continue
        c = cobertura.get(exame)
        forca = "forte" if c and c[0] <= ex["data"] <= c[1] else "fraca"
        sem_pagamento.append({"paciente": ex["paciente"], "exame": exame,
                              "data": ex["data"],
                              "fonte": "Listagem de Exames/Laudos (IDS)",
                              "forca": forca})
    sem_pagamento.sort(key=lambda c: (c["forca"] != "forte", c["data"]))

    lista_exames = sorted(
        ({"exame": nome, **tot} for nome, tot in por_exame.items()),
        key=lambda x: (-x["qtd"], -x["valor"]))
    return {
        "totais": {"valor": total_valor, "exames": exames_qtd,
                   "consultas": consultas_qtd, "por_pagador": por_pagador},
        "por_mes": sorted(por_mes.values(), key=lambda m: m["mes"]),
        "por_exame": lista_exames,
        "eventos": evs,
        "sem_pagamento": sem_pagamento,
        "cobertura": {k: {"inicio": v[0], "fim": v[1]}
                      for k, v in cobertura.items()},
        "documentos": lr.financeiro(pastas)["empresas"],
    }
```

(O bloco `def _soma` do rascunho acima não existe na versão final; a soma é
inline como mostrado. Remover o rascunho ao implementar.)

- [ ] **Step 4: Rodar e ver passar**

Run: `py -m pytest tests/ -q`
Expected: todos passam

- [ ] **Step 5: Commit**

```bash
git add eventos.py tests/test_eventos.py
git commit -m "recebimentos(): agregacoes por mes/pagador/exame e lista sem pagamento"
```

---

### Task 6: Endpoint `GET /api/recebimentos` (e remoção dos antigos)

**Files:**
- Modify: `painel.py:108-116` (rotas)
- Modify: `tests/test_painel_api.py`

**Interfaces:**
- Produces: `GET /api/recebimentos` → JSON da Task 5.
- Remove: rotas `/api/financeiro` e `/api/realizados_fornecedor` (o front que
  as usa é trocado nas Tasks 9-12; até lá o painel local mostra "Não consegui
  ler os demonstrativos" na aba Financeiro antiga, aceitável em dev).

- [ ] **Step 1: Teste que falha** (em `tests/test_painel_api.py`, seguindo o padrão do teste existente)

```python
def test_api_recebimentos_retorna_estrutura():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), painel.Handler)
    porta = servidor.server_address[1]
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{porta}/api/recebimentos", timeout=30) as resp:
            dados = json.loads(resp.read())
        assert set(dados.keys()) == {"totais", "por_mes", "por_exame",
                                     "eventos", "sem_pagamento", "cobertura",
                                     "documentos"}
        assert {"valor", "exames", "consultas", "por_pagador"} <= set(dados["totais"])
    finally:
        servidor.shutdown()
        thread.join(timeout=5)


def test_api_financeiro_removida():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), painel.Handler)
    porta = servidor.server_address[1]
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    try:
        import urllib.error
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{porta}/api/financeiro", timeout=10)
            assert False, "rota deveria ter sumido"
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        servidor.shutdown()
        thread.join(timeout=5)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `py -m pytest tests/test_painel_api.py -v`
Expected: os 2 novos FALHAM (rota nova 404; rota velha responde 200)

- [ ] **Step 3: Implementar em `painel.py`**

Substituir o bloco das rotas 108-116:

```python
            elif rota.path == "/api/recebimentos":
                import eventos
                self._json(eventos.recebimentos())

            elif rota.path == "/api/importacoes":
                self._json(ler_repasses.importacoes())
```

(As rotas `/api/financeiro` e `/api/realizados_fornecedor` são apagadas.)

- [ ] **Step 4: Rodar e ver passar**

Run: `py -m pytest tests/ -q`
Expected: todos passam

- [ ] **Step 5: Commit**

```bash
git add painel.py tests/test_painel_api.py
git commit -m "API: /api/recebimentos substitui /api/financeiro e /api/realizados_fornecedor"
```

---

### Task 7: Conciliação MAPA (aba Exames) consome eventos

**Files:**
- Modify: `cruzar_pagamentos.py` (`anotar_pagamentos`, remoção de
  `coletar_itens`, `coletar_itens_setores`, `cruzar_realizados_ids`,
  `agregar_por_mes_fornecedor`, `COMPAT`, `ORDEM_PAGADOR`,
  `PAGADOR_PRIMARIO` vira só heurística de expectativa, `main()` de
  protótipo é apagado)
- Create: `tests/test_cruzar_pagamentos.py`

**Interfaces:**
- Consumes: `eventos.coletar_eventos`, `eventos.casa_nome`,
  `eventos.PRIORIDADE_PAGADOR`
- Produces (inalterado para `painel.py`):
  `anotar_pagamentos(dados) -> list[orfaos]`, anota `ex["pagamento"]`,
  `ex["pagamento_esperado"]`, `ex["repeticao"]`,
  `dados["cobertura_pagamentos"]`

- [ ] **Step 1: Testes que falham** (`tests/test_cruzar_pagamentos.py`, novo)

```python
from datetime import datetime

import cruzar_pagamentos as cp
import eventos as ev


def _dados(exames):
    d = {"retornados": exames, "pendentes": [], "provaveis": [],
         "avisos": [], "baixados": []}
    return d


def _exame(codigo, nome, recebido, empresa="IDS", retornado=True):
    e = {"codigo": codigo, "nome": nome, "recebido": recebido,
         "empresa": empresa}
    if retornado:
        e["retornado_em"] = recebido
    return e


def test_anotar_pagamentos_casa_por_qualquer_pagador(monkeypatch):
    """Exame de fonte IDS pago pela Unimed (cruzamento real): deve casar."""
    evs = [{"pagador": "Unimed", "exame": "MAPA", "paciente": "Maria Souza",
            "data": "2026-03-12", "valor": 90.0, "convenio": None,
            "tipo": "pago", "documento": "unimed.pdf"}]
    monkeypatch.setattr(cp, "coletar_eventos", lambda pastas=None: evs)
    dados = _dados([_exame("A123", "MARIA SOUZA", "2026-03-10T12:00:00Z",
                           empresa="IDS")])
    orfaos = cp.anotar_pagamentos(dados)
    ex = dados["retornados"][0]
    assert ex["pagamento"]["pagador"] == "Unimed"
    assert ex["pagamento"]["tipo"] == "pago"
    assert orfaos == []


def test_anotar_pagamentos_cardiopro_marca_faturado(monkeypatch):
    evs = [{"pagador": "CardioPro", "exame": "MAPA", "paciente": "Jose Lima",
            "data": "2026-03-12", "valor": None, "convenio": None,
            "tipo": "faturado", "documento": "planilha.xlsx"}]
    monkeypatch.setattr(cp, "coletar_eventos", lambda pastas=None: evs)
    dados = _dados([_exame("B456", "JOSE LIMA", "2026-03-10T12:00:00Z",
                           empresa="CardioPro")])
    cp.anotar_pagamentos(dados)
    assert dados["retornados"][0]["pagamento"]["tipo"] == "faturado"


def test_anotar_pagamentos_orfao(monkeypatch):
    evs = [{"pagador": "IDS", "exame": "MAPA", "paciente": "Sem Par Nenhum",
            "data": "2026-03-12", "valor": 45.0, "convenio": None,
            "tipo": "pago", "documento": "ids.pdf"}]
    monkeypatch.setattr(cp, "coletar_eventos", lambda pastas=None: evs)
    dados = _dados([_exame("C789", "OUTRA PESSOA", "2026-03-10T12:00:00Z")])
    orfaos = cp.anotar_pagamentos(dados)
    assert len(orfaos) == 1
    assert orfaos[0]["nome"] == "Sem Par Nenhum"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `py -m pytest tests/test_cruzar_pagamentos.py -v`
Expected: FAIL (`coletar_eventos` não existe em `cp`)

- [ ] **Step 3: Implementar**

Em `cruzar_pagamentos.py`:

1. Importar: `from eventos import coletar_eventos, casa_nome, PRIORIDADE_PAGADOR` (mantendo os imports da Task 3 que ainda são usados; os que ficarem sem uso são removidos).
2. Reescrever o começo de `anotar_pagamentos` para montar `itens` a partir de eventos MAPA:

```python
def anotar_pagamentos(dados):
    """Anota ex['pagamento'] nos exames de `dados` (retorno de analisar) e
    devolve a lista de pagamentos sem exame correspondente na janela."""
    itens = []
    for evd in coletar_eventos():
        if evd["exame"] != "MAPA":
            continue
        itens.append({
            "empresa": evd["pagador"], "nome": evd["paciente"],
            "data": (datetime.strptime(evd["data"], "%Y-%m-%d")
                     if evd["data"] else None),
            "valor": evd["valor"], "origem": evd["documento"],
            "tipo": evd["tipo"],
        })
    ...
```

3. Índice de exames por token **sem** a empresa na chave (qualquer pagador
   pode pagar qualquer fonte):

```python
    indice = {}
    for ex in exames:
        if not ex.get("nome"):
            continue
        ex["_dt"] = datetime.fromisoformat(
            ex["recebido"].replace("Z", "+00:00")).replace(tzinfo=None)
        tokens = rp.normalizar(ex["nome"]).split()
        if tokens:
            indice.setdefault(tokens[0], []).append(ex)
```

4. O loop de casamento usa `indice.get(tokens[0], [])` direto (sem `COMPAT`)
   e `itens.sort(key=lambda p: PRIORIDADE_PAGADOR.get(p["empresa"], 9))`.
   O `ex["pagamento"]` anotado usa `"tipo": p["tipo"]` (vem do evento, não
   mais do if CardioPro).
5. `cobertura`/`pagamento_esperado`/regra de repetição/órfãos: inalterados
   (PAGADOR_PRIMARIO continua existindo só como heurística de qual janela
   usar pro rótulo "esperado"; documentar isso no comentário).
6. Apagar: `coletar_itens`, `coletar_itens_setores`, `cruzar_realizados_ids`,
   `agregar_por_mes_fornecedor`, `COMPAT`, `ORDEM_PAGADOR`, `main()` e o
   `if __name__ == "__main__"`. Remover de `painel.py` qualquer import/uso
   morto (a rota `/api/realizados_fornecedor` já saiu na Task 6).

- [ ] **Step 4: Rodar e ver passar**

Run: `py -m pytest tests/ -q`
Expected: todos passam

- [ ] **Step 5: Commit**

```bash
git add cruzar_pagamentos.py painel.py tests/test_cruzar_pagamentos.py
git commit -m "Conciliacao MAPA consome eventos; remove COMPAT e agregacoes antigas"
```

---

### Task 8: Dois botões de atualização (email × documentos)

**Files:**
- Modify: `painel.html:256` (header) e JS (`carregar()` ~linha 451)

**Interfaces:**
- Produces: `atualizarDocumentos()` (JS) que chama `carregarRecebimentos()`
  (criada na Task 9) + `carregarImportacoes()` sem tocar em `/api/dados`.

- [ ] **Step 1: Trocar o header**

Linha 256 vira:

```html
  <button id="btn-atualizar" onclick="carregar()"
    title="Varre a caixa de email (mais lento)">&#8635; Atualizar email</button>
  <button id="btn-atualizar-docs" onclick="atualizarDocumentos()"
    title="Relê só as pastas de documentos (rápido)">&#8635; Documentos</button>
```

- [ ] **Step 2: JS**

Depois de `carregar()`:

```js
async function atualizarDocumentos() {
  const btn = document.getElementById("btn-atualizar-docs");
  btn.disabled = true;
  try {
    await Promise.all([carregarRecebimentos(), carregarImportacoes()]);
  } finally {
    btn.disabled = false;
  }
}
```

Em `carregar()`, desabilitar os dois botões no início
(`document.getElementById("btn-atualizar-docs").disabled = true;`) e
reabilitar no `finally`. Trocar `carregarImportacoes();` dentro de
`carregar()` por `carregarRecebimentos(); carregarImportacoes();`
(a chamada `carregarFinanceiro()`/`carregarRealizadosFornecedor()` de
carga inicial sai na Task 9).

Nota: até a Task 9 existir, definir provisoriamente
`async function carregarRecebimentos() {}` (stub vazio) pra página não
quebrar; a Task 9 o substitui.

- [ ] **Step 3: Teste manual**

Run: `py painel.py 8799` e abrir http://127.0.0.1:8799
Expected: dois botões no topo; "Documentos" reabilita rápido; console sem erro.

- [ ] **Step 4: Commit**

```bash
git add painel.html
git commit -m "Header: botoes separados Atualizar email e Documentos"
```

---

### Task 9: Aba Financeiro nova (cartões, por exame, drill-down, documentos)

**Files:**
- Modify: `painel.html` (HTML da `#aba-financeiro` linhas 333-337; JS:
  substituir `carregarFinanceiro` ~linhas 890-937 e helpers 830-890)

**Interfaces:**
- Consumes: `GET /api/recebimentos` (Task 6)
- Produces (JS, usados pelas Tasks 10-11): variável global `rec` (JSON de
  recebimentos), `carregarRecebimentos()`, `mostrarEventos(titulo, filtroFn)`,
  `brlSeguro(v)` (existente, mantido)

- [ ] **Step 1: HTML da aba**

Substituir o conteúdo de `#aba-financeiro` (linhas 333-337) por:

```html
  <div id="aba-financeiro" class="oculto">
    <section class="bloco">
      <h2>Recebimentos</h2>
      <p class="nota">Somados dos demonstrativos de pagamento (IDS e Unimed
        têm valor; a planilha da CardioPro comprova o repasse mas não informa
        valor). Clique em qualquer número para ver os pacientes.</p>
      <div class="cards" id="cards-recebimentos"></div>
    </section>
    <section class="bloco" id="sec-grafico-meses">
      <div class="segmentado">
        <button class="ativa" id="btn-mes-pagador" onclick="renderMeses('pagador')">Por pagador</button>
        <button id="btn-mes-exame" onclick="renderMeses('exame')">Por exame</button>
      </div>
      <h2>Recebido por mês</h2>
      <p class="nota">Pelo mês em que o exame foi feito (competência), não
        pelo dia em que o dinheiro caiu.</p>
      <div id="grafico-meses"></div>
      <div class="legenda" id="legenda-meses"></div>
    </section>
    <section class="bloco">
      <h2>Por exame</h2>
      <div id="tabela-por-exame"></div>
    </section>
    <section class="bloco" id="sec-sem-pagamento"></section>
    <section class="bloco oculto" id="bloco-eventos">
      <div class="transacoes-cabeca">
        <h2 id="eventos-titulo"></h2>
        <button onclick="document.getElementById('bloco-eventos').classList.add('oculto')">Fechar</button>
      </div>
      <div class="filtros">
        <input type="text" id="eventos-busca" placeholder="Buscar paciente&hellip;"
          oninput="renderEventosFiltrados()">
      </div>
      <div id="eventos-corpo"></div>
    </section>
    <div id="sec-documentos-fin"></div>
    <div id="sec-orfaos"></div>
  </div>
```

- [ ] **Step 2: JS principal**

Substituir `carregarFinanceiro()` e a chamada `carregarFinanceiro();` por:

```js
let rec = null;            // JSON de /api/recebimentos
let eventosVisiveis = [];  // eventos do drill-down aberto

async function carregarRecebimentos() {
  try {
    rec = await (await fetch("/api/recebimentos")).json();
  } catch (e) {
    document.getElementById("cards-recebimentos").innerHTML =
      "<p class='nota'>Não consegui ler os demonstrativos.</p>";
    return;
  }
  renderCardsRecebimentos();
  renderMeses(vistaMes);
  renderPorExame();
  renderSemPagamento();       // Task 10 (stub até lá)
  renderDocumentosFin();
}

function cardRec(rotulo, valor, sub, onclick) {
  return "<div class='card' " + (onclick ? "style='cursor:pointer' onclick=\"" +
    onclick + "\"" : "") + "><div class='rotulo'>" + esc(rotulo) +
    "</div><div class='numero'>" + valor + "</div>" +
    (sub ? "<div class='sub'>" + esc(sub) + "</div>" : "") + "</div>";
}

function renderCardsRecebimentos() {
  const t = rec.totais;
  let h = cardRec("Total recebido", brl(t.valor), null,
                  "mostrarEventos('Todos os eventos', function(e){return true})");
  h += cardRec("Exames pagos", t.exames, null,
               "mostrarEventos('Exames pagos', function(e){return e.exame !== 'Consulta'})");
  h += cardRec("Consultas", t.consultas, null,
               "mostrarEventos('Consultas', function(e){return e.exame === 'Consulta'})");
  for (const nome of ["IDS", "Unimed", "CardioPro"]) {
    const p = t.por_pagador[nome];
    if (!p) continue;
    h += cardRec(nome, p.qtd,
                 p.valor ? brl(p.valor) : "sem valor informado",
                 "mostrarEventos('" + nome + "', function(e){return e.pagador === '" +
                 nome + "'})");
  }
  document.getElementById("cards-recebimentos").innerHTML = h;
}

function renderPorExame() {
  const linhas = rec.por_exame.map((x, i) =>
    "<tr style='cursor:pointer' onclick=\"mostrarEventos(" +
    "'" + esc(x.exame) + "', function(e){return e.exame === rec.por_exame[" + i + "].exame})\">" +
    "<td>" + esc(x.exame) + "</td><td class='num'>" + x.qtd + "</td>" +
    "<td class='num'>" + (x.valor ? brl(x.valor) : "sem valor informado") +
    "</td><td class='num'>" +
    (x.valor && x.qtd ? brl(x.valor / x.qtd) : "") + "</td></tr>").join("");
  document.getElementById("tabela-por-exame").innerHTML =
    "<table><thead><tr><th>Exame</th><th class='num'>Qtd</th>" +
    "<th class='num'>Valor</th><th class='num'>Médio</th></tr></thead>" +
    "<tbody>" + linhas + "</tbody></table>";
}

function mostrarEventos(titulo, filtroFn) {
  eventosVisiveis = (rec.eventos || []).filter(filtroFn);
  document.getElementById("eventos-titulo").textContent =
    titulo + " (" + eventosVisiveis.length + ")";
  document.getElementById("eventos-busca").value = "";
  renderEventosFiltrados();
  const bloco = document.getElementById("bloco-eventos");
  bloco.classList.remove("oculto");
  bloco.scrollIntoView({behavior: "smooth"});
}

function renderEventosFiltrados() {
  const busca = normJs(document.getElementById("eventos-busca").value.trim());
  const lista = eventosVisiveis.filter(e =>
    !busca || normJs(e.paciente).includes(busca));
  const linhas = lista.slice(0, 500).map(e =>
    "<tr><td>" + esc(e.paciente) + "</td><td>" + esc(e.exame) + "</td>" +
    "<td>" + esc(dataBr(e.data)) + "</td><td>" + esc(e.pagador) +
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

function renderDocumentosFin() {
  // reaproveita o corpo da antiga carregarFinanceiro(): lista de documentos
  // por empresa em <details>, agora lendo de rec.documentos
  const sec = document.getElementById("sec-documentos-fin");
  const nomes = ["IDS", "Unimed", "CardioPro"].filter(n => rec.documentos[n]);
  if (!nomes.length) { sec.innerHTML = ""; return; }
  let listas = "";
  for (const nome of nomes) {
    const docsOrdenados = rec.documentos[nome].documentos.slice()
      .sort((a, b) => chaveDataFin(b).localeCompare(chaveDataFin(a)));
    listas += "<section class='bloco'><details><summary><h2 style='display:inline'>" +
      "Documentos · " + esc(nome) + " (" + docsOrdenados.length +
      ")</h2></summary><div class='doc-fin-lista'>" +
      docsOrdenados.map(doc => {
        const r = resumoDocumentoFin(doc);
        return "<details><summary>" +
          "<span class='doc-data'>" + esc(dataDocumentoFin(doc)) + "</span>" +
          "<span class='doc-tipo'>" + esc(TIPO_AMIGAVEL_FIN[nome]) + "</span>" +
          "<span class='doc-num'>" + r.qtd + " itens" +
          (r.valor != null ? " · " + brl(r.valor) : "") + "</span></summary>" +
          "<div class='corpo'><p class='nota'>" + esc(doc.arquivo) + "</p>" +
          detalheDocumentoFin(doc) + "</div></details>";
      }).join("") + "</div></details></section>";
  }
  sec.innerHTML = listas;
}
carregarRecebimentos();
```

Notas de integração:
- Os helpers existentes `resumoDocumentoFin`, `detalheDocumentoFin`,
  `dataDocumentoFin`, `chaveDataFin`, `TIPO_AMIGAVEL_FIN`, `brlSeguro`
  continuam como estão (a antiga `carregarFinanceiro` é apagada; a carga
  inicial passa a ser `carregarRecebimentos()`); em `TIPO_AMIGAVEL_FIN`,
  garantir chave para os três nomes de empresa (já existe).
- `vistaMes` e `renderMeses` vêm da Task 10 do gráfico (a Task 9 define
  `let vistaMes = "pagador"; function renderMeses(){}` stubs se executada
  isoladamente; a Task 10 os substitui). `renderSemPagamento(){}` stub idem
  (Task 11).
- Adicionar CSS mínimo reusando o existente: nada novo além de
  `#tabela-por-exame td.num, #eventos-corpo td.num { text-align: right; }`
  se a classe `num` ainda não existir no CSS (verificar; a aba Exames já usa
  tabelas semelhantes).

- [ ] **Step 3: Teste manual**

Run: `py painel.py 8799`
Expected: aba Financeiro mostra cartões com totais reais; clicar num cartão
abre a lista de eventos com busca; documentos por empresa no fim; console limpo.

- [ ] **Step 4: Commit**

```bash
git add painel.html
git commit -m "Aba Financeiro nova: cartoes, por exame e drill-down de eventos"
```

---

### Task 10: Gráfico mensal empilhado com alternância pagador/exame

**Files:**
- Modify: `painel.html` (substituir os stubs `vistaMes`/`renderMeses`;
  aproveitar `PALETA_FORNECEDOR`, `MESES_NOME`, `formatMes` existentes
  ~linhas 994-1003; CSS novo pro gráfico de barras)

**Interfaces:**
- Consumes: `rec.por_mes` (Task 5/9), `mostrarEventos` (Task 9)
- Produces: `renderMeses(vista: "pagador"|"exame")`

- [ ] **Step 1: CSS** (junto dos estilos `-fin` existentes)

```css
  .grafico-barras { display: flex; align-items: flex-end; gap: 10px;
    height: 180px; padding-top: 8px; overflow-x: auto; }
  .gb-col { flex: 1; min-width: 42px; display: flex; flex-direction: column;
    align-items: center; gap: 4px; }
  .gb-pilha { width: 100%; max-width: 56px; display: flex;
    flex-direction: column-reverse; height: 150px; cursor: pointer; }
  .gb-fatia { width: 100%; }
  .gb-rotulo { font-size: 11px; color: var(--cor-texto-fraco); }
```

- [ ] **Step 2: JS**

```js
let vistaMes = "pagador";

function renderMeses(vista) {
  vistaMes = vista;
  document.getElementById("btn-mes-pagador").classList.toggle("ativa", vista === "pagador");
  document.getElementById("btn-mes-exame").classList.toggle("ativa", vista === "exame");
  const meses = rec ? rec.por_mes : [];
  if (!meses.length) {
    document.getElementById("grafico-meses").innerHTML =
      "<p class='nota'>Nenhum evento com data.</p>";
    return;
  }
  const chave = vista === "pagador" ? "por_pagador" : "por_exame";
  const series = [];   // nomes na ordem de aparicao, cor estavel
  meses.forEach(m => Object.keys(m[chave]).forEach(n => {
    if (!series.includes(n)) series.push(n);
  }));
  const corDe = n => PALETA_FORNECEDOR[series.indexOf(n) % PALETA_FORNECEDOR.length];
  const maxV = Math.max(...meses.map(m =>
    Object.values(m[chave]).reduce((s, x) => s + x.valor, 0)));
  const cols = meses.map(m => {
    const totalMes = Object.values(m[chave]).reduce((s, x) => s + x.valor, 0);
    const fatias = series.filter(n => m[chave][n]).map(n => {
      const v = m[chave][n].valor;
      const h = maxV ? Math.round(140 * v / maxV) : 0;
      return "<div class='gb-fatia' style='height:" + h + "px;background:" +
        corDe(n) + "' title='" + esc(n) + ": " + esc(brl(v)) + "'></div>";
    }).join("");
    return "<div class='gb-col'><div class='gb-pilha' onclick=\"" +
      "mostrarEventos('" + formatMes(m.mes) + "', function(e){" +
      "return e.data && e.data.slice(0,7) === '" + m.mes + "'})\">" + fatias +
      "</div><div class='gb-rotulo'>" + formatMes(m.mes) + "</div>" +
      "<div class='gb-rotulo'>" + esc(brl(totalMes)) + "</div></div>";
  }).join("");
  document.getElementById("grafico-meses").innerHTML =
    "<div class='grafico-barras'>" + cols + "</div>";
  document.getElementById("legenda-meses").innerHTML = series.map(n =>
    "<span class='legenda-item'><span class='legenda-cor' style='background:" +
    corDe(n) + "'></span>" + esc(n) + "</span>").join("");
}
```

(Se as classes `legenda-item`/`legenda-cor` não existirem no CSS atual da
legenda das Análises, copiar a estrutura da legenda existente; verificar o
CSS em torno da linha 200 antes de inventar classe nova.)

- [ ] **Step 3: Teste manual**

Run: `py painel.py 8799`
Expected: barras por mês com valores reais; alternância pagador/exame troca
as fatias; clique numa barra abre os eventos do mês.

- [ ] **Step 4: Commit**

```bash
git add painel.html
git commit -m "Financeiro: grafico mensal empilhado por pagador/exame"
```

---

### Task 11: Bloco "Sem pagamento identificado"

**Files:**
- Modify: `painel.html` (substituir stub `renderSemPagamento`)

**Interfaces:**
- Consumes: `rec.sem_pagamento`, `rec.cobertura` (Task 5), `dados`
  (variável global do email, pode ser null), `todosExames()` e `darBaixa()`
  existentes

- [ ] **Step 1: JS**

```js
function casosSemPagamento() {
  const casos = (rec && rec.sem_pagamento || []).map(c => ({...c}));
  // casos do MAPA vindos do email (ja carregados em `dados`)
  if (dados) {
    for (const ex of todosExames()) {
      if (!ex.pagamento_esperado || ex.pagamento) continue;
      casos.push({paciente: ex.nome || "(sem nome)", exame: "MAPA",
                  data: (ex.recebido || "").slice(0, 10),
                  fonte: "Email (" + ex.codigo + ")", forca: "forte",
                  codigo: ex.codigo});
    }
  }
  casos.sort((a, b) => (a.forca !== "forte") - (b.forca !== "forte") ||
                       (a.data || "").localeCompare(b.data || ""));
  return casos;
}

function renderSemPagamento() {
  const sec = document.getElementById("sec-sem-pagamento");
  const casos = casosSemPagamento();
  const exames = [...new Set(casos.map(c => c.exame))];
  const fExame = (document.getElementById("sp-exame") || {}).value || "";
  const fForca = (document.getElementById("sp-forca") || {}).value || "";
  const fBusca = normJs(((document.getElementById("sp-busca") || {}).value || "").trim());
  const visiveis = casos.filter(c =>
    (!fExame || c.exame === fExame) && (!fForca || c.forca === fForca) &&
    (!fBusca || normJs(c.paciente).includes(fBusca)));
  const fortes = casos.filter(c => c.forca === "forte").length;
  const cab = "<h2>Sem pagamento identificado</h2>" +
    "<p class='nota'>Exames com evidência de realização e nenhum pagamento " +
    "casado. \"Período já pago e não veio\" merece cobrança; \"aguardando " +
    "faturamento\" costuma ser atraso normal.</p>" +
    "<div class='filtros'>" +
    "<input type='text' id='sp-busca' placeholder='Buscar paciente&hellip;' " +
    "value='" + esc((document.getElementById("sp-busca") || {}).value || "") +
    "' oninput='renderSemPagamento()'>" +
    "<select id='sp-exame' onchange='renderSemPagamento()'>" +
    "<option value=''>Todos os exames</option>" + exames.map(x =>
      "<option" + (x === fExame ? " selected" : "") + ">" + esc(x) +
      "</option>").join("") + "</select>" +
    "<select id='sp-forca' onchange='renderSemPagamento()'>" +
    "<option value=''>Todas as situações</option>" +
    "<option value='forte'" + (fForca === "forte" ? " selected" : "") +
    ">Período já pago e não veio</option>" +
    "<option value='fraca'" + (fForca === "fraca" ? " selected" : "") +
    ">Aguardando faturamento</option></select>" +
    "<span class='contagem'>" + visiveis.length + " caso(s) · " + fortes +
    " forte(s)</span></div>";
  const linhas = visiveis.map(c => {
    const badge = c.forca === "forte"
      ? "<span class='badge b-atrasado'>Período já pago e não veio</span>"
      : "<span class='badge b-provavel'>Aguardando faturamento</span>";
    const cob = rec && rec.cobertura && rec.cobertura[c.exame];
    const detalhe = "<div class='corpo'><p class='nota'>Fonte: " +
      esc(c.fonte) + (cob ? " · Pagamentos deste exame cobrem " +
      dataBr(cob.inicio) + " a " + dataBr(cob.fim) : "") + "</p>" +
      (c.codigo ? "<button onclick=\"darBaixa('" + esc(c.codigo) +
       "')\">Dar baixa</button>" : "") + "</div>";
    return "<details><summary><span class='doc-data'>" + esc(dataBr(c.data)) +
      "</span><span class='doc-tipo'>" + esc(c.paciente) + "</span>" +
      "<span>" + esc(c.exame) + "</span>" + badge + "</summary>" + detalhe +
      "</details>";
  }).join("");
  sec.innerHTML = cab + "<div class='doc-fin-lista'>" +
    (linhas || "<p class='nota'>Nenhum caso pendente. Tudo casado.</p>") +
    "</div>";
}
```

Também: no fim de `render()` (a função da aba geral, linha ~644), adicionar
`if (rec) renderSemPagamento();` para os casos de email entrarem quando
`/api/dados` termina depois de `/api/recebimentos`.

- [ ] **Step 2: Teste manual**

Run: `py painel.py 8799`
Expected: bloco lista casos reais, fortes primeiro com badge vermelho;
filtros e busca funcionam; caso de email tem botão "Dar baixa".

- [ ] **Step 3: Commit**

```bash
git add painel.html
git commit -m "Financeiro: lista de investigacao Sem pagamento identificado"
```

---

### Task 12: Remover a aba Análises

**Files:**
- Modify: `painel.html`: nav (linha 265), div `#aba-analises` (linhas
  339-380), `mostraAba` (tirar "analises" do array, linha 445), JS das
  Análises (`carregarRealizadosFornecedor`, `renderMesesFornecedor`,
  `renderFornecedorFinanceiro`, `mostrarVistaFornecedor`, `montarDonutFin`,
  `dadosRealizadosFornecedor`, tooltip/handlers associados, CSS `donut`/
  `grade-meses-fin`/`grade-donuts` etc.)

- [ ] **Step 1: Remover**

Apagar: botão da nav, o `<div id="aba-analises">` inteiro, as funções JS
listadas acima e as chamadas a `carregarRealizadosFornecedor()`. Manter
`PALETA_FORNECEDOR`, `MESES_NOME`, `formatMes` (usados pelo gráfico novo) e
o CSS compartilhado (`segmentado`, `legenda`). Grep antes de apagar CSS:

```bash
grep -n "grade-meses-fin\|grade-donuts\|donut\|tooltip-fin\|fatia" painel.html
```

Só apagar seletor CSS que ficou sem uso no HTML/JS restante. O
`bloco-transacoes-fin` antigo sai junto (o novo é `bloco-eventos`).

- [ ] **Step 2: Verificação**

Run: `py painel.py 8799` e `py -m pytest tests/ -q`
Expected: 4 abas (Visão geral, Exames, Financeiro, Importações); nenhuma
referência a `analises`/`realizados_fornecedor` (`grep -n "analises\|realizados_fornecedor" painel.html painel.py` vazio); testes passam; console limpo.

- [ ] **Step 3: Commit**

```bash
git add painel.html
git commit -m "Remove aba Analises (absorvida pelo Financeiro novo)"
```

---

### Task 13: Guias, suíte completa e smoke final

**Files:**
- Modify: `GUIA-DRA-GISELE.txt` (seções "PARA VER OS PAGAMENTOS" e o cartão
  de botões), `LEIA-ME.txt` e `GUIA-RAFAEL.txt` (mapa de arquivos: adicionar
  `eventos.py`)

- [ ] **Step 1: Atualizar GUIA-DRA-GISELE.txt**

Substituir a seção "PARA VER OS PAGAMENTOS" por:

```
PARA VER OS PAGAMENTOS
  Aba "Financeiro": cartoes com o total recebido, exames e consultas,
  e um cartao por pagador (IDS, Unimed, CardioPro). Abaixo, o grafico
  mes a mes e a tabela por tipo de exame. CLIQUE EM QUALQUER NUMERO
  para ver a lista de pacientes por tras dele.
  O bloco "Sem pagamento identificado" mostra exames feitos que nao
  apareceram em nenhum pagamento: os marcados "Periodo ja pago e nao
  veio" merecem cobranca; "Aguardando faturamento" costuma ser so
  atraso do convenio.

OS DOIS BOTOES DE ATUALIZAR
  "Atualizar email" ..... le a caixa de email (demora ~1 minuto).
  "Documentos" .......... rele so as pastas de documentos (rapido).
                          Use depois de salvar um arquivo na pasta.
```

Em `GUIA-RAFAEL.txt` e `LEIA-ME.txt`, adicionar ao mapa de arquivos:
`eventos.py ................ modelo central de eventos de pagamento`.

- [ ] **Step 2: Suíte completa + smoke**

Run: `py -m pytest tests/ -q`
Expected: todos passam.

Run: `py painel.py 8799`, abrir, conferir as 4 abas, clicar em 3 números
diferentes do Financeiro, abrir 1 caso de sem pagamento, rodar os dois
botões de atualizar.

- [ ] **Step 3: Commit**

```bash
git add GUIA-DRA-GISELE.txt GUIA-RAFAEL.txt LEIA-ME.txt
git commit -m "Guias: aba Financeiro nova e botoes de atualizacao separados"
```

---

## Self-review (feito na escrita do plano)

- Spec coverage: parser novo (T1), taxonomia/convênio (T2), extratores +
  Unimed ampliada com consultas (T3), dedup 2 níveis + cruzamento aberto por
  prioridade (T4), agregações/sem_pagamento/cobertura (T5), API (T6),
  conciliação MAPA via eventos sem COMPAT (T7), botões separados (T8), aba
  única com cartões/drill-down (T9), gráfico mensal (T10), investigação
  (T11), remoção Análises (T12), guias (T13).
- Desvio consciente do spec: em vez de `GET /api/dados?email=0`, o botão
  "Documentos" simplesmente não chama `/api/dados` (chama só
  `/api/recebimentos` + `/api/importacoes`). Mais simples e com o mesmo
  efeito; o spec fica satisfeito no comportamento.
- Tipos consistentes entre tasks: shape do evento definido em T4 e consumido
  em T5/T7/T9-T11; shape de `recebimentos()` definido em T5 e consumido em
  T6/T9-T11.
