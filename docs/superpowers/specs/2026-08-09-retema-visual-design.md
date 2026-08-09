# Retematização visual do painel — design

## Objetivo

O visual atual do painel (`painel.html`) é funcional mas genérico: cantos muito
arredondados, sombra pesada em tudo, cores soltas sem sistema, e um emoji no
favicon/título. A aba Financeiro em particular empilha uma tabela crua por
documento recebido sem agrupar nem recolher nada — com dezenas de arquivos
acumulados ao longo dos meses, vira uma parede de tabelas ilegível.

Esta fase retrabalha o visual de todas as telas pra uma linguagem mais séria e
atual (direção "corporativo, denso em dados": azul-marinho, cantos retos,
bordas finas em vez de sombra), e reestrutura especificamente a aba Financeiro
pra virar resumo + lista expansível em vez de parede de tabelas. Clareza pra
usuária não-técnica (Dra. Gisele) vem antes de qualquer ousadia visual.

## Decisões já validadas (mockups comparados com a usuária)

- **Direção visual:** C — corporativo, denso em dados (navy `#0f172a` no
  cabeçalho/navegação, cantos retos a levemente arredondados, bordas finas de
  1px no lugar de sombra pesada, badges de canto reto, `tabular-nums` em
  colunas numéricas, rótulos pequenos em maiúsculas com leve espaçamento).
- **Tipografia:** mantém Segoe UI em tudo (comparado com Bahnschrift, Georgia
  e Consolas; a usuária preferiu manter a atual — o problema percebido como
  "muito IA" não era a fonte, e sim o excesso de sombra/pill/espaçamento
  genérico do mockup).
- **Ícones/emoji:** remove emoji pictográfico (🩺 do favicon/título). Mantém
  símbolos funcionais como ✓/↻ — não são "emoji" no sentido que incomoda,
  são iconografia padrão de qualquer software sério.
- **Pontuação:** sem travessão (—) em nenhum texto da interface.
- **Modo escuro:** fora de escopo, só modo claro.
- **Escopo:** visual **e** reorganização de layout estão liberados (não é só
  reskin de CSS).
- **Prioridade:** clareza pra Dra. Gisele vem antes de moderno/ousado.

## Sistema visual

### Paleta

Formalizada como variáveis CSS (`:root`), substituindo os hex soltos e um
pouco inconsistentes de hoje (ex.: `#1e5a8a` no header vs `#16466c` nas abas
inativas, sem relação declarada entre eles):

```css
:root {
  --cor-fundo: #f4f5f7;
  --cor-superficie: #fff;
  --cor-borda: #d8dae0;
  --cor-borda-forte: #334155;
  --cor-texto: #1e293b;
  --cor-texto-fraco: #64748b;
  --cor-navy: #0f172a;      /* cabeçalho, nav, ativos escuros */
  --cor-navy-suave: #1e293b; /* fundo de abas inativas, nav */
  --cor-primaria: #2563eb;   /* ações, links, aba ativa */
  --cor-erro: #dc2626;   --cor-erro-fundo: #fee2e2;
  --cor-ok: #16a34a;     --cor-ok-fundo: #dcfce7;
  --cor-alerta: #ca8a04; --cor-alerta-fundo: #fef3c7;
  --raio: 6px;
  --raio-pequeno: 4px;
}
```

Os status (erro/ok/alerta) mapeiam 1:1 pros badges e cards já existentes
(`.b-atrasado`, `.card.vermelho`, etc.) — só trocam a fonte da cor pra
variável, sem mudar o que cada cor *significa*.

### Tipografia

Sem mudança de família (Segoe UI). Ajustes de tratamento:
- Números importantes (cards de contagem, colunas de valor/quantidade em
  tabela) ganham `font-variant-numeric: tabular-nums` de forma consistente
  (hoje só alguns componentes têm isso).
- Rótulos pequenos (cabeçalho de tabela, rótulo de card) padronizados em
  maiúsculas com `letter-spacing: .03em` — já usado em alguns lugares
  (`.mes-card-fin h3`), vira padrão em todos.

### Forma

- Raio de borda: 4-6px (hoje varia entre 8px e 20px dependendo do
  componente). Nada de cantos muito arredondados.
- Bordas finas (`1px solid var(--cor-borda)`) no lugar de
  `box-shadow` pesada como recurso padrão de separação visual. Sombra fica
  reservada pra elementos flutuantes de verdade (tooltip, o que já teria
  motivo real pra "levitar" sobre o conteúdo).
- Badges com `border-radius: var(--raio-pequeno)` (canto reto), não mais
  pill arredondado.

### Ícones

- Favicon/título: remove o emoji 🩺. Substitui por um favicon SVG simples de
  traço único (monocromático, cor `--cor-navy`): uma linha de pulso/ECG
  minimalista, coerente com o tema do painel (MAPA é exame cardiológico) sem
  ser um emoji colorido. Fica embutido como data URI, igual ao favicon
  atual, só troca o conteúdo do SVG.
- Símbolos funcionais (✓ sucesso, ↻ atualizar) continuam como estão.

## Componentes (aplicados nas 5 abas + telas globais)

