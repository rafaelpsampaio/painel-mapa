# Aba "Importações" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new "Importações" tab to the painel that lists every file in the local documents folder and in the email-downloaded `repasses/` folder as a horizontal card, showing what each parser recognized (friendly type name + one-line summary) and flagging files that weren't recognized ("não identificado") or that a parser choked on ("erro").

**Architecture:** Backend adds a pure classification layer in `ler_repasses.py` (`_tentar_parsers`, `_inspecionar_arquivo`, `inventario_pasta`, `importacoes`) built on top of the existing parser functions, without changing their behavior or the output of `coletar()`/`financeiro()`. A new `GET /api/importacoes` route in `painel.py` exposes it. The front end gets a new tab in `painel.html` with a folder picker (moved from the Financeiro tab) plus two card sections, rendered by new vanilla-JS functions following the existing render patterns already used for Financeiro/Análises.

**Tech Stack:** Python 3.14 stdlib (`http.server`), `pypdf`, `openpyxl`, vanilla JS/HTML/CSS (no build step, no framework), pytest for backend tests.

## Global Constraints

- Run tests with `py -m pytest tests/ -v` from the repo root (`py -m pytest` puts the repo root on `sys.path`, so `import ler_repasses` / `import painel` work with no path hacks — verified in this environment).
- Do not change the observable behavior of `coletar()`, `financeiro()`, or anything in `cruzar_pagamentos.py` — the refactor in Task 2 must be behavior-preserving (covered by a regression test).
- All user-facing strings are Portuguese (pt-BR), same informal tone already used in `painel.html`'s existing `.nota` text.
- Do not add `pytest` to `requirements.txt` — that file feeds the app's own runtime auto-installer (see commit `57744cb`); tests are dev-only.
- Reuse existing CSS classes (`.badge`, `.b-atrasado`, `.b-provavel`, `.nota`, `.filtros`, `.contagem`) instead of inventing new badge colors.
- Currency in card summaries is formatted Brazilian-style (`R$ 11.282,34`) since it's rendered server-side as a plain string, not passed through the client's `brl()` helper.

---

### Task 1: `_macro()` summary helper + friendly parser names

**Files:**
- Modify: `ler_repasses.py` (insert after `processar_cardiopro`, before `pastas_padrao()`, i.e. after line 272)
- Modify: `.gitignore` (add `.pytest_cache/`)
- Test: `tests/test_ler_repasses_inventario.py` (new)

