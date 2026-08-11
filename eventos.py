# -*- coding: utf-8 -*-
"""Modelo central de eventos de pagamento.

Todo demonstrativo (IDS, Unimed, CardioPro) e reduzido a uma lista unica de
eventos {pagador, exame, paciente, data, valor, convenio, tipo, documento}.
As agregacoes do painel (por mes, por pagador, por exame) e a investigacao
de "sem pagamento" trabalham so em cima dessa lista.
"""

import difflib
import os
import re
from datetime import datetime, timedelta

import openpyxl

import rotina_pendencias as rp
from ler_repasses import (_regex_tolerante, texto_pdf, dinheiro,
                           SETOR_EXAME_LISTAGEM,
                           processar_relatorio_repasses)

# ordem de prioridade quando o mesmo exame aparece pago em mais de uma fonte
PRIORIDADE_PAGADOR = {"IDS": 0, "Unimed": 1, "CardioPro": 2}

# nomes de setor (IDS) e de procedimento (Relatorio de Repasses) -> canonico
EXAME_CANONICO = {
    "MAPA": "MAPA",
    "M.A.P.A": "MAPA",
    "TESTE ERGOMETRICO": "Teste Ergométrico",
    "TESTE ERGOMETRICO MIBI": "Teste Ergométrico MIBI",
    "HONORARIO MEDICO": "Laudo Stress Farmacológico",
    "LAUDO STRESS FARMACOLOGICO": "Laudo Stress Farmacológico",
    "ECG": "Eletrocardiograma",
    "ELETROCARDIOGRAMA": "Eletrocardiograma",
}

# codigos de servico dos demonstrativos Unimed/CardioPro -> canonico
CODIGO_UNIMED_CANONICO = {
    "20102038": "MAPA",
    "20102020": "Holter",
    "40101010": "Eletrocardiograma",
    "10101012": "Consulta",
    "99910073": "Consulta",
    "20101201": "Aval. marca-passo",
}


def exame_canonico(nome):
    """Nome canonico do exame; desconhecido passa como veio (title case)."""
    chave = rp.normalizar(nome)
    return EXAME_CANONICO.get(chave, (nome or "").strip().title())


# convenios conhecidos grudados no fim do campo "nome" da Listagem de
# Repasse da IDS (sem separador); descobertos minerando os sufixos
CONVENIO_DISPLAY = {
    "INTERMEDICA SAUDE S.A": "Intermédica",
    "INTERMEDICA- MEDIPLAN": "Intermédica",
    "CARTAO IDS MATRIZ": "Cartão IDS",
    "HAPVIDA - SOROCABA": "Hapvida",
    "BRADESCO OPERADORA PLANOS S/A": "Bradesco Operadora",
    "BRADESCO SAUDE": "Bradesco Saúde",
    "CAIXA ECONOMICA FEDERAL": "Caixa Econômica Federal",
    "SUL AMERICA": "Sul América",
    "PORTO SEGURO": "Porto Seguro",
    "CEPOS- EMPRESA": "Cepos",
    "UNIMED": "Unimed",
    "AMIL": "Amil",
    "APAS": "Apas",
    "CASSI": "Cassi",
    "CABESP": "Cabesp",
    "MARINHA": "Marinha",
}
_PADROES_CONVENIO = sorted(CONVENIO_DISPLAY, key=len, reverse=True)
_PADROES_CONVENIO = [(c, re.compile(_regex_tolerante(c) + r"$"))
                     for c in _PADROES_CONVENIO]


def separar_convenio(nome):
    """(nome sem o sufixo de convenio, convenio de exibicao ou None)."""
    for canonico, padrao in _PADROES_CONVENIO:
        m = padrao.search(nome or "")
        if m:
            return (nome[:m.start()].strip(), CONVENIO_DISPLAY[canonico])
    return ((nome or "").strip(), None)


# -------------------------------------- extratores de itens por paciente
def data_de(v):
    if hasattr(v, "year"):
        return datetime(v.year, v.month, v.day)
    try:
        return datetime.strptime(str(v)[:10], "%d/%m/%Y")
    except ValueError:
        return None


def data_valida(d):
    """Descarta datas absurdas digitadas errado nos demonstrativos."""
    return (d is not None
            and datetime(2024, 1, 1) <= d <= datetime.now() + timedelta(days=45))


def casa_nome(nome_email, nome_pag):
    """nome_pag pode vir com o convenio grudado no fim (IDS)."""
    a = rp.normalizar(nome_email or "")
    b = rp.normalizar(nome_pag or "")
    if len(a.split()) < 2 or not b:
        return False
    if b.startswith(a) or a in b:
        return True
    return difflib.SequenceMatcher(None, a, b[:len(a) + 4]).ratio() >= 0.85


def itens_ids(caminho):
    txt = texto_pdf(caminho)
    if "Listagem de Repasse" not in txt:
        return []
    itens = []
    for linha in txt.splitlines():
        m = re.match(r"(\d{2}/\d{2}/\d{4})\s+(.+?)\s*M\.A\.P\.A", linha.strip())
        if m:
            mv = re.search(r"R\$\s*([\d\.]+,\d{2})", linha)
            valor = (float(mv.group(1).replace(".", "").replace(",", "."))
                     if mv else None)
            itens.append({"empresa": "IDS", "mod": "MAPA",
                          "data": data_de(m.group(1)),
                          "nome": m.group(2),  # nome + convenio grudados
                          "valor": valor,
                          "origem": os.path.basename(caminho)})
    return itens


