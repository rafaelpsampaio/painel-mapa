# Cache incremental de leitura de email — design

## Objetivo

`rotina_pendencias.analisar()` busca ao vivo no Graph API, toda vez que o
painel abre ou o botão "Atualizar email" é clicado, as pastas `inbox`,
`MAPA`, `UNIMED`, `IDS` e `sentitems` filtradas por um corte de dias
(`?dias=`, hoje 30/60/90/180). Não existe nenhum cache local dessa leitura:
cada abertura do painel refaz a varredura inteira, o que é a causa raiz da
demora ao iniciar o app, e piora conforme o período aumenta (daí o aviso
"mais lento" em 180 dias).

Este design introduz um cache local persistente das mensagens dessas 5
pastas, com uma primeira leitura completa cobrindo 2 anos (rodando sozinha,
em segundo plano, de forma resumível) e sincronizações incrementais rápidas
a partir daí. A lógica de conciliação (extração de código/nome, matching,
status, buracos de numeração) não muda — só deixa de depender de uma
chamada de rede a cada execução.

**Fora de escopo:** o fluxo de repasses/financeiro (`baixar_repasses.py` +
`ler_repasses.py`/`eventos.py`) já baixa arquivos localmente e não sofre
desse problema; não é tocado aqui. Filtro de data para exibição nas telas
fica para o sub-projeto de filtros/ordenação de tabelas — este design só
garante que os dados dos últimos 2 anos estejam sempre disponíveis
localmente; o que a tela mostra por padrão é decisão de outro momento.

## Formato do cache

Novo arquivo `cache_emails.json` na raiz do projeto (mesmo padrão de
`config.json`, `cache_pdf.json`, `atualizacao.json`):

```json
{
  "pastas": {
    "inbox": {
      "backfill_completo_ate": "2026-05-10T00:00:00Z",
      "ultimo_sync": "2026-08-12T14:00:00Z",
      "mensagens": {
        "AAMkAG...id_da_mensagem...": {
          "assunto": "...",
          "de": "remetente@dominio.com",
          "recebido": "2026-08-01T10:00:00Z",
          "conversa": "AAQkAG...",
          "anexos": ["0RC-04973 FULANA.dmw"],
          "corpo_texto": "..."
        }
      }
    },
    "MAPA": { "...": "..." },
    "UNIMED": { "...": "..." },
    "IDS": { "...": "..." },
    "sentitems": { "...": "..." }
  }
}
```

Guardamos os campos quase-crus da mensagem (assunto, remetente, data,
anexos, corpo em texto plano — mesma limpeza que `texto_plano()` já faz),
**não** o código/nome já extraídos. Assim, se uma regex de extração
(`RE_CODIGO`, `RE_NOME`, etc.) for ajustada no futuro, o histórico inteiro
se beneficia na próxima leitura, sem precisar reler nada do Outlook. Para
`sentitems` o campo de data equivalente é `sentDateTime`, guardado também
em `recebido` por simplicidade de formato (o significado depende da pasta).

## Módulo novo: `cache_email.py`

Responsável só por ler/escrever `cache_emails.json` e conversar com o Graph
API para popular/atualizar. `rotina_pendencias.analisar()` deixa de fazer
qualquer chamada HTTP: recebe as mensagens já sincronizadas (via
`cache_email.mensagens(pasta)`), reconstrói os dicionários `exames` /
`codigos_enviados` / `conversas_respondidas` e roda a mesma lógica de
conciliação que já existe hoje, inalterada.

### Backfill inicial (automático, resumível)

- Ao abrir o painel, para cada pasta cujo `backfill_completo_ate` ainda não
  cobre os últimos 2 anos, sincroniza em blocos mensais, do mês mais
  recente para o mais antigo (o que importa no dia a dia fica disponível
  primeiro).
- Cada bloco concluído grava `backfill_completo_ate` imediatamente, com
  escrita atômica (arquivo temporário + `os.replace()`). Uma interrupção
  (queda de internet, PC desligado) perde no máximo o bloco em andamento;
  a próxima abertura retoma dali, não do zero.
- Token renovado (`outlook_auth.get_access_token()`) a cada poucos blocos,
  já que o backfill completo (2 anos × 5 pastas) pode passar de 1h — mais
  que a validade de um access token.
- Chamadas ao Graph ganham retry com espera em HTTP 429 (throttling),
  respeitando o header `Retry-After` quando presente. Hoje `gget()` não
  trata isso; num backfill grande de milhares de mensagens isso aparece.
