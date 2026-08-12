# -*- coding: utf-8 -*-
"""
Conciliacao de exames MAPA (aba Exames do painel): cruza os exames
recebidos/laudados por email com os eventos de pagamento (eventos.py).

Pareamento por NOME (aproximado) + DATA (+-10 dias); qualquer pagador pode
casar com exame de qualquer fonte (o cruzamento real acontece assim, ex.
exame de fonte IDS pago pela Unimed).
"""

from datetime import datetime, timedelta

import rotina_pendencias as rp
from eventos import coletar_eventos, casa_nome, PRIORIDADE_PAGADOR

# janela de cobertura usada no alerta "sem registro": heuristica de qual
# pagador/janela representa a expectativa de pagamento pra cada fonte de
# exame (nao restringe o casamento em si, so o rotulo "esperado")
PAGADOR_PRIMARIO = {"IDS": "IDS", "Unimed": "Unimed", "CardioPro": "Unimed"}


def anotar_pagamentos(dados):
    """Anota ex['pagamento'] nos exames de `dados` (retorno de analisar) e
    devolve a lista de pagamentos sem exame correspondente na janela."""
    itens = []
    for evd in coletar_eventos():
        if evd["exame"] != "MAPA":
            continue
        itens.append({
            "empresa": evd["pagador"], "nome": evd["paciente"],
            "data": (datetime.strptime(evd["data"], "%Y-%m-%d")
                     if evd["data"] else None),
            "valor": evd["valor"], "origem": evd["documento"],
            "tipo": evd["tipo"],
        })

    exames = []
    for lista in ("retornados", "pendentes", "provaveis", "avisos", "baixados"):
        exames.extend(dados[lista])

    # indice de exames por primeiro token do nome, sem a empresa na chave:
    # qualquer pagador pode casar com exame de qualquer fonte
    indice = {}
    for ex in exames:
        if not ex.get("nome"):
            continue
        ex["_dt"] = datetime.fromisoformat(
            ex["recebido"].replace("Z", "+00:00")).replace(tzinfo=None)
        tokens = rp.normalizar(ex["nome"]).split()
        if tokens:
            indice.setdefault(tokens[0], []).append(ex)

    # pagamentos reais (IDS, Unimed) tem prioridade sobre a planilha de
    # producao da CardioPro na hora de reivindicar um exame
    itens.sort(key=lambda p: PRIORIDADE_PAGADOR.get(p["empresa"], 9))

    # janela de cobertura por empresa: intervalo de datas de exame que os
    # demonstrativos ja pagaram; exame dentro dela sem pagamento = em falta
    cobertura = {}
    for p in itens:
        if p["data"]:
            c = cobertura.setdefault(p["empresa"], [p["data"], p["data"]])
            if p["data"] < c[0]:
                c[0] = p["data"]
            if p["data"] > c[1]:
                c[1] = p["data"]
    dados["cobertura_pagamentos"] = {
        emp: {"inicio": c[0].strftime("%Y-%m-%d"),
              "fim": c[1].strftime("%Y-%m-%d")}
        for emp, c in cobertura.items()
    }

    inicio = min((ex["_dt"] for ex in exames if "_dt" in ex), default=None)
    usados = set()
    orfaos = []
    for p in itens:
        if not p["data"] or not p["nome"]:
            continue
        tokens = rp.normalizar(p["nome"]).split()
        achou = None
        for ex in indice.get(tokens[0], []) if tokens else []:
            if ex["codigo"] in usados:
                continue
            if abs((ex["_dt"] - p["data"]).days) > 10:
                continue
            if casa_nome(ex["nome"], p["nome"]):
                achou = ex
                break
        if achou:
            usados.add(achou["codigo"])
            achou["pagamento"] = {
                "data": p["data"].strftime("%Y-%m-%d"),
                "valor": p.get("valor"),
                "origem": p["origem"],
                "pagador": p["empresa"],
                "tipo": p["tipo"],
            }
        elif inicio and p["data"] >= inicio - timedelta(days=3):
            orfaos.append({"empresa": p["empresa"], "nome": p["nome"],
                           "data": p["data"].strftime("%Y-%m-%d"),
                           "origem": p["origem"]})
    for ex in exames:
        # so faz sentido cobrar pagamento de exame ja laudado; a janela
        # usada e a do pagador responsavel pela fonte do exame
        if ("_dt" in ex and not ex.get("pagamento")
                and ex.get("retornado_em") and not ex.get("baixa")):
            pagador = PAGADOR_PRIMARIO.get(ex["empresa"])
            c = cobertura.get(pagador) if pagador else None
            if c and c[0] <= ex["_dt"] <= c[1]:
                ex["pagamento_esperado"] = True

    # regra da repeticao: mesmo paciente, mesma fonte, exames com <= 15
    # dias de intervalo e so um pagamento = o outro e repeticao (exame
    # que nao deu certo), nao pendencia
    por_paciente = {}
    for ex in exames:
        if ex.get("nome") and "_dt" in ex:
            chave = (ex["empresa"], rp.normalizar(ex["nome"]))
            por_paciente.setdefault(chave, []).append(ex)
    for grupo in por_paciente.values():
        if len(grupo) < 2:
            continue
        for ex in grupo:
            if not ex.get("pagamento_esperado"):
                continue
            for irmao in grupo:
                if (irmao is not ex and irmao.get("pagamento")
                        and abs((ex["_dt"] - irmao["_dt"]).days) <= 15):
                    ex["repeticao"] = True
                    ex.pop("pagamento_esperado", None)
                    break

    for ex in exames:
        ex.pop("_dt", None)
    orfaos.sort(key=lambda o: (o["empresa"], o["data"]))
    return orfaos