def itens_ids_setores(caminho):
    """Itens de pagamento por paciente da Listagem de Repasse da IDS, para os
    setores que NAO sao MAPA (Teste Ergometrico, MIBI, ECG, Laudo Stress...).
    Cabecalho da tabela no PDF: Data Paciente Convenio Exame Pre-Labore Quant."""
    txt = texto_pdf(caminho)
    if "Listagem de Repasse" not in txt:
        return []
    itens = []
    setor_atual = None
    for linha in txt.splitlines():
        linha = linha.strip()
        m = re.match(r"Setor: (?!Selecionado)(.+)", linha)
        if m:
            setor_atual = m.group(1).strip()
            continue
        if not setor_atual or setor_atual == "MAPA":
            continue
        exame_canon = SETOR_EXAME_LISTAGEM.get(setor_atual)
        if not exame_canon:
            continue
        padrao = (r"^(\d{2}/\d{2}/\d{4})\s+(.+?)\s+" +
                  _regex_tolerante(exame_canon) +
                  r"\s+R\s*\$\s*([\d\.]+\s*,\s*\d{2})\s+\d+\s*$")
        m = re.match(padrao, linha)
        if not m:
            continue
        nome = m.group(2).strip()
        itens.append({
            "empresa": "IDS", "mod": setor_atual,
            "data": data_de(m.group(1)), "nome": nome,
            "valor": dinheiro(re.sub(r"\s+", "", m.group(3))),
            "origem": os.path.basename(caminho),
            "convenio": separar_convenio(nome)[1],
        })
    return itens


def itens_unimed(caminho):
    """No PDF da Unimed cada campo sai numa linha:
    ... NOME / UF / plano(A|E) / data / CODIGO-SERVICO / qt / R$ ... / R$ pago"""
    txt = texto_pdf(caminho)
    if "UNIMED" not in txt.upper():
        return []
    linhas = [l.strip() for l in txt.splitlines()]
    itens = []
    for i, linha in enumerate(linhas):
        m = re.match(r"^(\d{8})-", linha)
        if not m or i < 4:
            continue
        codigo = m.group(1)
        mod = CODIGO_UNIMED_CANONICO.get(codigo)
        if not mod:
            continue
        data = data_de(linhas[i - 1])
        if not data:
            continue
        # nome: linhas alfabeticas logo acima do codigo de plano (i-3)
        partes = []
        j = i - 4
        while j >= 0 and len(partes) < 3:
            cand = linhas[j]
            if not cand or re.search(r"\d", cand):
                break  # protocolo/lote ou vazio: acabou o nome
            partes.insert(0, cand)
            j -= 1
        nome = " ".join(partes).strip()
        if len(nome.split()) < 2:
            continue
        # valor pago: ultimo "R$ ..." antes do proximo item
        valor = None
        for l2 in linhas[i + 1:i + 9]:
            if re.match(r"^\d{8}-", l2):
                break
            mv = re.match(r"^R\$\s*([\d\.,]+)$", l2)
            if mv:
                valor = dinheiro(mv.group(1))
        itens.append({"empresa": "Unimed", "mod": mod, "data": data,
                      "nome": nome, "valor": valor, "convenio": None,
                      "origem": os.path.basename(caminho)})
    return itens


def itens_cardiopro(caminho):
    wb = openpyxl.load_workbook(caminho, data_only=True)
    if not any("repasse" in aba.lower() for aba in wb.sheetnames):
        return []  # planilha de outro formato
    itens = []
    for aba in wb.sheetnames:
        for row in wb[aba].iter_rows(values_only=True):
            cells = list(row)
            for i, c in enumerate(cells):
                v = str(c).strip() if c is not None else ""
                if v != "20102038":
                    continue
                nome = cells[i + 1] if i + 1 < len(cells) else None
                nome = str(nome).strip() if nome else ""
                if len(nome.split()) < 2:
                    continue
                data = None
                for c2 in cells[i + 2:i + 6]:
                    d = data_de(c2) if c2 is not None else None
                    if d:
                        data = d
                        break
                itens.append({"empresa": "CardioPro", "mod": "MAPA",
                              "data": data, "nome": nome, "convenio": None,
                              "origem": f"{os.path.basename(caminho)} [{aba}]"})
    return itens


def itens_relatorio(caminho):
    """Itens por paciente do Relatorio de Repasses Medicos (IDS)."""
    r = processar_relatorio_repasses(caminho)
    if not r:
        return []
    return [{"empresa": "IDS", "mod": it["procedimento"],
             "data": datetime.strptime(it["data"], "%Y-%m-%d"),
             "nome": it["paciente"], "valor": it["valor"],
             "convenio": separar_convenio(it["convenio"])[1] or it["convenio"].title(),
             "origem": r["arquivo"]}
            for it in r["itens"]]
