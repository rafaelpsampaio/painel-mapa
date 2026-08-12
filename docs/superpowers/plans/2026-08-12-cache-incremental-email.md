# Cache incremental de leitura de email Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminar a varredura ao vivo do Graph API a cada abertura do painel, substituindo-a por um cache local (`cache_emails.json`) com backfill resumível de ~2 anos e sincronização incremental rápida.

**Architecture:** Módulo novo `cache_email.py` concentra toda a comunicação com o Graph API e a persistência do cache (JSON, escrita atômica). `rotina_pendencias.analisar()` deixa de fazer I/O: passa a receber as mensagens já sincronizadas e rodar a mesma lógica de conciliação de sempre. `painel.py` orquestra: sincroniza um passo por requisição (`/api/dados`) e devolve progresso enquanto o backfill não termina.

**Tech Stack:** Python stdlib apenas (`json`, `urllib`, `datetime`), sem dependências novas. Testes com `pytest` + `monkeypatch`, sem chamada de rede real.

## Global Constraints

- Sem dependências novas: só biblioteca padrão do Python.
- Backfill cobre `DIAS_BACKFILL = 730` dias (~2 anos) por pasta.
- Todo acesso ao Graph API é somente leitura (escopo `Mail.Read`, inalterado).
- Toda escrita do cache é atômica: arquivo temporário + `os.replace()`.
- Testes não fazem chamada de rede real: usam `monkeypatch` (padrão já usado em `tests/test_eventos.py`).
- Design de referência: `docs/superpowers/specs/2026-08-12-cache-incremental-email-design.md`.

---

### Task 1: Armazenamento do cache (`cache_email.py`)

**Files:**
- Create: `cache_email.py`
- Modify: `.gitignore`
- Test: `tests/test_cache_email.py`

**Interfaces:**
- Produces: `PASTAS: dict[str, dict]` (pasta lógica → `{"campo_data": str, "select": str}`), `ARQ_CACHE: str`, `carregar_cache() -> dict`, `salvar_cache(cache: dict) -> None`, `mensagens(cache: dict, pasta: str) -> dict`

- [ ] **Step 1: Escrever os testes de armazenamento (devem falhar: módulo não existe)**

Criar `tests/test_cache_email.py`:

```python
import cache_email as ce


def test_carregar_cache_sem_arquivo_retorna_esqueleto(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "ARQ_CACHE", str(tmp_path / "cache_emails.json"))
    cache = ce.carregar_cache()
    assert set(cache["pastas"]) == {"inbox", "MAPA", "UNIMED", "IDS", "sentitems"}
    for estado in cache["pastas"].values():
        assert estado == {"backfill_completo_ate": None, "ultimo_sync": None,
                          "mensagens": {}}


def test_salvar_e_carregar_cache_preserva_dados(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "ARQ_CACHE", str(tmp_path / "cache_emails.json"))
    cache = ce.carregar_cache()
    cache["pastas"]["MAPA"]["mensagens"]["msg-1"] = {"assunto": "teste"}
    cache["pastas"]["MAPA"]["ultimo_sync"] = "2026-08-12T10:00:00Z"
    ce.salvar_cache(cache)

    recarregado = ce.carregar_cache()
    assert recarregado["pastas"]["MAPA"]["mensagens"]["msg-1"] == {"assunto": "teste"}
    assert recarregado["pastas"]["MAPA"]["ultimo_sync"] == "2026-08-12T10:00:00Z"


def test_carregar_cache_arquivo_corrompido_retorna_esqueleto(tmp_path, monkeypatch):
    arq = tmp_path / "cache_emails.json"
    arq.write_text("{nao e json valido")
    monkeypatch.setattr(ce, "ARQ_CACHE", str(arq))
    cache = ce.carregar_cache()
    assert cache["pastas"]["inbox"]["mensagens"] == {}


def test_salvar_cache_nao_deixa_arquivo_temporario_para_tras(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "ARQ_CACHE", str(tmp_path / "cache_emails.json"))
    cache = ce.carregar_cache()
    ce.salvar_cache(cache)
    arquivos = {p.name for p in tmp_path.iterdir()}
    assert arquivos == {"cache_emails.json"}


def test_mensagens_retorna_dicionario_da_pasta(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "ARQ_CACHE", str(tmp_path / "cache_emails.json"))
    cache = ce.carregar_cache()
    cache["pastas"]["IDS"]["mensagens"]["m1"] = {"assunto": "x"}
    assert ce.mensagens(cache, "IDS") == {"m1": {"assunto": "x"}}
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `pytest tests/test_cache_email.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'cache_email'`

- [ ] **Step 3: Criar `cache_email.py` com o armazenamento**

```python
# -*- coding: utf-8 -*-
"""Cache local das mensagens de email usadas pela conciliacao MAPA.

Mantem uma copia local (cache_emails.json) das mensagens das pastas
inbox, MAPA, UNIMED, IDS (exames recebidos) e sentitems (laudos
enviados), evitando reconsultar o Graph API a cada abertura do painel.
A primeira sincronizacao de cada pasta cobre os ultimos DIAS_BACKFILL
dias, em blocos mensais resumiveis; depois disso so busca mensagens
novas (ver sincronizar_um_passo).
"""

import json
import os

ARQ_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "cache_emails.json")

# pasta logica -> campos de consulta no Graph API
PASTAS = {
    "inbox":     {"campo_data": "receivedDateTime",
                  "select": "from,subject,receivedDateTime,conversationId,hasAttachments,body"},
    "MAPA":      {"campo_data": "receivedDateTime",
                  "select": "from,subject,receivedDateTime,conversationId,hasAttachments,body"},
    "UNIMED":    {"campo_data": "receivedDateTime",
                  "select": "from,subject,receivedDateTime,conversationId,hasAttachments,body"},
    "IDS":       {"campo_data": "receivedDateTime",
                  "select": "from,subject,receivedDateTime,conversationId,hasAttachments,body"},
    "sentitems": {"campo_data": "sentDateTime",
                  "select": "subject,sentDateTime,conversationId,hasAttachments"},
}


def _cache_vazio():
    return {"pastas": {nome: {"backfill_completo_ate": None,
                              "ultimo_sync": None, "mensagens": {}}
                       for nome in PASTAS}}


def carregar_cache():
    """Le o cache do disco; devolve um esqueleto vazio se nao existir ou
    estiver corrompido (nunca levanta excecao)."""
    base = _cache_vazio()
    if not os.path.exists(ARQ_CACHE):
        return base
    try:
        with open(ARQ_CACHE, "r", encoding="utf-8") as f:
            salvo = json.load(f)
    except (OSError, ValueError):
        return base
    for nome in PASTAS:
        base["pastas"][nome].update(salvo.get("pastas", {}).get(nome, {}))
    return base


def salvar_cache(cache):
    """Escrita atomica: grava num arquivo temporario e troca por cima do
    definitivo, pra nunca deixar o JSON pela metade se o processo for
    interrompido no meio da gravacao."""
    tmp = ARQ_CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, ARQ_CACHE)


def mensagens(cache, pasta):
    """Dicionario {id_mensagem: registro} da pasta logica indicada."""
    return cache["pastas"][pasta]["mensagens"]
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `pytest tests/test_cache_email.py -v`
Expected: PASS (5 testes)

