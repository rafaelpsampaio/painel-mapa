# -*- coding: utf-8 -*-
"""
Rotina de conciliacao de exames MAPA: quais exames recebidos ja foram
retornados (laudo enviado) e quais estao pendentes.

Uso:  py rotina_pendencias.py [--dias 30] [--listar-retornados] [--salvar-historico]

Logica (descoberta na investigacao da caixa):
 - Exames chegam como anexo .dmw cujo nome contem o codigo unico (ex. ED9-00159).
 - A doutora responde na MESMA conversa anexando o laudo <codigo>.pdf.
 - Apos responder, a mensagem costuma ser movida da Caixa de Entrada
   para a pasta MAPA; a caixa de entrada funciona como fila de pendentes.

Classificacao de cada exame recebido:
 1. RETORNADO: um PDF com o mesmo codigo foi enviado.
 2. BAIXADO: codigo consta em baixas.txt (resolvido fora do email).
 3. PROVAVEL: sem PDF do codigo, mas nome parecido (>=85%) em anexo ou
    assunto de resposta enviada apos o recebimento.
 4. AVISO: conversa respondida, mas sem PDF nem nome batendo.
 5. PENDENTE: nada disso.

Somente leitura (Mail.Read). Nada e alterado na caixa.
O nucleo esta em analisar(); o painel web (painel.py) usa a mesma funcao.
"""

import argparse
import difflib
import html as htmlmod
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import outlook_auth

GRAPH = "https://graph.microsoft.com/v1.0"
# inbox = pendentes; MAPA = arquivadas; UNIMED e IDS tambem recebem exames
PASTAS_RECEBIDOS = ["inbox", "MAPA", "UNIMED", "IDS"]
RE_CODIGO = re.compile(r"\b([A-Z0-9]{2,4})[-\s]?(\d{4,6})\b")
RE_NOME = re.compile(r"([A-ZÀ-Ü][A-Za-zÀ-ü]+(?:[ ][A-Za-zÀ-ü]{2,}){1,7})")
RE_LIXO_NOME = re.compile(
    r"(?i)\s+(att|req|requisicao|requisição|motivo|medicamentos?|exames?|"
    r"atenciosamente|controle|resultados?|segue|data|obs|laudar)\b.*$")
RE_ASSUNTO_LIXO = re.compile(
    r"(?i)\b(re|res|fw|fwd|enc|mapa|maps|laudar|laudo|urgente|und?|unid|"
    r"unidade|dra?|gisele|com|sem|requisicao|requisição|para|dia|"
    r"resultados?)\b|[\d/:.\-–]")
ARQ_BAIXAS = "baixas.txt"
# padroes de prazo de entrega no texto dos emails das fontes:
# "RESULTADOS 29/07", "resultado para 28/07/2026", "MAPAS PARA 28/07",
# "para serem entregues ate o dia 29/07", "RESULTADO MAPA 27/07"
RE_PRAZOS = [
    re.compile(r"(?i)resultados?\W{0,8}(?:para\s*|dia\s*)?"
               r"(\d{1,2})/0*(\d{1,3})(?:/(\d{2,4}))?"),
    re.compile(r"(?i)resultados?\s+mapa\s+"
               r"(\d{1,2})/0*(\d{1,3})(?:/(\d{2,4}))?"),
    re.compile(r"(?i)entregues?\s*(?:ate\s*)?(?:o\s*)?(?:dia\s*)?"
               r"(\d{1,2})/0*(\d{1,3})(?:/(\d{2,4}))?"),
    re.compile(r"(?i)mapas?\s+para\s+(?:o\s*)?(?:dia\s*)?"
               r"(\d{1,2})/0*(\d{1,3})(?:/(\d{2,4}))?"),
]
# sem prazo declarado, considera atrasado apos N dias do recebimento
DIAS_SEM_PRAZO = 5

# dominio do remetente -> empresa
EMPRESAS = {
    "ids.med.br": "IDS",
    "cardiopro.com.br": "CardioPro",
    "unimedsorocaba.coop.br": "Unimed",
    "eletrocardio.com.br": "Eletrocardio",
}
# prefixo do codigo do exame -> empresa (mais confiavel que o remetente,
# pois exames Unimed chegam encaminhados por giperroud@uol.com.br)
PREFIXO_EMPRESA = {
    "CCQ": "Unimed", "6OA": "Unimed",
    "CY0": "CardioPro",
    "ED9": "IDS", "0RC": "IDS", "0NS": "IDS", "9IS": "IDS", "0S3": "IDS",
}


