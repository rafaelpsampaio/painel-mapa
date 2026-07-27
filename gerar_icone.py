# -*- coding: utf-8 -*-
"""Gera painel.ico (coracao vermelho) sem depender de bibliotecas."""

import struct

TAM = 32
FUNDO = (0, 0, 0, 0)          # transparente
COR = (60, 60, 200, 255)      # vermelho (ordem BGRA)


def dentro_coracao(px, py):
    # formula classica do coracao: (x^2 + y^2 - 1)^3 - x^2*y^3 <= 0
    x = (px - TAM / 2 + 0.5) / (TAM / 2.6)
    y = -(py - TAM / 2 + 0.5) / (TAM / 2.6) + 0.2
    return (x * x + y * y - 1) ** 3 - x * x * y ** 3 <= 0


linhas = []
for py in range(TAM - 1, -1, -1):  # BMP e de baixo para cima
    linha = b""
    for px in range(TAM):
        cor = COR if dentro_coracao(px, py) else FUNDO
        linha += bytes(cor)
    linhas.append(linha)
pixels = b"".join(linhas)
mascara = b"\x00" * (TAM * 4)  # AND mask zerada (alfa ja resolve)

bmp = struct.pack("<IiiHHIIiiII", 40, TAM, TAM * 2, 1, 32, 0,
                  len(pixels) + len(mascara), 0, 0, 0, 0)
imagem = bmp + pixels + mascara
cabecalho = struct.pack("<HHH", 0, 1, 1)
entrada = struct.pack("<BBBBHHII", TAM, TAM, 0, 0, 1, 32,
                      len(imagem), 6 + 16)

with open("painel.ico", "wb") as f:
    f.write(cabecalho + entrada + imagem)
print("painel.ico gerado")
