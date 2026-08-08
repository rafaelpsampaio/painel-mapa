# -*- coding: utf-8 -*-
"""
Painel web local da conciliacao de exames MAPA.

Uso: py painel.py  (ou duplo clique em "Painel MAPA.bat")
Abre http://127.0.0.1:8765 no navegador. So aceita conexoes do proprio
computador. A atualizacao acontece ao abrir a pagina e no botao Atualizar;
nao ha tarefa agendada.
"""

import json
import os
import sys
import threading
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import ler_repasses
import outlook_auth
import rotina_pendencias

# porta opcional na linha de comando (py painel.py 8799), padrao 8765
PORTA = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
URL = f"http://127.0.0.1:{PORTA}/"

# rodando via pythonw (sem console), manda prints para um log
if sys.stdout is None or sys.stderr is None:
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "relatorios"), exist_ok=True)
    _log = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "relatorios", "painel.log"), "a",
                encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = _log
    if sys.stderr is None:
        sys.stderr = _log
PASTA = os.path.dirname(os.path.abspath(__file__))
TRAVA = threading.Lock()  # uma varredura de cada vez


def salvar_historico(dados):
    texto = rotina_pendencias.relatorio_texto(dados)
    with open(os.path.join(PASTA, "relatorio_pendencias.txt"),
              "w", encoding="utf-8") as f:
        f.write(texto)
    os.makedirs(os.path.join(PASTA, "relatorios"), exist_ok=True)
    destino = os.path.join(
        PASTA, "relatorios",
        f"pendencias_{datetime.now().strftime('%Y-%m-%d')}.txt")
    with open(destino, "w", encoding="utf-8") as f:
        f.write(texto)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # sem ruido no console

    def _json(self, obj, status=200):
        corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        rota = urlparse(self.path)
        try:
            if rota.path == "/":
                with open(os.path.join(PASTA, "painel.html"), "rb") as f:
                    corpo = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            elif rota.path == "/api/ping":
                self._json({"painel": "mapa"})

            elif rota.path == "/api/dados":
                dias = int(parse_qs(rota.query).get("dias", ["30"])[0])
                dias = max(1, min(dias, 365))
                try:
                    token = outlook_auth.get_access_token("silencioso")
                except outlook_auth.AuthExpirada as e:
                    self._json({"precisa_login": True, "mensagem": str(e)})
                    return
                try:
                    import baixar_repasses
                    baixar_repasses.varrer(token)
                except Exception:
                    pass  # sem repasses novos nao pode travar o painel
                with TRAVA:
                    dados = rotina_pendencias.analisar(dias, token=token)
                try:
                    import cruzar_pagamentos
                    dados["pagamentos_orfaos"] = (
                        cruzar_pagamentos.anotar_pagamentos(dados))
                except Exception:
                    dados["pagamentos_orfaos"] = []
                salvar_historico(dados)
                self._json(dados)

            elif rota.path == "/api/financeiro":
                self._json(ler_repasses.financeiro())

            elif rota.path == "/api/realizados_fornecedor":
                import cruzar_pagamentos
                self._json(cruzar_pagamentos.agregar_por_mes_fornecedor())

            elif rota.path == "/api/importacoes":
                self._json(ler_repasses.importacoes())

            elif rota.path == "/api/config":
                pasta = ler_repasses.pasta_documentos()
                arquivos = (len(os.listdir(pasta)) if pasta else 0)
                self._json({"pasta_documentos": pasta or "",
                            "arquivos": arquivos})

            elif rota.path == "/api/login/start":
                resp = outlook_auth.iniciar_device_flow()
                self._json({
                    "uri": resp["verification_uri"],
                    "codigo": resp["user_code"],
                    "device_code": resp["device_code"],
                    "intervalo": int(resp.get("interval", 5)),
                })

            elif rota.path == "/api/login/poll":
                device_code = parse_qs(rota.query).get("device_code", [""])[0]
                self._json({"status": outlook_auth.poll_device(device_code)})

            else:
                self._json({"erro": "rota desconhecida"}, 404)
        except Exception as e:
            self._json({"erro": str(e)}, 500)

    def do_POST(self):
        rota = urlparse(self.path)
        try:
            if rota.path == "/api/config":
                tam = int(self.headers.get("Content-Length", "0"))
                corpo = json.loads(self.rfile.read(tam).decode("utf-8"))
                pasta = (corpo.get("pasta_documentos") or "").strip()
                if pasta and not os.path.isdir(pasta):
                    self._json({"ok": False,
                                "erro": "Pasta não encontrada: " + pasta}, 400)
                    return
                with open(ler_repasses.ARQ_CONFIG_LOCAL, "w",
                          encoding="utf-8") as f:
                    json.dump({"pasta_documentos": pasta}, f,
                              ensure_ascii=False)
                arquivos = len(os.listdir(pasta)) if pasta else 0
                self._json({"ok": True, "pasta_documentos": pasta,
                            "arquivos": arquivos})
            elif rota.path == "/api/sair":
                self._json({"ok": True})
                threading.Thread(target=self.server.shutdown,
                                 daemon=True).start()
            elif rota.path == "/api/baixa":
                tam = int(self.headers.get("Content-Length", "0"))
                corpo = json.loads(self.rfile.read(tam).decode("utf-8"))
                cod = rotina_pendencias.registrar_baixa(
                    corpo.get("codigo", ""), corpo.get("motivo", ""))
                self._json({"ok": True, "codigo": cod})
            else:
                self._json({"erro": "rota desconhecida"}, 404)
        except ValueError as e:
            self._json({"erro": str(e)}, 400)
        except Exception as e:
            self._json({"erro": str(e)}, 500)


def ja_rodando():
    try:
        with urllib.request.urlopen(f"{URL}api/ping", timeout=2) as r:
            return json.load(r).get("painel") == "mapa"
    except Exception:
        return False


def main():
    if ja_rodando():
        print("O painel ja estava aberto; abrindo o navegador.")
        webbrowser.open(URL)
        return
    servidor = ThreadingHTTPServer(("127.0.0.1", PORTA), Handler)
    threading.Timer(0.8, lambda: webbrowser.open(URL)).start()
    print(f"Painel disponivel em {URL}")
    print("Deixe esta janela aberta enquanto usa o painel; "
          "feche-a para encerrar.")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
