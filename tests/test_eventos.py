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
