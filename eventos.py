# -*- coding: utf-8 -*-
"""Modelo central de eventos de pagamento.

Todo demonstrativo (IDS, Unimed, CardioPro) e reduzido a uma lista unica de
eventos {pagador, exame, paciente, data, valor, convenio, tipo, documento}.
As agregacoes do painel (por mes, por pagador, por exame) e a investigacao
de "sem pagamento" trabalham so em cima dessa lista.
"""

import re

import rotina_pendencias as rp
from ler_repasses import _regex_tolerante

# ordem de prioridade quando o mesmo exame aparece pago em mais de uma fonte
PRIORIDADE_PAGADOR = {"IDS": 0, "Unimed": 1, "CardioPro": 2}

# nomes de setor (IDS) e de procedimento (Relatorio de Repasses) -> canonico
EXAME_CANONICO = {
    "MAPA": "MAPA",
    "M.A.P.A": "MAPA",
    "TESTE ERGOMETRICO": "Teste Ergométrico",
    "TESTE ERGOMETRICO MIBI": "Teste Ergométrico MIBI",
    "HONORARIO MEDICO": "Laudo Stress Farmacológico",
    "LAUDO STRESS FARMACOLOGICO": "Laudo Stress Farmacológico",
    "ECG": "Eletrocardiograma",
    "ELETROCARDIOGRAMA": "Eletrocardiograma",
}

# codigos de servico dos demonstrativos Unimed/CardioPro -> canonico
CODIGO_UNIMED_CANONICO = {
    "20102038": "MAPA",
    "20102020": "Holter",
    "40101010": "Eletrocardiograma",
    "10101012": "Consulta",
    "99910073": "Consulta",
    "20101201": "Aval. marca-passo",
}


def exame_canonico(nome):
    """Nome canonico do exame; desconhecido passa como veio (title case)."""
    chave = rp.normalizar(nome)
    return EXAME_CANONICO.get(chave, (nome or "").strip().title())


# convenios conhecidos grudados no fim do campo "nome" da Listagem de
# Repasse da IDS (sem separador); descobertos minerando os sufixos
CONVENIO_DISPLAY = {
    "INTERMEDICA SAUDE S.A": "Intermédica",
    "INTERMEDICA- MEDIPLAN": "Intermédica",
    "CARTAO IDS MATRIZ": "Cartão IDS",
    "HAPVIDA - SOROCABA": "Hapvida",
    "BRADESCO OPERADORA PLANOS S/A": "Bradesco Operadora",
    "BRADESCO SAUDE": "Bradesco Saúde",
    "CAIXA ECONOMICA FEDERAL": "Caixa Econômica Federal",
    "SUL AMERICA": "Sul América",
    "PORTO SEGURO": "Porto Seguro",
    "CEPOS- EMPRESA": "Cepos",
    "UNIMED": "Unimed",
    "AMIL": "Amil",
    "APAS": "Apas",
    "CASSI": "Cassi",
    "CABESP": "Cabesp",
    "MARINHA": "Marinha",
}
_PADROES_CONVENIO = sorted(CONVENIO_DISPLAY, key=len, reverse=True)
_PADROES_CONVENIO = [(c, re.compile(_regex_tolerante(c) + r"$"))
                     for c in _PADROES_CONVENIO]


def separar_convenio(nome):
    """(nome sem o sufixo de convenio, convenio de exibicao ou None)."""
    for canonico, padrao in _PADROES_CONVENIO:
        m = padrao.search(nome or "")
        if m:
            return (nome[:m.start()].strip(), CONVENIO_DISPLAY[canonico])
    return ((nome or "").strip(), None)