- [ ] **Step 5: Adicionar `cache_emails.json` ao `.gitignore`**

Em `.gitignore`, na seção "dados baixados/gerados localmente" (junto de `cache_pdf.json`):

```
cache_pdf.json
cache_emails.json
```

- [ ] **Step 6: Commit**

```bash
git add cache_email.py tests/test_cache_email.py .gitignore
git commit -m "Adiciona armazenamento do cache local de mensagens de email"
```

---

### Task 2: Camada de acesso ao Graph API (`cache_email.py`)

**Files:**
- Modify: `cache_email.py`
- Modify: `tests/test_cache_email.py`

**Interfaces:**
- Consumes: `PASTAS` (Task 1)
- Produces: `GRAPH: str`, `_gget(token, url, tentativas=5) -> dict`, `_listar_pagina(token, url) -> list`, `_resolver_ids_pastas(token) -> dict`, `_registro_de(msg, config) -> dict`, `_buscar(token, pasta_id, config, inicio_iso, fim_iso=None) -> list`

- [ ] **Step 1: Escrever os testes da camada HTTP (devem falhar: funções não existem)**

Adicionar a `tests/test_cache_email.py`:

```python
import io
import urllib.error
import urllib.parse

import pytest


def _http_error(codigo, corpo=b"{}", headers=None):
    return urllib.error.HTTPError(
        url="http://x", code=codigo, msg="erro",
        hdrs=headers or {}, fp=io.BytesIO(corpo))


class _RespostaFake:
    def __init__(self, corpo):
        self._corpo = corpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._corpo


def test_gget_retorna_json_da_resposta(monkeypatch):
    monkeypatch.setattr(ce.urllib.request, "urlopen",
                        lambda req, timeout=60: _RespostaFake(b'{"value": [1, 2]}'))
    assert ce._gget("tok", "http://x") == {"value": [1, 2]}


def test_gget_tenta_de_novo_em_429_e_depois_funciona(monkeypatch):
    chamadas = []

    def fake_urlopen(req, timeout=60):
        chamadas.append(1)
        if len(chamadas) == 1:
            raise _http_error(429, headers={"Retry-After": "0"})
        return _RespostaFake(b'{"value": []}')

    monkeypatch.setattr(ce.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(ce.time, "sleep", lambda s: None)
    resultado = ce._gget("tok", "http://x")
    assert resultado == {"value": []}
    assert len(chamadas) == 2


def test_gget_erro_nao_429_propaga_runtimeerror(monkeypatch):
    def fake_urlopen(req, timeout=60):
        raise _http_error(500, b"deu ruim")
    monkeypatch.setattr(ce.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError):
        ce._gget("tok", "http://x")


def test_listar_pagina_segue_odata_nextlink(monkeypatch):
    paginas = [
        {"value": [{"id": "1"}], "@odata.nextLink": "http://x/pag2"},
        {"value": [{"id": "2"}]},
    ]
    chamadas = {"n": 0}

    def fake_gget(token, url):
        pagina = paginas[chamadas["n"]]
        chamadas["n"] += 1
        return pagina

    monkeypatch.setattr(ce, "_gget", fake_gget)
    resultado = ce._listar_pagina("tok", "http://x/pag1")
    assert [m["id"] for m in resultado] == ["1", "2"]


def test_resolver_ids_pastas(monkeypatch):
    monkeypatch.setattr(ce, "_gget", lambda token, url: {
        "value": [{"displayName": "MAPA", "id": "id-mapa"},
                  {"displayName": "UNIMED", "id": "id-unimed"}]})
    assert ce._resolver_ids_pastas("tok") == {"MAPA": "id-mapa", "UNIMED": "id-unimed"}


def test_registro_de_mensagem_de_pasta_de_exame():
    msg = {
        "subject": "Exame MAPA",
        "receivedDateTime": "2026-08-01T10:00:00Z",
        "conversationId": "conv-1",
        "from": {"emailAddress": {"address": "Contato@IDS.med.BR"}},
        "body": {"content": "<html><body>Segue anexo. <b>HELENA MARIA</b></body></html>"},
        "attachments": [{"name": "0RC-04973 FULANA.dmw"}],
    }
    registro = ce._registro_de(msg, ce.PASTAS["inbox"])
    assert registro["assunto"] == "Exame MAPA"
    assert registro["recebido"] == "2026-08-01T10:00:00Z"
    assert registro["conversa"] == "conv-1"
    assert registro["anexos"] == ["0RC-04973 FULANA.dmw"]
    assert registro["de"] == "contato@ids.med.br"
    assert "HELENA MARIA" in registro["corpo_texto"]
    assert "<b>" not in registro["corpo_texto"]


def test_registro_de_mensagem_enviada_sem_from_nem_corpo():
    msg = {
        "subject": "RE: Exame MAPA",
        "sentDateTime": "2026-08-02T09:00:00Z",
        "conversationId": "conv-1",
        "attachments": [{"name": "0RC-04973.pdf"}],
    }
    registro = ce._registro_de(msg, ce.PASTAS["sentitems"])
    assert registro["recebido"] == "2026-08-02T09:00:00Z"
    assert "de" not in registro
    assert "corpo_texto" not in registro


def test_registro_de_mensagem_sem_remetente_usa_interrogacao():
    msg = {"subject": "x", "receivedDateTime": "2026-08-01T10:00:00Z",
           "conversationId": None, "attachments": []}
    registro = ce._registro_de(msg, ce.PASTAS["inbox"])
    assert registro["de"] == "?"


def test_buscar_monta_filtro_com_intervalo(monkeypatch):
    urls = []
    monkeypatch.setattr(ce, "_listar_pagina", lambda token, url: urls.append(url) or [])
    ce._buscar("tok", "id-mapa", ce.PASTAS["MAPA"],
              "2026-06-01T00:00:00Z", "2026-07-01T00:00:00Z")
    url_decodificada = urllib.parse.unquote(urls[0])
    assert "mailFolders/id-mapa/messages" in urls[0]
    assert "receivedDateTime ge 2026-06-01T00:00:00Z" in url_decodificada
    assert "receivedDateTime lt 2026-07-01T00:00:00Z" in url_decodificada


def test_buscar_sem_fim_nao_inclui_lt(monkeypatch):
    urls = []
    monkeypatch.setattr(ce, "_listar_pagina", lambda token, url: urls.append(url) or [])
    ce._buscar("tok", "id-mapa", ce.PASTAS["MAPA"], "2026-06-01T00:00:00Z")
    url_decodificada = urllib.parse.unquote(urls[0])
    assert " lt " not in url_decodificada
```

Adicionar `import io`, `import urllib.error`, `import urllib.parse` e `import pytest` no topo do arquivo de teste, junto do `import cache_email as ce` já existente.

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `pytest tests/test_cache_email.py -v`
Expected: FAIL com `AttributeError: module 'cache_email' has no attribute '_gget'` (e afins)

- [ ] **Step 3: Adicionar a camada HTTP em `cache_email.py`**

No topo do arquivo, junto dos imports existentes:

```python
import re
import time
import urllib.error
import urllib.parse
import urllib.request
```