**Interfaces:**
- Produces: `ler_repasses._fmt_valor(v: float) -> str` (Brazilian-style currency string, no "R$" prefix), `ler_repasses.NOMES_AMIGAVEIS: dict[str, str]` (parser `tipo` string → friendly display name), `ler_repasses._macro(r: dict) -> str` (one-line summary for a card, given a parser's resumo dict).

- [ ] **Step 1: Add `.pytest_cache/` to `.gitignore`**

In `.gitignore`, under the `# python` section:

```gitignore
# python
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 2: Create the test file with the failing tests**

Create `tests/test_ler_repasses_inventario.py`:

```python
import ler_repasses as lr


def test_macro_ids_repasse_com_total():
    r = {"tipo": "IDS - Listagem de Repasse",
         "setores": [{"unidade": "A", "setor": "B", "qtd": 1, "valor": 1.0}],
         "total": {"qtd": 239, "valor": 11282.34}}
    assert lr._macro(r) == "239 exames · R$ 11.282,34"


def test_macro_ids_repasse_sem_total():
    r = {"tipo": "IDS - Listagem de Repasse",
         "setores": [{"unidade": "A", "setor": "B", "qtd": 1, "valor": 1.0},
                     {"unidade": "A", "setor": "C", "qtd": 2, "valor": 2.0}],
         "total": None}
    assert lr._macro(r) == "2 setor(es)"


def test_macro_ids_listagem_exames():
    r = {"tipo": "IDS - Listagem de Exames/Laudos", "total": 1459,
         "periodo": "01/01/2026 a 30/06/2026"}
    assert lr._macro(r) == "1459 exames · período 01/01/2026 a 30/06/2026"


def test_macro_unimed_com_liquido_e_periodo():
    r = {"tipo": "Unimed - Demonstrativo", "liquido": 51794.67, "periodo": "202606",
         "executantes": []}
    assert lr._macro(r) == "R$ 51.794,67 líquido · período 202606"


def test_macro_unimed_sem_liquido_nem_periodo():
    r = {"tipo": "Unimed - Demonstrativo", "liquido": None, "periodo": None,
         "executantes": [{"nome": "A"}, {"nome": "B"}]}
    assert lr._macro(r) == "2 executante(s)"


def test_macro_cardiopro():
    r = {"tipo": "CardioPro - Planilha de repasse",
         "meses": [{"mes": "Jan", "ecg": 104, "mapa": 36},
                   {"mes": "Fev", "ecg": 147, "mapa": 89}]}
    assert lr._macro(r) == "2 mes(es) · 251 ECG · 125 MAPA"


def test_nomes_amigaveis_cobre_os_4_tipos_conhecidos():
    assert lr.NOMES_AMIGAVEIS == {
        "IDS - Listagem de Repasse": "IDS · Repasse por unidade",
        "IDS - Listagem de Exames/Laudos": "IDS · Exames e laudos",
        "Unimed - Demonstrativo": "Unimed · Demonstrativo",
        "CardioPro - Planilha de repasse": "CardioPro · Planilha",
    }
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `py -m pytest tests/test_ler_repasses_inventario.py -v`
Expected: FAIL — `AttributeError: module 'ler_repasses' has no attribute '_macro'` (and `NOMES_AMIGAVEIS`).

- [ ] **Step 4: Implement `_fmt_valor`, `NOMES_AMIGAVEIS`, `_macro`**

In `ler_repasses.py`, insert immediately after the end of `processar_cardiopro` (after its `return resumo` line) and before `def pastas_padrao():`:

```python
def _fmt_valor(v):
    """Valor em reais no padrao brasileiro (ex.: 11.282,34)."""
    return f"{v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


NOMES_AMIGAVEIS = {
    "IDS - Listagem de Repasse": "IDS · Repasse por unidade",
    "IDS - Listagem de Exames/Laudos": "IDS · Exames e laudos",
    "Unimed - Demonstrativo": "Unimed · Demonstrativo",
    "CardioPro - Planilha de repasse": "CardioPro · Planilha",
}


def _macro(r):
    """Resumo de uma linha pro card da aba Importacoes."""
    tipo = r["tipo"]
    if tipo == "IDS - Listagem de Repasse":
        if r.get("total"):
            return f"{r['total']['qtd']} exames · R$ {_fmt_valor(r['total']['valor'])}"
        return f"{len(r['setores'])} setor(es)"
    if tipo == "IDS - Listagem de Exames/Laudos":
        partes = [f"{r.get('total', '?')} exames"]
        if r.get("periodo"):
            partes.append(f"período {r['periodo']}")
        return " · ".join(partes)
    if tipo.startswith("Unimed"):
        partes = []
        if r.get("liquido"):
            partes.append(f"R$ {_fmt_valor(r['liquido'])} líquido")
        if r.get("periodo"):
            partes.append(f"período {r['periodo']}")
        return " · ".join(partes) if partes else f"{len(r['executantes'])} executante(s)"
    tot_ecg = sum(m["ecg"] for m in r["meses"])
    tot_mapa = sum(m["mapa"] for m in r["meses"])
    return f"{len(r['meses'])} mes(es) · {tot_ecg} ECG · {tot_mapa} MAPA"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/test_ler_repasses_inventario.py -v`
Expected: PASS (7 tests).

- [ ] **Step 6: Commit**

```bash
git add ler_repasses.py .gitignore tests/test_ler_repasses_inventario.py
git commit -m "Resumo de uma linha e nomes amigaveis pros parsers de demonstrativos"
```

---

### Task 2: Shared parser-dispatch helper + `coletar()` refactor (behavior-preserving)

**Files:**
- Modify: `ler_repasses.py:287-312` (the `coletar()` function)
- Test: `tests/test_ler_repasses_inventario.py` (append)

**Interfaces:**
- Consumes: `processar_ids`, `processar_unimed`, `processar_listagem_exames`, `processar_cardiopro` (existing, unchanged).
- Produces: `ler_repasses._tentar_parsers(caminho: str) -> tuple[dict | None, str | None]` — `(resumo, erro)`. `resumo` is `None` if no parser recognized the content (or the extension isn't `.pdf`/`.xlsx`); `erro` is the exception message if a parser raised, `None` otherwise. `coletar()` keeps its existing signature and output.

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_ler_repasses_inventario.py`:

```python
def test_tentar_parsers_extensao_nao_suportada(tmp_path):
    caminho = tmp_path / "arquivo.csv"
    caminho.write_text("a,b,c")
    resumo, erro = lr._tentar_parsers(str(caminho))
    assert resumo is None
    assert erro is None


def test_tentar_parsers_pdf_corrompido(tmp_path):
    caminho = tmp_path / "corrompido.pdf"
    caminho.write_bytes(b"nao e um pdf de verdade")
    resumo, erro = lr._tentar_parsers(str(caminho))
    assert resumo is None
    assert erro is not None


def test_tentar_parsers_pdf_reconhecido():
    import os
    caminho = os.path.join("amostras", "DEMAIS EXAMES - FERNANDO SAMPAIO.pdf")
    resumo, erro = lr._tentar_parsers(caminho)
    assert erro is None
    assert resumo["tipo"] == "IDS - Listagem de Repasse"


def test_coletar_amostras_preserva_comportamento():
    docs = lr.coletar(pastas=("amostras",))
    tipos_arquivos = sorted((d["tipo"], d["arquivo"]) for d in docs)
    assert tipos_arquivos == sorted([
        ("IDS - Listagem de Repasse", "DEMAIS EXAMES - FERNANDO SAMPAIO.pdf"),
        ("IDS - Listagem de Repasse", "DR. FERNANDO SAMPAIO.pdf"),
        ("IDS - Listagem de Repasse", "MAPA - DR. FERNANDO SAMPAIO.pdf"),
        ("Unimed - Demonstrativo", "ExibeDemonstrativoPdf.pdf"),
        ("CardioPro - Planilha de repasse", "Repasse Dr. Fernando 2026.xlsx"),
        ("CardioPro - Planilha de repasse", "Repasse Dr. Fernando.xlsx"),
    ])
```

Note: these tests read real files under `amostras/` and must be run from the repo root (see Global Constraints).

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_ler_repasses_inventario.py -v -k "tentar_parsers or coletar_amostras"`
Expected: FAIL — `AttributeError: module 'ler_repasses' has no attribute '_tentar_parsers'`.

- [ ] **Step 3: Add `_tentar_parsers` and refactor `coletar()`**

In `ler_repasses.py`, insert `_tentar_parsers` right after the `_macro` function added in Task 1 (before `def pastas_padrao():`):

```python
def _tentar_parsers(caminho):
    """Roda o(s) parser(es) da extensao do arquivo.
    Devolve (resumo, erro): resumo e None se nenhum parser reconheceu o
    conteudo (ou a extensao nao tem parser); erro e a mensagem de excecao
    se algum parser quebrou no meio do caminho."""
    ext = os.path.splitext(caminho)[1].lower()
    try:
        if ext == ".pdf":
            r = None
            for parser in (processar_ids, processar_unimed, processar_listagem_exames):
                r = parser(caminho)
                if r:
                    break
            return r, None
        if ext == ".xlsx":
            return processar_cardiopro(caminho), None
        return None, None
    except Exception as e:
        return None, str(e)
```

Then replace the whole body of `coletar()`:

```python
def coletar(pastas=None):
    """Processa todos os demonstrativos das pastas (dedup por nome)."""
    if pastas is None:
        pastas = pastas_padrao()
    docs = []
    vistos = set()
    for pasta in pastas:
        for caminho in sorted(glob.glob(os.path.join(pasta, "*"))):
            nome = os.path.basename(caminho).lower()
            if nome in vistos:
                continue
            r, erro = _tentar_parsers(caminho)
            if erro:
                print(f"ERRO ao processar {caminho}: {erro}")
                continue
            if r:
                vistos.add(nome)
                docs.append(r)
    return docs
```

(This is the same dispatch order and short-circuit-on-error semantics as before — a file only skips to the next chained parser if the current one returns `None`, not if it raises. That parity matters: `financeiro()` must keep producing exactly the same output.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_ler_repasses_inventario.py -v`
Expected: PASS (all tests from Task 1 and Task 2).

- [ ] **Step 5: Regression-check the two other callers of the parser functions**

Run: `py -c "import ler_repasses as lr; print(len(lr.financeiro()['empresas']))"`
Expected: prints `3` (IDS, Unimed, CardioPro) — same as before the refactor, confirming `financeiro()` (which calls `coletar()`) still works.

- [ ] **Step 6: Commit**

```bash
git add ler_repasses.py tests/test_ler_repasses_inventario.py
git commit -m "Extrai _tentar_parsers compartilhado; coletar() sem mudanca de comportamento"
```

---

### Task 3: File classification for the Importações tab

**Files:**
- Modify: `ler_repasses.py` (insert before `def main():`, i.e. right after `financeiro()`'s `return {"empresas": empresas}`)
- Test: `tests/test_ler_repasses_inventario.py` (append)

**Interfaces:**
- Consumes: `_tentar_parsers`, `_macro`, `NOMES_AMIGAVEIS` (Tasks 1-2), `pasta_documentos()` (existing).
- Produces:
  - `ler_repasses._inspecionar_arquivo(caminho: str) -> dict` — always has `arquivo` (basename) and `status` (`"ok"` | `"nao_identificado"` | `"erro"`); `status == "ok"` additionally has `tipo`, `tipo_amigavel`, `resumo`; the other two statuses additionally have `motivo` (string).
  - `ler_repasses.inventario_pasta(pasta: str | None) -> list[dict]` — one entry per file (via `_inspecionar_arquivo`) in `pasta`, sorted by filename; `[]` if `pasta` is falsy or not a directory.
  - `ler_repasses.importacoes(pasta_email: str = "repasses") -> dict` — `{"local": {"pasta": str, "arquivos": list[dict]}, "email": {"pasta": str, "arquivos": list[dict]}}`. `local.pasta` is `""` (and `arquivos` is `[]`) when no local folder is configured.

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_ler_repasses_inventario.py`:

```python
import os
import shutil

from pypdf import PdfWriter

AMOSTRAS = "amostras"
DOCUMENTOS = "documentos"


def test_inspecionar_arquivo_ok_ids_repasse():
    caminho = os.path.join(AMOSTRAS, "DEMAIS EXAMES - FERNANDO SAMPAIO.pdf")
    item = lr._inspecionar_arquivo(caminho)
    assert item["status"] == "ok"
    assert item["tipo"] == "IDS - Listagem de Repasse"
    assert item["tipo_amigavel"] == "IDS · Repasse por unidade"
    assert item["resumo"] == "239 exames · R$ 11.282,34"


def test_inspecionar_arquivo_ok_unimed():
    caminho = os.path.join(AMOSTRAS, "ExibeDemonstrativoPdf.pdf")
    item = lr._inspecionar_arquivo(caminho)
    assert item["status"] == "ok"
    assert item["tipo_amigavel"] == "Unimed · Demonstrativo"
    assert item["resumo"] == "R$ 51.794,67 líquido · período 202606"


def test_inspecionar_arquivo_ok_cardiopro():
    caminho = os.path.join(AMOSTRAS, "Repasse Dr. Fernando 2026.xlsx")
    item = lr._inspecionar_arquivo(caminho)
    assert item["status"] == "ok"
    assert item["tipo_amigavel"] == "CardioPro · Planilha"
    assert item["resumo"] == "6 mes(es) · 854 ECG · 509 MAPA"


def test_inspecionar_arquivo_ok_ids_listagem_exames():
    caminho = os.path.join(
        DOCUMENTOS, "Listagem de Exames_Laudos - DR. FERNANDO SAMPAIO.pdf")
    item = lr._inspecionar_arquivo(caminho)
    assert item["status"] == "ok"
    assert item["tipo_amigavel"] == "IDS · Exames e laudos"
    assert item["resumo"] == "1459 exames · período 01/01/2026 a 30/06/2026"


def test_inspecionar_arquivo_extensao_nao_suportada(tmp_path):
    caminho = tmp_path / "planilha.csv"
    caminho.write_text("a,b,c")
    item = lr._inspecionar_arquivo(str(caminho))
    assert item["status"] == "nao_identificado"
    assert ".csv" in item["motivo"]


def test_inspecionar_arquivo_pdf_sem_conteudo_reconhecido(tmp_path):
    caminho = tmp_path / "vazio.pdf"
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    with open(caminho, "wb") as f:
        w.write(f)
    item = lr._inspecionar_arquivo(str(caminho))
    assert item["status"] == "nao_identificado"
    assert "Nenhum parser" in item["motivo"]


def test_inspecionar_arquivo_erro(tmp_path):
    caminho = tmp_path / "corrompido.pdf"
    caminho.write_bytes(b"nao e um pdf de verdade")
    item = lr._inspecionar_arquivo(str(caminho))
    assert item["status"] == "erro"
    assert item["motivo"]


def test_inventario_pasta_agrega_varios_arquivos(tmp_path):
    (tmp_path / "planilha.csv").write_text("a,b,c")
    (tmp_path / "corrompido.pdf").write_bytes(b"nao e um pdf")
    shutil.copy(os.path.join(AMOSTRAS, "DEMAIS EXAMES - FERNANDO SAMPAIO.pdf"), tmp_path)
    itens = lr.inventario_pasta(str(tmp_path))
    status_por_arquivo = {i["arquivo"]: i["status"] for i in itens}
    assert status_por_arquivo == {
        "planilha.csv": "nao_identificado",
        "corrompido.pdf": "erro",
        "DEMAIS EXAMES - FERNANDO SAMPAIO.pdf": "ok",
    }


def test_inventario_pasta_vazia_ou_inexistente(tmp_path):
    assert lr.inventario_pasta("") == []
    assert lr.inventario_pasta(None) == []
    assert lr.inventario_pasta(str(tmp_path / "nao-existe")) == []


def test_importacoes_combina_local_e_email(tmp_path, monkeypatch):
    shutil.copy(os.path.join(AMOSTRAS, "ExibeDemonstrativoPdf.pdf"), tmp_path)
    monkeypatch.setattr(lr, "pasta_documentos", lambda: str(tmp_path))
    resultado = lr.importacoes(pasta_email=AMOSTRAS)
    assert resultado["local"]["pasta"] == str(tmp_path)
    assert len(resultado["local"]["arquivos"]) == 1
    assert resultado["local"]["arquivos"][0]["status"] == "ok"
    assert resultado["email"]["pasta"] == AMOSTRAS
    assert len(resultado["email"]["arquivos"]) == 6


def test_importacoes_sem_pasta_local_configurada(monkeypatch):
    monkeypatch.setattr(lr, "pasta_documentos", lambda: None)
    resultado = lr.importacoes(pasta_email=AMOSTRAS)
    assert resultado["local"] == {"pasta": "", "arquivos": []}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_ler_repasses_inventario.py -v`
Expected: FAIL — `AttributeError: module 'ler_repasses' has no attribute '_inspecionar_arquivo'`.

- [ ] **Step 3: Implement `_inspecionar_arquivo`, `inventario_pasta`, `importacoes`**

In `ler_repasses.py`, insert right after `financeiro()`'s closing `return {"empresas": empresas}` and before `def main():`:

```python
def _inspecionar_arquivo(caminho):
    """Classifica um arquivo pro card da aba Importacoes: ok, nao_identificado
    ou erro."""
    nome = os.path.basename(caminho)
    ext = os.path.splitext(nome)[1].lower()
    if ext not in (".pdf", ".xlsx"):
        return {"arquivo": nome, "status": "nao_identificado",
                "motivo": f'Extensão "{ext or "(sem extensão)"}" ainda não tem parser'}
    r, erro = _tentar_parsers(caminho)
    if erro:
        return {"arquivo": nome, "status": "erro", "motivo": erro}
    if r is None:
        return {"arquivo": nome, "status": "nao_identificado",
                "motivo": "Nenhum parser conhecido reconheceu o conteúdo deste arquivo"}
    return {"arquivo": nome, "status": "ok", "tipo": r["tipo"],
            "tipo_amigavel": NOMES_AMIGAVEIS.get(r["tipo"], r["tipo"]),
            "resumo": _macro(r)}


def inventario_pasta(pasta):
    """Status de cada arquivo de uma pasta pra aba Importacoes."""
    if not pasta or not os.path.isdir(pasta):
        return []
    return [_inspecionar_arquivo(caminho)
            for caminho in sorted(glob.glob(os.path.join(pasta, "*")))
            if os.path.isfile(caminho)]


def importacoes(pasta_email="repasses"):
    """Estrutura pra aba Importacoes: pasta local (prioritaria) + pasta do email."""
    local = pasta_documentos()
    return {
        "local": {"pasta": local or "",
                  "arquivos": inventario_pasta(local) if local else []},
        "email": {"pasta": pasta_email, "arquivos": inventario_pasta(pasta_email)},
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_ler_repasses_inventario.py -v`
Expected: PASS (all tests in the file).

- [ ] **Step 5: Commit**

```bash
git add ler_repasses.py tests/test_ler_repasses_inventario.py
git commit -m "Classificacao de arquivos (ok/nao identificado/erro) pra aba Importacoes"
```

---

### Task 4: `GET /api/importacoes` endpoint

**Files:**
- Modify: `painel.py` (add route inside `do_GET`, after the `/api/realizados_fornecedor` branch and before `/api/config`)
- Test: `tests/test_painel_api.py` (new)

**Interfaces:**
- Consumes: `ler_repasses.importacoes()` (Task 3).
- Produces: `GET /api/importacoes` → JSON with the exact shape of `ler_repasses.importacoes()`'s return value.

- [ ] **Step 1: Add the failing test**

Create `tests/test_painel_api.py`:

```python
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import painel


def test_api_importacoes_retorna_estrutura_local_e_email():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), painel.Handler)
    porta = servidor.server_address[1]
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{porta}/api/importacoes", timeout=5) as resp:
            dados = json.loads(resp.read())
        assert set(dados.keys()) == {"local", "email"}
        for secao in ("local", "email"):
            assert "pasta" in dados[secao]
            assert "arquivos" in dados[secao]
            assert isinstance(dados[secao]["arquivos"], list)
    finally:
        servidor.shutdown()
        thread.join(timeout=5)
```

(This hits the real `ler_repasses.importacoes()` — with whatever `repasses/`/local folder currently exist on disk — so it only checks the response shape, not specific file contents, keeping it robust regardless of what's actually in those folders.)

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/test_painel_api.py -v`
Expected: FAIL — response JSON has key `"erro": "rota desconhecida"` instead of `"local"`/`"email"` (route not wired yet), so the `set(dados.keys()) == {"local", "email"}` assertion fails.

- [ ] **Step 3: Add the route**

In `painel.py`, inside `do_GET`, insert a new branch right after the `/api/realizados_fornecedor` branch and before `/api/config`:

```python
            elif rota.path == "/api/realizados_fornecedor":
                import cruzar_pagamentos
                self._json(cruzar_pagamentos.agregar_por_mes_fornecedor())

            elif rota.path == "/api/importacoes":
                self._json(ler_repasses.importacoes())

            elif rota.path == "/api/config":
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/test_painel_api.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full test suite**

Run: `py -m pytest tests/ -v`
Expected: PASS (all tests from Tasks 1-4).

- [ ] **Step 6: Commit**

```bash
git add painel.py tests/test_painel_api.py
git commit -m "Endpoint /api/importacoes pra aba Importacoes"
```

---

### Task 5: Tab shell — nav button, sections, folder picker moved from Financeiro

**Files:**
- Modify: `painel.html` (CSS block, nav, aba-financeiro block, new aba-importacoes block)

**Interfaces:**
- Consumes: none (static markup).
- Produces DOM ids/classes that Task 6's JS binds to: `aba-btn-importacoes`, `aba-importacoes`, `sec-import-local`, `sec-import-email` (each containing a `.import-resumo` element and a `.grade-importacoes` container), plus the *relocated* `#cfg-pasta` input, `salvarPasta()` button, and `#cfg-status` span (same ids/behavior as before, new location).

- [ ] **Step 1: Add CSS for the cards**

In `painel.html`, insert right before the closing `</style>` tag (after the existing `#transacoes-corpo-fin td.muted` rule):

```css
  .import-resumo { color: #667; font-size: 14.5px; margin: 4px 0 10px; }
  .grade-importacoes { display: flex; flex-direction: column; gap: 10px; }
  .card-import { display: flex; flex-wrap: wrap; align-items: center; gap: 14px;
    background: #fff; border-radius: 10px; padding: 12px 16px;
    box-shadow: 0 1px 4px rgba(0,0,0,.08); border-left: 5px solid #1e5a8a; }
  .card-import.st-nao_identificado { border-left-color: #b26a00; }
  .card-import.st-erro { border-left-color: #c62828; }
  .card-import .ci-arquivo { font-weight: 600; flex: 1 1 220px; min-width: 180px; }
  .card-import .ci-tipo { color: #1e5a8a; font-size: 14px; }
  .card-import .ci-resumo { color: #667; font-size: 14px; }
  .card-import .ci-motivo { color: #667; font-size: 13.5px; flex: 2 1 280px; }
```

- [ ] **Step 2: Add the nav button**

In `painel.html`, in `<nav class="abas">`, change:

```html
  <button id="aba-btn-analises" onclick="mostraAba('analises')">Análises</button>
</nav>
```

to:

```html
  <button id="aba-btn-analises" onclick="mostraAba('analises')">Análises</button>
  <button id="aba-btn-importacoes" onclick="mostraAba('importacoes')">Importações</button>
</nav>
```

- [ ] **Step 3: Remove the folder-picker block from the Financeiro tab**

In `painel.html`, change:

```html
  <div id="aba-financeiro" class="oculto">
    <section class="bloco">
      <h2>Pasta local de documentos</h2>
      <p class="nota">Além dos que chegam por email, o painel lê os
        demonstrativos colocados nesta pasta do computador (opcional).
        Cole o caminho e salve; deixe em branco para desativar.</p>
      <div class="filtros">
        <input type="text" id="cfg-pasta"
          placeholder="Ex.: C:\Users\gisele\Documents\Demonstrativos">
        <button onclick="salvarPasta()">Salvar</button>
        <span class="contagem" id="cfg-status"></span>
      </div>
    </section>
    <section class="bloco" id="sec-financeiro"><p>Carregando&hellip;</p></section>

    <div id="sec-orfaos"></div>
  </div>
```

to:

```html
  <div id="aba-financeiro" class="oculto">
    <section class="bloco" id="sec-financeiro"><p>Carregando&hellip;</p></section>

    <div id="sec-orfaos"></div>
  </div>
```

- [ ] **Step 4: Add the new aba-importacoes block**

In `painel.html`, the `aba-analises` div is immediately followed by the floating tooltip div:

```html
  </div>
  <div class="tooltip-fin" id="tooltip-fin"></div>
```

(that first `</div>` closes `#aba-analises`). Change it to:

```html
  </div>

  <div id="aba-importacoes" class="oculto">
    <section class="bloco">
      <h2>Pasta local</h2>
      <p class="nota">Além dos que chegam por email, o painel lê os
        demonstrativos colocados nesta pasta do computador (opcional).
        Cole o caminho e salve; deixe em branco para desativar.</p>
      <div class="filtros">
        <input type="text" id="cfg-pasta"
          placeholder="Ex.: C:\Users\gisele\Documents\Demonstrativos">
        <button onclick="salvarPasta()">Salvar</button>
        <span class="contagem" id="cfg-status"></span>
      </div>
    </section>

    <section class="bloco" id="sec-import-local">
      <h2>Arquivos da pasta local</h2>
      <p class="nota">Hoje reconhecemos: IDS · Repasse por unidade, IDS · Exames
        e laudos, Unimed · Demonstrativo, CardioPro · Planilha. Um arquivo
        diferente desses aparece como "não identificado" abaixo.</p>
      <p class="import-resumo"></p>
      <div class="grade-importacoes"><p class="nota">Carregando&hellip;</p></div>
    </section>

    <section class="bloco" id="sec-import-email">
      <h2>Arquivos da pasta do email (repasses)</h2>
      <p class="nota">Baixados automaticamente sempre que o painel atualiza.</p>
      <p class="import-resumo"></p>
      <div class="grade-importacoes"><p class="nota">Carregando&hellip;</p></div>
    </section>
  </div>
  <div class="tooltip-fin" id="tooltip-fin"></div>
```

- [ ] **Step 5: Update `mostraAba()` to include the new tab**

In `painel.html`, change:

```js
function mostraAba(nome) {
  for (const a of ["geral", "exames", "financeiro", "analises"]) {
```

to:

```js
function mostraAba(nome) {
  for (const a of ["geral", "exames", "financeiro", "analises", "importacoes"]) {
```

- [ ] **Step 6: Manually verify the shell renders**

Run: `py painel.py` from the repo root, open `http://127.0.0.1:8765/` in a browser, click the "Importações" tab.
Expected: tab switches, shows the "Pasta local" input pre-filled with whatever `config.json` has configured, and both sections show "Carregando…" (no JS wired yet — that's Task 6). No console errors. Close the painel window (or leave it running for Task 6).

- [ ] **Step 7: Commit**

```bash
git add painel.html
git commit -m "Aba Importacoes: estrutura, seletor de pasta movido de Financeiro"
```

---

### Task 6: Render the cards (fetch, sort, empty states, wire folder save)

**Files:**
- Modify: `painel.html` (JS section)

**Interfaces:**
- Consumes: `GET /api/importacoes` (Task 4), DOM ids from Task 5, existing `esc()` helper.
- Produces: `ler_repasses`-facing behavior only in the browser — `carregarImportacoes()`, `renderSecaoImportacoes()`, `cardImportacao()`, `ordemStatusImportacao()`.

- [ ] **Step 1: Add the render functions**

In `painel.html`, insert right after the `carregarFinanceiro();` call (the top-level one that immediately follows the `carregarFinanceiro` function definition, right before the `const PALETA_FORNECEDOR = ...` line):

```js
carregarFinanceiro();

function ordemStatusImportacao(status) {
  return status === "erro" ? 0 : status === "nao_identificado" ? 1 : 2;
}

function cardImportacao(item) {
  if (item.status === "ok") {
    return "<div class='card-import'>" +
      "<div class='ci-arquivo'>" + esc(item.arquivo) + "</div>" +
      "<div class='ci-tipo'>" + esc(item.tipo_amigavel) + "</div>" +
      "<div class='ci-resumo'>" + esc(item.resumo) + "</div></div>";
  }
  const rotulo = item.status === "erro" ? "Erro ao ler" : "Não identificado";
  const classeBadge = item.status === "erro" ? "b-atrasado" : "b-provavel";
  return "<div class='card-import st-" + item.status + "'>" +
    "<div class='ci-arquivo'>" + esc(item.arquivo) + "</div>" +
    "<span class='badge " + classeBadge + "'>" + rotulo + "</span>" +
    "<div class='ci-motivo'>" + esc(item.motivo) + "</div></div>";
}

function renderSecaoImportacoes(idSecao, secao) {
  const raiz = document.getElementById(idSecao);
  const resumoEl = raiz.querySelector(".import-resumo");
  const listaEl = raiz.querySelector(".grade-importacoes");
  if (!secao.arquivos.length) {
    resumoEl.textContent = "";
    listaEl.innerHTML = secao.pasta
      ? "<p class='nota'>Nenhum arquivo encontrado nesta pasta.</p>"
      : "<p class='nota'>Nenhuma pasta configurada. Cole o caminho acima e salve.</p>";
    return;
  }
  const naoId = secao.arquivos.filter(a => a.status === "nao_identificado").length;
  const erro = secao.arquivos.filter(a => a.status === "erro").length;
  resumoEl.textContent = secao.arquivos.length + " arquivo" +
    (secao.arquivos.length === 1 ? "" : "s") +
    (naoId ? " · " + naoId + " não identificado" + (naoId === 1 ? "" : "s") : "") +
    (erro ? " · " + erro + " com erro" : "");
  const ordenados = secao.arquivos.slice().sort((a, b) =>
    ordemStatusImportacao(a.status) - ordemStatusImportacao(b.status) ||
    a.arquivo.localeCompare(b.arquivo));
  listaEl.innerHTML = ordenados.map(cardImportacao).join("");
}

async function carregarImportacoes() {
  try {
    const d = await (await fetch("/api/importacoes")).json();
    renderSecaoImportacoes("sec-import-local", d.local);
    renderSecaoImportacoes("sec-import-email", d.email);
  } catch (e) {
    const msg = "<p class='nota'>Não consegui ler os arquivos.</p>";
    document.querySelector("#sec-import-local .grade-importacoes").innerHTML = msg;
    document.querySelector("#sec-import-email .grade-importacoes").innerHTML = msg;
  }
}
carregarImportacoes();
```

- [ ] **Step 2: Wire the folder-save flow to refresh the new tab**

In `painel.html`, inside `salvarPasta()`, change:

```js
  carregarFinanceiro();
  carregarRealizadosFornecedor();
}
```

to:

```js
  carregarFinanceiro();
  carregarRealizadosFornecedor();
  carregarImportacoes();
}
```

- [ ] **Step 3: Manual verification in the browser**

Run: `py painel.py` from the repo root (or reuse the instance from Task 5 — reload the page since `painel.html` is served fresh on each request). Open `http://127.0.0.1:8765/`, click "Importações".

Expected:
- "Pasta local" section shows a resumo line and cards for the files under whatever folder `config.json` has configured (the repo's `documentos/` folder by default in this dev environment) — at least one card with a blue left border showing "IDS · Exames e laudos" and a matching summary.
- "Pasta do email (repasses)" section shows cards for whatever is in `repasses/`.
- No browser console errors.

If Chrome browser automation tools are available, use them to load the page and confirm the above instead of asking the user to check manually. If not available, ask the user to check and describe what they see.

- [ ] **Step 4: Manual verification of the "não identificado" and "erro" states**

Temporarily copy a harmless file with an unsupported extension into the configured local folder (e.g. copy `LEIA-ME.txt` into `documentos/`), reload the Importações tab (or click "Atualizar" then switch back to the tab — note `carregarImportacoes()` only runs on page load and on folder save, so a full page reload is the reliable way to see it pick up a new file dropped directly into the folder).

Expected: a new card appears with an amber left border, badge "Não identificado", and motivo mentioning the `.txt` extension, sorted above the "ok" cards.

Delete the temporary file from `documentos/` afterward so it doesn't linger in the dev folder.

- [ ] **Step 5: Run the full automated test suite one more time**

Run: `py -m pytest tests/ -v`
Expected: PASS (all tests from Tasks 1-4; Tasks 5-6 have no automated tests, verified manually above).

- [ ] **Step 6: Commit**

```bash
git add painel.html
git commit -m "Aba Importacoes: renderiza cards, ordena problemas primeiro"
```

---

## Post-plan check

After Task 6, do a final read-through of `painel.html`'s Financeiro tab to confirm the folder-picker block was fully removed (not just visually replaced) and that `cfg-pasta`/`cfg-status` ids appear exactly once in the whole file (in the new Importações location) — a leftover duplicate id would make the browser silently bind events to the wrong element.
