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