def empresa_de(fonte, codigo=None):
    if codigo:
        prefixo = codigo.split("-")[0]
        if prefixo in PREFIXO_EMPRESA:
            return PREFIXO_EMPRESA[prefixo]
    return EMPRESAS.get((fonte or "").split("@")[-1].lower(), "Outros")


def extrair_prazo(texto, recebido_iso):
    """Data de entrega prometida no email, se houver ('AAAA-MM-DD')."""
    base = datetime.fromisoformat(recebido_iso.replace("Z", "+00:00"))
    candidatos = []
    for rx in RE_PRAZOS:
        for m in rx.finditer(texto):
            dia, mes = int(m.group(1)), int(m.group(2))
            ano = int(m.group(3)) if m.group(3) else base.year
            if ano < 100:
                ano += 2000
            if not (1 <= mes <= 12 and 1 <= dia <= 31):
                continue
            try:
                dt = datetime(ano, mes, dia, tzinfo=timezone.utc)
            except ValueError:
                continue
            if not m.group(3) and dt < base - timedelta(days=2):
                # sem ano explicito e no passado: virada de ano
                try:
                    dt = datetime(ano + 1, mes, dia, tzinfo=timezone.utc)
                except ValueError:
                    continue
            if base - timedelta(days=2) <= dt <= base + timedelta(days=45):
                candidatos.append(dt)
    return max(candidatos).strftime("%Y-%m-%d") if candidatos else None


