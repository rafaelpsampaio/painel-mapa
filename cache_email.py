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
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

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


GRAPH = "https://graph.microsoft.com/v1.0"


def _gget(token, url, tentativas=5):
    """GET autenticado no Graph API, com retry em throttling (HTTP 429)."""
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    espera = 2
    for tentativa in range(tentativas):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and tentativa < tentativas - 1:
                retry_after = e.headers.get("Retry-After")
                time.sleep(float(retry_after) if retry_after else espera)
                espera *= 2
                continue
            corpo = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"Erro HTTP {e.code} ao consultar o email: {corpo}")


def _listar_pagina(token, url):
    out = []
    while url:
        data = _gget(token, url)
        out.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
    return out


def _resolver_ids_pastas(token):
    pastas = _gget(token, f"{GRAPH}/me/mailFolders?$top=50").get("value", [])
    return {p["displayName"]: p["id"] for p in pastas}


_RE_STYLE = re.compile(r"<style.*?</style>", re.S | re.I)
_RE_TAG = re.compile(r"<[^>]+>")


def _texto_plano_de_corpo(conteudo_html):
    import html as htmlmod
    texto = _RE_STYLE.sub(" ", conteudo_html or "")
    texto = _RE_TAG.sub(" ", texto)
    return htmlmod.unescape(texto)


def _registro_de(msg, config):
    """Converte uma mensagem do Graph API no registro quase-cru guardado
    no cache: so os campos usados pela conciliacao, corpo ja em texto
    plano (sem HTML)."""
    campo = config["campo_data"]
    registro = {
        "assunto": msg.get("subject") or "",
        "recebido": msg[campo],
        "conversa": msg.get("conversationId"),
        "anexos": [a.get("name") or "" for a in msg.get("attachments", [])],
    }
    if "from" in config["select"]:
        try:
            registro["de"] = msg["from"]["emailAddress"]["address"].lower()
        except (KeyError, TypeError):
            registro["de"] = "?"
    if "body" in config["select"]:
        registro["corpo_texto"] = _texto_plano_de_corpo(
            msg.get("body", {}).get("content", ""))
    return registro


def _buscar(token, pasta_id, config, inicio_iso, fim_iso=None):
    """Mensagens da pasta com campo_data em [inicio_iso, fim_iso), ou
    [inicio_iso, agora] se fim_iso for None."""
    campo = config["campo_data"]
    condicoes = f"{campo} ge {inicio_iso}"
    if fim_iso:
        condicoes += f" and {campo} lt {fim_iso}"
    filtro = urllib.parse.quote(condicoes)
    ordem = urllib.parse.quote(f"{campo} desc")
    expand = urllib.parse.quote("attachments($select=name)")
    params = (f"$select={config['select']}&$top=50&$filter={filtro}"
              f"&$orderby={ordem}&$expand={expand}")
    url = f"{GRAPH}/me/mailFolders/{pasta_id}/messages?{params}"
    return _listar_pagina(token, url)


DIAS_BACKFILL = 730  # ~2 anos
TAMANHO_BLOCO_DIAS = 30
MARGEM_INCREMENTAL = timedelta(days=1)


def _fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _limite_backfill(agora):
    return agora - timedelta(days=DIAS_BACKFILL)


def sincronizar_um_passo(token, cache, agora=None):
    """Avanca uma unidade de sincronizacao do cache local e grava o
    resultado em disco.

    Se alguma pasta ainda nao cobre os ultimos DIAS_BACKFILL dias, busca
    mais um bloco mensal dessa pasta (do mais recente para o mais antigo)
    e devolve {"pasta": nome, "mes": "AAAA-MM"} -- o chamador deve repetir
    a chamada ate receber None. Quando todas as pastas ja tem o backfill
    completo, faz a sincronizacao incremental (mensagens novas desde a
    ultima vez) de todas elas numa unica chamada e devolve None.
    """
    agora = agora or datetime.now(timezone.utc)
    limite = _limite_backfill(agora)
    ids_pastas = {}

    def resolver(pasta):
        if pasta in ("inbox", "sentitems"):
            return pasta
        if not ids_pastas:
            ids_pastas.update(_resolver_ids_pastas(token))
        return ids_pastas.get(pasta, pasta)

    pasta_pendente = None
    for pasta in PASTAS:
        estado = cache["pastas"][pasta]
        completo_ate = (_parse(estado["backfill_completo_ate"])
                        if estado["backfill_completo_ate"] else None)
        if completo_ate is None or completo_ate > limite:
            pasta_pendente = pasta
            break

    if pasta_pendente:
        pasta = pasta_pendente
        config = PASTAS[pasta]
        estado = cache["pastas"][pasta]
        fim = (_parse(estado["backfill_completo_ate"])
               if estado["backfill_completo_ate"] else agora)
        inicio_bloco = max(limite, fim - timedelta(days=TAMANHO_BLOCO_DIAS))
        msgs = _buscar(token, resolver(pasta), config,
                       _fmt(inicio_bloco), _fmt(fim))
        for msg in msgs:
            estado["mensagens"][msg["id"]] = _registro_de(msg, config)
        estado["backfill_completo_ate"] = _fmt(inicio_bloco)
        if inicio_bloco <= limite:
            estado["ultimo_sync"] = _fmt(agora)
        salvar_cache(cache)
        return {"pasta": pasta, "mes": inicio_bloco.strftime("%Y-%m")}

    for pasta, config in PASTAS.items():
        estado = cache["pastas"][pasta]
        desde = (_parse(estado["ultimo_sync"]) - MARGEM_INCREMENTAL
                 if estado["ultimo_sync"] else limite)
        msgs = _buscar(token, resolver(pasta), config, _fmt(desde))
        for msg in msgs:
            estado["mensagens"][msg["id"]] = _registro_de(msg, config)
        estado["ultimo_sync"] = _fmt(agora)
    salvar_cache(cache)
    return None
