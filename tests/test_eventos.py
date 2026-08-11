import os
from datetime import datetime

import eventos as ev

AMOSTRAS = "amostras"


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


def test_itens_cardiopro_shape_completa():
    itens = ev.itens_cardiopro(
        os.path.join(AMOSTRAS, "Repasse Dr. Fernando 2026.xlsx"))
    assert itens
    assert set(itens[0]) == {"empresa", "mod", "data", "nome", "valor",
                             "convenio", "origem"}
    assert itens[0]["valor"] is None


def test_coletar_eventos_shape_e_dedup_exato(tmp_path):
    import shutil
    shutil.copy(os.path.join(AMOSTRAS, "RELATORIO REPASSES - MIBI PCT.pdf"),
                tmp_path / "a.pdf")
    shutil.copy(os.path.join(AMOSTRAS, "RELATORIO REPASSES - MIBI PCT.pdf"),
                tmp_path / "b.pdf")  # reenvio: mesmo conteudo, outro nome
    evs = ev.coletar_eventos(pastas=(str(tmp_path),))
    assert len(evs) == 17  # nao 34
    e0 = next(e for e in evs if e["paciente"] == "Odail Jose Dendevite")
    documento = e0.pop("documento")
    assert documento in ("a.pdf", "b.pdf")
    assert e0 == {"pagador": "IDS", "exame": "Teste Ergométrico MIBI",
                  "paciente": "Odail Jose Dendevite", "data": "2025-01-07",
                  "valor": 98.83, "convenio": "Unimed", "tipo": "pago"}


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
