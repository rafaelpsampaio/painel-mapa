import io
import json
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone

import pytest

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


def test_carregar_cache_json_valido_mas_formato_errado_retorna_esqueleto(tmp_path, monkeypatch):
    arq = tmp_path / "cache_emails.json"
    arq.write_text("42")
    monkeypatch.setattr(ce, "ARQ_CACHE", str(arq))
    cache = ce.carregar_cache()
    assert set(cache["pastas"]) == {"inbox", "MAPA", "UNIMED", "IDS", "sentitems"}
    for estado in cache["pastas"].values():
        assert estado == {"backfill_completo_ate": None, "ultimo_sync": None,
                          "mensagens": {}}


def test_carregar_cache_json_lista_retorna_esqueleto(tmp_path, monkeypatch):
    arq = tmp_path / "cache_emails.json"
    arq.write_text("[1, 2, 3]")
    monkeypatch.setattr(ce, "ARQ_CACHE", str(arq))
    cache = ce.carregar_cache()
    assert cache["pastas"]["inbox"]["mensagens"] == {}


def test_carregar_cache_pastas_com_formato_errado_retorna_esqueleto(tmp_path, monkeypatch):
    arq = tmp_path / "cache_emails.json"
    arq.write_text(json.dumps({"pastas": ["nao", "e", "dict"]}))
    monkeypatch.setattr(ce, "ARQ_CACHE", str(arq))
    cache = ce.carregar_cache()
    assert cache["pastas"]["inbox"]["mensagens"] == {}


def test_carregar_cache_pasta_individual_com_formato_errado_usa_default(tmp_path, monkeypatch):
    arq = tmp_path / "cache_emails.json"
    arq.write_text(json.dumps({"pastas": {"inbox": "corrompido",
                                          "MAPA": {"ultimo_sync": "2026-08-12T10:00:00Z"}}}))
    monkeypatch.setattr(ce, "ARQ_CACHE", str(arq))
    cache = ce.carregar_cache()
    assert cache["pastas"]["inbox"] == {"backfill_completo_ate": None,
                                        "ultimo_sync": None, "mensagens": {}}
    assert cache["pastas"]["MAPA"]["ultimo_sync"] == "2026-08-12T10:00:00Z"


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


def test_registro_de_colapsa_espacos_e_quebras_de_linha_do_corpo():
    msg = {
        "subject": "Exame MAPA",
        "receivedDateTime": "2026-08-01T10:00:00Z",
        "conversationId": "conv-1",
        "attachments": [],
        "body": {"content": (
            "<html>\n  <body>\n    <p>Segue   anexo.</p>\n\n"
            "    <p>HELENA MARIA</p>\n  </body>\n</html>\n"
        )},
    }
    registro = ce._registro_de(msg, ce.PASTAS["inbox"])
    assert registro["corpo_texto"] == "Segue anexo. HELENA MARIA"
    assert "\n" not in registro["corpo_texto"]
    assert "  " not in registro["corpo_texto"]


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


def _msg(id_, subject="x"):
    return {"id": id_, "subject": subject, "receivedDateTime": "2026-08-12T00:00:00Z"}


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


def test_backfill_retomado_em_sessoes_diferentes_ancora_ultimo_sync_no_inicio(tmp_path, monkeypatch):
    """Regressao: um backfill pode ser retomado em sessoes bem separadas no
    tempo (app fechado e reaberto dias depois), ja que cada chamada avanca
    so um bloco. ultimo_sync precisa ficar ancorado no INICIO do backfill
    da pasta (T0), nao no "agora" do bloco que o conclui (que pode ser
    dias depois de T0) -- senao mensagens chegadas durante o proprio
    backfill caem num buraco que nem o backfill nem a sincronizacao
    incremental cobrem."""
    monkeypatch.setattr(ce, "ARQ_CACHE", str(tmp_path / "cache_emails.json"))
    monkeypatch.setattr(ce, "DIAS_BACKFILL", 70)
    cache = ce.carregar_cache()
    monkeypatch.setattr(ce, "_buscar", lambda *a, **k: [])
    monkeypatch.setattr(ce, "_resolver_ids_pastas",
                        lambda token: {"MAPA": "m", "UNIMED": "u", "IDS": "i"})

    t0 = datetime(2026, 8, 12, tzinfo=timezone.utc)

    # bloco 1: inicia o backfill do inbox (primeira pasta) em T0
    p1 = ce.sincronizar_um_passo("tok", cache, agora=t0)
    assert p1["pasta"] == "inbox"
    assert cache["pastas"]["inbox"]["ultimo_sync"] == ce._fmt(t0)

    # bloco 2: sessao retomada 3 dias depois -- ainda backfill do inbox
    p2 = ce.sincronizar_um_passo("tok", cache, agora=t0 + timedelta(days=3))
    assert p2["pasta"] == "inbox"
    assert cache["pastas"]["inbox"]["ultimo_sync"] == ce._fmt(t0)

    # bloco 3: sessao retomada 5 dias depois de T0 -- conclui o backfill
    # do inbox
    p3 = ce.sincronizar_um_passo("tok", cache, agora=t0 + timedelta(days=5))
    assert p3["pasta"] == "inbox"
    limite_final = (t0 + timedelta(days=5)) - timedelta(days=ce.DIAS_BACKFILL)
    assert ce._parse(cache["pastas"]["inbox"]["backfill_completo_ate"]) <= limite_final

    # ultimo_sync continua perto de T0 (inicio do backfill), nao dos 5
    # dias depois em que o ultimo bloco rodou
    ultimo_sync = ce._parse(cache["pastas"]["inbox"]["ultimo_sync"])
    assert ultimo_sync == t0


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