No final do arquivo:

```python
GRAPH = "https://graph.microsoft.com/v1.0"


def _gget(token, url, tentativas=5):
    """GET autenticado no Graph API, com retry em throttling (HTTP 429)."""
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    espera = 2
    for tentativa in range(tentativas):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and tentativa < tentativas - 1:
                retry_after = e.headers.get("Retry-After")
                time.sleep(float(retry_after) if retry_after else espera)
                espera *= 2
                continue
            corpo = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"Erro HTTP {e.code} ao consultar o email: {corpo}")


def _listar_pagina(token, url):
    out = []
    while url:
        data = _gget(token, url)
        out.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
    return out


def _resolver_ids_pastas(token):
    pastas = _gget(token, f"{GRAPH}/me/mailFolders?$top=50").get("value", [])
    return {p["displayName"]: p["id"] for p in pastas}


_RE_STYLE = re.compile(r"<style.*?</style>", re.S | re.I)
_RE_TAG = re.compile(r"<[^>]+>")


def _texto_plano_de_corpo(conteudo_html):
    import html as htmlmod
    texto = _RE_STYLE.sub(" ", conteudo_html or "")
    texto = _RE_TAG.sub(" ", texto)
    return htmlmod.unescape(texto)


def _registro_de(msg, config):
    """Converte uma mensagem do Graph API no registro quase-cru guardado
    no cache: so os campos usados pela conciliacao, corpo ja em texto
    plano (sem HTML)."""
    campo = config["campo_data"]
    registro = {
        "assunto": msg.get("subject") or "",
        "recebido": msg[campo],
        "conversa": msg.get("conversationId"),
        "anexos": [a.get("name") or "" for a in msg.get("attachments", [])],
    }
    if "from" in config["select"]:
        try:
            registro["de"] = msg["from"]["emailAddress"]["address"].lower()
        except (KeyError, TypeError):
            registro["de"] = "?"
    if "body" in config["select"]:
        registro["corpo_texto"] = _texto_plano_de_corpo(
            msg.get("body", {}).get("content", ""))
    return registro


def _buscar(token, pasta_id, config, inicio_iso, fim_iso=None):
    """Mensagens da pasta com campo_data em [inicio_iso, fim_iso), ou
    [inicio_iso, agora] se fim_iso for None."""
    campo = config["campo_data"]
    condicoes = f"{campo} ge {inicio_iso}"
    if fim_iso:
        condicoes += f" and {campo} lt {fim_iso}"
    filtro = urllib.parse.quote(condicoes)
    ordem = urllib.parse.quote(f"{campo} desc")
    expand = urllib.parse.quote("attachments($select=name)")
    params = (f"$select={config['select']}&$top=50&$filter={filtro}"
              f"&$orderby={ordem}&$expand={expand}")
    url = f"{GRAPH}/me/mailFolders/{pasta_id}/messages?{params}"
    return _listar_pagina(token, url)
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `pytest tests/test_cache_email.py -v`
Expected: PASS (14 testes: 5 da Task 1 + 9 novos)

- [ ] **Step 5: Commit**

```bash
git add cache_email.py tests/test_cache_email.py
git commit -m "Adiciona camada de acesso ao Graph API do cache de email"
```

---

### Task 3: Sincronização em blocos, backfill e incremental (`cache_email.py`)

**Files:**
- Modify: `cache_email.py`
- Modify: `tests/test_cache_email.py`

**Interfaces:**
- Consumes: `carregar_cache`, `salvar_cache`, `mensagens`, `PASTAS` (Task 1); `_buscar`, `_resolver_ids_pastas`, `_registro_de` (Task 2)
- Produces: `DIAS_BACKFILL: int`, `TAMANHO_BLOCO_DIAS: int`, `sincronizar_um_passo(token, cache, agora=None) -> dict | None`. Devolve `{"pasta": str, "mes": "AAAA-MM"}` se ainda falta backfill (o chamador deve repetir a chamada até receber `None`), ou `None` quando backfill e sincronização incremental de todas as pastas estão em dia.

- [ ] **Step 1: Escrever os testes de sincronização (devem falhar: função não existe)**

Adicionar a `tests/test_cache_email.py`:

```python
from datetime import datetime, timedelta, timezone


def _msg(id_, subject="x"):
    return {"id": id_, "subject": subject}


def test_primeiro_passo_faz_backfill_do_bloco_mais_recente(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "ARQ_CACHE", str(tmp_path / "cache_emails.json"))
    monkeypatch.setattr(ce, "DIAS_BACKFILL", 65)
    cache = ce.carregar_cache()
    agora = datetime(2026, 8, 12, tzinfo=timezone.utc)

    chamadas = []

    def fake_buscar(token, pasta_id, config, inicio_iso, fim_iso=None):
        chamadas.append((pasta_id, inicio_iso, fim_iso))
        return []

    monkeypatch.setattr(ce, "_buscar", fake_buscar)
    monkeypatch.setattr(ce, "_resolver_ids_pastas",
                        lambda token: {"MAPA": "id-mapa", "UNIMED": "id-unimed", "IDS": "id-ids"})

    progresso = ce.sincronizar_um_passo("tok", cache, agora=agora)

    assert progresso == {"pasta": "inbox", "mes": "2026-07"}
    assert cache["pastas"]["inbox"]["backfill_completo_ate"] == "2026-07-13T00:00:00Z"
    assert len(chamadas) == 1
    assert chamadas[0][0] == "inbox"  # pasta_id de inbox e o proprio nome: nao precisou resolver


