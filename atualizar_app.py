# -*- coding: utf-8 -*-
"""
Autoatualizador: antes de abrir, verifica no GitHub se ha versao nova do
codigo e aplica. So sobrescreve arquivos de CODIGO (py/html/vbs/bat e
LEIA-ME.txt); dados locais (baixas, tokens, repasses, relatorios) nunca
sao tocados. Qualquer erro e silencioso: o app abre na versao atual.

Config em atualizacao.json: {"repo": "usuario/nome", "branch": "main"}
Repo privado: colocar um token de leitura em update_token.txt (nao
versionado).
"""

import io
import json
import os
import urllib.request
import zipfile

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ_CONFIG = os.path.join(PASTA, "atualizacao.json")
ARQ_VERSAO = os.path.join(PASTA, ".versao")
ARQ_TOKEN = os.path.join(PASTA, "update_token.txt")

EXTENSOES = (".py", ".html", ".vbs", ".bat")
TXT_PERMITIDOS = {"leia-me.txt"}
NUNCA = {"baixas.txt", "update_token.txt", "token_cache.json",
         "atualizacao.json", ".versao", ".env", ".env.txt"}


def _req(url, token):
    cab = {"User-Agent": "painel-mapa", "Accept": "application/vnd.github+json"}
    if token:
        cab["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=cab)


def verificar():
    """Retorna string descrevendo o resultado (para log)."""
    if os.path.isdir(os.path.join(PASTA, ".git")):
        # maquina de desenvolvimento: quem manda e o git, nao o updater
        return "maquina de desenvolvimento (.git presente): pulado"
    with open(ARQ_CONFIG, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    repo = cfg["repo"]
    branch = cfg.get("branch", "main")
    token = None
    if os.path.exists(ARQ_TOKEN):
        with open(ARQ_TOKEN, "r", encoding="utf-8") as f:
            token = f.read().strip() or None

    with urllib.request.urlopen(
            _req(f"https://api.github.com/repos/{repo}/commits/{branch}",
                 token), timeout=15) as r:
        sha = json.load(r)["sha"]

    atual = ""
    if os.path.exists(ARQ_VERSAO):
        with open(ARQ_VERSAO, "r", encoding="utf-8") as f:
            atual = f.read().strip()
    if atual == sha:
        return f"ja atualizado ({sha[:10]})"

    with urllib.request.urlopen(
            _req(f"https://api.github.com/repos/{repo}/zipball/{branch}",
                 token), timeout=60) as r:
        dados = r.read()

    aplicados = 0
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            # remove o prefixo usuario-repo-sha/ do zipball
            rel = info.filename.split("/", 1)[-1]
            nome = os.path.basename(rel).lower()
            if nome in NUNCA:
                continue
            if not (nome.endswith(EXTENSOES) or nome in TXT_PERMITIDOS):
                continue
            destino = os.path.normpath(os.path.join(PASTA, rel))
            if not destino.startswith(PASTA):
                continue  # protecao contra caminhos maliciosos
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            with z.open(info) as origem, open(destino, "wb") as f:
                f.write(origem.read())
            aplicados += 1

    with open(ARQ_VERSAO, "w", encoding="utf-8") as f:
        f.write(sha)
    return f"atualizado para {sha[:10]} ({aplicados} arquivos)"


if __name__ == "__main__":
    print(verificar())