- **Cabeçalho:** fundo `--cor-navy`, sem gradiente.
- **Navegação por abas:** fundo `--cor-navy-suave`, aba ativa com indicador
  de sublinhado (`border-bottom`) na cor primária, em vez do bloco totalmente
  recortado de hoje.
- **Cards de número** (Visão geral): bordas finas separando cards numa grade
  única, em vez de cada card ter sua própria sombra solta.
- **Tabelas:** cabeçalho em maiúsculas/cinza, linhas com borda inferior fina,
  números alinhados/tabulares.
- **Badges de status:** canto reto, cores do sistema.
- **Botões:** primário sólido (`--cor-primaria`), secundário com borda fina
  e fundo neutro — sem o botão amarelo (`#ffb300`) que destoa da paleta nova.
- **Telas de carregamento/login/erro/banner offline:** herdam a paleta nova
  (spinner, banner vermelho de erro, tela de login) sem mudança de
  comportamento.

## Aba a aba

- **Visão geral:** aplica o sistema visual (cards, tabelas, badges). Sem
  mudança estrutural — a organização atual (atrasados → aguardando prazo →
  status da caixa → detalhes expansíveis) já faz sentido.
- **Exames:** aplica o sistema visual na tabela de filtros e resultados. Sem
  mudança estrutural.
- **Financeiro — redesenhado:** ver seção dedicada abaixo.
- **Análises:** aplica o sistema visual (cards de mês, donuts, legendas,
  tooltip). A lógica dos gráficos (funil, donut, clique-pra-detalhar) não
  muda, só a paleta de cores e as bordas/cantos dos containers.
- **Importações:** aplica o sistema visual aos cards horizontais (já
  relativamente novos — herdam bordas finas e cores do sistema em vez das
  cores ad-hoc atuais).

### Financeiro: de parede de tabelas a resumo + lista expansível

**Hoje:** `carregarFinanceiro()` (painel.html:761) itera cada documento de
cada empresa e empilha, sem agrupar: nome do arquivo, uma tabela crua num
formato diferente por tipo de fornecedor (IDS tem coluna "Unidade", Unimed
tem parágrafo de executantes + bruto/líquido, CardioPro tem tabela de meses),
e um total. Isso se repete pra cada PDF/planilha recebido ao longo do tempo,
sem colapsar nada.

**Proposta** (sem mudança nenhuma no back-end — os dados que `/api/financeiro`
já devolve são suficientes; é reestruturação de `carregarFinanceiro()` e do
HTML que ela gera):

1. **Resumo por fornecedor:** um card por empresa (IDS, Unimed, CardioPro)
   mostrando total de documentos, total de exames e valor agregado (soma de
   `doc.total`/`doc.linhas`/`doc.meses` conforme o tipo), calculado
   client-side a partir do que já vem da API.
2. **Lista de documentos como tabela compacta:** uma linha por documento
   (data · tipo amigável · qtd · valor), mais recentes primeiro. Os "tipos
   amigáveis" são os mesmos já usados na aba Importações (`IDS · Repasse por
   unidade`, `Unimed · Demonstrativo`, `CardioPro · Planilha`) — reaproveita
   o mapeamento `NOMES_AMIGAVEIS` que já existe em `ler_repasses.py`, criando
   um vocabulário consistente entre as duas abas. Ordenação mais-recente-
   primeiro é a ordem que a API já devolve (glob ordenado por nome de
   arquivo, que já vem prefixado por data em `repasses/`), só invertida no
   render — sem parsing de data novo no back-end.
3. **Detalhe sob demanda:** clicar numa linha expande, no mesmo padrão
   `<details>` já usado em "Provavelmente laudados, conferir" (Visão geral),
   a tabela detalhada daquele documento específico (setores, executantes,
   bruto/líquido) — em vez de vir tudo aberto sempre.
4. A seção "Pagamentos sem exame correspondente" (`sec-orfaos`) continua
   estruturalmente como está (já é colapsável); só herda o novo visual.

## Fora de escopo

- Modo escuro.
- Mudança de funcionalidade/dados (nenhum endpoint novo, nenhuma lógica de
  negócio nova) — isto é retrabalho visual + reorganização de apresentação,
  não uma feature nova.
- Reestruturação das abas Visão geral, Exames, Análises, Importações além de
  herdar o sistema visual (só Financeiro tem reestruturação de verdade).
- Fontes customizadas/baixadas — mantém Segoe UI, fonte já instalada.

## Testes / verificação

Trabalho é puramente visual/estrutural em `painel.html` (CSS + JS de
renderização), sem lógica de negócio nova — não há função pura nova que
justifique teste automatizado (diferente da fase anterior, que adicionou
classificação de arquivos). Verificação é manual: abrir o painel no
navegador, conferir cada aba visualmente, e conferir especificamente que a
nova estrutura do Financeiro (resumo + expandir) mostra os mesmos números
que a versão antiga mostrava (mesma soma de qtd/valor), só organizados
melhor. Os 26 testes automatizados existentes (`ler_repasses.py`,
`painel.py`) continuam cobrindo o back-end, que não muda nesta fase.
