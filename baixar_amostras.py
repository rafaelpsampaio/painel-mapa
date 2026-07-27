# -*- coding: utf-8 -*-
"""Baixa para a pasta amostras/ os anexos dos emails encaminhados
com demonstrativos de pagamento (IDS, Unimed, CardioPro)."""

import base64
import json
import os
import re
import urllib.parse
import urllib.request

import outlook_auth

GRAPH = "https://graph.microsoft.com/v1.0"
DESTINO = "amostras"


def gget(token, url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def main():
    token = outlook_auth.get_access_token()
    os.makedirs(DESTINO, exist_ok=True)
    params = (
        "$select=id,from,subject,receivedDateTime,hasAttachments"
        "&$top=15&$orderby=receivedDateTime%20desc"
        "&$filter=" + urllib.parse.quote("receivedDateTime ge 2026-07-25T20:00:00Z")
    )
    msgs = gget(token, f"{GRAPH}/me/mailFolders/inbox/messages?{params}")["value"]
    for m in msgs:
        try:
            rem = m["from"]["emailAddress"]["address"].lower()
        except (KeyError, TypeError):
            rem = "?"
        if "giperroud" not in rem or not m.get("hasAttachments"):
            continue
        anexos = gget(token, f"{GRAPH}/me/messages/{m['id']}/attachments")["value"]
        for a in anexos:
            if "contentBytes" not in a:
                continue
            nome = re.sub(r'[\\/:*?"<>|]', "_", a["name"])
            caminho = os.path.join(DESTINO, nome)
            with open(caminho, "wb") as f:
                f.write(base64.b64decode(a["contentBytes"]))
            print(f"Salvo: {caminho}  ({len(a['contentBytes']) * 3 // 4} bytes)")


if __name__ == "__main__":
    main()
