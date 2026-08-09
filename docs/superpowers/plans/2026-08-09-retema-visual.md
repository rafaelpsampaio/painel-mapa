# Retematização Visual Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retheme every screen of `painel.html` from the current generic/soft look to the "corporativo, denso em dados" direction validated with the usuária (navy header, sharp-to-slightly-rounded corners, thin borders instead of heavy shadow, tabular numbers, no pictographic emoji), and restructure the Financeiro tab from a wall of raw stacked tables into a per-fornecedor summary plus an expandable document list.

**Architecture:** A `:root` CSS custom-property token system (colors, radii) replaces the scattered hex literals in `painel.html`'s single `<style>` block. Every existing component (cards, tables, badges, tabs, details, donuts, tooltip, import cards) is edited in place to consume those tokens instead of being redesigned from scratch — same selectors, same class names, same JS hooks, new values. The Financeiro tab is the one place with real JS logic change: `carregarFinanceiro()` is rewritten to aggregate per-fornecedor totals and render each document behind a `<details>` toggle, using data `/api/financeiro` already returns (no backend change).

**Tech Stack:** Same as before — plain HTML/CSS/JS in one file, no build step, no new dependencies.

## Global Constraints

- No dark mode — light mode only, matches spec `docs/superpowers/specs/2026-08-09-retema-visual-design.md`.
- No pictographic emoji anywhere in `painel.html` (replace the 🩺 favicon). Functional symbols already in use (✓, ✔, ↻) stay — they are not in scope for removal.
- No em dash (—) in any UI string. (A grep of the current file found none; don't introduce any in new copy.)
- Font stays Segoe UI everywhere — do not introduce new font families or embedded/downloaded fonts.
- No backend changes (`ler_repasses.py`, `painel.py` are untouched by this plan) — every task only edits `painel.html`.
- No new automated tests — this is visual/structural front-end work with no new business logic; verification is manual (browser). The existing 26 backend tests (`py -m pytest tests/ -v`) must still pass untouched since no backend file changes.
- Every CSS edit must consume the `:root` tokens defined in Task 1 (`var(--cor-...)`, `var(--raio...)`) — no new hardcoded hex colors introduced after Task 1, except inside inline SVG data URIs where CSS variables aren't available.
- Reuse existing class names and element `id`s exactly as they are today unless a task explicitly says to rename/restructure — JS elsewhere in the file (`mostraAba`, `renderExames`, tooltip handlers, etc.) depends on those hooks and this plan does not touch that JS except in Task 6.

---

### Task 1: Design tokens + global chrome (favicon, header, nav, buttons)

**Files:**
- Modify: `painel.html` (favicon `<link>`, `<style>` block lines 9-24, header `<button id="btn-sair">` markup)

**Interfaces:**
- Produces: the `:root` token set (`--cor-fundo`, `--cor-superficie`, `--cor-borda`, `--cor-texto`, `--cor-texto-fraco`, `--cor-navy`, `--cor-navy-suave`, `--cor-navy-ativo`, `--cor-primaria`, `--cor-primaria-fraca`, `--cor-erro`/`--cor-erro-fundo`, `--cor-ok`/`--cor-ok-fundo`, `--cor-alerta`/`--cor-alerta-fundo`, `--cor-cinza`/`--cor-cinza-fundo`, `--raio`, `--raio-pequeno`) that every later task's CSS consumes.

- [ ] **Step 1: Replace the favicon**

In `painel.html`, change:

```html
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🩺</text></svg>">
```

to (a minimal single-stroke pulse/ECG line in navy — no emoji; `#` is percent-encoded as `%23` because a literal `#` inside a raw, non-base64 `data:image/svg+xml,` URI would be read as a URL fragment and truncate everything after it):

```html
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><path d='M6 55 L26 55 L36 22 L52 82 L62 38 L70 55 L94 55' fill='none' stroke='%230f172a' stroke-width='9' stroke-linecap='round' stroke-linejoin='round'/></svg>">
```

- [ ] **Step 2: Replace the reset/body/header/nav CSS block with tokens**

In `painel.html`'s `<style>` block, change:

```css
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: "Segoe UI", Arial, sans-serif; background: #f4f6f8;
         color: #223; font-size: 17px; padding-bottom: 60px; }
  header { background: #1e5a8a; color: #fff; padding: 16px 24px 0;
           display: flex; flex-wrap: wrap; align-items: center; gap: 16px; }
  header h1 { font-size: 24px; flex: 1; min-width: 240px; }
  header .sub { font-size: 14px; opacity: .85; width: 100%; }
  select, button, input[type=text] { font-size: 16px; padding: 9px 14px;
    border-radius: 8px; border: 1px solid #ccc; }
  select, button { cursor: pointer; }
  #btn-atualizar { background: #ffb300; border: none; font-weight: 600; }
  #btn-atualizar:disabled { opacity: .6; cursor: wait; }
  nav.abas { background: #1e5a8a; padding: 10px 24px 0; display: flex; gap: 6px; }
  nav.abas button { border: none; border-radius: 10px 10px 0 0;
    padding: 12px 22px; font-size: 17px; background: #16466c; color: #cfe0ef; }
  nav.abas button.ativa { background: #f4f6f8; color: #1e5a8a; font-weight: 700; }
```

to:

```css
  * { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --cor-fundo: #f4f5f7;
    --cor-superficie: #fff;
    --cor-borda: #d8dae0;
    --cor-texto: #1e293b;
    --cor-texto-fraco: #64748b;
    --cor-navy: #0f172a;
    --cor-navy-suave: #1e293b;
    --cor-navy-ativo: #263449;
    --cor-primaria: #2563eb;
    --cor-primaria-fraca: #dbeafe;
    --cor-erro: #dc2626;   --cor-erro-fundo: #fee2e2;
    --cor-ok: #16a34a;     --cor-ok-fundo: #dcfce7;
    --cor-alerta: #ca8a04; --cor-alerta-fundo: #fef3c7;
    --cor-cinza: #475569;  --cor-cinza-fundo: #e2e8f0;
    --raio: 6px;
    --raio-pequeno: 4px;
  }

  body { font-family: "Segoe UI", Arial, sans-serif; background: var(--cor-fundo);
         color: var(--cor-texto); font-size: 16px; padding-bottom: 60px; }
  header { background: var(--cor-navy); color: #fff; padding: 16px 24px 0;
           display: flex; flex-wrap: wrap; align-items: center; gap: 16px; }
  header h1 { font-size: 19px; font-weight: 700; flex: 1; min-width: 240px;
              letter-spacing: .01em; }
  header .sub { font-size: 12.5px; opacity: .75; width: 100%; }
  select, button, input[type=text] { font-size: 14px; padding: 8px 12px;
    border-radius: var(--raio-pequeno); border: 1px solid var(--cor-borda);
    font-family: inherit; }
  select, button { cursor: pointer; }
  header select { background: rgba(255,255,255,.08); border-color: rgba(255,255,255,.25);
    color: #fff; }
  #btn-atualizar { background: var(--cor-primaria); border: none; color: #fff;
    font-weight: 600; }
  #btn-atualizar:disabled { opacity: .6; cursor: wait; }
  #btn-sair { background: transparent; color: #cbd5e1;
    border: 1px solid rgba(255,255,255,.25); }
  nav.abas { background: var(--cor-navy-suave); padding: 0 24px; display: flex; gap: 0; }
  nav.abas button { border: none; border-bottom: 3px solid transparent;
    padding: 11px 18px; font-size: 13.5px; font-weight: 600; background: transparent;
    color: #94a3b8; }
  nav.abas button.ativa { color: #fff; border-bottom-color: var(--cor-primaria);
    background: var(--cor-navy-ativo); }
```

- [ ] **Step 3: Remove the inline style on the "Encerrar" button**

The button had an inline `style` attribute that would override the new `#btn-sair` CSS rule (inline styles always beat a stylesheet id selector). In `painel.html`, change:

```html
  <button id="btn-sair" onclick="encerrar()" title="Fecha o painel por completo"
    style="background:#16466c;color:#dfe9f2;border:1px solid #3a6d99">
    Encerrar</button>
```

to:

```html
  <button id="btn-sair" onclick="encerrar()" title="Fecha o painel por completo">
    Encerrar</button>
```

- [ ] **Step 4: Manual verification**

Run `py painel.py` from the repo root, open `http://127.0.0.1:8765/` in a browser (or use Chrome automation tools if available). Confirm:
- Favicon in the browser tab is a small dark pulse-line icon, not the old emoji.
- Header background is dark navy, "Atualizar" button is blue, "Encerrar" button is a subtle outlined button (not the old flat blue-gray box).
- Nav tab bar is dark, active tab has a blue underline (not a fully block-colored tab).
- No browser console errors.
- The rest of the page below the header still looks like the OLD styling (unchanged) — that's expected, later tasks handle it.

- [ ] **Step 5: Commit**

```bash
git add painel.html
git commit -m "Sistema de tokens visuais + cabecalho/nav/favicon na direcao corporativa"
```

---

### Task 2: Core shared components (cards, blocos, tabelas, badges, details, filtros)

**Files:**
- Modify: `painel.html` (`<style>` block, the region between `nav.abas button.ativa` from Task 1 and `.oculto`)

**Interfaces:**
- Consumes: tokens from Task 1 (`var(--cor-...)`, `var(--raio...)`).
- Produces: no new class names — same selectors (`.cards`, `.card`, `section.bloco`, `table`/`th`/`td`, `.codigo`, `.btn-baixa`, `.ok-grande`, `.alerta`, `.badge` + status variants, `.pago`, `details`, `.filtros`), just retokenized. Every later task and all existing JS keep working unchanged since no selector or id changes.

- [ ] **Step 1: Replace the component CSS block**

In `painel.html`'s `<style>` block, change:

```css
  main, .tela { max-width: 1180px; margin: 22px auto; padding: 0 16px; }
  .cards { display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 22px; }
  .card { flex: 1; min-width: 150px; background: #fff; border-radius: 12px;
          padding: 16px; text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
  .card .num { font-size: 38px; font-weight: 700; }
  .card .rot { font-size: 15px; color: #556; }
  .card.vermelho .num { color: #c62828; }
  .card.verde .num { color: #2e7d32; }
  .card.ambar .num { color: #b26a00; }
  .card.cinza .num { color: #546e7a; }
  .card.azul .num { color: #1e5a8a; }
  section.bloco { background: #fff; border-radius: 12px; padding: 18px 20px;
                  margin-bottom: 18px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
  section.bloco h2 { font-size: 20px; margin-bottom: 12px; }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 8px 8px; border-bottom: 1px solid #eee;
           font-size: 15px; }
  th { color: #667; font-size: 13px; text-transform: uppercase;
       position: sticky; top: 0; background: #fff; z-index: 2;
       box-shadow: 0 1px 0 #e0e0e0; }
  tr:last-child td { border-bottom: none; }
  .codigo { font-family: Consolas, monospace; white-space: nowrap; }
  .btn-baixa { background: #eceff1; border: 1px solid #b0bec5; font-size: 13px;
               padding: 5px 10px; }
  .btn-baixa:hover { background: #cfd8dc; }
  .ok-grande { text-align: center; padding: 30px; font-size: 22px;
               color: #2e7d32; }
  .alerta { color: #c62828; font-weight: 600; }
  .badge { display: inline-block; padding: 3px 10px; border-radius: 12px;
           font-size: 13px; font-weight: 600; white-space: nowrap; }
  .b-atrasado { background: #fdecea; color: #c62828; }
  .b-no_prazo { background: #e3f0fa; color: #1e5a8a; }
  .b-retornado { background: #e8f5e9; color: #2e7d32; }
  .b-provavel, .b-aviso { background: #fff3cd; color: #8a6d00; }
  .b-baixado { background: #eceff1; color: #546e7a; }
  .pago { color: #2e7d32; font-weight: 600; white-space: nowrap; }
  details { margin-bottom: 14px; }
  details summary { font-size: 18px; padding: 12px 16px; background: #fff;
                    border-radius: 10px; cursor: pointer;
                    box-shadow: 0 1px 4px rgba(0,0,0,.08); }
  details .corpo { background: #fff; border-radius: 0 0 10px 10px;
                   padding: 12px 16px; }
  .filtros { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px;
             align-items: center; }
  .filtros input[type=text] { flex: 1; min-width: 220px; }
  .filtros .contagem { color: #667; font-size: 15px; margin-left: auto; }
```

to:

```css
  main, .tela { max-width: 1180px; margin: 22px auto; padding: 0 16px; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px,1fr));
    gap: 1px; background: var(--cor-borda); border: 1px solid var(--cor-borda);
    border-radius: var(--raio); overflow: hidden; margin-bottom: 22px; }
  .card { background: var(--cor-superficie); padding: 14px 16px; }
  .card .num { font-size: 28px; font-weight: 700; font-variant-numeric: tabular-nums;
    color: var(--cor-texto); }
  .card .rot { font-size: 11.5px; color: var(--cor-texto-fraco); margin-top: 3px;
    text-transform: uppercase; letter-spacing: .03em; font-weight: 600; }
  .card.vermelho .num { color: var(--cor-erro); }
  .card.verde .num { color: var(--cor-ok); }
  .card.ambar .num { color: var(--cor-alerta); }
  .card.cinza .num { color: var(--cor-cinza); }
  .card.azul .num { color: var(--cor-primaria); }
  section.bloco { background: var(--cor-superficie); border: 1px solid var(--cor-borda);
    border-radius: var(--raio); padding: 18px 20px; margin-bottom: 16px; }
  section.bloco h2 { font-size: 15px; font-weight: 700; margin-bottom: 12px;
    color: var(--cor-texto); }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 9px 8px; border-bottom: 1px solid var(--cor-borda);
           font-size: 13.5px; }
  th { color: var(--cor-texto-fraco); font-size: 11px; text-transform: uppercase;
       letter-spacing: .03em; font-weight: 700; position: sticky; top: 0;
       background: var(--cor-superficie); z-index: 2; }
  tr:last-child td { border-bottom: none; }
  .codigo { font-family: Consolas, monospace; white-space: nowrap; font-size: 13px; }
  .btn-baixa { background: var(--cor-fundo); border: 1px solid var(--cor-borda);
               font-size: 12.5px; padding: 5px 10px; color: var(--cor-texto); }
  .btn-baixa:hover { background: var(--cor-borda); }
  .ok-grande { text-align: center; padding: 30px; font-size: 18px; font-weight: 600;
               color: var(--cor-ok); }
  .alerta { color: var(--cor-erro); font-weight: 600; }
  .badge { display: inline-block; padding: 2px 9px; border-radius: var(--raio-pequeno);
           font-size: 11.5px; font-weight: 700; white-space: nowrap;
           text-transform: uppercase; letter-spacing: .02em; }
  .b-atrasado { background: var(--cor-erro-fundo); color: var(--cor-erro); }
  .b-no_prazo { background: var(--cor-primaria-fraca); color: var(--cor-primaria); }
  .b-retornado { background: var(--cor-ok-fundo); color: var(--cor-ok); }
  .b-provavel, .b-aviso { background: var(--cor-alerta-fundo); color: var(--cor-alerta); }
  .b-baixado { background: var(--cor-cinza-fundo); color: var(--cor-cinza); }
  .pago { color: var(--cor-ok); font-weight: 600; white-space: nowrap; }
  details { margin-bottom: 12px; border: 1px solid var(--cor-borda);
    border-radius: var(--raio); overflow: hidden; }
  details summary { font-size: 14.5px; font-weight: 600; padding: 12px 16px;
    background: var(--cor-superficie); cursor: pointer; list-style: none; }
  details summary::-webkit-details-marker { display: none; }
  details .corpo { background: var(--cor-superficie); padding: 4px 16px 14px;
    border-top: 1px solid var(--cor-borda); }
  .filtros { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px;
             align-items: center; }
  .filtros input[type=text] { flex: 1; min-width: 220px; }
  .filtros .contagem { color: var(--cor-texto-fraco); font-size: 13px; margin-left: auto; }
```

- [ ] **Step 2: Manual verification**

Reload the painel in the browser (Task 1's server is still running, or start it again). Go to "Visão geral" and "Exames" tabs. Confirm:
- The 7 number cards at the top of Visão geral now sit in one hairline-bordered grid strip (no individual floating shadows).
- Tables (Exames tab, Atrasados list) have thin gray dividers, uppercase small headers, no more zebra-shadow header.
- Badges (Atrasado, Aguardando prazo, etc.) have sharp-ish corners now, not full pills.
- "Provavelmente laudados, conferir" `<details>` sections still expand/collapse on click and show a thin bordered box.
- No console errors.

- [ ] **Step 3: Commit**

```bash
git add painel.html
git commit -m "Retema cards, blocos, tabelas, badges e details pro sistema de tokens"
```

---

### Task 3: Telas globais (carregando, login, erro, banner offline, rodapé)

**Files:**
- Modify: `painel.html` (`<style>` block, region from `.oculto` through `.nota`)

**Interfaces:**
- Consumes: tokens from Task 1.
- Produces: no new selectors; same ids/classes (`#carregando`, `.spinner`, `#tela-login`, `#login-codigo`, `#login-status`, `.rodape`, `#banner-offline`, `.nota`) retokenized.

- [ ] **Step 1: Replace the global-screens CSS block**

In `painel.html`'s `<style>` block, change:

```css
  .oculto { display: none !important; }
  #carregando { text-align: center; padding: 60px 20px; }
  .spinner { width: 46px; height: 46px; border: 5px solid #cfd8dc;
             border-top-color: #1e5a8a; border-radius: 50%;
             animation: gira 1s linear infinite; margin: 0 auto 18px; }
  @keyframes gira { to { transform: rotate(360deg); } }
  #tela-login { background: #fff; border-radius: 12px; padding: 30px;
                text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
  #tela-login h2 { margin-bottom: 16px; }
  #tela-login ol { text-align: left; display: inline-block; font-size: 19px;
                   line-height: 2; }
  #login-codigo { font-size: 34px; font-weight: 700; letter-spacing: 4px;
                  background: #fff3cd; padding: 4px 14px; border-radius: 8px; }
  #login-status { margin-top: 18px; color: #667; }
  .rodape { text-align: center; color: #99a; font-size: 13px; margin-top: 30px; }
  #banner-offline { position: fixed; top: 0; left: 0; right: 0; z-index: 10;
                    background: #c62828; color: #fff; text-align: center;
                    padding: 12px 16px; font-size: 17px; }
  .nota { color: #667; font-size: 14px; margin: 6px 0; }
```

to:

```css
  .oculto { display: none !important; }
  #carregando { text-align: center; padding: 60px 20px; }
  .spinner { width: 40px; height: 40px; border: 4px solid var(--cor-borda);
             border-top-color: var(--cor-primaria); border-radius: 50%;
             animation: gira 1s linear infinite; margin: 0 auto 18px; }
  @keyframes gira { to { transform: rotate(360deg); } }
  #tela-login { background: var(--cor-superficie); border: 1px solid var(--cor-borda);
                border-radius: var(--raio); padding: 30px; text-align: center; }
  #tela-login h2 { margin-bottom: 16px; font-size: 18px; }
  #tela-login ol { text-align: left; display: inline-block; font-size: 16px;
                   line-height: 2; }
  #login-codigo { font-size: 28px; font-weight: 700; letter-spacing: 3px;
                  background: var(--cor-alerta-fundo); color: var(--cor-alerta);
                  padding: 4px 14px; border-radius: var(--raio-pequeno); }
  #login-status { margin-top: 18px; color: var(--cor-texto-fraco); }
  .rodape { text-align: center; color: #99a3af; font-size: 12.5px; margin-top: 30px; }
  #banner-offline { position: fixed; top: 0; left: 0; right: 0; z-index: 10;
                    background: var(--cor-erro); color: #fff; text-align: center;
                    padding: 12px 16px; font-size: 14.5px; }
  .nota { color: var(--cor-texto-fraco); font-size: 13px; margin: 6px 0; }
```

- [ ] **Step 2: Manual verification**

These screens are only visible in specific states, so verify by simulating them:
- Stop `painel.py` (close the console window / Ctrl+C) with the browser tab still open: confirm the red `#banner-offline` bar at the top uses the new red token color and smaller font, still readable.
- Briefly, while the page is loading (right after opening the URL, before data arrives), confirm the spinner is now a thinner ring in the new blue.
- If you have a way to trigger `tela-erro` (e.g. temporarily rename `painel.py` and reload), confirm the error box uses the new bordered-card style, not the old shadowed rounded box. If you can't easily trigger it, visually inspect the CSS change is self-consistent with Task 2's `section.bloco` styling (the error tela wraps a `section.bloco`) and note in the report that this specific screen wasn't live-verified.
- Confirm no console errors on normal load.

- [ ] **Step 3: Commit**

```bash
git add painel.html
git commit -m "Retema telas de carregamento, login, erro e banner offline"
```

---

### Task 4: Aba Análises (segmentado, cards de mês, donuts, legenda, tooltip)

**Files:**
- Modify: `painel.html` (`<style>` block, region from `.segmentado` through `#transacoes-corpo-fin td.muted`)

**Interfaces:**
- Consumes: tokens from Task 1.
- Produces: no new selectors — same classes (`.segmentado`, `.grade-meses-fin`, `.mes-card-fin`, `.funil-*`, `.divisor`, `.pago-rot`, `.barra-empilhada`, `.seg`, `.fornecedor-cabeca`, `.badge-alerta`, `.grade-donuts`, `.mes-donut`, `.legenda`, `.ponto`, `.tooltip-fin`, `.transacoes-cabeca`, `#transacoes-corpo-fin`) retokenized. The donut/funil rendering JS (`montarDonutFin`, `renderMesesFornecedor`, `renderFornecedorFinanceiro`) is untouched — it reads `PALETA_FORNECEDOR`/`COR_OUTROS`/`COR_SEM_LAUDO` JS constants, not CSS, so those stay as-is (out of scope: they're a distinct per-fornecedor color coding, not part of the UI chrome token system).

- [ ] **Step 1: Replace the Análises CSS block**

In `painel.html`'s `<style>` block, change:

```css
  .segmentado { display: inline-flex; background: #f4f6f8; border-radius: 9px;
    padding: 3px; margin-bottom: 16px; gap: 2px; }
  .segmentado button { border: none; background: transparent; font-size: 14.5px;
    padding: 8px 16px; border-radius: 7px; cursor: pointer; color: #667;
    font-family: inherit; }
  .segmentado button.ativa { background: #fff; color: #223; font-weight: 600;
    box-shadow: 0 1px 3px rgba(0,0,0,.12); }

  .grade-meses-fin { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 14px; }
  .mes-card-fin { border: 1px solid #e1e0d9; border-radius: 10px; padding: 14px 16px; }
  .mes-card-fin h3 { font-size: 15px; text-transform: uppercase; letter-spacing: .04em;
    color: #667; font-weight: 600; margin: 0 0 12px; }
  .funil-linha { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
  .funil-rot { width: 74px; font-size: 12.5px; color: #667; flex-shrink: 0; }
  .funil-trilho { flex: 1; background: #e1e0d9; border-radius: 3px; height: 16px;
    position: relative; overflow: hidden; }
  .funil-barra { display: block; height: 100%; border-radius: 3px; }
  .funil-num { width: 40px; text-align: right; font-size: 13px; font-weight: 600;
    font-variant-numeric: tabular-nums; flex-shrink: 0; }
  .divisor { height: 1px; background: #e1e0d9; margin: 14px 0 12px; }
  .pago-rot { font-size: 12.5px; color: #667; margin-bottom: 6px;
    display: flex; justify-content: space-between; }
  .pago-rot b { color: #223; font-variant-numeric: tabular-nums; }
  .barra-empilhada { display: flex; height: 22px; border-radius: 4px; overflow: hidden;
    background: #e1e0d9; }
  .seg { height: 100%; cursor: pointer; border-right: 2px solid #fff; }
  .seg:last-child { border-right: none; }
  .seg:hover { filter: brightness(1.12); }

  .fornecedor-cabeca { display: flex; flex-wrap: wrap; align-items: center; gap: 14px;
    margin-bottom: 20px; }
  .badge-alerta { display: inline-flex; align-items: center; gap: 6px; font-size: 13.5px;
    font-weight: 600; color: #b24a2c; background: #fbe6dd; padding: 6px 12px;
    border-radius: 20px; }
  .badge-alerta::before { content: "!"; display: inline-flex; align-items: center;
    justify-content: center; width: 16px; height: 16px; border-radius: 50%;
    background: #c25b39; color: #fff; font-size: 11px; font-weight: 800; }

  .grade-donuts { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 18px 10px; text-align: center; }
  .mes-donut .rot-mes { font-size: 12px; color: #667; font-weight: 600; margin-bottom: 8px; }
  .mes-donut .donut-wrap { position: relative; width: 104px; height: 104px; margin: 0 auto; }
  .mes-donut .donut-wrap svg circle.fatia { cursor: pointer; }
  .mes-donut .donut-wrap svg circle.fatia:hover { filter: brightness(1.15); }
  .mes-donut .donut-centro { position: absolute; inset: 0; display: flex; flex-direction: column;
    align-items: center; justify-content: center; pointer-events: none; }
  .mes-donut .donut-centro b { font-size: 19px; font-variant-numeric: tabular-nums; line-height: 1; }
  .mes-donut .donut-centro small { font-size: 10px; color: #99a; margin-top: 2px; }
  .mes-donut .rot-fornecedor { margin-top: 8px; font-size: 13px; font-weight: 700;
    font-variant-numeric: tabular-nums; }
  .mes-donut .rot-valor { font-size: 11.5px; color: #99a;
    font-variant-numeric: tabular-nums; margin-top: 1px; }

  .legenda { display: flex; flex-wrap: wrap; gap: 14px 20px; margin-top: 18px;
    padding-top: 16px; border-top: 1px solid #e1e0d9; font-size: 13.5px; }
  .legenda span { display: inline-flex; align-items: center; gap: 7px; color: #667; }
  .ponto { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }

  .tooltip-fin { position: fixed; pointer-events: none; background: #223;
    color: #fff; font-size: 13px; padding: 7px 11px; border-radius: 7px;
    box-shadow: 0 4px 14px rgba(0,0,0,.25); opacity: 0; transform: translateY(4px);
    transition: opacity .1s, transform .1s; z-index: 20; white-space: nowrap; }
  .tooltip-fin.on { opacity: 1; transform: translateY(0); }
  .tooltip-fin .tt-conv { font-weight: 700; }
  .tooltip-fin .tt-val { opacity: .75; margin-left: 6px; }

  .transacoes-cabeca { display: flex; flex-wrap: wrap; align-items: center;
    justify-content: space-between; gap: 10px; margin-bottom: 10px; }
  .transacoes-cabeca h2 { margin: 0; }
  .transacoes-cabeca button { border: 1px solid #dcdad0; background: #fff; color: #667;
    border-radius: 7px; padding: 6px 14px; cursor: pointer; font-family: inherit; font-size: 13.5px; }
  #transacoes-corpo-fin { overflow-x: auto; }
  #transacoes-corpo-fin td.muted { color: #99a; font-size: 12.5px; }
```

to:

```css
  .segmentado { display: inline-flex; background: var(--cor-fundo);
    border: 1px solid var(--cor-borda); border-radius: var(--raio);
    padding: 3px; margin-bottom: 16px; gap: 2px; }
  .segmentado button { border: none; background: transparent; font-size: 13px;
    padding: 7px 14px; border-radius: var(--raio-pequeno); cursor: pointer;
    color: var(--cor-texto-fraco); font-family: inherit; }
  .segmentado button.ativa { background: var(--cor-superficie); color: var(--cor-texto);
    font-weight: 600; }

  .grade-meses-fin { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 12px; }
  .mes-card-fin { border: 1px solid var(--cor-borda); border-radius: var(--raio);
    padding: 14px 16px; }
  .mes-card-fin h3 { font-size: 13px; text-transform: uppercase; letter-spacing: .04em;
    color: var(--cor-texto-fraco); font-weight: 700; margin: 0 0 12px; }
  .funil-linha { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
  .funil-rot { width: 74px; font-size: 12px; color: var(--cor-texto-fraco); flex-shrink: 0; }
  .funil-trilho { flex: 1; background: var(--cor-fundo); border-radius: 3px; height: 14px;
    position: relative; overflow: hidden; }
  .funil-barra { display: block; height: 100%; border-radius: 3px; }
  .funil-num { width: 40px; text-align: right; font-size: 12.5px; font-weight: 600;
    font-variant-numeric: tabular-nums; flex-shrink: 0; }
  .divisor { height: 1px; background: var(--cor-borda); margin: 14px 0 12px; }
  .pago-rot { font-size: 12px; color: var(--cor-texto-fraco); margin-bottom: 6px;
    display: flex; justify-content: space-between; }
  .pago-rot b { color: var(--cor-texto); font-variant-numeric: tabular-nums; }
  .barra-empilhada { display: flex; height: 20px; border-radius: 3px; overflow: hidden;
    background: var(--cor-fundo); }
  .seg { height: 100%; cursor: pointer; border-right: 2px solid #fff; }
  .seg:last-child { border-right: none; }
  .seg:hover { filter: brightness(1.12); }

  .fornecedor-cabeca { display: flex; flex-wrap: wrap; align-items: center; gap: 14px;
    margin-bottom: 20px; }
  .badge-alerta { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px;
    font-weight: 600; color: var(--cor-erro); background: var(--cor-erro-fundo);
    padding: 5px 10px; border-radius: var(--raio-pequeno); }
  .badge-alerta::before { content: "!"; display: inline-flex; align-items: center;
    justify-content: center; width: 15px; height: 15px; border-radius: 50%;
    background: var(--cor-erro); color: #fff; font-size: 10.5px; font-weight: 800; }

  .grade-donuts { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 18px 10px; text-align: center; }
  .mes-donut .rot-mes { font-size: 11.5px; color: var(--cor-texto-fraco); font-weight: 600;
    margin-bottom: 8px; text-transform: uppercase; letter-spacing: .03em; }
  .mes-donut .donut-wrap { position: relative; width: 104px; height: 104px; margin: 0 auto; }
  .mes-donut .donut-wrap svg circle.fatia { cursor: pointer; }
  .mes-donut .donut-wrap svg circle.fatia:hover { filter: brightness(1.15); }
  .mes-donut .donut-centro { position: absolute; inset: 0; display: flex; flex-direction: column;
    align-items: center; justify-content: center; pointer-events: none; }
  .mes-donut .donut-centro b { font-size: 18px; font-variant-numeric: tabular-nums; line-height: 1;
    color: var(--cor-texto); }
  .mes-donut .donut-centro small { font-size: 9.5px; color: var(--cor-texto-fraco); margin-top: 2px; }
  .mes-donut .rot-fornecedor { margin-top: 8px; font-size: 12.5px; font-weight: 700;
    font-variant-numeric: tabular-nums; }
  .mes-donut .rot-valor { font-size: 11px; color: var(--cor-texto-fraco);
    font-variant-numeric: tabular-nums; margin-top: 1px; }

  .legenda { display: flex; flex-wrap: wrap; gap: 14px 20px; margin-top: 18px;
    padding-top: 16px; border-top: 1px solid var(--cor-borda); font-size: 12.5px; }
  .legenda span { display: inline-flex; align-items: center; gap: 7px; color: var(--cor-texto-fraco); }
  .ponto { width: 9px; height: 9px; border-radius: 2px; display: inline-block; }

  .tooltip-fin { position: fixed; pointer-events: none; background: var(--cor-navy);
    color: #fff; font-size: 12.5px; padding: 7px 11px; border-radius: var(--raio-pequeno);
    box-shadow: 0 4px 14px rgba(0,0,0,.25); opacity: 0; transform: translateY(4px);
    transition: opacity .1s, transform .1s; z-index: 20; white-space: nowrap; }
  .tooltip-fin.on { opacity: 1; transform: translateY(0); }
  .tooltip-fin .tt-conv { font-weight: 700; }
  .tooltip-fin .tt-val { opacity: .75; margin-left: 6px; }

  .transacoes-cabeca { display: flex; flex-wrap: wrap; align-items: center;
    justify-content: space-between; gap: 10px; margin-bottom: 10px; }
  .transacoes-cabeca h2 { margin: 0; }
  .transacoes-cabeca button { border: 1px solid var(--cor-borda); background: var(--cor-superficie);
    color: var(--cor-texto-fraco); border-radius: var(--raio-pequeno); padding: 6px 12px;
    cursor: pointer; font-family: inherit; font-size: 12.5px; }
  #transacoes-corpo-fin { overflow-x: auto; }
  #transacoes-corpo-fin td.muted { color: var(--cor-texto-fraco); font-size: 12px; }
```

- [ ] **Step 2: Manual verification**

Go to the "Análises" tab. Confirm:
- The "Por mês" / "Por fornecedor" segmented toggle at the top has the new flat pill-in-a-box look.
- Month cards, funil bars, donut charts and their legends still render (colors from `PALETA_FORNECEDOR` are unchanged JS constants, so the fornecedor colors themselves look the same — only the surrounding chrome like borders/tooltip/legend text changed).
- Hover over a donut slice or a stacked-bar segment: the tooltip still appears and now has a dark navy background instead of near-black.
- Click a slice to open the "transações" panel at the bottom: still opens, table still renders.
- No console errors.

- [ ] **Step 3: Commit**

```bash
git add painel.html
git commit -m "Retema aba Analises: segmentado, cards de mes, donuts, legenda, tooltip"
```

---

### Task 5: Aba Importações (cards horizontais)

**Files:**
- Modify: `painel.html` (`<style>` block, `.import-resumo` through `.card-import .ci-motivo`)

**Interfaces:**
- Consumes: tokens from Task 1.
- Produces: no new selectors — same classes (`.import-resumo`, `.grade-importacoes`, `.card-import` + `.st-nao_identificado`/`.st-erro` modifiers, `.ci-arquivo`, `.ci-tipo`, `.ci-resumo`, `.ci-motivo`) retokenized.

- [ ] **Step 1: Replace the Importações CSS block**

In `painel.html`'s `<style>` block, change:

```css
  .import-resumo { color: #667; font-size: 14.5px; margin: 4px 0 10px; }
  .grade-importacoes { display: flex; flex-direction: column; gap: 10px; }
  .card-import { display: flex; flex-wrap: wrap; align-items: center; gap: 14px;
    background: #fff; border-radius: 10px; padding: 12px 16px;
    box-shadow: 0 1px 4px rgba(0,0,0,.08); border-left: 5px solid #1e5a8a; }
  .card-import.st-nao_identificado { border-left-color: #b26a00; }
  .card-import.st-erro { border-left-color: #c62828; }
  .card-import .ci-arquivo { font-weight: 600; flex: 1 1 220px; min-width: 180px; }
  .card-import .ci-tipo { color: #1e5a8a; font-size: 14px; }
  .card-import .ci-resumo { color: #667; font-size: 14px; }
  .card-import .ci-motivo { color: #667; font-size: 13.5px; flex: 2 1 280px; }
```

to:

```css
  .import-resumo { color: var(--cor-texto-fraco); font-size: 13px; margin: 4px 0 10px; }
  .grade-importacoes { display: flex; flex-direction: column; gap: 8px; }
  .card-import { display: flex; flex-wrap: wrap; align-items: center; gap: 14px;
    background: var(--cor-superficie); border: 1px solid var(--cor-borda);
    border-left: 3px solid var(--cor-primaria); border-radius: var(--raio-pequeno);
    padding: 11px 14px; }
  .card-import.st-nao_identificado { border-left-color: var(--cor-alerta); }
  .card-import.st-erro { border-left-color: var(--cor-erro); }
  .card-import .ci-arquivo { font-weight: 600; font-size: 13.5px; flex: 1 1 220px;
    min-width: 180px; }
  .card-import .ci-tipo { color: var(--cor-primaria); font-size: 12.5px; font-weight: 600; }
  .card-import .ci-resumo { color: var(--cor-texto-fraco); font-size: 12.5px; }
  .card-import .ci-motivo { color: var(--cor-texto-fraco); font-size: 12.5px; flex: 2 1 280px; }
```

- [ ] **Step 2: Manual verification**

Go to the "Importações" tab. Confirm:
- Cards for recognized files have a thin blue left border (not a thick 5px shadowed pill).
- Cards for "não identificado" files have an amber left border; "erro" files have a red left border.
- Layout (file name, tipo/resumo or badge/motivo) is unchanged, just restyled.
- No console errors.

- [ ] **Step 3: Commit**

```bash
git add painel.html
git commit -m "Retema cards horizontais da aba Importacoes"
```

---

### Task 6: Financeiro — resumo por fornecedor + lista de documentos expansível

**Files:**
- Modify: `painel.html` (HTML: `#aba-financeiro` wrapper markup; JS: the `carregarFinanceiro()` region; CSS: append new rules before `</style>`)

**Interfaces:**
- Consumes: `/api/financeiro`'s existing response shape (unchanged — see `docs/superpowers/specs/2026-08-09-retema-visual-design.md` for the full shape recap), `esc()`, `brl()`, `brlSeguro()` helpers (existing, unchanged), tokens from Task 1, `section.bloco`/`table`/`details` styling from Task 2.
- Produces: new CSS classes `.grade-fornecedores-fin`, `.resumo-fornecedor-fin` (+ `.num-grande`/`.num-sub`), `.doc-fin-lista` (+ `summary` children `.doc-data`/`.doc-tipo`/`.doc-num`). New JS helpers `TIPO_AMIGAVEL_FIN` (const), `periodoBr(p)`, `resumoDocumentoFin(doc)`, `dataDocumentoFin(doc)`, `detalheDocumentoFin(doc)`, all local to this region — no other task or existing code calls them.

- [ ] **Step 1: Change the `#aba-financeiro` wrapper markup**

The `sec-financeiro` element was previously itself a `.bloco` card wrapping one giant dump of HTML. The new `carregarFinanceiro()` (Step 3) generates its own multiple `.bloco` sections inside it, so the wrapper itself must stop being a card (avoids a card nested inside a card). In `painel.html`, change:

```html
  <div id="aba-financeiro" class="oculto">
    <section class="bloco" id="sec-financeiro"><p>Carregando&hellip;</p></section>

    <div id="sec-orfaos"></div>
  </div>
```

to:

```html
  <div id="aba-financeiro" class="oculto">
    <div id="sec-financeiro"><p class="nota">Carregando&hellip;</p></div>

    <div id="sec-orfaos"></div>
  </div>
```

- [ ] **Step 2: Run the existing test suite as a pre-check**

Run: `py -m pytest tests/ -v` from the repo root.
Expected: 26 passed (this task doesn't touch any backend file, so this must stay green throughout — run it again after Step 3 too).

- [ ] **Step 3: Rewrite `carregarFinanceiro()`**

In `painel.html`'s `<script>` block, change (this spans from the `brlSeguro` helper through the `carregarFinanceiro();` call that follows the function):

```javascript
function brlSeguro(v) { return v == null ? "" : brl(v); }

async function carregarFinanceiro() {
  const sec = document.getElementById("sec-financeiro");
  try {
    const f = await (await fetch("/api/financeiro")).json();
    const nomes = Object.keys(f.empresas || {});
    if (!nomes.length) {
      sec.innerHTML = "<p class='nota'>Nenhum demonstrativo na pasta " +
        "repasses ainda.</p>";
      return;
    }
    let h = "<h2>Produção e pagamentos (demonstrativos recebidos)</h2>";
    for (const nome of ["IDS", "Unimed", "CardioPro"]) {
      const emp = f.empresas[nome];
      if (!emp) continue;
      h += "<h3 style='margin:14px 0 6px'>" + esc(nome) + "</h3>";
      for (const doc of emp.documentos) {
        h += "<p class='nota'>" + esc(doc.arquivo) +
          (doc.periodo ? " · período " + esc(doc.periodo) : "") +
          (doc.emitido_em ? " · emitido " + esc(doc.emitido_em) : "") + "</p>";
        if (doc.meses) {
          h += "<table><tr><th>Mês</th><th>ECG</th><th>MAPA</th></tr>" +
            doc.meses.map(m => "<tr><td>" + esc(m.mes) + "</td><td>" +
              m.ecg + "</td><td>" + m.mapa + "</td></tr>").join("") +
            "</table>";
        } else {
          h += "<table><tr><th>Tipo</th>" +
            (doc.linhas.some(l => l.detalhe) ? "<th>Unidade</th>" : "") +
            "<th>Qtd</th><th>Valor</th></tr>" +
            doc.linhas.map(l => "<tr><td>" + esc(l.tipo) + "</td>" +
              (doc.linhas.some(x => x.detalhe)
                ? "<td>" + esc(l.detalhe || "") + "</td>" : "") +
              "<td>" + l.qtd + "</td><td>" + brlSeguro(l.valor) + "</td></tr>")
              .join("") + "</table>";
        }
        if (doc.total && doc.total.qtd) {
          h += "<p><b>Total do documento: " + doc.total.qtd + " exames · " +
            brlSeguro(doc.total.valor) + "</b></p>";
        }
        if (doc.executantes) {
          h += "<p style='font-size:15px'>" + doc.executantes.map(e =>
            esc(e.nome) + ": " + e.servicos + " serviços (" + brlSeguro(e.valor) +
            ")").join(" · ") + "</p>";
          if (doc.bruto) {
            h += "<p><b>Bruto p/ nota: " + brlSeguro(doc.bruto) +
              " · Líquido: " + brlSeguro(doc.liquido) + "</b></p>";
          }
        }
      }
    }
    sec.innerHTML = h;
  } catch (e) {
    sec.innerHTML = "<p class='nota'>Não consegui ler os demonstrativos.</p>";
  }
}
carregarFinanceiro();
```

to:

```javascript
function brlSeguro(v) { return v == null ? "" : brl(v); }

const TIPO_AMIGAVEL_FIN = {
  IDS: "IDS · Repasse por unidade",
  Unimed: "Unimed · Demonstrativo",
  CardioPro: "CardioPro · Planilha",
};

function periodoBr(p) {
  const m = String(p || "").match(/^(\d{4})(\d{2})$/);
  return m ? m[2] + "/" + m[1] : (p || "");
}

function dataDocumentoFin(doc) {
  if (doc.emitido_em) return doc.emitido_em;
  if (doc.periodo) return periodoBr(doc.periodo);
  return "";
}

function resumoDocumentoFin(doc) {
  if (doc.total) return { qtd: doc.total.qtd, valor: doc.total.valor };
  if (doc.meses) {
    const qtd = doc.meses.reduce((s, m) => s + m.ecg + m.mapa, 0);
    return { qtd, valor: null };
  }
  const qtd = doc.linhas.reduce((s, l) => s + l.qtd, 0);
  const valor = doc.liquido != null ? doc.liquido
    : doc.linhas.some(l => l.valor != null)
      ? doc.linhas.reduce((s, l) => s + (l.valor || 0), 0)
      : null;
  return { qtd, valor };
}

function detalheDocumentoFin(doc) {
  let h = "";
  if (doc.meses) {
    h += "<table><tr><th>Mês</th><th>ECG</th><th>MAPA</th></tr>" +
      doc.meses.map(m => "<tr><td>" + esc(m.mes) + "</td><td>" +
        m.ecg + "</td><td>" + m.mapa + "</td></tr>").join("") + "</table>";
  } else {
    h += "<table><tr><th>Tipo</th>" +
      (doc.linhas.some(l => l.detalhe) ? "<th>Unidade</th>" : "") +
      "<th>Qtd</th><th>Valor</th></tr>" +
      doc.linhas.map(l => "<tr><td>" + esc(l.tipo) + "</td>" +
        (doc.linhas.some(x => x.detalhe)
          ? "<td>" + esc(l.detalhe || "") + "</td>" : "") +
        "<td>" + l.qtd + "</td><td>" + brlSeguro(l.valor) + "</td></tr>")
        .join("") + "</table>";
  }
  if (doc.executantes) {
    h += "<p class='nota' style='margin-top:8px'>" + doc.executantes.map(e =>
      esc(e.nome) + ": " + e.servicos + " serviços (" + brlSeguro(e.valor) +
      ")").join(" · ") + "</p>";
    if (doc.bruto) {
      h += "<p style='margin-top:4px'><b>Bruto p/ nota: " + brlSeguro(doc.bruto) +
        " · Líquido: " + brlSeguro(doc.liquido) + "</b></p>";
    }
  }
  return h;
}

async function carregarFinanceiro() {
  const sec = document.getElementById("sec-financeiro");
  try {
    const f = await (await fetch("/api/financeiro")).json();
    const nomes = ["IDS", "Unimed", "CardioPro"].filter(n => f.empresas[n]);
    if (!nomes.length) {
      sec.innerHTML = "<p class='nota'>Nenhum demonstrativo na pasta " +
        "repasses ainda.</p>";
      return;
    }
    let resumos = "<div class='grade-fornecedores-fin'>";
    let listas = "";
    for (const nome of nomes) {
      const emp = f.empresas[nome];
      const docsOrdenados = emp.documentos.slice().reverse();
      let totalQtd = 0, totalValor = 0, temValor = false;
      docsOrdenados.forEach(doc => {
        const r = resumoDocumentoFin(doc);
        totalQtd += r.qtd;
        if (r.valor != null) { totalValor += r.valor; temValor = true; }
      });
      resumos += "<div class='resumo-fornecedor-fin'><h3>" + esc(nome) + "</h3>" +
        "<div class='num-grande'>" + totalQtd + " exames</div>" +
        "<div class='num-sub'>" + docsOrdenados.length + " documento" +
        (docsOrdenados.length === 1 ? "" : "s") +
        (temValor ? " · " + brl(totalValor) : "") + "</div></div>";
      listas += "<section class='bloco'><h2>" + esc(nome) + "</h2>" +
        "<div class='doc-fin-lista'>" +
        docsOrdenados.map(doc => {
          const r = resumoDocumentoFin(doc);
          return "<details><summary>" +
            "<span class='doc-data'>" + esc(dataDocumentoFin(doc)) + "</span>" +
            "<span class='doc-tipo'>" + esc(TIPO_AMIGAVEL_FIN[nome]) + "</span>" +
            "<span class='doc-num'>" + r.qtd + " exames" +
            (r.valor != null ? " · " + brl(r.valor) : "") + "</span></summary>" +
            "<div class='corpo'><p class='nota'>" + esc(doc.arquivo) + "</p>" +
            detalheDocumentoFin(doc) + "</div></details>";
        }).join("") + "</div></section>";
    }
    resumos += "</div>";
    sec.innerHTML = "<section class='bloco'><h2>Produção e pagamentos " +
      "(demonstrativos recebidos)</h2>" + resumos + "</section>" + listas;
  } catch (e) {
    sec.innerHTML = "<p class='nota'>Não consegui ler os demonstrativos.</p>";
  }
}
carregarFinanceiro();
```

- [ ] **Step 4: Append the new CSS for the Financeiro components**

In `painel.html`'s `<style>` block, immediately before the closing `</style>` tag (right after Task 5's retokenized `.card-import .ci-motivo` rule), add:

```css

  .grade-fornecedores-fin { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px,1fr));
    gap: 12px; }
  .resumo-fornecedor-fin { border: 1px solid var(--cor-borda); border-radius: var(--raio);
    padding: 14px 16px; }
  .resumo-fornecedor-fin h3 { font-size: 12.5px; text-transform: uppercase; letter-spacing: .03em;
    color: var(--cor-texto-fraco); font-weight: 700; margin-bottom: 8px; }
  .resumo-fornecedor-fin .num-grande { font-size: 22px; font-weight: 700;
    font-variant-numeric: tabular-nums; color: var(--cor-texto); }
  .resumo-fornecedor-fin .num-sub { font-size: 12px; color: var(--cor-texto-fraco); margin-top: 2px; }
  .doc-fin-lista details { margin-bottom: 6px; }
  .doc-fin-lista summary { display: flex; align-items: center; gap: 12px;
    font-weight: 400; font-size: 13.5px; }
  .doc-fin-lista summary .doc-tipo { color: var(--cor-primaria); font-weight: 600; flex: 1; }
  .doc-fin-lista summary .doc-data { color: var(--cor-texto-fraco); width: 90px; flex-shrink: 0; }
  .doc-fin-lista summary .doc-num { font-variant-numeric: tabular-nums; font-weight: 600; }
```

- [ ] **Step 5: Run the existing test suite again**

Run: `py -m pytest tests/ -v` from the repo root.
Expected: 26 passed (unchanged — confirms this front-end-only task didn't regress the backend).

- [ ] **Step 6: Manual verification — data parity is the critical check**

Before making this change, note (from the running painel, Financeiro tab, in a browser) the total exam count and total value shown per fornecedor in the OLD layout (sum the per-document totals by hand, or note a couple of specific document line values to spot-check). Then reload with the new code and confirm:
- Each fornecedor (IDS, Unimed, CardioPro — whichever have data) shows a summary card at the top with a total exam count and, where money data exists, a total value.
- Below that, one card per fornecedor lists its documents as collapsed rows (date · tipo amigável · qtd · valor), most recent first.
- Clicking a row expands it and shows the same detail table/executantes/bruto-líquido info the old flat layout used to show inline — spot-check at least one IDS, one Unimed, and one CardioPro document (if present) against what the old version showed, to confirm no numbers were dropped or double-counted.
- "Pagamentos sem exame correspondente" (below, `sec-orfaos`) still works as before.
- No console errors.

If you have Chrome browser automation tools available, use them to do this comparison (e.g. capture the old numbers before your edit via git stash, or note them from the task description if already recorded); otherwise do it by visual inspection and describe what you checked in the report.

- [ ] **Step 7: Commit**

```bash
git add painel.html
git commit -m "Financeiro: resumo por fornecedor + lista de documentos expansivel"
```

---

### Task 7: Sweep final — cores antigas remanescentes + QA visual completo

**Files:**
- Modify: `painel.html` only if the grep in Step 1 finds something Tasks 1-6 missed.

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — this task verifies Tasks 1-6's combined result and fixes stragglers if any.

- [ ] **Step 1: Grep for leftover hardcoded colors from the old palette**

Run, from the repo root:

```bash
grep -noE "#(1e5a8a|16466c|cfe0ef|c62828|2e7d32|b26a00|546e7a|fdecea|e3f0fa|e8f5e9|fff3cd|eceff1|8a6d00|667|556|223|e1e0d9|99a|dcdad0|ffb300|3a6d99|dfe9f2)\b" painel.html
```

Expected: no matches. These are the specific old hex/shorthand colors this plan's Tasks 1-6 were supposed to replace with tokens. If anything is still there, it means a task's old_string match landed slightly differently than planned (e.g. a color reused in a spot this plan didn't anticipate) — read the surrounding context of each match and replace it with the appropriate `var(--cor-...)` token from Task 1's palette, matching what the same color means elsewhere (e.g. `#1e5a8a` anywhere remaining means `var(--cor-primaria)` or `var(--cor-navy)` depending on context — check what it's styling).

- [ ] **Step 2: Grep for the removed emoji and for em dashes**

Run:

```bash
grep -n "🩺" painel.html
grep -n "—" painel.html
```

Expected: both return nothing. If the emoji grep finds something, Task 1's favicon edit didn't land — fix it. If the em-dash grep finds something, it's new text introduced by mistake during this plan's implementation — rewrite it without the dash (comma, period, or colon, matching this project's writing convention).

- [ ] **Step 3: Full visual walkthrough in a browser**

Run `py painel.py` from the repo root. If Chrome browser automation tools are available, use them for this step and note what you observed; otherwise describe exactly what a human should check and ask the user to confirm.

Walk through, in order:
1. Initial load screen (spinner) — new navy/blue spinner.
2. Header + nav — dark navy header, blue "Atualizar", outlined "Encerrar", underline-style active tab.
3. "Visão geral" — cards grid, atrasados/aguardando tables, status section, expandable "extras" sections.
4. "Exames" — filter bar, table with badges.
5. "Financeiro" — fornecedor summary cards, expandable document lists (this is the tab the usuária specifically flagged as broken — confirm it now reads as organized, not a wall of tables).
6. "Análises" — segmented toggle, month cards / donut view, tooltip on hover, click-to-drill-down panel.
7. "Importações" — pasta local input + Salvar, local and email file cards with the three status colors.
8. Favicon in the browser tab.

For each, confirm: no visual regression (nothing overlapping, nothing unreadably small, nothing still using the old rounded-pill/heavy-shadow look), and no browser console errors across the whole walkthrough.

- [ ] **Step 4: Run the backend test suite one final time**

Run: `py -m pytest tests/ -v` from the repo root.
Expected: 26 passed.

- [ ] **Step 5: Commit (only if Steps 1-2 required fixes)**

If no fixes were needed in Steps 1-2, skip this commit — report that the sweep found nothing and Task 6's commit is the last one. If fixes were needed:

```bash
git add painel.html
git commit -m "Sweep final: remove cores/emoji remanescentes da retematizacao"
```
