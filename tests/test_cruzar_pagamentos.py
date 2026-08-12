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


def test_anotar_pagamentos_baixa_nao_marca_esperado(monkeypatch):
    """Exame retornado com baixa nao deve ficar pagamento_esperado mesmo
    dentro da janela de cobertura do pagador; o irmao sem baixa, na mesma
    janela, deve ser marcado normalmente."""
    evs = [{"pagador": "IDS", "exame": "MAPA", "paciente": "Sem Par Nenhum",
            "data": "2026-03-12", "valor": 45.0, "convenio": None,
            "tipo": "pago", "documento": "ids.pdf"}]
    monkeypatch.setattr(cp, "coletar_eventos", lambda pastas=None: evs)
    com_baixa = _exame("D111", "FULANO BAIXADO", "2026-03-12T00:00:00Z",
                        empresa="IDS")
    com_baixa["baixa"] = "D111: resolvido fora do email"
    sem_baixa = _exame("D222", "CICLANO PENDENTE", "2026-03-12T00:00:00Z",
                        empresa="IDS")
    dados = _dados([com_baixa, sem_baixa])
    cp.anotar_pagamentos(dados)
    assert "pagamento_esperado" not in com_baixa
    assert sem_baixa.get("pagamento_esperado") is True
