# -*- coding: utf-8 -*-
"""
Autenticacao OAuth2 (device code flow) para IMAP de conta pessoal Outlook/Hotmail.

Uso inicial:  py outlook_auth.py
  -> mostra um link e um codigo; voce faz login na pagina da Microsoft.
  -> tokens ficam salvos em token_cache.json (local, fora do git).

Depois, os outros scripts chamam get_access_token(), que renova sozinho.
Nenhuma senha e armazenada.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request

CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"  # Microsoft Graph PowerShell (publico)
SCOPE = "https://graph.microsoft.com/Mail.Read offline_access"
AUTHORITY = "https://login.microsoftonline.com/consumers/oauth2/v2.0"
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token_cache.json")


def _post(url, params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return {"error": f"http_{e.code}"}


def _save(tok):
    tok["expires_at"] = time.time() + int(tok.get("expires_in", 3600)) - 60
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(tok, f)


class AuthExpirada(Exception):
    """Sem acesso valido a caixa; e preciso logar de novo."""


def iniciar_device_flow():
    """Inicia o device flow; retorna resposta com user_code/verification_uri."""
    resp = _post(f"{AUTHORITY}/devicecode", {"client_id": CLIENT_ID, "scope": SCOPE})
    if "user_code" not in resp:
        raise AuthExpirada(f"Falha ao iniciar autenticacao: {resp}")
    return resp


def poll_device(device_code):
    """Uma tentativa de concluir o device flow.
    Retorna 'ok' (tokens salvos), 'aguardando' ou mensagem de erro."""
    tok = _post(f"{AUTHORITY}/token", {
        "client_id": CLIENT_ID,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "device_code": device_code,
    })
    if "access_token" in tok:
        _save(tok)
        return "ok"
    if tok.get("error") in ("authorization_pending", "slow_down"):
        return "aguardando"
    return tok.get("error_description") or tok.get("error", "erro desconhecido")


def device_flow():
    try:
        resp = iniciar_device_flow()
    except AuthExpirada as e:
        print(e)
        sys.exit(2)
    print("=" * 60)
    print("ACESSE:", resp["verification_uri"])
    print("CODIGO:", resp["user_code"])
    print("=" * 60)
    print("Aguardando voce concluir o login (ate 15 minutos)...", flush=True)
    intervalo = int(resp.get("interval", 5))
    prazo = time.time() + int(resp.get("expires_in", 900))
    while time.time() < prazo:
        time.sleep(intervalo)
        tok = _post(f"{AUTHORITY}/token", {
            "client_id": CLIENT_ID,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": resp["device_code"],
        })
        if "access_token" in tok:
            _save(tok)
            print("Autenticado com sucesso. Tokens salvos em token_cache.json")
            return tok
        erro = tok.get("error")
        if erro == "slow_down":
            intervalo += 5
        elif erro != "authorization_pending":
            print("Erro na autenticacao:", erro, tok.get("error_description", ""))
            sys.exit(2)
    print("Tempo esgotado. Rode novamente: py outlook_auth.py")
    sys.exit(2)


def _reautenticar(motivo):
    """Sem acesso valido: se ha alguem no console, reloga na hora;
    se e execucao agendada, registra instrucao clara e sai."""
    if sys.stdout.isatty():
        print(f"{motivo} E preciso entrar na conta de novo (leva 1 minuto).")
        tok = device_flow()
        return tok["access_token"]
    print(motivo)
    print("ACESSO AO EMAIL EXPIROU OU FOI REVOGADO.")
    print("Abra 'Autenticar Email.bat' na pasta do programa para entrar de novo.")
    sys.exit(2)


def get_access_token(modo="auto"):
    """Retorna access token valido, renovando via refresh token se preciso.

    modo="auto": sem acesso, reloga no console (interativo) ou sai com erro.
    modo="silencioso": sem acesso, levanta AuthExpirada (usado pelo painel).
    """
    def sem_acesso(motivo):
        if modo == "silencioso":
            raise AuthExpirada(motivo)
        return _reautenticar(motivo)

    if not os.path.exists(CACHE):
        return sem_acesso("Nenhum acesso salvo neste computador.")
    with open(CACHE, "r", encoding="utf-8") as f:
        tok = json.load(f)
    if time.time() < tok.get("expires_at", 0):
        return tok["access_token"]
    novo = _post(f"{AUTHORITY}/token", {
        "client_id": CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": tok["refresh_token"],
        "scope": SCOPE,
    })
    if "access_token" not in novo:
        return sem_acesso(
            f"Falha ao renovar acesso ({novo.get('error', 'erro desconhecido')}).")
    if "refresh_token" not in novo:
        novo["refresh_token"] = tok["refresh_token"]
    _save(novo)
    return novo["access_token"]


if __name__ == "__main__":
    device_flow()
