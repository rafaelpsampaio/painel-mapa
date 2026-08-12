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


def test_api_recebimentos_aceita_filtro_de_data():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), painel.Handler)
    porta = servidor.server_address[1]
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{porta}/api/recebimentos"
                "?de=2026-01-01&ate=2026-12-31", timeout=30) as resp:
            dados = json.loads(resp.read())
        assert set(dados.keys()) == {"totais", "por_mes", "por_exame",
                                     "eventos", "sem_pagamento", "cobertura",
                                     "documentos"}
    finally:
        servidor.shutdown()
        thread.join(timeout=5)


def test_api_exportar_devolve_xlsx():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), painel.Handler)
    porta = servidor.server_address[1]
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    try:
        payload = json.dumps({
            "titulo": "Exames",
            "colunas": [{"chave": "codigo", "rotulo": "Código", "tipo": "texto"}],
            "linhas": [{"codigo": "ED9-00159"}],
        }).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{porta}/api/exportar", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            assert resp.headers["Content-Type"] == (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet")
            assert "Exames_" in resp.headers["Content-Disposition"]
            conteudo = resp.read()
        import io as _io
        import openpyxl as _openpyxl
        wb = _openpyxl.load_workbook(_io.BytesIO(conteudo))
        assert wb.active.cell(row=1, column=1).value == "Código"
    finally:
        servidor.shutdown()
        thread.join(timeout=5)