# ---------------------------------------------------------------- acesso http
def gget(token, url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Erro HTTP {e.code} ao consultar o email: {corpo}")


def listar(token, pasta_id, select, cutoff_iso, campo_data, expand=None):
    filtro = urllib.parse.quote(f"{campo_data} ge {cutoff_iso}")
    ordem = urllib.parse.quote(f"{campo_data} desc")
    params = f"$select={select}&$top=50&$filter={filtro}&$orderby={ordem}"
    if expand:
        params += f"&$expand={urllib.parse.quote(expand)}"
    url = f"{GRAPH}/me/mailFolders/{pasta_id}/messages?{params}"
    out = []
    while url:
        data = gget(token, url)
        out.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
    return out


# ------------------------------------------------------------- extracao
def codigos_de_anexos(msg, extensoes):
    """Extrai codigos normalizados (PREFIXO-NUMERO) dos nomes de anexos."""
    achados = []
    for a in msg.get("attachments", []):
        nome = (a.get("name") or "").upper()
        if not any(nome.endswith(e) for e in extensoes):
            continue
        m = RE_CODIGO.search(nome)
        if m:
            achados.append((f"{m.group(1)}-{m.group(2)}", a.get("name")))
    return achados


def texto_plano(msg):
    corpo = msg.get("body", {}).get("content", "") or ""
    corpo = re.sub(r"<style.*?</style>", " ", corpo, flags=re.S | re.I)
    corpo = re.sub(r"<[^>]+>", " ", corpo)
    corpo = htmlmod.unescape(corpo)
    return re.sub(r"\s+", " ", (msg.get("subject") or "") + " " + corpo)


def nome_no_texto(texto, codigo):
    """Procura nome de paciente proximo ao codigo (ou numero) no texto."""
    prefixo, numero = codigo.split("-")
    variantes = [
        codigo,
        f"{prefixo} {numero}",
        f"{prefixo}: {numero}",
        f"{prefixo}:{numero}",
        numero,
        numero.lstrip("0"),
    ]
    for v in variantes:
        if not v:
            continue
        for m in re.finditer(re.escape(v), texto, re.I):
            trecho = texto[m.end():m.end() + 90]
            trecho = re.sub(r"^[\s:\-–—.]+", "", trecho)
            n = RE_NOME.match(trecho)
            if n:
                nome = n.group(1).strip()
                if len(nome.split()) >= 2 and not re.match(
                        r"(?i)(att|resultado|controle|segue|para|boa|bom)", nome):
                    return nome
    return None


def nome_antes_do_codigo(texto, codigo):
    """Nome que aparece logo ANTES do codigo (ex.: 'FULANA - CCQ-11504')."""
    prefixo, numero = codigo.split("-")
    variantes = [codigo, f"{prefixo}- {numero}", f"{prefixo} {numero}",
                 numero, numero.lstrip("0")]
    for v in variantes:
        if not v:
            continue
        for m in re.finditer(re.escape(v), texto, re.I):
            janela = texto[max(0, m.start() - 60):m.start()]
            # confina ao mesmo trecho/anexo (os anexos sao separados por |)
            janela = janela.split("|")[-1]
            achados = list(RE_NOME.finditer(janela))
            if not achados:
                continue
            ult = achados[-1]
            if len(janela) - ult.end() <= 12:
                nome = ult.group(1).strip()
                if len(nome.split()) >= 2:
                    return nome
    return None


def nome_avulso(texto):
    m = re.search(r"(?i)nome[\s:]+", texto)
    if m:
        n = RE_NOME.match(texto[m.end():])
        if n:
            return n.group(1).strip()
    return None


RE_NAO_NOME = re.compile(
    r"(?i)\b(bom|boa|obrigad[ao]|segue|anexos?|semana|final|dia|tarde|"
    r"noite|voc[eê]s?|desde|ja|já|att)\b")


def limpar_nome(nome):
    if not nome:
        return nome
    nome = RE_LIXO_NOME.sub("", nome).strip(" -_.,")
    if not nome or RE_NAO_NOME.search(nome):
        return None
    return nome if len(nome.split()) >= 2 else None


def normalizar(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s.upper()).strip()


def nomes_nas_respostas(enviados):
    """Candidatos a nome de paciente em anexos e assuntos dos enviados."""
    candidatos = []  # (nome_normalizado, origem, data)
    for m in enviados:
        data = m["sentDateTime"]
        for a in m.get("attachments", []):
            base = re.sub(r"(?i)\.(pdf|dmw|png|jpe?g|docx?)$", "",
                          a.get("name") or "")
            base = RE_CODIGO.sub("", base)
            base = re.sub(r"[_\d]+", " ", base)
            base = re.sub(r"\s+", " ", base).strip(" -_.")
            if len(base.split()) >= 2:
                candidatos.append(
                    (normalizar(base), f"anexo '{a.get('name')}'", data))
        assunto = m.get("subject") or ""
        limpo = re.sub(r"\s+", " ", RE_ASSUNTO_LIXO.sub(" ", assunto)).strip()
        if len(limpo.split()) >= 2:
            candidatos.append(
                (normalizar(limpo), f"assunto '{assunto[:60]}'", data))
    return candidatos


def melhor_match(nome, candidatos, apos):
    """Melhor aproximacao (>=85%) do nome entre respostas enviadas apos a data."""
    alvo = normalizar(nome)
    melhor = None
    for cand, origem, data in candidatos:
        if data < apos:
            continue
        r = difflib.SequenceMatcher(None, alvo, cand).ratio()
        if r >= 0.85 and (melhor is None or r > melhor["similaridade"]):
            melhor = {"similaridade": r, "origem": origem, "data": data}
    return melhor


# ------------------------------------------------------------- baixas manuais
def carregar_baixas(path=ARQ_BAIXAS):
    """Le baixas manuais: uma por linha, codigo + motivo livre.
    Linhas iniciadas por # sao comentario."""
    baixas = {}
    if not os.path.exists(path):
        return baixas
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            m = RE_CODIGO.search(linha.upper())
            if m:
                baixas[f"{m.group(1)}-{m.group(2)}"] = linha
    return baixas


def registrar_baixa(codigo, motivo=""):
    """Registra baixa manual em baixas.txt. Retorna o codigo normalizado."""
    m = RE_CODIGO.search((codigo or "").upper())
    if not m:
        raise ValueError(f"Codigo invalido: {codigo!r}")
    cod = f"{m.group(1)}-{m.group(2)}"
    quando = datetime.now().strftime("%d/%m/%Y %H:%M")
    motivo = (motivo or "").strip() or "sem motivo informado"
    with open(ARQ_BAIXAS, "a", encoding="utf-8") as f:
        f.write(f"{cod}: {motivo} (baixa em {quando})\n")
    return cod


# ------------------------------------------------------------- nucleo
def analisar(dias=30, token=None):
    """Varre a caixa e devolve um dicionario com toda a conciliacao."""
    agora = datetime.now(timezone.utc)
    cutoff = (agora - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if token is None:
        token = outlook_auth.get_access_token()

    pastas = gget(token, f"{GRAPH}/me/mailFolders?$top=50").get("value", [])
    ids = {p["displayName"]: p["id"] for p in pastas}

    # ---- recebidos: exames (.dmw) ----
    exames = {}
    for pasta in PASTAS_RECEBIDOS:
        pasta_id = ids.get(pasta, pasta)  # 'inbox' e nome conhecido da API
        msgs = listar(
            token, pasta_id,
            "from,subject,receivedDateTime,conversationId,hasAttachments,body",
            cutoff, "receivedDateTime",
            expand="attachments($select=name)",
        )
        for m in msgs:
            achados = codigos_de_anexos(m, (".DMW",))
            if not achados:
                continue
            # nomes de anexos entram no texto: fotos tipo
            # "HELENA MARIA - CCQ-11504.png" carregam nome + codigo
            texto = (texto_plano(m) + " | " +
                     " | ".join(a.get("name") or ""
                                for a in m.get("attachments", [])))
            prazo_msg = extrair_prazo(texto, m["receivedDateTime"])
            for codigo, nome_arq in achados:
                # nome pode estar no proprio arquivo: "0RC-04973 FULANA.dmw"
                sobra = re.sub(r"(?i)\.dmw$", "", nome_arq)
                sobra = re.sub(RE_CODIGO, "", sobra).strip(" -_")
                nome = limpar_nome(sobra) if len(sobra.split()) >= 2 else None
                if not nome:
                    nome = limpar_nome(nome_no_texto(texto, codigo))
                if not nome:
                    nome = limpar_nome(nome_antes_do_codigo(texto, codigo))
                if not nome and len(achados) == 1:
                    nome = limpar_nome(nome_avulso(texto))
                atual = exames.get(codigo)
                if atual is None or m["receivedDateTime"] < atual["recebido"]:
                    try:
                        rem = m["from"]["emailAddress"]["address"].lower()
                    except (KeyError, TypeError):
                        rem = "?"
                    exames[codigo] = {
                        "codigo": codigo,
                        "nome": nome or (atual or {}).get("nome"),
                        "fonte": rem,
                        "recebido": m["receivedDateTime"],
                        "conversa": m.get("conversationId"),
                        "pasta": pasta,
                        "prazo": prazo_msg or (atual or {}).get("prazo"),
                        "empresa": empresa_de(rem, codigo),
                    }
                elif nome and not atual.get("nome"):
                    atual["nome"] = nome

    # ---- enviados: laudos (.pdf) e conversas respondidas ----
    enviados = listar(
        token, "sentitems",
        "subject,sentDateTime,conversationId,hasAttachments",
        cutoff, "sentDateTime",
        expand="attachments($select=name)",
    )
    codigos_enviados = {}
    conversas_respondidas = defaultdict(list)
    for m in enviados:
        if m.get("conversationId"):
            conversas_respondidas[m["conversationId"]].append(m["sentDateTime"])
        for codigo, _ in codigos_de_anexos(m, (".PDF",)):
            d = codigos_enviados.get(codigo)
            if d is None or m["sentDateTime"] > d:
                codigos_enviados[codigo] = m["sentDateTime"]

    # ---- conciliacao ----
    candidatos_nome = nomes_nas_respostas(enviados)
    baixas = carregar_baixas()
    pendentes, retornados, provaveis, avisos, baixados = [], [], [], [], []
    hoje = agora.strftime("%Y-%m-%d")
    for codigo, ex in sorted(exames.items(), key=lambda kv: kv[1]["recebido"]):
        ex["dias_espera"] = (
            agora - datetime.fromisoformat(ex["recebido"].replace("Z", "+00:00"))
        ).days
        ex["atrasado"] = (ex["prazo"] < hoje if ex.get("prazo")
                          else ex["dias_espera"] >= DIAS_SEM_PRAZO)
        if codigo in codigos_enviados:
            ex["retornado_em"] = codigos_enviados[codigo]
            if codigo in baixas:
                ex["baixa"] = baixas[codigo]
            retornados.append(ex)
            continue
        if codigo in baixas:
            ex["baixa"] = baixas[codigo]
            baixados.append(ex)
            continue
        match = (melhor_match(ex["nome"], candidatos_nome, ex["recebido"])
                 if ex["nome"] else None)
        respostas = [
            d for d in conversas_respondidas.get(ex["conversa"], [])
            if d > ex["recebido"]
        ]
        if match:
            ex["evidencia"] = match
            provaveis.append(ex)
        elif respostas:
            avisos.append(ex)
        else:
            pendentes.append(ex)

    # ---- status da caixa ----
    por_fonte = defaultdict(list)
    for ex in exames.values():
        por_fonte[ex["fonte"]].append(ex["recebido"])
    fontes = []
    for fonte, datas in sorted(por_fonte.items(), key=lambda kv: -len(kv[1])):
        u = max(datas)
        dias_mudo = (
            agora - datetime.fromisoformat(u.replace("Z", "+00:00"))
        ).days
        fontes.append({"fonte": fonte, "empresa": empresa_de(fonte),
                       "exames": len(datas), "ultimo": u,
                       "dias_sem_enviar": dias_mudo})
    por_empresa = defaultdict(lambda: {"exames": 0, "pendentes": 0})
    for ex in exames.values():
        por_empresa[ex["empresa"]]["exames"] += 1
    for ex in pendentes:
        por_empresa[ex["empresa"]]["pendentes"] += 1
    empresas = [
        {"empresa": nome, **dados}
        for nome, dados in sorted(por_empresa.items(),
                                  key=lambda kv: -kv[1]["exames"])
    ]
    ultimo = (max(exames.values(), key=lambda e: e["recebido"])
              if exames else None)

    # ---- buracos de numeracao ----
    # so vale para prefixos cuja sequencia e dedicada a Dra.; CY0/ED9/CCQ/
    # 6OA/9IS sao numeracoes compartilhadas com outros medicos (chegam
    # numeros alternados) e gerariam falso "faltou receber"
    PREFIXOS_DEDICADOS = {"0RC", "0NS"}
    por_prefixo = defaultdict(dict)
    for codigo, ex in exames.items():
        p, n = codigo.split("-")
        if p not in PREFIXOS_DEDICADOS:
            continue
        por_prefixo[p][int(n)] = (len(n), ex["recebido"])
    buracos = []
    for p, nums in por_prefixo.items():
        ordenados = sorted(nums)
        largura = max(v[0] for v in nums.values())
        for a, b in zip(ordenados, ordenados[1:]):
            if not (1 < b - a <= 15):
                continue
            dist_dias = abs(
                (datetime.fromisoformat(nums[b][1].replace("Z", "+00:00"))
                 - datetime.fromisoformat(nums[a][1].replace("Z", "+00:00")))
                .days)
            if dist_dias > 7:
                continue
            for falta in range(a + 1, b):
                cod = f"{p}-{str(falta).zfill(largura)}"
                if cod not in codigos_enviados:
                    buracos.append(cod)

    return {
        "gerado_em": agora.astimezone().strftime("%d/%m/%Y %H:%M"),
        "dias": dias,
        "contagens": {
            "recebidos": len(exames),
            "retornados": len(retornados),
            "pendentes": len(pendentes),
            "atrasados": sum(1 for e in pendentes if e["atrasado"]),
            "provaveis": len(provaveis),
            "avisos": len(avisos),
            "baixados": len(baixados),
        },
        "pendentes": pendentes,
        "provaveis": provaveis,
        "avisos": avisos,
        "baixados": baixados,
        "retornados": retornados,
        "status": {"ultimo": ultimo, "fontes": fontes, "empresas": empresas},
        "buracos": sorted(buracos),
    }


# ------------------------------------------------------------- relatorio texto
def _fmt(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d/%m")


def _fmt_hora(iso):
    return (datetime.fromisoformat(iso.replace("Z", "+00:00"))
            .astimezone().strftime("%d/%m %H:%M"))


def relatorio_texto(dados, listar_retornados=False):
    out = []
    w = out.append
    c = dados["contagens"]
    w(f"CONCILIACAO DE EXAMES MAPA - ultimos {dados['dias']} dias "
      f"({dados['gerado_em']})")
    w("=" * 70)
    w(f"Exames recebidos (anexo .dmw): {c['recebidos']}   "
      f"Retornados: {c['retornados']}   Pendentes: {c['pendentes']}   "
      f"Provaveis: {c['provaveis']}   Avisos: {c['avisos']}   "
      f"Baixados manualmente: {c['baixados']}")

    w("\nSTATUS DA CAIXA:")
    w(f"  Email ativo: conexao e leitura OK em {dados['gerado_em']}")
    u = dados["status"]["ultimo"]
    if u:
        w(f"  Ultimo exame recebido: {u['codigo']} "
          f"({u['nome'] or 'sem nome'}), de {u['fonte']}, "
          f"em {_fmt_hora(u['recebido'])}")
    w("  Por empresa (mapas na janela):")
    for e in dados["status"]["empresas"]:
        w(f"    {e['empresa']:14s} {e['exames']:4d} exames "
          f"({e['pendentes']} pendentes)")
    w("  Por fonte:")
    for f in dados["status"]["fontes"]:
        alerta = (f"   << SEM ENVIOS HA {f['dias_sem_enviar']} DIAS"
                  if f["dias_sem_enviar"] >= 7 else "")
        w(f"    {f['fonte']:32s} [{f['empresa']:12s}] {f['exames']:4d} exames; "
          f"ultimo em {_fmt(f['ultimo'])}{alerta}")

    if dados["buracos"]:
        w("\nFALTAM RECEBER? Numeracao pulada nas sequencias recebidas "
          "(exame pode nao ter chegado, ou ser de outro medico):")
        for cod in dados["buracos"]:
            w(f"  {cod}")

    atrasados = [e for e in dados["pendentes"] if e["atrasado"]]
    no_prazo = [e for e in dados["pendentes"] if not e["atrasado"]]

    def linha_pend(ex):
        prazo = (f"prazo {ex['prazo'][8:10]}/{ex['prazo'][5:7]}"
                 if ex.get("prazo") else "sem prazo declarado")
        return (f"  {ex['codigo']:12s} "
                f"{ex['nome'] or '(nome nao identificado)':45s} "
                f"{ex['fonte']:32s} recebido {_fmt(ex['recebido'])} "
                f"({ex['dias_espera']}d); {prazo}")

    if atrasados:
        w("\nPENDENTES ATRASADOS (prazo vencido ou muito tempo sem laudo):")
        for ex in atrasados:
            w(linha_pend(ex))
    else:
        w("\nNenhum exame atrasado.")
    if no_prazo:
        w("\nPENDENTES NO PRAZO (aguardando a data de entrega):")
        for ex in no_prazo:
            w(linha_pend(ex))

    if dados["provaveis"]:
        w("\nPROVAVELMENTE RETORNADOS - sem PDF com o codigo, mas nome "
          "parecido em resposta enviada (conferir):")
        for ex in dados["provaveis"]:
            ev = ex["evidencia"]
            w(f"  {ex['codigo']:12s} {ex['nome']:45s} "
              f"recebido {_fmt(ex['recebido'])}; evidencia em "
              f"{_fmt(ev['data'])}: {ev['origem']} "
              f"(similaridade {ev['similaridade']:.0%})")

    if dados["avisos"]:
        w("\nAVISOS - conversa respondida, mas sem PDF com o codigo do exame:")
        for ex in dados["avisos"]:
            w(f"  {ex['codigo']:12s} {ex['nome'] or '(nome nao identificado)':45s} "
              f"{ex['fonte']:32s} recebido {_fmt(ex['recebido'])}")

    if dados["baixados"]:
        w("\nBAIXADOS MANUALMENTE (via baixas.txt / Dar Baixa.bat):")
        for ex in dados["baixados"]:
            w(f"  {ex['codigo']:12s} {ex['nome'] or '(nome nao identificado)':45s} "
              f"anotacao: {ex['baixa']}")

    if listar_retornados and dados["retornados"]:
        w("\nRETORNADOS:")
        for ex in dados["retornados"]:
            w(f"  {ex['codigo']:12s} {ex['nome'] or '(nome nao identificado)':45s} "
              f"recebido {_fmt(ex['recebido'])} -> laudo "
              f"{_fmt(ex['retornado_em'])}")

    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=30)
    ap.add_argument("--listar-retornados", action="store_true")
    ap.add_argument("--salvar-historico", action="store_true",
                    help="salva copia datada em relatorios\\")
    args = ap.parse_args()

    dados = analisar(args.dias)
    relatorio = relatorio_texto(dados, args.listar_retornados)

    with open("relatorio_pendencias.txt", "w", encoding="utf-8") as f:
        f.write(relatorio)
    if args.salvar_historico:
        os.makedirs("relatorios", exist_ok=True)
        destino = os.path.join(
            "relatorios",
            f"pendencias_{datetime.now().strftime('%Y-%m-%d')}.txt")
        with open(destino, "w", encoding="utf-8") as f:
            f.write(relatorio)
    print(relatorio)


if __name__ == "__main__":
    main()
