# -*- coding: utf-8 -*-
"""Ponto de entrada do painel: tenta atualizar o codigo e abre.
Qualquer problema na atualizacao e ignorado (abre a versao atual)."""

import sys

try:
    import atualizar_app
    resultado = atualizar_app.verificar()
    print(f"atualizacao: {resultado}")
except Exception as e:  # sem internet, sem config etc.: segue o jogo
    print(f"atualizacao pulada: {e}")

# importa DEPOIS da atualizacao, para ja carregar o codigo novo
import painel  # noqa: E402

painel.main()