- Progresso visível na tela de carregamento existente: "Lendo histórico:
  Junho/2025 (pasta MAPA)…", reaproveitando o spinner atual.

### Sincronização incremental (toda abertura da página e clique em
"Atualizar email", uma vez que o backfill de uma pasta já tenha terminado)

- Busca só mensagens com `recebido/enviado >= ultimo_sync - 1 dia` (margem
  de 1 dia para mensagens que o Graph demora a indexar), faz upsert por id
  de mensagem no cache, atualiza `ultimo_sync`.
- Rápida (tipicamente zero a poucas dezenas de mensagens novas), continua
  acontecendo automaticamente a cada abertura, sem botão separado — mantém
  o comportamento atual de "sempre atualizado".
- `baixar_repasses.varrer()` não muda.

### Concorrência e integridade

- Reaproveita o `threading.Lock` (`TRAVA`) já existente em `painel.py`, que
  hoje serializa `analisar()`: passa a envolver também a sincronização do
  cache, evitando duas sincronizações simultâneas (clique duplo em
  "Atualizar", ou coincidência com o `vigiar()` que faz ping a cada 15s).
- Cache ausente ou corrompido (arquivo apagado manualmente, ou primeira
  vez) é tratado como "nenhuma pasta sincronizada" → dispara backfill
  completo, sem tratamento especial de erro.
- Forçar recomeço do zero (ex.: ampliar a janela de 2 para 3 anos no
  futuro) é feito apagando `cache_emails.json` manualmente — mesmo
  espírito de `baixas.txt`/`config.json` hoje; não precisa de botão
  dedicado na interface.

## Mudanças em `painel.py`

- `GET /api/dados` deixa de usar `dias` para controlar a busca no Outlook.
  A rota dispara a sincronização incremental (rápida) e chama
  `analisar()` sobre o cache completo (2 anos).
- `analisar(dias=...)` continua aceitando `dias`, mas seu papel muda: a
  conciliação (matching código/nome, "retornado", buracos de numeração)
  passa a rodar sobre os 2 anos inteiros do cache — mais precisa, já que
  um laudo enviado para um exame antigo é encontrado mesmo fora da janela
  — e só o **resultado devolvido** é filtrado pelas últimas `dias`. Do
  ponto de vista da interface, o seletor "30/60/90/180 dias" continua
  funcionando exatamente como hoje (mesma contagem de cartões, mesmas
  listas), só que instantâneo em qualquer valor, sem o aviso de lentidão.
  Isso é deliberadamente o comportamento mínimo/provisório: um filtro de
  exibição de verdade (por coluna, por intervalo de datas) é o
  sub-projeto de filtros/ordenação de tabelas, que substitui este
  seletor.
- Se algum backfill ainda estiver em andamento, a resposta inclui o
  progresso (ex.: `{"sincronizando": {"pasta": "MAPA", "mes": "2025-06"}}`)
  para o front mostrar na tela de carregamento.

## Testes

Seguindo o padrão já usado no projeto (`pytest` + `monkeypatch`, sem
chamada de rede real — ver `tests/test_eventos.py`):

- `cache_email.py`: upsert incremental correto por id de mensagem;
  backfill resume do checkpoint certo após interrupção simulada (bloco
  parcialmente processado); escrita atômica não perde dados se simulada
  uma falha no meio da gravação; retry/backoff em 429.
- `rotina_pendencias.analisar()`: refatorado para receber as mensagens já
  sincronizadas (do cache) em vez de buscar do Graph diretamente — mantém
  os testes de lógica de conciliação (código/nome/status/buracos) rodando
  sem rede.
- `test_painel_api.py`: ajusta o teste de `/api/dados` para o novo
  contrato (sem `dias` controlando a busca).

## Fora de escopo

- Fluxo de repasses/financeiro (já é local).
- Filtro de exibição por data nas telas (sub-projeto separado).
- Detecção de mensagens movidas entre pastas monitoradas ou apagadas da
  caixa: uma mensagem já sincronizada permanece no cache mesmo se movida
  ou apagada depois — consistente com o cache ser aditivo e com o painel
  já ser somente leitura hoje. Não é um problema real neste fluxo: o
  código-fonte já documenta que a única movimentação esperada é
  Inbox → MAPA após resposta, e ambas já são pastas monitoradas, então a
  mensagem já está capturada antes de mover.
- Autenticação/login (fluxo de device code inalterado).
