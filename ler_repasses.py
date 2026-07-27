# -*- coding: utf-8 -*-
"""
Prototipo: processa os demonstrativos de pagamento recebidos por email
e monta um resumo por empresa e modalidade.

Fontes suportadas (pasta amostras/):
 - IDS: "Listagem de Repasse de Medico" (PDF) - totais por unidade/setor
 - Unimed Sorocaba: Demonstrativo de Pagamento (PDF) - servicos por codigo
 - CardioPro: planilha de repasse mensal (XLSX) - contagem ECG x MAPA

Uso:  py ler_repasses.py
"""

import glob
import os
import re

import openpyxl
from pypdf import PdfReader

PASTA = "amostras"


def texto_pdf(caminho):
    return "\n".join(p.extract_text() or "" for p in PdfReader(caminho).pages)


def dinheiro(s):
    return float(s.replace(".", "").replace(",", "."))


# ---------------------------------------------------------------- IDS
def processar_ids(caminho):
    """Le totais por unidade/setor da Listagem de Repasse da IDS."""
    txt = texto_pdf(caminho)
    if "Listagem de Repasse" not in txt:
        return None
    resumo = {"tipo": "IDS - Listagem de Repasse", "arquivo": os.path.basename(caminho),
              "setores": [], "total": None}
    m = re.search(r"Listagem de Repasse de M.dico\s+Data: (\d{2}/\d{2}/\d{4})", txt)
    if m:
        resumo["emitido_em"] = m.group(1)
    unidade = None
    setor = None
    for linha in txt.splitlines():
        linha = linha.strip()
        # na extracao do PDF a ordem sai "Qtd Exames: N Total ...: R$ V"
        m = re.match(r"Unidade:\s*(.+)", linha)
        if m and "Todas" not in linha:
            unidade = m.group(1).strip()
            continue
        m = re.match(r"Setor:\s*(.+)", linha)
        if m:
            setor = m.group(1).strip()
            continue
        m = re.search(r"Qtd Exames:\s*(\d+)\s*Total para o setor:.*?"
                      r"R\$\s*([\d\.,]+)", linha)
        if m:
            resumo["setores"].append({
                "unidade": unidade, "setor": setor,
                "qtd": int(m.group(1)), "valor": dinheiro(m.group(2)),
            })
            continue
        m = re.search(r"Qtd Exames:\s*(\d+)\s*Total\s*R\$\s*([\d\.,]+)", linha)
        if m:
            resumo["total"] = {"qtd": int(m.group(1)),
                               "valor": dinheiro(m.group(2))}
    return resumo


# ---------------------------------------------------------------- Unimed
SERVICOS_UNIMED = {
    "20102038": "MAPA",
    "20102020": "Holter",
    "40101010": "ECG",
    "10101012": "Consulta",
    "99910073": "Consulta urgencia",
    "20101201": "Aval. marca-passo",
}


def processar_unimed(caminho):
    txt = texto_pdf(caminho)
    if "DEMONSTRATIVO" not in txt.upper() or "UNIMED" not in txt.upper():
        return None
    resumo = {"tipo": "Unimed - Demonstrativo", "arquivo": os.path.basename(caminho),
              "executantes": [], "servicos": {}, "liquido": None}
    m = re.search(r"Per.odo\s*(\d{6})", txt)
    if m:
        resumo["periodo"] = m.group(1)
    for m in re.finditer(
            r"Total prestador:\s*(\d+)\s+(.+?)\s+Servi.os:\s*(\d+)\s*R\$\s*([\d\.,]+)",
            txt):
        resumo["executantes"].append({
            "codigo": m.group(1), "nome": m.group(2).strip(),
            "servicos": int(m.group(3)), "valor": dinheiro(m.group(4)),
        })
    for codigo, nome in SERVICOS_UNIMED.items():
        n = len(re.findall(rf"\b{codigo}-", txt))
        if n:
            resumo["servicos"][nome] = n
    resumo["liquido"] = _valor_na_linha(txt, "total líquido")
    resumo["bruto"] = _valor_na_linha(txt, "emissão da nota")
    return resumo


def _valor_na_linha(txt, chave):
    """Valor R$ na linha que contem a chave, ou na linha seguinte."""
    linhas = txt.splitlines()
    for i, linha in enumerate(linhas):
        if chave.lower() not in linha.lower():
            continue
        proxima = linhas[i + 1] if i + 1 < len(linhas) else ""
        for cand in (linha, proxima):
            m = re.search(r"R\$\s*([\d\.,]+)", cand)
            if m:
                return dinheiro(m.group(1))
    return None


