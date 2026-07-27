# -*- coding: utf-8 -*-
"""
Varre a caixa inteira atras de demonstrativos de pagamento (IDS, Unimed,
CardioPro) e baixa os anexos para repasses/, prefixados com a data do email
(AAAA-MM-DD_nome.pdf). Ja baixados sao pulados.

Remetentes monitorados: giperroud (encaminhamentos da Dra.), contasmedicas
da IDS e faturamento da CardioPro.

Uso: py baixar_repasses.py
"""

import base64
import json
import os
import re
import urllib.parse
import urllib.request

import outlook_auth

GRAPH = "https://graph.microsoft.com/v1.0"
DESTINO = "repasses"
BUSCAS = ["from:giperroud", "from:contasmedicas",
          "from:analaurafaturamentocardiopro", "from:fgsampaio65"]
# padroes de anexo que caracterizam demonstrativo de pagamento
RE_REPASSE = re.compile(
    r"(?i)(fernando sampaio|gisele.*sampaio|exibedemonstrativo|"
    r"^repasse.*\.xlsx$|demonstrativo)")


def gget(token, url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


INDICE = os.path.join(DESTINO, ".mensagens_verificadas.json")


def varrer(token=None):
    """Baixa demonstrativos novos; mensagens ja verificadas sao puladas.
    Retorna (baixados, pulados)."""
    if token is None:
        token = outlook_auth.get_access_token()
    os.makedirs(DESTINO, exist_ok=True)
    try:
        with open(INDICE, "r", encoding="utf-8") as f:
            verificadas = set(json.load(f))
    except (OSError, ValueError):
        verificadas = set()
    vistos_msg = set(verificadas)
    baixados = pulados = 0

    for busca in BUSCAS:
        url = (f"{GRAPH}/me/messages?$search={urllib.parse.quote(chr(34) + busca + chr(34))}"
               "&$select=id,subject,from,receivedDateTime,hasAttachments&$top=100")
        while url:
            data = gget(token, url)
            for m in data.get("value", []):
                if m["id"] in vistos_msg or not m.get("hasAttachments"):
                    continue
                vistos_msg.add(m["id"])
                anexos = gget(
                    token, f"{GRAPH}/me/messages/{m['id']}/attachments"
                           "?$select=id,name,size").get("value", [])
                for a in anexos:
                    nome = a.get("name") or ""
                    if not RE_REPASSE.search(nome):
                        continue
                    if not nome.lower().endswith((".pdf", ".xlsx")):
                        continue
                    limpo = re.sub(r'[\\/:*?"<>|]', "_", nome)
                    destino = os.path.join(
                        DESTINO, f"{m['receivedDateTime'][:10]}_{limpo}")
                    if os.path.exists(destino):
                        pulados += 1
                        continue
                    cheio = gget(token,
                                 f"{GRAPH}/me/messages/{m['id']}/attachments/"
                                 f"{a['id']}")
                    if "contentBytes" not in cheio:
                        continue
                    with open(destino, "wb") as f:
                        f.write(base64.b64decode(cheio["contentBytes"]))
                    baixados += 1
                    print(f"baixado: {os.path.basename(destino)}")
            url = data.get("@odata.nextLink")

    with open(INDICE, "w", encoding="utf-8") as f:
        json.dump(sorted(vistos_msg), f)
    return baixados, pulados


def main():
    baixados, pulados = varrer()
    print(f"\nConcluido: {baixados} novos, {pulados} ja existiam.")


if __name__ == "__main__":
    main()
