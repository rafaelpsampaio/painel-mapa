# -*- coding: utf-8 -*-
"""
Investigacao inicial da caixa de email de exames via Microsoft Graph API.

Requer autenticacao previa: py outlook_auth.py
Somente leitura (escopo Mail.Read). Nada e alterado na caixa.

Gera relatorio_investigacao.txt com:
 - pastas e contagens
 - principais remetentes/dominios da caixa de entrada
 - exemplos de assuntos, previas de corpo e nomes de anexos
 - enviados: destinatarios e assuntos
 - cruzamento: quais conversas recebidas ja tem resposta enviada
"""

import json
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

import outlook_auth

GRAPH = "https://graph.microsoft.com/v1.0"
MAX_MSGS = 300


def gget(token, url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", "replace")[:300]
        print(f"ERRO HTTP {e.code} em {url}\n{corpo}")
        sys.exit(2)


def listar(token, pasta, select, max_msgs=MAX_MSGS, orderby="receivedDateTime desc",
           expand=None):
    params = f"$select={select}&$top=100&$orderby={urllib.parse.quote(orderby)}"
    if expand:
        params += f"&$expand={urllib.parse.quote(expand)}"
    url = f"{GRAPH}/me/mailFolders/{pasta}/messages?{params}"
    out = []
    while url and len(out) < max_msgs:
        data = gget(token, url)
        out.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
    return out[:max_msgs]


def addr_de(msg, campo="from"):
    try:
        return msg[campo]["emailAddress"]["address"].lower()
    except (KeyError, TypeError):
        return "(desconhecido)"


def main():
    token = outlook_auth.get_access_token()
    out = []
    w = out.append
    w("RELATORIO DE INVESTIGACAO DA CAIXA DE EMAIL (Graph API)")
    w("=" * 60)

    # ---- pastas ----
    pastas = gget(token, f"{GRAPH}/me/mailFolders?$top=50").get("value", [])
    w("\nPASTAS:")
    for p in pastas:
        w(f"  {p['displayName']:30s} total={p['totalItemCount']:5d} "
          f"nao-lidas={p['unreadItemCount']}")

    # ---- caixa de entrada ----
    entrada = listar(
        token, "inbox",
        "from,subject,receivedDateTime,hasAttachments,conversationId,bodyPreview",
    )
    w(f"\nCAIXA DE ENTRADA: {len(entrada)} mensagens analisadas (mais recentes)")
    if entrada:
        w(f"  Periodo: {entrada[-1]['receivedDateTime']} ate "
          f"{entrada[0]['receivedDateTime']}")
        remetentes = Counter()
        dominios = Counter()
        assuntos = defaultdict(list)
        com_anexo = 0
        for m in entrada:
            rem = addr_de(m)
            remetentes[rem] += 1
            if "@" in rem:
                dominios[rem.split("@")[1]] += 1
            if len(assuntos[rem]) < 5:
                assuntos[rem].append((m.get("subject") or "(sem assunto)")[:100])
            if m.get("hasAttachments"):
                com_anexo += 1
        w(f"  Com anexo: {com_anexo} de {len(entrada)}")
        w("\n  TOP 15 REMETENTES:")
        for rem, qtd in remetentes.most_common(15):
            w(f"    {qtd:4d}x  {rem}")
        w("\n  TOP 10 DOMINIOS:")
        for dom, qtd in dominios.most_common(10):
            w(f"    {qtd:4d}x  {dom}")
        w("\n  EXEMPLOS DE ASSUNTO POR REMETENTE (top 8):")
        for rem, _ in remetentes.most_common(8):
            w(f"    -- {rem}:")
            for a in assuntos[rem]:
                w(f"         {a}")
        w("\n  PREVIA DO CORPO (10 mensagens mais recentes):")
        for m in entrada[:10]:
            prev = (m.get("bodyPreview") or "").replace("\r", " ").replace("\n", " ")
            w(f"    [{addr_de(m)}] {prev[:180]}")

    # ---- nomes de anexos (ultimas 25 msgs com anexo) ----
    com_anexos = listar(
        token, "inbox", "from,subject,hasAttachments",
        max_msgs=25, expand="attachments($select=name,size)",
    )
    w("\n  NOMES DE ANEXOS (mensagens recentes):")
    achou = False
    for m in com_anexos:
        for a in m.get("attachments", []):
            achou = True
            w(f"    [{addr_de(m)}] {a.get('name')}")
    if not achou:
        w("    (nenhum anexo nas mensagens amostradas)")

    # ---- enviados ----
    enviados = listar(
        token, "sentitems",
        "toRecipients,subject,sentDateTime,conversationId",
        orderby="sentDateTime desc",
    )
    w(f"\nENVIADOS: {len(enviados)} mensagens analisadas")
    if enviados:
        dest = Counter()
        for m in enviados:
            for r in m.get("toRecipients", []):
                dest[r["emailAddress"]["address"].lower()] += 1
        w("\n  TOP 15 DESTINATARIOS:")
        for d, qtd in dest.most_common(15):
            w(f"    {qtd:4d}x  {d}")
        w("\n  ULTIMOS 15 ASSUNTOS ENVIADOS:")
        for m in enviados[:15]:
            w(f"    {(m.get('subject') or '(sem assunto)')[:100]}")

    # ---- cruzamento: conversas respondidas ----
    if entrada and enviados:
        conv_enviadas = {m["conversationId"] for m in enviados if m.get("conversationId")}
        respondidas = sum(
            1 for m in entrada if m.get("conversationId") in conv_enviadas
        )
        w("\nCRUZAMENTO (por conversa):")
        w(f"  Das {len(entrada)} mensagens recebidas analisadas, "
          f"{respondidas} pertencem a conversas com resposta enviada.")

    relatorio = "\n".join(out)
    with open("relatorio_investigacao.txt", "w", encoding="utf-8") as f:
        f.write(relatorio)
    print(relatorio)
    print("\nRelatorio salvo em relatorio_investigacao.txt")


if __name__ == "__main__":
    main()
