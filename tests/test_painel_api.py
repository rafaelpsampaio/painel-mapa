import json
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer

# Limpa sys.argv para permitir importacao de painel.py (que usa argv para porta)
_argv_orig = sys.argv[:]
sys.argv = [sys.argv[0]]

import painel

sys.argv = _argv_orig


def test_api_importacoes_retorna_estrutura_local_e_email():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), painel.Handler)
    porta = servidor.server_address[1]
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{porta}/api/importacoes", timeout=5) as resp:
            dados = json.loads(resp.read())
        assert set(dados.keys()) == {"local", "email"}
        for secao in ("local", "email"):
            assert "pasta" in dados[secao]
            assert "arquivos" in dados[secao]
            assert isinstance(dados[secao]["arquivos"], list)
    finally:
        servidor.shutdown()
        thread.join(timeout=5)


def test_api_recebimentos_retorna_estrutura():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), painel.Handler)
    porta = servidor.server_address[1]
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{porta}/api/recebimentos", timeout=30) as resp:
            dados = json.loads(resp.read())
        assert set(dados.keys()) == {"totais", "por_mes", "por_exame",
                                     "eventos", "sem_pagamento", "cobertura",
                                     "documentos"}
        assert {"valor", "exames", "consultas", "por_pagador"} <= set(dados["totais"])
    finally:
        servidor.shutdown()
        thread.join(timeout=5)


def test_api_financeiro_removida():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), painel.Handler)
    porta = servidor.server_address[1]
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    try:
        import urllib.error
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{porta}/api/financeiro", timeout=10)
            assert False, "rota deveria ter sumido"
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        servidor.shutdown()
        thread.join(timeout=5)
