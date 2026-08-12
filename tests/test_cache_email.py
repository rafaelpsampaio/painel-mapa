import json

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