def test_backfill_avanca_ate_cobrir_o_limite_e_marca_ultimo_sync(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "ARQ_CACHE", str(tmp_path / "cache_emails.json"))
    monkeypatch.setattr(ce, "DIAS_BACKFILL", 65)
    cache = ce.carregar_cache()
    agora = datetime(2026, 8, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(ce, "_buscar", lambda *a, **k: [])
    monkeypatch.setattr(ce, "_resolver_ids_pastas",
                        lambda token: {"MAPA": "m", "UNIMED": "u", "IDS": "i"})

    passos = 0
    while True:
        passos += 1
        assert passos < 50, "sincronizacao nao terminou (possivel loop infinito)"
        p = ce.sincronizar_um_passo("tok", cache, agora=agora)
        if p is None:
            break

    for pasta in ce.PASTAS:
        estado = cache["pastas"][pasta]
        limite = agora - timedelta(days=ce.DIAS_BACKFILL)
        assert ce._parse(estado["backfill_completo_ate"]) <= limite
        assert estado["ultimo_sync"] is not None


def test_apos_backfill_completo_proximo_passo_e_incremental(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "ARQ_CACHE", str(tmp_path / "cache_emails.json"))
    monkeypatch.setattr(ce, "DIAS_BACKFILL", 65)
    cache = ce.carregar_cache()
    agora = datetime(2026, 8, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(ce, "_buscar", lambda *a, **k: [])
    monkeypatch.setattr(ce, "_resolver_ids_pastas",
                        lambda token: {"MAPA": "m", "UNIMED": "u", "IDS": "i"})
    while ce.sincronizar_um_passo("tok", cache, agora=agora) is not None:
        pass

    chamadas = []

    def fake_buscar_incremental(token, pasta_id, config, inicio_iso, fim_iso=None):
        chamadas.append((pasta_id, inicio_iso, fim_iso))
        return [_msg("novo-1")] if pasta_id == "inbox" else []

    monkeypatch.setattr(ce, "_buscar", fake_buscar_incremental)
    resultado = ce.sincronizar_um_passo("tok", cache, agora=agora + timedelta(hours=2))

    assert resultado is None
    assert len(chamadas) == 5  # uma consulta por pasta
    assert all(fim is None for _, _, fim in chamadas)  # incremental: sem limite superior
    assert "novo-1" in cache["pastas"]["inbox"]["mensagens"]


def test_sincronizar_grava_mensagens_no_registro_da_pasta(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "ARQ_CACHE", str(tmp_path / "cache_emails.json"))
    monkeypatch.setattr(ce, "DIAS_BACKFILL", 1)  # backfill de 1 dia: termina numa chamada
    cache = ce.carregar_cache()
    agora = datetime(2026, 8, 12, tzinfo=timezone.utc)
    msg_real = {
        "id": "abc123",
        "subject": "Exame MAPA",
        "receivedDateTime": "2026-08-11T10:00:00Z",
        "conversationId": "conv-1",
        "from": {"emailAddress": {"address": "contato@ids.med.br"}},
        "body": {"content": "texto"},
        "attachments": [{"name": "0RC-04973 FULANA.dmw"}],
    }
    monkeypatch.setattr(ce, "_buscar", lambda *a, **k: [msg_real])
    monkeypatch.setattr(ce, "_resolver_ids_pastas",
                        lambda token: {"MAPA": "m", "UNIMED": "u", "IDS": "i"})

    ce.sincronizar_um_passo("tok", cache, agora=agora)

    registro = cache["pastas"]["inbox"]["mensagens"]["abc123"]
    assert registro["assunto"] == "Exame MAPA"
    assert registro["anexos"] == ["0RC-04973 FULANA.dmw"]


def test_resolver_ids_pastas_nao_e_chamado_para_inbox_e_sentitems(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "ARQ_CACHE", str(tmp_path / "cache_emails.json"))
    monkeypatch.setattr(ce, "DIAS_BACKFILL", 65)
    cache = ce.carregar_cache()
    agora = datetime(2026, 8, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(ce, "_buscar", lambda *a, **k: [])
    chamado = []
    monkeypatch.setattr(ce, "_resolver_ids_pastas", lambda token: chamado.append(1) or {})

    ce.sincronizar_um_passo("tok", cache, agora=agora)  # backfill do inbox, primeira pasta

    assert chamado == []
```

Adicionar `from datetime import datetime, timedelta, timezone` no topo do arquivo de teste (junto dos imports já existentes).

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `pytest tests/test_cache_email.py -v`
Expected: FAIL com `AttributeError: module 'cache_email' has no attribute 'sincronizar_um_passo'` (e `_parse`)

- [ ] **Step 3: Adicionar `sincronizar_um_passo` em `cache_email.py`**

No topo do arquivo, adicionar aos imports existentes:

```python
from datetime import datetime, timedelta, timezone
```

No final do arquivo:

```python
DIAS_BACKFILL = 730  # ~2 anos
TAMANHO_BLOCO_DIAS = 30
MARGEM_INCREMENTAL = timedelta(days=1)


def _fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _limite_backfill(agora):
    return agora - timedelta(days=DIAS_BACKFILL)


def sincronizar_um_passo(token, cache, agora=None):
    """Avanca uma unidade de sincronizacao do cache local e grava o
    resultado em disco.

    Se alguma pasta ainda nao cobre os ultimos DIAS_BACKFILL dias, busca
    mais um bloco mensal dessa pasta (do mais recente para o mais antigo)
    e devolve {"pasta": nome, "mes": "AAAA-MM"} -- o chamador deve repetir
    a chamada ate receber None. Quando todas as pastas ja tem o backfill
    completo, faz a sincronizacao incremental (mensagens novas desde a
    ultima vez) de todas elas numa unica chamada e devolve None.
    """
    agora = agora or datetime.now(timezone.utc)
    limite = _limite_backfill(agora)
    ids_pastas = {}

    def resolver(pasta):
        if pasta in ("inbox", "sentitems"):
            return pasta
        if not ids_pastas:
            ids_pastas.update(_resolver_ids_pastas(token))
        return ids_pastas.get(pasta, pasta)

    pasta_pendente = None
    for pasta in PASTAS:
        estado = cache["pastas"][pasta]
        completo_ate = (_parse(estado["backfill_completo_ate"])
                        if estado["backfill_completo_ate"] else None)
        if completo_ate is None or completo_ate > limite:
            pasta_pendente = pasta
            break

    if pasta_pendente:
        pasta = pasta_pendente
        config = PASTAS[pasta]
        estado = cache["pastas"][pasta]
        fim = (_parse(estado["backfill_completo_ate"])
               if estado["backfill_completo_ate"] else agora)
        inicio_bloco = max(limite, fim - timedelta(days=TAMANHO_BLOCO_DIAS))
        msgs = _buscar(token, resolver(pasta), config,
                       _fmt(inicio_bloco), _fmt(fim))
        for msg in msgs:
            estado["mensagens"][msg["id"]] = _registro_de(msg, config)
        estado["backfill_completo_ate"] = _fmt(inicio_bloco)
        if inicio_bloco <= limite:
            estado["ultimo_sync"] = _fmt(agora)
        salvar_cache(cache)
        return {"pasta": pasta, "mes": inicio_bloco.strftime("%Y-%m")}

    for pasta, config in PASTAS.items():
        estado = cache["pastas"][pasta]
        desde = (_parse(estado["ultimo_sync"]) - MARGEM_INCREMENTAL
                 if estado["ultimo_sync"] else limite)
        msgs = _buscar(token, resolver(pasta), config, _fmt(desde))
        for msg in msgs:
            estado["mensagens"][msg["id"]] = _registro_de(msg, config)
        estado["ultimo_sync"] = _fmt(agora)
    salvar_cache(cache)
    return None
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `pytest tests/test_cache_email.py -v`
Expected: PASS (19 testes: 14 anteriores + 5 novos)

- [ ] **Step 5: Commit**

```bash
git add cache_email.py tests/test_cache_email.py
git commit -m "Adiciona sincronizacao em blocos (backfill resumivel + incremental)"
```

---

### Task 4: Refatorar `rotina_pendencias.py` para consumir o cache

**Files:**
- Modify: `rotina_pendencias.py`
- Test: `tests/test_rotina_pendencias.py` (novo)

**Interfaces:**
- Consumes: `cache_email.carregar_cache()`, `cache_email.mensagens(cache, pasta)`, `cache_email.sincronizar_um_passo(token, cache, agora=None)` (Tasks 1-3)
- Produces: `analisar(cache: dict, dias: int = 30) -> dict` (mesmo formato de saída de antes: `gerado_em`, `dias`, `contagens`, `pendentes`, `provaveis`, `avisos`, `baixados`, `retornados`, `status`, `buracos`). Consumido por `painel.py` na Task 5.

- [ ] **Step 1: Escrever os testes de conciliação sobre o cache (devem falhar: assinatura antiga)**

Criar `tests/test_rotina_pendencias.py`:

```python
from datetime import datetime, timedelta, timezone

import cache_email as ce
import rotina_pendencias as rp


def _cache_com_mensagens(inbox=None, sentitems=None):
    cache = ce._cache_vazio()
    for msg_id, registro in (inbox or {}).items():
        cache["pastas"]["inbox"]["mensagens"][msg_id] = registro
    for msg_id, registro in (sentitems or {}).items():
        cache["pastas"]["sentitems"]["mensagens"][msg_id] = registro
    return cache


def _iso(dias_atras):
    return (datetime.now(timezone.utc) - timedelta(days=dias_atras)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def test_exame_sem_laudo_e_pendente(monkeypatch):
    monkeypatch.setattr(rp, "carregar_baixas", lambda: {})
    cache = _cache_com_mensagens(inbox={
        "m1": {"assunto": "Exame", "de": "contato@ids.med.br",
               "recebido": _iso(2), "conversa": "c1",
               "anexos": ["ED9-00159 MARIA SILVA.dmw"], "corpo_texto": ""},
    })
    dados = rp.analisar(cache, dias=30)
    assert dados["contagens"]["pendentes"] == 1
    assert dados["pendentes"][0]["codigo"] == "ED9-00159"
    assert dados["pendentes"][0]["nome"] == "MARIA SILVA"
    assert dados["pendentes"][0]["empresa"] == "IDS"


def test_exame_com_laudo_enviado_e_retornado(monkeypatch):
    monkeypatch.setattr(rp, "carregar_baixas", lambda: {})
    cache = _cache_com_mensagens(
        inbox={"m1": {"assunto": "Exame", "de": "contato@ids.med.br",
                      "recebido": _iso(5), "conversa": "c1",
                      "anexos": ["ED9-00159 MARIA SILVA.dmw"], "corpo_texto": ""}},
        sentitems={"s1": {"assunto": "RE: Exame", "recebido": _iso(2),
                          "conversa": "c1", "anexos": ["ED9-00159.pdf"]}},
    )
    dados = rp.analisar(cache, dias=30)
    assert dados["contagens"]["retornados"] == 1
    assert dados["contagens"]["pendentes"] == 0
    assert dados["retornados"][0]["retornado_em"] == _iso(2)


def test_baixa_manual_remove_de_pendentes(monkeypatch):
    monkeypatch.setattr(rp, "carregar_baixas",
                        lambda: {"ED9-00159": "resolvido por telefone"})
    cache = _cache_com_mensagens(inbox={
        "m1": {"assunto": "Exame", "de": "contato@ids.med.br",
               "recebido": _iso(2), "conversa": "c1",
               "anexos": ["ED9-00159 MARIA SILVA.dmw"], "corpo_texto": ""},
    })
    dados = rp.analisar(cache, dias=30)
    assert dados["contagens"]["baixados"] == 1
    assert dados["contagens"]["pendentes"] == 0


def test_dias_filtra_exames_e_enviados_fora_da_janela(monkeypatch):
    monkeypatch.setattr(rp, "carregar_baixas", lambda: {})
    cache = _cache_com_mensagens(
        inbox={"m1": {"assunto": "Exame", "de": "contato@ids.med.br",
                      "recebido": _iso(40), "conversa": "c1",
                      "anexos": ["ED9-00159 MARIA SILVA.dmw"], "corpo_texto": ""}},
        sentitems={"s1": {"assunto": "RE: Exame", "recebido": _iso(35),
                          "conversa": "c1", "anexos": ["ED9-00159.pdf"]}},
    )
    dados = rp.analisar(cache, dias=30)
    assert dados["contagens"]["recebidos"] == 0
    assert dados["pendentes"] == [] and dados["retornados"] == []


def test_buracos_de_numeracao_prefixo_dedicado(monkeypatch):
    monkeypatch.setattr(rp, "carregar_baixas", lambda: {})
    cache = _cache_com_mensagens(inbox={
        "m1": {"assunto": "Exame", "de": "contato@ids.med.br",
               "recebido": _iso(3), "conversa": "c1",
               "anexos": ["0RC-00100 FULANO.dmw"], "corpo_texto": ""},
        "m2": {"assunto": "Exame", "de": "contato@ids.med.br",
               "recebido": _iso(2), "conversa": "c2",
               "anexos": ["0RC-00102 CICLANO.dmw"], "corpo_texto": ""},
    })
    dados = rp.analisar(cache, dias=30)
    assert dados["buracos"] == ["0RC-00101"]
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `pytest tests/test_rotina_pendencias.py -v`
Expected: FAIL com `TypeError: analisar() missing 1 required positional argument` ou erro de assinatura

- [ ] **Step 3: Atualizar o docstring e os imports de `rotina_pendencias.py`**

Substituir o docstring do módulo (linhas 1-24) por:

```python
# -*- coding: utf-8 -*-
"""
Rotina de conciliacao de exames MAPA: quais exames recebidos ja foram
retornados (laudo enviado) e quais estao pendentes.

Uso:  py rotina_pendencias.py [--dias 30] [--listar-retornados] [--salvar-historico]

Logica (descoberta na investigacao da caixa):
 - Exames chegam como anexo .dmw cujo nome contem o codigo unico (ex. ED9-00159).
 - A doutora responde na MESMA conversa anexando o laudo <codigo>.pdf.
 - Apos responder, a mensagem costuma ser movida da Caixa de Entrada
   para a pasta MAPA; a caixa de entrada funciona como fila de pendentes.

Classificacao de cada exame recebido:
 1. RETORNADO: um PDF com o mesmo codigo foi enviado.
 2. BAIXADO: codigo consta em baixas.txt (resolvido fora do email).
 3. PROVAVEL: sem PDF do codigo, mas nome parecido (>=85%) em anexo ou
    assunto de resposta enviada apos o recebimento.
 4. AVISO: conversa respondida, mas sem PDF nem nome batendo.
 5. PENDENTE: nada disso.

As mensagens vem do cache local (cache_email.py), que sincroniza com o
Outlook em segundo plano; este modulo nao faz chamada de rede. O nucleo
esta em analisar(); o painel web (painel.py) usa a mesma funcao.
"""
```

Substituir o bloco de imports (linhas 26-44) por:

```python
import argparse
import difflib
import html as htmlmod
import os
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import cache_email
import outlook_auth

# inbox = pendentes; MAPA = arquivadas; UNIMED e IDS tambem recebem exames
PASTAS_RECEBIDOS = ["inbox", "MAPA", "UNIMED", "IDS"]
RE_CODIGO = re.compile(r"\b([A-Z0-9]{2,4})[-\s]?(\d{4,6})\b")
RE_NOME = re.compile(r"([A-ZÀ-Ü][A-Za-zÀ-ü]+(?:[ ][A-Za-zÀ-ü]{2,}){1,7})")
RE_LIXO_NOME = re.compile(
    r"(?i)\s+(att|req|requisicao|requisição|motivo|medicamentos?|exames?|"
    r"atenciosamente|controle|resultados?|segue|data|obs|laudar)\b.*$")
RE_ASSUNTO_LIXO = re.compile(
    r"(?i)\b(re|res|fw|fwd|enc|mapa|maps|laudar|laudo|urgente|und?|unid|"
    r"unidade|dra?|gisele|com|sem|requisicao|requisição|para|dia|"
    r"resultados?)\b|[\d/:.\-–]")
ARQ_BAIXAS = "baixas.txt"
# padroes de prazo de entrega no texto dos emails das fontes:
# "RESULTADOS 29/07", "resultado para 28/07/2026", "MAPAS PARA 28/07",
# "para serem entregues ate o dia 29/07", "RESULTADO MAPA 27/07"
RE_PRAZOS = [
    re.compile(r"(?i)resultados?\W{0,8}(?:para\s*|dia\s*)?"
               r"(\d{1,2})/0*(\d{1,3})(?:/(\d{2,4}))?"),
    re.compile(r"(?i)resultados?\s+mapa\s+"
               r"(\d{1,2})/0*(\d{1,3})(?:/(\d{2,4}))?"),
    re.compile(r"(?i)entregues?\s*(?:ate\s*)?(?:o\s*)?(?:dia\s*)?"
               r"(\d{1,2})/0*(\d{1,3})(?:/(\d{2,4}))?"),
    re.compile(r"(?i)mapas?\s+para\s+(?:o\s*)?(?:dia\s*)?"
               r"(\d{1,2})/0*(\d{1,3})(?:/(\d{2,4}))?"),
]
# sem prazo declarado, considera atrasado apos N dias do recebimento
DIAS_SEM_PRAZO = 5

# dominio do remetente -> empresa
EMPRESAS = {
    "ids.med.br": "IDS",
    "cardiopro.com.br": "CardioPro",
    "unimedsorocaba.coop.br": "Unimed",
    "eletrocardio.com.br": "Eletrocardio",
}
# prefixo do codigo do exame -> empresa (mais confiavel que o remetente,
# pois exames Unimed chegam encaminhados por giperroud@uol.com.br)
PREFIXO_EMPRESA = {
    "CCQ": "Unimed", "6OA": "Unimed",
    "CY0": "CardioPro",
    "ED9": "IDS", "0RC": "IDS", "0NS": "IDS", "9IS": "IDS", "0S3": "IDS",
}
```

(Removidos: `import json`, `import urllib.parse`, `import urllib.request` e a constante `GRAPH`, que não são mais usados neste módulo: a comunicação com o Graph API mora inteira em `cache_email.py`. Adicionado `import cache_email`.)

- [ ] **Step 4: Remover `gget()` e `listar()`**

Apagar inteiramente a seção (era o bloco "acesso http", logo antes de `codigos_de_anexos`):

```python
# ---------------------------------------------------------------- acesso http
def gget(token, url):
    ...

def listar(token, pasta_id, select, cutoff_iso, campo_data, expand=None):
    ...
```

- [ ] **Step 5: Adaptar `codigos_de_anexos`, `texto_plano` e `nomes_nas_respostas`**

Substituir:

```python
def codigos_de_anexos(msg, extensoes):
    """Extrai codigos normalizados (PREFIXO-NUMERO) dos nomes de anexos."""
    achados = []
    for a in msg.get("attachments", []):
        nome = (a.get("name") or "").upper()
        if not any(nome.endswith(e) for e in extensoes):
            continue
        m = RE_CODIGO.search(nome)
        if m:
            achados.append((f"{m.group(1)}-{m.group(2)}", a.get("name")))
    return achados


def texto_plano(msg):
    corpo = msg.get("body", {}).get("content", "") or ""
    corpo = re.sub(r"<style.*?</style>", " ", corpo, flags=re.S | re.I)
    corpo = re.sub(r"<[^>]+>", " ", corpo)
    corpo = htmlmod.unescape(corpo)
    return re.sub(r"\s+", " ", (msg.get("subject") or "") + " " + corpo)
```

por:

```python
def codigos_de_anexos(nomes_anexos, extensoes):
    """Extrai codigos normalizados (PREFIXO-NUMERO) dos nomes de anexos."""
    achados = []
    for nome in nomes_anexos:
        nome_upper = (nome or "").upper()
        if not any(nome_upper.endswith(e) for e in extensoes):
            continue
        m = RE_CODIGO.search(nome_upper)
        if m:
            achados.append((f"{m.group(1)}-{m.group(2)}", nome))
    return achados


def texto_plano(m):
    """Assunto + corpo (ja em texto plano no cache) normalizado."""
    return re.sub(r"\s+", " ", (m.get("assunto") or "") + " " +
                  (m.get("corpo_texto") or ""))
```

Substituir:

```python
def nomes_nas_respostas(enviados):
    """Candidatos a nome de paciente em anexos e assuntos dos enviados."""
    candidatos = []  # (nome_normalizado, origem, data)
    for m in enviados:
        data = m["sentDateTime"]
        for a in m.get("attachments", []):
            base = re.sub(r"(?i)\.(pdf|dmw|png|jpe?g|docx?)$", "",
                          a.get("name") or "")
            base = RE_CODIGO.sub("", base)
            base = re.sub(r"[_\d]+", " ", base)
            base = re.sub(r"\s+", " ", base).strip(" -_.")
            if len(base.split()) >= 2:
                candidatos.append(
                    (normalizar(base), f"anexo '{a.get('name')}'", data))
        assunto = m.get("subject") or ""
        limpo = re.sub(r"\s+", " ", RE_ASSUNTO_LIXO.sub(" ", assunto)).strip()
        if len(limpo.split()) >= 2:
            candidatos.append(
                (normalizar(limpo), f"assunto '{assunto[:60]}'", data))
    return candidatos
```

por:

```python
def nomes_nas_respostas(enviados):
    """Candidatos a nome de paciente em anexos e assuntos dos enviados."""
    candidatos = []  # (nome_normalizado, origem, data)
    for m in enviados:
        data = m["recebido"]
        for nome_anexo in m.get("anexos", []):
            base = re.sub(r"(?i)\.(pdf|dmw|png|jpe?g|docx?)$", "", nome_anexo)
            base = RE_CODIGO.sub("", base)
            base = re.sub(r"[_\d]+", " ", base)
            base = re.sub(r"\s+", " ", base).strip(" -_.")
            if len(base.split()) >= 2:
                candidatos.append(
                    (normalizar(base), f"anexo '{nome_anexo}'", data))
        assunto = m.get("assunto") or ""
        limpo = re.sub(r"\s+", " ", RE_ASSUNTO_LIXO.sub(" ", assunto)).strip()
        if len(limpo.split()) >= 2:
            candidatos.append(
                (normalizar(limpo), f"assunto '{assunto[:60]}'", data))
    return candidatos
```

- [ ] **Step 6: Reescrever `analisar()` para consumir o cache**

Substituir a função inteira (da assinatura `def analisar(dias=30, token=None):` até o `return {...}` no final dela) por:

```python
def analisar(cache, dias=30):
    """Roda a conciliacao sobre as mensagens ja sincronizadas no cache
    local (cache_email.py). Nao faz nenhuma chamada de rede."""
    agora = datetime.now(timezone.utc)
    cutoff = (agora - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ---- recebidos: exames (.dmw) ----
    exames = {}
    for pasta in PASTAS_RECEBIDOS:
        for m in cache_email.mensagens(cache, pasta).values():
            if m["recebido"] < cutoff:
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
                if m["recebido"] >= cutoff]
    codigos_enviados = {}
    conversas_respondidas = defaultdict(list)
    for m in enviados:
        if m.get("conversa"):
            conversas_respondidas[m["conversa"]].append(m["recebido"])
        for codigo, _ in codigos_de_anexos(m["anexos"], (".PDF",)):
            d = codigos_enviados.get(codigo)
            if d is None or m["recebido"] > d:
                codigos_enviados[codigo] = m["recebido"]

    # ---- conciliacao ----
    candidatos_nome = nomes_nas_respostas(enviados)
    baixas = carregar_baixas()
    pendentes, retornados, provaveis, avisos, baixados = [], [], [], [], []
    hoje = agora.strftime("%Y-%m-%d")
    for codigo, ex in sorted(exames.items(), key=lambda kv: kv[1]["recebido"]):
        ex["dias_espera"] = (
            agora - datetime.fromisoformat(ex["recebido"].replace("Z", "+00:00"))
        ).days
        ex["atrasado"] = (ex["prazo"] < hoje if ex.get("prazo")
                          else ex["dias_espera"] >= DIAS_SEM_PRAZO)
        if codigo in codigos_enviados:
            ex["retornado_em"] = codigos_enviados[codigo]
            if codigo in baixas:
                ex["baixa"] = baixas[codigo]
            retornados.append(ex)
            continue
        if codigo in baixas:
            ex["baixa"] = baixas[codigo]
            baixados.append(ex)
            continue
        match = (melhor_match(ex["nome"], candidatos_nome, ex["recebido"])
                 if ex["nome"] else None)
        respostas = [
            d for d in conversas_respondidas.get(ex["conversa"], [])
            if d > ex["recebido"]
        ]
        if match:
            ex["evidencia"] = match
            provaveis.append(ex)
        elif respostas:
            avisos.append(ex)
        else:
            pendentes.append(ex)

    # ---- status da caixa ----
    por_fonte = defaultdict(list)
    for ex in exames.values():
        por_fonte[ex["fonte"]].append(ex["recebido"])
    fontes = []
    for fonte, datas in sorted(por_fonte.items(), key=lambda kv: -len(kv[1])):
        u = max(datas)
        dias_mudo = (
            agora - datetime.fromisoformat(u.replace("Z", "+00:00"))
        ).days
        fontes.append({"fonte": fonte, "empresa": empresa_de(fonte),
                       "exames": len(datas), "ultimo": u,
                       "dias_sem_enviar": dias_mudo})
    por_empresa = defaultdict(lambda: {"exames": 0, "pendentes": 0})
    for ex in exames.values():
        por_empresa[ex["empresa"]]["exames"] += 1
    for ex in pendentes:
        por_empresa[ex["empresa"]]["pendentes"] += 1
    empresas = [
        {"empresa": nome, **dados}
        for nome, dados in sorted(por_empresa.items(),
                                  key=lambda kv: -kv[1]["exames"])
    ]
    ultimo = (max(exames.values(), key=lambda e: e["recebido"])
              if exames else None)

    # ---- buracos de numeracao ----
    # so vale para prefixos cuja sequencia e dedicada a Dra.; CY0/ED9/CCQ/
    # 6OA/9IS sao numeracoes compartilhadas com outros medicos (chegam
    # numeros alternados) e gerariam falso "faltou receber"
    PREFIXOS_DEDICADOS = {"0RC", "0NS"}
    por_prefixo = defaultdict(dict)
    for codigo, ex in exames.items():
        p, n = codigo.split("-")
        if p not in PREFIXOS_DEDICADOS:
            continue
        por_prefixo[p][int(n)] = (len(n), ex["recebido"])
    buracos = []
    for p, nums in por_prefixo.items():
        ordenados = sorted(nums)
        largura = max(v[0] for v in nums.values())
        for a, b in zip(ordenados, ordenados[1:]):
            if not (1 < b - a <= 15):
                continue
            dist_dias = abs(
                (datetime.fromisoformat(nums[b][1].replace("Z", "+00:00"))
                 - datetime.fromisoformat(nums[a][1].replace("Z", "+00:00")))
                .days)
            if dist_dias > 7:
                continue
            for falta in range(a + 1, b):
                cod = f"{p}-{str(falta).zfill(largura)}"
                if cod not in codigos_enviados:
                    buracos.append(cod)

    return {
        "gerado_em": agora.astimezone().strftime("%d/%m/%Y %H:%M"),
        "dias": dias,
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

- [ ] **Step 7: Rodar os testes e confirmar que passam**

Run: `pytest tests/test_rotina_pendencias.py -v`
Expected: PASS (5 testes)

- [ ] **Step 8: Atualizar `main()` (uso via linha de comando)**

Substituir:

```python
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=30)
    ap.add_argument("--listar-retornados", action="store_true")
    ap.add_argument("--salvar-historico", action="store_true",
                    help="salva copia datada em relatorios\\")
    args = ap.parse_args()

    dados = analisar(args.dias)
    relatorio = relatorio_texto(dados, args.listar_retornados)
```

por:

```python
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=30)
    ap.add_argument("--listar-retornados", action="store_true")
    ap.add_argument("--salvar-historico", action="store_true",
                    help="salva copia datada em relatorios\\")
    args = ap.parse_args()

    token = outlook_auth.get_access_token()
    cache = cache_email.carregar_cache()
    while True:
        progresso = cache_email.sincronizar_um_passo(token, cache)
        if not progresso:
            break
        print(f"Sincronizando: {progresso['pasta']} {progresso['mes']}...")

    dados = analisar(cache, args.dias)
    relatorio = relatorio_texto(dados, args.listar_retornados)
```

- [ ] **Step 9: Rodar toda a suíte de testes do projeto e confirmar que nada quebrou**

Run: `pytest -v`
Expected: PASS em todos os testes (os novos desta task, os de `cache_email.py`, e os pré-existentes de `eventos.py`/`ler_repasses.py`/`cruzar_pagamentos.py`/`painel.py`, que não dependem de `rotina_pendencias.analisar`)

- [ ] **Step 10: Commit**

```bash
git add rotina_pendencias.py tests/test_rotina_pendencias.py
git commit -m "Refatora rotina_pendencias.analisar para consumir o cache local de email"
```

---

### Task 5: Orquestrar sincronização e progresso (`painel.py`)

**Files:**
- Modify: `painel.py`

**Interfaces:**
- Consumes: `cache_email.carregar_cache`, `cache_email.sincronizar_um_passo` (Tasks 1-3); `rotina_pendencias.analisar(cache, dias)` (Task 4)
- Produces: resposta de `GET /api/dados` passa a ser `{"sincronizando": {"pasta": str, "mes": str}}` enquanto o backfill está em andamento, ou o objeto `dados` completo de sempre quando termina. Consumido pelo front-end na Task 6.

- [ ] **Step 1: Adicionar o import de `cache_email`**

No topo de `painel.py`, junto dos imports de módulos locais já existentes:

```python
import ler_repasses
import outlook_auth
import rotina_pendencias

import cache_email
```

- [ ] **Step 2: Reescrever o handler de `/api/dados`**

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
                try:
                    import baixar_repasses
                    baixar_repasses.varrer(token)
                except Exception:
                    pass  # sem repasses novos nao pode travar o painel
                with TRAVA:
                    dados = rotina_pendencias.analisar(dias, token=token)
                try:
                    import cruzar_pagamentos
                    dados["pagamentos_orfaos"] = (
                        cruzar_pagamentos.anotar_pagamentos(dados))
                except Exception:
                    dados["pagamentos_orfaos"] = []
                salvar_historico(dados)
                self._json(dados)
```

por:

```python
            elif rota.path == "/api/dados":
                dias = int(parse_qs(rota.query).get("dias", ["30"])[0])
                dias = max(1, min(dias, 365))
                try:
                    token = outlook_auth.get_access_token("silencioso")
                except outlook_auth.AuthExpirada as e:
                    self._json({"precisa_login": True, "mensagem": str(e)})
                    return
                try:
                    import baixar_repasses
                    baixar_repasses.varrer(token)
                except Exception:
                    pass  # sem repasses novos nao pode travar o painel
                with TRAVA:
                    cache = cache_email.carregar_cache()
                    progresso = cache_email.sincronizar_um_passo(token, cache)
                    if progresso:
                        self._json({"sincronizando": progresso})
                        return
                    dados = rotina_pendencias.analisar(cache, dias)
                try:
                    import cruzar_pagamentos
                    dados["pagamentos_orfaos"] = (
                        cruzar_pagamentos.anotar_pagamentos(dados))
                except Exception:
                    dados["pagamentos_orfaos"] = []
                salvar_historico(dados)
                self._json(dados)
```

- [ ] **Step 3: Verificação manual (não há teste automatizado de `/api/dados` hoje: exige token real)**

Run: `py painel.py`

Confirmar no navegador (`http://127.0.0.1:8765`):
1. Com `cache_emails.json` ainda inexistente (primeira vez): a página fica na tela de carregamento por mais tempo (o backfill roda em passos, um por requisição) e eventualmente carrega o painel normalmente.
2. Um segundo `Atualizar email` carrega rápido (sincronização incremental).
3. `cache_emails.json` aparece na raiz do projeto com as 5 pastas preenchidas.

Não faça commit ainda desta verificação manual: ela só é possível de ponta a ponta depois da Task 6 (o front-end da Task 6 é quem trata `sincronizando` de forma amigável; sem ela, o front atual vai exibir um objeto sem `dados.contagens` e quebrar ao tentar renderizar). Prossiga direto para a Task 6 antes de testar no navegador.

- [ ] **Step 4: Commit**

```bash
git add painel.py
git commit -m "painel.py: orquestra sincronizacao incremental do cache de email em /api/dados"
```

---

### Task 6: Progresso do backfill e limpeza do seletor de período (`painel.html`)

**Files:**
- Modify: `painel.html`

**Interfaces:**
- Consumes: resposta `{"sincronizando": {"pasta": str, "mes": "AAAA-MM"}}` de `GET /api/dados` (Task 5); usa a função `formatMes(ym)` já existente no arquivo.

- [ ] **Step 1: Adicionar a linha de status na tela de carregamento**

Substituir:

```html
<div class="tela" id="carregando">
  <div class="spinner"></div>
  <p>Lendo a caixa de email&hellip; isso pode levar um minuto.</p>
</div>
```

por:

```html
<div class="tela" id="carregando">
  <div class="spinner"></div>
  <p>Lendo a caixa de email&hellip; isso pode levar um minuto.</p>
  <p class="nota" id="carregando-status">&nbsp;</p>
</div>
```

- [ ] **Step 2: Remover o aviso de lentidão do seletor de período**

Substituir:

```html
      <option value="180">180 dias (mais lento)</option>
```

por:

```html
      <option value="180">180 dias</option>
```

- [ ] **Step 3: Fazer `carregar()` repetir a chamada enquanto o backfill estiver em andamento**

Substituir:

```javascript
async function carregar() {
  const btn = document.getElementById("btn-atualizar");
  const btnDocs = document.getElementById("btn-atualizar-docs");
  btn.disabled = true;
  btnDocs.disabled = true;
  mostrar("carregando");
  try {
    const dias = document.getElementById("dias").value;
    const r = await fetch("/api/dados?dias=" + dias);
    const d = await r.json();
    if (d.precisa_login) { await telaLogin(); return; }
    if (d.erro) throw new Error(d.erro);
    dados = d;
    render();
    carregarRecebimentos();
    carregarImportacoes();
    mostrar("conteudo");
  } catch (e) {
    const semServidor = (e instanceof TypeError);
    document.getElementById("erro-msg").textContent = semServidor
      ? "Não consegui falar com o programa do painel. Ele funciona junto " +
        "com a janelinha preta que abre com o atalho 'Painel MAPA'; se ela " +
        "foi fechada, feche esta aba e dê duplo clique no atalho de novo."
      : (e.message || String(e));
    mostrar("tela-erro");
  } finally {
    btn.disabled = false;
    btnDocs.disabled = false;
  }
}
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
    const semServidor = (e instanceof TypeError);
    document.getElementById("erro-msg").textContent = semServidor
      ? "Não consegui falar com o programa do painel. Ele funciona junto " +
        "com a janelinha preta que abre com o atalho 'Painel MAPA'; se ela " +
        "foi fechada, feche esta aba e dê duplo clique no atalho de novo."
      : (e.message || String(e));
    mostrar("tela-erro");
  } finally {
    btn.disabled = false;
    btnDocs.disabled = false;
  }
}
```

- [ ] **Step 4: Verificação manual de ponta a ponta**

Run: `py painel.py`

No navegador (`http://127.0.0.1:8765`):
1. Apagar `cache_emails.json` (se existir) e recarregar a página: a tela de carregamento deve mostrar "Lendo histórico: Mês/Ano (pasta)…" trocando de mensagem a cada poucos segundos, até o painel carregar normalmente com os dados de sempre (cartões, pendentes, exames).
2. Clicar em "Atualizar email" de novo: deve carregar rápido, sem mostrar mensagem de histórico (backfill já completo, só sincronização incremental).
3. Selecionar 180 dias no seletor de período: confirma que não tem mais "(mais lento)" no texto da opção, e que carrega instantâneo.
4. Conferir a aba Exames: contagens e listas iguais às de antes da mudança (usar `relatorio_pendencias.txt` de uma execução anterior como referência, se houver).

- [ ] **Step 5: Commit**

```bash
git add painel.html
git commit -m "painel.html: mostra progresso do backfill e remove aviso de lentidao do seletor de periodo"
```

---

## Fora de escopo (ver design)

- Filtro de exibição por data nas telas (sub-projeto de filtros/ordenação de tabelas).
- Fluxo de repasses/financeiro (`baixar_repasses.py`, `ler_repasses.py`, `eventos.py`): já é local, não tocado aqui.
- Detecção de mensagens movidas entre pastas monitoradas ou apagadas da caixa (ver "Fora de escopo" no design).
