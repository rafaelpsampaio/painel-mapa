# Aba "Importações" — design

## Objetivo

Hoje, quando `ler_repasses.coletar()` varre as pastas de demonstrativos, qualquer
arquivo que nenhum parser reconhece (extensão não suportada, ou PDF/XLSX de
formato desconhecido) é descartado silenciosamente. Se um parser lança
exceção, ela só vai pro `print()` do console, que ninguém vê rodando via
`pythonw`. Não há como a Dra. Gisele saber que um demonstrativo ficou de fora
da conciliação.

Nova aba **Importações** no painel: lista cada arquivo das pastas
processadas como um card horizontal, mostrando o que foi reconhecido (tipo
amigável + resumo) e destacando os que não foram (não identificado ou erro).
O seletor de pasta local, hoje na aba Financeiro, muda para cá.

## Escopo de pastas

Duas seções, pasta local em primeiro (prioridade combinada com a usuária):

1. **Pasta local** — a pasta configurada manualmente em `config.json`
   (`pasta_documentos`). Inclui o campo de caminho + botão Salvar, movidos da
   aba Financeiro (sai de lá, fica só aqui).
2. **Pasta do email (`repasses/`)** — arquivos baixados automaticamente pelo
   fluxo de email. Só leitura, sem seletor.

A pasta `amostras/` (reserva de dev quando `repasses/` está vazio) não é
mostrada nesta aba — é um detalhe interno de desenvolvimento, não uma pasta
real de importação pra usuária final.

## Back-end (`ler_repasses.py`)

Extrai a lógica "tentar os parsers em cadeia" pra uma função compartilhada,
preservando o comportamento atual de `coletar()` (usado por `financeiro()`)
e alimentando a nova função de inventário:

```python
PARSERS_PDF = [processar_ids, processar_unimed, processar_listagem_exames]

NOMES_AMIGAVEIS = {
    "IDS - Listagem de Repasse": "IDS · Repasse por unidade",
    "IDS - Listagem de Exames/Laudos": "IDS · Exames e laudos",
    "Unimed - Demonstrativo": "Unimed · Demonstrativo",
    "CardioPro - Planilha de repasse": "CardioPro · Planilha",
}

def _tentar_parsers(caminho):
    """Roda o(s) parser(es) da extensao do arquivo.
    Devolve (resumo, erro): resumo e None se nenhum parser reconheceu o
    conteudo; erro e a mensagem de excecao se algum parser quebrou."""
    ext = os.path.splitext(caminho)[1].lower()
    try:
        if ext == ".pdf":
            r = None
            for parser in PARSERS_PDF:
                r = parser(caminho)
                if r:
                    break
            return r, None
        if ext == ".xlsx":
            return processar_cardiopro(caminho), None
        return None, None
    except Exception as e:
        return None, str(e)
```

`coletar()` passa a chamar `_tentar_parsers` internamente, mesma semântica
de hoje (se um parser da cadeia lança exceção, o arquivo inteiro cai em erro
sem tentar os parsers seguintes da cadeia — igual ao comportamento atual).

Nova função de inventário, uma entrada por arquivo:

```python
def _inspecionar_arquivo(caminho):
    nome = os.path.basename(caminho)
    ext = os.path.splitext(nome)[1].lower()
    if ext not in (".pdf", ".xlsx"):
        return {"arquivo": nome, "status": "nao_identificado",
                "motivo": f'Extensão "{ext or "(sem extensão)"}" ainda não tem parser'}
    r, erro = _tentar_parsers(caminho)
    if erro:
        return {"arquivo": nome, "status": "erro", "motivo": erro}
    if r is None:
        return {"arquivo": nome, "status": "nao_identificado",
                "motivo": "Nenhum parser conhecido reconheceu o conteúdo deste arquivo"}
    return {"arquivo": nome, "status": "ok", "tipo": r["tipo"],
            "tipo_amigavel": NOMES_AMIGAVEIS.get(r["tipo"], r["tipo"]),
            "resumo": _macro(r)}


def inventario_pasta(pasta):
    if not pasta or not os.path.isdir(pasta):
        return []
    return [_inspecionar_arquivo(c)
            for c in sorted(glob.glob(os.path.join(pasta, "*")))
            if os.path.isfile(c)]


def importacoes():
    local = pasta_documentos()
    return {
        "local": {"pasta": local or "",
                  "arquivos": inventario_pasta(local) if local else []},
        "email": {"pasta": "repasses", "arquivos": inventario_pasta("repasses")},
    }
```

`_macro(r)` monta o resumo de uma linha por tipo (reaproveita campos que os
parsers já produzem, sem tocar nos parsers em si):

- IDS Repasse: `"{qtd} exames · R$ {valor}"` (ou contagem de setores se não
  houver total)
- IDS Exames/Laudos: `"{total} exames · período {periodo}"`
- Unimed: `"R$ {liquido} líquido · período {periodo}"`
- CardioPro: `"{n} mes(es) · {ecg} ECG · {mapa} MAPA"`

## API (`painel.py`)

Novo endpoint:

```python
elif rota.path == "/api/importacoes":
    self._json(ler_repasses.importacoes())
```

O endpoint existente `POST /api/config` (salvar pasta local) é reaproveitado
sem mudanças.

## Front-end (`painel.html`)

Nova aba no menu, ao final: `Visão geral | Exames | Financeiro | Análises |
Importações`.

Remove o bloco "Pasta local de documentos" da aba Financeiro; ele passa a
viver no topo da aba Importações (mesmos ids/função `salvarPasta()`, só
reposicionado). Após salvar com sucesso, além de recarregar Financeiro e
Análises (como já faz), recarrega também a nova aba.

Estrutura da aba, de cima pra baixo:

1. Bloco "Pasta local" — campo de caminho + Salvar (movido da aba
   Financeiro) + contagem de arquivos.
2. Seção **Pasta local**: nota fixa listando os 4 parsers conhecidos ("Hoje
   reconhecemos: IDS · Repasse por unidade, IDS · Exames e laudos, Unimed ·
   Demonstrativo, CardioPro · Planilha"), linha de resumo ("14 arquivos · 2
   não identificados · 1 com erro"), lista de cards.
3. Seção **Pasta do email (repasses)**: mesma estrutura, sem seletor.

Estados vazios:
- Pasta local não configurada: mensagem "Nenhuma pasta configurada. Cole o
  caminho acima e salve." sem lista de cards.
- Pasta configurada mas sem arquivos, ou `repasses/` vazia: "Nenhum arquivo
  encontrado nesta pasta."

### Card horizontal

Uma faixa de cor à esquerda por status:

- **`ok`** (azul): nome do arquivo, tipo amigável em destaque, resumo de uma
  linha.
- **`nao_identificado`** (âmbar): nome do arquivo, badge "Não identificado",
  motivo.
- **`erro`** (vermelho): nome do arquivo, badge "Erro ao ler", mensagem da
  exceção.

### Ordenação

Dentro de cada seção: `erro` → `nao_identificado` → `ok`, e dentro de cada
grupo por nome de arquivo. Problemas aparecem primeiro, sem precisar
procurar.

## Fora de escopo

- Não altera os parsers existentes nem a lógica de `financeiro()` /
  `cruzar_pagamentos.py` (comportamento preservado via `_tentar_parsers`
  compartilhado).
- Não adiciona parser novo para nenhum formato ainda não suportado — o
  objetivo é só visibilidade.
- Não mostra a pasta `amostras/` (reserva de dev).
