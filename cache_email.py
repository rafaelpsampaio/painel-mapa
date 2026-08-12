# -*- coding: utf-8 -*-
"""Cache local das mensagens de email usadas pela conciliacao MAPA.

Mantem uma copia local (cache_emails.json) das mensagens das pastas
inbox, MAPA, UNIMED, IDS (exames recebidos) e sentitems (laudos
enviados), evitando reconsultar o Graph API a cada abertura do painel.
A primeira sincronizacao de cada pasta cobre os ultimos DIAS_BACKFILL
dias, em blocos mensais resumiveis; depois disso so busca mensagens
novas (ver sincronizar_um_passo).
"""

import json
import os

ARQ_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "cache_emails.json")

# pasta logica -> campos de consulta no Graph API
PASTAS = {
    "inbox":     {"campo_data": "receivedDateTime",
                  "select": "from,subject,receivedDateTime,conversationId,hasAttachments,body"},
    "MAPA":      {"campo_data": "receivedDateTime",
                  "select": "from,subject,receivedDateTime,conversationId,hasAttachments,body"},
    "UNIMED":    {"campo_data": "receivedDateTime",
                  "select": "from,subject,receivedDateTime,conversationId,hasAttachments,body"},
    "IDS":       {"campo_data": "receivedDateTime",
                  "select": "from,subject,receivedDateTime,conversationId,hasAttachments,body"},
    "sentitems": {"campo_data": "sentDateTime",
                  "select": "subject,sentDateTime,conversationId,hasAttachments"},
}


def _cache_vazio():
    return {"pastas": {nome: {"backfill_completo_ate": None,
                              "ultimo_sync": None, "mensagens": {}}
                       for nome in PASTAS}}


def carregar_cache():
    """Le o cache do disco; devolve um esqueleto vazio se nao existir ou
    estiver corrompido (nunca levanta excecao)."""
    base = _cache_vazio()
    if not os.path.exists(ARQ_CACHE):
        return base
    try:
        with open(ARQ_CACHE, "r", encoding="utf-8") as f:
            salvo = json.load(f)
    except (OSError, ValueError):
        return base
    if not isinstance(salvo, dict):
        return base
    pastas_salvas = salvo.get("pastas")
    if not isinstance(pastas_salvas, dict):
        return base
    for nome in PASTAS:
        dados = pastas_salvas.get(nome)
        if isinstance(dados, dict):
            base["pastas"][nome].update(dados)
    return base


def salvar_cache(cache):
    """Escrita atomica: grava num arquivo temporario e troca por cima do
    definitivo, pra nunca deixar o JSON pela metade se o processo for
    interrompido no meio da gravacao."""
    tmp = ARQ_CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, ARQ_CACHE)


def mensagens(cache, pasta):
    """Dicionario {id_mensagem: registro} da pasta logica indicada."""
    return cache["pastas"][pasta]["mensagens"]
