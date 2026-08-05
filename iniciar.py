# -*- coding: utf-8 -*-
"""Ponto de entrada do painel: tenta atualizar o codigo e abre.
Qualquer problema na atualizacao e ignorado (abre a versao atual)."""

import os
import subprocess
import sys
import traceback

PASTA = os.path.dirname(os.path.abspath(__file__))


def _instalar_dependencias():
    """Instala openpyxl/pypdf se faltarem (ex.: computador novo onde o
    instalar.bat nao chegou a rodar isso, ou rodou sem internet)."""
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet",
         "--disable-pip-version-check", "-r",
         os.path.join(PASTA, "requirements.txt")],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"pip install falhou:\n{r.stdout}\n{r.stderr}")


def _erro_fatal(titulo, mensagem):
    """Roda via pyw (sem console): sem isso um erro aqui trava tudo em
    silencio. Grava no log e mostra um aviso nativo do Windows."""
    try:
        os.makedirs(os.path.join(PASTA, "relatorios"), exist_ok=True)
        with open(os.path.join(PASTA, "relatorios", "painel.log"), "a",
                  encoding="utf-8") as f:
            f.write(f"\n=== {titulo} ===\n{mensagem}\n")
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0, mensagem + "\n\nMande um print desta tela para o Rafael.",
            titulo, 0x10)  # MB_ICONERROR
    except Exception:
        pass


try:
    import atualizar_app
    resultado = atualizar_app.verificar()
    print(f"atualizacao: {resultado}")
except Exception as e:  # sem internet, sem config etc.: segue o jogo
    print(f"atualizacao pulada: {e}")

# importa DEPOIS da atualizacao, para ja carregar o codigo novo
try:
    import painel  # noqa: E402
except ModuleNotFoundError:
    # primeira vez neste computador: faltam bibliotecas, instala e tenta de novo
    try:
        _instalar_dependencias()
        import painel  # noqa: E402
    except Exception:
        _erro_fatal("Painel MAPA nao conseguiu abrir",
                     traceback.format_exc())
        sys.exit(1)
except Exception:
    _erro_fatal("Painel MAPA nao conseguiu abrir", traceback.format_exc())
    sys.exit(1)

try:
    painel.main()
except Exception:
    _erro_fatal("Painel MAPA nao conseguiu abrir", traceback.format_exc())
    sys.exit(1)
