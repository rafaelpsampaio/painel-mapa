# -*- coding: utf-8 -*-
"""Lista mensagens recentes da caixa (todas, nao so .dmw) para identificar
os exemplos encaminhados de demonstrativos de pagamento (IDS, Unimed)."""

import json
import urllib.request
import urllib.parse

import outlook_auth

GRAPH = "https://graph.microsoft.com/v1.0"


def gget(token, url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main():
    token = outlook_auth.get_access_token()
    params = (
        "$select=id,from,subject,receivedDateTime,hasAttachments,bodyPreview"
        "&$top=25&$orderby=receivedDateTime%20desc"
        "&$expand=" + urllib.parse.quote("attachments($select=id,name,size)")
    )
    data = gget(token, f"{GRAPH}/me/mailFolders/inbox/messages?{params}")
    for m in data.get("value", []):
        try:
            rem = m["from"]["emailAddress"]["address"]
        except (KeyError, TypeError):
            rem = "?"
        print("=" * 70)
        print(f"DE: {rem}")
        print(f"DATA: {m['receivedDateTime']}")
        print(f"ASSUNTO: {m.get('subject')}")
        print(f"ID: {m['id'][:40]}...")
        for a in m.get("attachments", []):
            print(f"  ANEXO: {a.get('name')}  ({a.get('size', 0)} bytes)")
        prev = (m.get("bodyPreview") or "").replace("\r", " ").replace("\n", " ")
        print(f"  PREVIA: {prev[:220]}")


if __name__ == "__main__":
    main()