# ---------------------------------------------------------------- CardioPro
def processar_cardiopro(caminho):
    wb = openpyxl.load_workbook(caminho, data_only=True)
    if not any("repasse" in aba.lower() for aba in wb.sheetnames):
        return None  # planilha de outro formato (ex.: contas medicas IDS)
    resumo = {"tipo": "CardioPro - Planilha de repasse",
              "arquivo": os.path.basename(caminho), "meses": []}
    for aba in wb.sheetnames:
        ws = wb[aba]
        ecg = mapa = 0
        for row in ws.iter_rows(values_only=True):
            for i, c in enumerate(row):
                v = str(c).strip() if c is not None else ""
                if v == "40101010" and i == 0:
                    ecg += 1
                elif v == "20102038":
                    mapa += 1
        resumo["meses"].append({"mes": aba, "ecg": ecg, "mapa": mapa})
    return resumo


def pastas_padrao():
    """repasses/ e a pasta oficial; amostras/ so como reserva se vazia."""
    if glob.glob(os.path.join("repasses", "*")):
        return ("repasses",)
    return ("amostras",)


def coletar(pastas=None):
    """Processa todos os demonstrativos das pastas (dedup por nome)."""
    if pastas is None:
        pastas = pastas_padrao()
    docs = []
    vistos = set()
    for pasta in pastas:
        for caminho in sorted(glob.glob(os.path.join(pasta, "*"))):
            nome = os.path.basename(caminho).lower()
            if nome in vistos:
                continue
            try:
                if nome.endswith(".pdf"):
                    r = processar_ids(caminho) or processar_unimed(caminho)
                elif nome.endswith(".xlsx"):
                    r = processar_cardiopro(caminho)
                else:
                    continue
            except Exception as e:
                print(f"ERRO ao processar {caminho}: {e}")
                continue
            if r:
                vistos.add(nome)
                docs.append(r)
    return docs


def financeiro(pastas=None):
    """Estrutura consolidada por empresa para o painel."""
    empresas = {}
    for r in coletar(pastas):
        if r["tipo"].startswith("IDS"):
            emp = empresas.setdefault("IDS", {"documentos": []})
            emp["documentos"].append({
                "arquivo": r["arquivo"],
                "emitido_em": r.get("emitido_em"),
                "linhas": [{"tipo": s["setor"].title(),
                            "detalhe": s["unidade"].title(),
                            "qtd": s["qtd"], "valor": s["valor"]}
                           for s in r["setores"]],
                "total": r.get("total"),
            })
        elif r["tipo"].startswith("Unimed"):
            emp = empresas.setdefault("Unimed", {"documentos": []})
            emp["documentos"].append({
                "arquivo": r["arquivo"],
                "periodo": r.get("periodo"),
                "linhas": [{"tipo": t, "qtd": n, "valor": None}
                           for t, n in r["servicos"].items()],
                "executantes": r["executantes"],
                "bruto": r.get("bruto"),
                "liquido": r.get("liquido"),
            })
        else:
            emp = empresas.setdefault("CardioPro", {"documentos": []})
            tot_ecg = sum(m["ecg"] for m in r["meses"])
            tot_mapa = sum(m["mapa"] for m in r["meses"])
            emp["documentos"].append({
                "arquivo": r["arquivo"],
                "meses": r["meses"],
                "linhas": [{"tipo": "ECG", "qtd": tot_ecg, "valor": None},
                           {"tipo": "MAPA", "qtd": tot_mapa, "valor": None}],
            })
    return {"empresas": empresas}


def main():
    achados = coletar()

    for r in achados:
        print("=" * 70)
        print(f"{r['tipo']}  [{r['arquivo']}]")
        if r["tipo"].startswith("IDS"):
            soma_q = soma_v = 0
            for s in r["setores"]:
                print(f"  {s['unidade']:22s} {s['setor']:28s} "
                      f"{s['qtd']:4d} exames  R$ {s['valor']:10,.2f}")
                soma_q += s["qtd"]
                soma_v += s["valor"]
            if r["total"]:
                ok = ("OK" if (soma_q == r["total"]["qtd"]
                               and abs(soma_v - r["total"]["valor"]) < 0.01)
                      else "DIVERGENTE")
                print(f"  TOTAL DO DOCUMENTO: {r['total']['qtd']} exames "
                      f"R$ {r['total']['valor']:,.2f}  "
                      f"[conferencia soma dos setores: {ok}]")
        elif r["tipo"].startswith("Unimed"):
            print(f"  Periodo: {r.get('periodo', '?')}")
            for e in r["executantes"]:
                print(f"  Executante {e['nome']:30s} {e['servicos']:4d} "
                      f"servicos  R$ {e['valor']:10,.2f}")
            print(f"  Servicos por tipo: {r['servicos']}")
            if r.get("bruto"):
                print(f"  Bruto p/ nota: R$ {r['bruto']:,.2f}   "
                      f"Liquido: R$ {r['liquido']:,.2f}")
        else:
            for mes in r["meses"]:
                print(f"  {mes['mes']:28s} ECG: {mes['ecg']:4d}   "
                      f"MAPA: {mes['mapa']:4d}")


if __name__ == "__main__":
    main()
