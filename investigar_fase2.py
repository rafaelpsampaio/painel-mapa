# -*- coding: utf-8 -*-
"""
Fase 2 da investigacao: confirma a hipotese de fluxo
(entrada = pendentes; respondidos vao para a pasta MAPA)
e examina como as respostas enviadas se parecem.
"""

import json
import sys
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone

import outlook_auth

GRAPH = "https://graph.microsoft.com/v1.0"


def gget(token, url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        print(f"ERRO HTTP {e.code} em {url}\n{e.read().decode('utf-8', 'replace')[:300]}")
        sys.exit(2)


def listar_url(token, url, max_msgs):
    out = []
    while url and len(out) < max_msgs:
        data = gget(token, url)
        out.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
    return out[:max_msgs]


def listar(token, pasta_id, select, max_msgs, orderby, expand=None):
    params = f"$select={select}&$top=100&$orderby={urllib.parse.quote(orderby)}"
    if expand:
        params += f"&$expand={urllib.parse.quote(expand)}"
    return listar_url(
        token, f"{GRAPH}/me/mailFolders/{pasta_id}/messages?{params}", max_msgs
    )


def main():
    token = outlook_auth.get_access_token()
    out = []
    w = out.append
    w("INVESTIGACAO FASE 2 - PASTA MAPA x ENVIADOS")
    w("=" * 60)

    pastas = gget(token, f"{GRAPH}/me/mailFolders?$top=50").get("value", [])
    ids = {p["displayName"]: p["id"] for p in pastas}
    if "MAPA" not in ids:
        print("Pasta MAPA nao encontrada")
        sys.exit(1)

    # enviados (ate 600, mais recentes)
    enviados = listar(
        token, "sentitems",
        "toRecipients,subject,sentDateTime,conversationId,hasAttachments",
        600, "sentDateTime desc",
    )
    conv_enviadas = {}
    for m in enviados:
        cid = m.get("conversationId")
        if cid and cid not in conv_enviadas:
            conv_enviadas[cid] = m["sentDateTime"]
    mais_antigo_env = enviados[-1]["sentDateTime"] if enviados else None
    w(f"\nENVIADOS: {len(enviados)} analisados "
      f"(desde {mais_antigo_env})")
    com_anexo_env = sum(1 for m in enviados if m.get("hasAttachments"))
    w(f"  Com anexo: {com_anexo_env} de {len(enviados)}")

    # pasta MAPA (ate 300, mais recentes)
    mapa = listar(
        token, ids["MAPA"],
        "from,subject,receivedDateTime,conversationId,hasAttachments",
        300, "receivedDateTime desc",
    )
    w(f"\nPASTA MAPA: {len(mapa)} mensagens analisadas "
      f"(de {mapa[-1]['receivedDateTime']} ate {mapa[0]['receivedDateTime']})")

    # so compara mensagens do MAPA dentro da janela coberta pelos enviados
    janela = [m for m in mapa if m["receivedDateTime"] >= mais_antigo_env]
    respondidas = [m for m in janela if m.get("conversationId") in conv_enviadas]
    w(f"\nCRUZAMENTO (janela coberta pelos enviados: {len(janela)} msgs):")
    if janela:
        pct = 100 * len(respondidas) / len(janela)
        w(f"  Com resposta enviada na mesma conversa: "
          f"{len(respondidas)} ({pct:.0f}%)")

    remetentes_mapa = Counter()
    for m in mapa:
        try:
            remetentes_mapa[m["from"]["emailAddress"]["address"].lower()] += 1
        except (KeyError, TypeError):
            pass
    w("\n  REMETENTES NA PASTA MAPA (top 10):")
    for rem, qtd in remetentes_mapa.most_common(10):
        w(f"    {qtd:4d}x  {rem}")

    w("\n  EXEMPLOS DE ASSUNTO NA PASTA MAPA (20 recentes):")
    for m in mapa[:20]:
        marca = "[OK]" if m.get("conversationId") in conv_enviadas else "[??]"
        w(f"    {marca} {(m.get('subject') or '(sem assunto)')[:90]}")

    # como sao as respostas enviadas: anexos e corpo
    env_anexo = listar(
        token, "sentitems",
        "toRecipients,subject,sentDateTime,hasAttachments",
        20, "sentDateTime desc",
        expand="attachments($select=name)",
    )
    w("\nANEXOS DAS ULTIMAS RESPOSTAS ENVIADAS:")
    for m in env_anexo:
        nomes = [a.get("name") for a in m.get("attachments", [])]
        if nomes:
            w(f"  [{(m.get('subject') or '')[:50]}]")
            for n in nomes:
                w(f"      {n}")

    env_corpo = listar(
        token, "sentitems", "subject,bodyPreview", 8, "sentDateTime desc",
    )
    w("\nPREVIA DO CORPO DAS ULTIMAS RESPOSTAS:")
    for m in env_corpo:
        prev = (m.get("bodyPreview") or "").replace("\r", " ").replace("\n", " ")
        w(f"  [{(m.get('subject') or '')[:50]}] {prev[:160]}")

    relatorio = "\n".join(out)
    with open("relatorio_fase2.txt", "w", encoding="utf-8") as f:
        f.write(relatorio)
    print(relatorio)


if __name__ == "__main__":
    main()
