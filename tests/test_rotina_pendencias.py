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
    dados = rp.analisar(cache)
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
    dados = rp.analisar(cache)
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
    dados = rp.analisar(cache)
    assert dados["contagens"]["baixados"] == 1
    assert dados["contagens"]["pendentes"] == 0


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
    dados = rp.analisar(cache)
    assert dados["buracos"] == ["0RC-00101"]
