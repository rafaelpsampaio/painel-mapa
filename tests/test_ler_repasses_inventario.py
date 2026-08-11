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
    assert len(resultado["email"]["arquivos"]) == 7


def test_importacoes_sem_pasta_local_configurada(monkeypatch):
    monkeypatch.setattr(lr, "pasta_documentos", lambda: None)
    resultado = lr.importacoes(pasta_email=AMOSTRAS)
    assert resultado["local"] == {"pasta": "", "arquivos": []}


def test_inventario_pasta_nome_com_colchetes(tmp_path):
    """Pasta com [ ] no nome nao pode confundir o glob.glob e sumir com os arquivos."""
    pasta = tmp_path / "Demonstrativos [2026]"
    pasta.mkdir()
    shutil.copy(os.path.join(AMOSTRAS, "DEMAIS EXAMES - FERNANDO SAMPAIO.pdf"), pasta)
    itens = lr.inventario_pasta(str(pasta))
    assert [i["arquivo"] for i in itens] == ["DEMAIS EXAMES - FERNANDO SAMPAIO.pdf"]


def test_coletar_pasta_nome_com_colchetes(tmp_path):
    """Mesmo bug de glob.escape, na funcao usada pela aba Financeiro."""
    pasta = tmp_path / "Demonstrativos [2026]"
    pasta.mkdir()
    shutil.copy(os.path.join(AMOSTRAS, "DEMAIS EXAMES - FERNANDO SAMPAIO.pdf"), pasta)
    docs = lr.coletar(pastas=(str(pasta),))
    assert [d["arquivo"] for d in docs] == ["DEMAIS EXAMES - FERNANDO SAMPAIO.pdf"]


def test_inspecionar_arquivo_erro_na_classificacao_nao_derruba(monkeypatch):
    """Se algo quebrar depois do _tentar_parsers (ex.: _macro), vira card 'erro',
    nao uma excecao que sobe e derruba o /api/importacoes inteiro."""
    caminho = os.path.join(AMOSTRAS, "DEMAIS EXAMES - FERNANDO SAMPAIO.pdf")

    def _macro_quebrado(r):
        raise KeyError("campo inesperado")

    monkeypatch.setattr(lr, "_macro", _macro_quebrado)
    item = lr._inspecionar_arquivo(caminho)
    assert item["status"] == "erro"
    assert item["motivo"]


def test_coletar_nao_conta_2x_mesmo_conteudo_com_nomes_diferentes(tmp_path):
    """O mesmo demonstrativo pode chegar por email 2x (reenvio), baixado com
    nomes diferentes (prefixo de data). Sem isso, o total da aba Financeiro
    duplica: mesmo exame/valor contado 2x."""
    origem = os.path.join(AMOSTRAS, "DEMAIS EXAMES - FERNANDO SAMPAIO.pdf")
    shutil.copy(origem, tmp_path / "2026-06-24_DEMAIS EXAMES.pdf")
    shutil.copy(origem, tmp_path / "2026-07-08_DEMAIS EXAMES.pdf")
    docs = lr.coletar(pastas=(str(tmp_path),))
    assert len(docs) == 1
    assert docs[0]["total"] == {"qtd": 239, "valor": 11282.34}


def test_coletar_mantem_arquivos_de_mesmo_nome_e_conteudo_diferente(tmp_path):
    """Caso oposto: nomes iguais (ex.: 'MAPA.pdf' na pasta local e na pasta do
    email), conteudo diferente. Hoje o dedup por nome descartaria o segundo
    silenciosamente; deve manter os dois."""
    pasta_a = tmp_path / "a"
    pasta_b = tmp_path / "b"
    pasta_a.mkdir()
    pasta_b.mkdir()
    shutil.copy(os.path.join(AMOSTRAS, "DEMAIS EXAMES - FERNANDO SAMPAIO.pdf"),
                pasta_a / "demonstrativo.pdf")
    shutil.copy(os.path.join(AMOSTRAS, "MAPA - DR. FERNANDO SAMPAIO.pdf"),
                pasta_b / "demonstrativo.pdf")
    docs = lr.coletar(pastas=(str(pasta_a), str(pasta_b)))
    assert len(docs) == 2
