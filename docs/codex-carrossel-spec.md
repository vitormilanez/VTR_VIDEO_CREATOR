# Spec para o Codex — três famílias de carrossel (1080 × 1350)

Referência visual: `Modelos de Carrossel.dc.html` (21 artboards em escala real 1080×1350, escala 0,3 na tela).
Contrato de dados: `carousel-contract.schema.json`.
Repositório: `vitormilanez/VTR_VIDEO_CREATOR`, branch `codex/intelligent-video-workflows`.

---

## 0. Princípio central

**Uma única versão canônica de conteúdo. Três famílias de layout. Zero token na troca.**

```
Claude (1 chamada) ──► CarouselContent (papéis semânticos + campos)
                            │
                            ├─► render(EDITORIAL)   ──┐
                            ├─► render(DIDATICO)     ─┼─► preview (React) e PNG (Playwright)
                            └─► render(STORYTELLING) ─┘   pelo MESMO componente
```

Trocar de família = trocar um enum no Pack. Não chama Claude. Não regenera texto. Não invalida cache.

---

## 1. Auditoria — o que já existe (não reescrever)

| Peça | Arquivo | Papel hoje | O que fazer |
| --- | --- | --- | --- |
| Vocabulário de layouts | `api/pack_design.py` → `PACK_LAYOUTS` | 12 layouts fixos, misturando papel semântico e composição | **Separar**: papel semântico vai para o contrato, composição vira variante de família |
| Limites editoriais | `LAYOUT_SPECS[*].max` / `item_max` | corte determinístico de copy | Manter, mas passar a indexar por **papel**, não por layout |
| Reparo de copy | `repair_pack_copy`, `_fit_copy` | corta sem quebrar frase | Manter integralmente |
| Validação | `validate_pack_contract` | ritmo, foto, emoji, contraste de fundos | Manter e ampliar (ver §7) |
| Biblioteca de fotos | `PHOTO_LIBRARY` | 6 fotos com `facePointX/Y` e `brightness` | Ampliar para `focalPointX/Y`, `fit`, `position`, `overlayStrength` |
| Renderer PNG | `api/slides.py` | Playwright screenshot 1080×1350 | Manter o mecanismo; trocar a fonte do HTML (ver §6) |
| Editor | `web/src/routes/_app.packs.tsx` | grade de cards administrativos | Trocar o card por miniatura do artboard real |

**Regras duplicadas a eliminar:** hoje o HTML dos PNGs e o preview do editor são construídos em lugares diferentes. Depois desta mudança, existe **uma** função de render.

---

## 2. Design system de carrossel (`carouselDesignSystem`)

Tokens **derivados de `web/src/styles.css`** (paleta Ocean Deep), versionados como `carousel-ds@1`.

```ts
export const CDS = {
  version: 'carousel-ds@1',
  canvas: { w: 1080, h: 1350, safeTop: 88, safeBottom: 88, safeX: 72, igSafeBottom: 120 },
  color: {
    ink:   '#0c2340',  // --primary  oklch(0.29 0.06 240)
    deep:  '#1a4a6e',
    teal:  '#2d8a9e',  // acento funcional
    aqua:  '#5cbdb9',  // acento sobre fundo escuro / CTA
    paper: '#f2f5f6',  // --background
    white: '#ffffff',
    muted: '#5b7185',
    rule:  '#0c2340',  // réguas 2px
  },
  font: {
    display: 'Urbanist',  // --font-display
    body:    'Epilogue',  // --font-sans
    mono:    'JetBrains Mono', // eyebrows, numeração, metadados
  },
  // Três degraus fixos por papel. Nunca autofit contínuo.
  typeSteps: {
    headline: { L: 88, M: 70, S: 56 },
    hero:     { L: 118, M: 100, S: 84 },
    body:     { L: 46, M: 38, S: 32 },
    item:     { L: 40, M: 36, S: 32 },
    eyebrow:  { L: 26, M: 24, S: 24 },
    meta:     { L: 24, M: 24, S: 22 },
  },
  minFontSize: 28,     // corpo nunca abaixo disso; abaixo → dividir slide
  rule: 2,             // espessura de régua, em px
  radius: 0,           // sem cantos arredondados no artboard
  overlay: { light: 0.55, medium: 0.82, heavy: 0.92 },
} as const;
```

Regras que **as três famílias compartilham** (não são configuráveis por família):

- paleta, tipografia, espessura de régua 2px, raio 0;
- margens e safe areas (`safeX` 72, `safeTop`/`safeBottom` 88; no rodapé reservar `igSafeBottom` 120 quando houver texto vital, por causa da UI do Instagram);
- alinhamento à esquerda para título e corpo;
- tratamento fotográfico: overlay com os três degraus acima, nunca colorização;
- contraste mínimo 4,5:1 para corpo e 3:1 para display;
- CTA sempre como bloco sólido `aqua` sobre fundo escuro ou `ink` sobre paper, com rótulo flush-left;
- disclaimer sempre presente no slide de CTA, `meta.S`, opacidade ≥ 0,55.

---

## 3. Contrato de conteúdo (`CarouselContentContract`)

Substitui o acoplamento atual entre conteúdo e `layoutId`.

```ts
type SlideRole =
  | 'cover' | 'context' | 'question' | 'problem' | 'mechanism'
  | 'explanation' | 'steps' | 'key_points' | 'statistic'
  | 'myth_fact' | 'medical_quote' | 'conclusion' | 'cta';

interface CarouselSlide {
  role: SlideRole;
  fields: {
    eyebrow?: string; headline?: string; subheadline?: string; body?: string;
    statistic?: string; caption?: string; quote?: string; attribution?: string;
    cta?: string; footer?: string; disclaimer?: string;
    items?: { title?: string; text: string }[];   // máx. 3
    steps?: { label: string }[];                   // máx. 4, para mechanism/steps
  };
  photo?: {
    assetId: string; focalPointX: number; focalPointY: number;
    fit: 'cover' | 'contain'; position?: string; overlayStrength: number;
  };
  densityHint?: 'L' | 'M' | 'S';   // opcional; o renderer calcula se ausente
  continuation?: { of: string; part: number; total: number }; // slides divididos
}

interface CarouselContent {
  schemaVersion: 'carousel-content-v1';
  packId: string;
  topic: string;
  slides: CarouselSlide[];          // 6 a 9; padrão 7
  caption: string;
  hashtags: string[];
  recommendedFamily?: 'editorial' | 'didatico' | 'storytelling';
  recommendationReason?: string;
  evidenceLevel: 'observational' | 'trial' | 'consensus' | 'opinion';
}
```

O `layoutId` legado **não morre**: `LEGACY_LAYOUT_MAP` ganha um segundo mapa `LAYOUT_TO_ROLE` para migrar Packs salvos sem nova chamada de IA.

```py
LAYOUT_TO_ROLE = {
  "hero_photo": "cover", "photo_overlay": "cover", "big_statement": "context",
  "question": "question", "explainer": "explanation", "three_points": "key_points",
  "number_stat": "statistic", "myth_fact": "myth_fact", "do_dont": "myth_fact",
  "doctor_quote": "medical_quote", "photo_split": "explanation", "cta_photo": "cta",
}
```

---

## 4. As três famílias

Todas recebem `CarouselContent` e devolvem o mesmo número de artboards.

### `editorial` — Editorial médico premium
Autoridade, silêncio, foto grande. Uma ideia por tela.

| Papel | Variante | Regras |
| --- | --- | --- |
| cover | `photo_full` | foto full-bleed, gradiente `ink` de 52% para baixo, hero L, régua 2px, sub ≤ 2 linhas |
| context / problem | `big_statement` | fundo `ink` sólido, headline L, régua, body M, terço inferior livre |
| question | `poster` | fundo `paper`, headline L em `ink`, sem foto |
| mechanism | `chain` | lista de 3–4 etapas separadas por régua 2px; última etapa em `teal` |
| key_points | `three_points` | fundo `ink`, numeração mono `aqua`, régua entre itens |
| medical_quote | `photo_split` | foto ocupa 40% da largura em altura cheia; painel `paper` com aspas |
| cta | `photo_bottom_panel` | foto no topo (620px) + painel `ink` com bloco CTA `aqua` |

Densidade máxima: **headline ≤ 60 car.**, **body ≤ 160 car.**, **sem listas de 3 itens fora de `key_points`**.

### `didatico` — Didático científico
Grade visível, etapas numeradas, relações desenhadas.

| Papel | Variante | Regras |
| --- | --- | --- |
| cover | `photo_split` | foto no topo (520px) + chip `aqua` com o eyebrow + headline M |
| context | `flow_diagram` | 2–4 caixas de borda 2px ligadas por `↓`; último nó em `ink` sólido |
| question | `marker` | glifo `?` display 220px em `aqua`, headline M |
| mechanism / steps | `numbered_steps` | 3–4 linhas `01…04` separadas por régua; rodapé com nota de evidência |
| key_points | `grid_cells` | três células de altura igual (`grid-template-rows: repeat(3,1fr)`) |
| statistic | `big_number` | número display 260px `teal`, caption M, fonte do dado obrigatória |
| medical_quote | `card_rule` | régua superior, retrato 120×120, nome + especialidade |
| cta | `checklist` | 2–3 itens com marcador quadrado `teal` + faixa de foto de 340px no rodapé |

Densidade máxima: **body ≤ 280 car.**, **listas ≤ 3 itens de ≤ 90 car.**, **≤ 4 etapas**.

### `storytelling` — Storytelling humano
Foto presente, texto curtíssimo, tensão e resposta.

| Papel | Variante | Regras |
| --- | --- | --- |
| cover | `photo_full_cinematic` | duplo gradiente (topo 0,55 / base 0,92), hero L 118px, barra `aqua` 88×6 |
| context | `photo_overlay` | foto com overlay 0,82, texto centrado verticalmente |
| question | `color_field` | campo sólido `teal`, hero L branco — único slide colorido do carrossel |
| mechanism | `staggered` | 4 frases curtas com indentação progressiva (0/110/220/330px), última em `teal` |
| key_points | `ghost_numerals` | numerais 96px `aqua` a 35% de opacidade ao lado de frases ≤ 30 car. |
| medical_quote | `portrait_panel` | close-up 760px no topo + painel branco com aspas e assinatura |
| cta | `side_panel` | painel `ink` 560px à esquerda + foto à direita |

Densidade máxima: **headline ≤ 46 car.**, **body ≤ 110 car.**, **listas ≤ 3 itens de ≤ 40 car.**
Se o conteúdo canônico exceder isso, o renderer **não corta**: marca `overflow` e o editor sugere `didatico` (ver §7).

---

## 5. Densidade — mais texto, menos texto

O renderer escolhe um dos três degraus por campo, **determinístico**, por contagem de caracteres:

| Campo | Degrau L | Degrau M | Degrau S |
| --- | --- | --- | --- |
| headline | ≤ 34 car. | 35–60 car. | 61–90 car. |
| body | ≤ 90 car. | 91–190 car. | 191–280 car. |
| item.text | ≤ 40 car. | 41–70 car. | 71–90 car. |
| quote | ≤ 60 car. | 61–110 car. | 111–160 car. |

Regra de estouro, nesta ordem — **nunca reduzir a fonte abaixo de `minFontSize` (28px)**:

1. Aplicar o degrau S.
2. Se ainda estourar a caixa medida, pedir a Claude **apenas uma reescrita curta daquele campo** (não do carrossel).
3. Se o campo for clinicamente indivisível, **dividir em dois slides**: mesmo `role`, `continuation: { of, part, total }`, eyebrow ganha “parte 1 de 2”, o primeiro recebe uma faixa de transição.
4. Nunca truncar informação clínica automaticamente — `_fit_copy` só age em campos decorativos (eyebrow, footer, caption).

Quando o conteúdo é **curto demais** (headline ≤ 20 car. e sem body), subir o degrau para L e aumentar a área de respiro; não inventar texto para preencher.

---

## 6. Renderer determinístico e paridade preview/export

Fonte única de verdade: um módulo de render puro.

```
packages/carousel-render/
  contract.ts        # tipos + zod schema (espelha carousel-contract.schema.json)
  design-system.ts   # CDS (§2)
  density.ts         # resolveDensity(field, text) -> 'L'|'M'|'S'
  families/
    editorial.tsx  didatico.tsx  storytelling.tsx
  Artboard.tsx       # <Artboard slide family assets scale />  → sempre 1080×1350
  index.ts
```

- **Preview (React)**: o editor renderiza `<Artboard scale={0.28} />`. Cada item da grade é o artboard real, não um card.
- **Export (PNG)**: `api/slides.py` continua abrindo o Playwright, mas a página carrega o **mesmo bundle** com `scale={1}` e captura 1080×1350 em `deviceScaleFactor: 2`.
- Proibido: CSS ou HTML vindos de Claude; posições hardcoded em componentes de rota; um caminho de estilo para preview e outro para export.
- Fontes empacotadas localmente (`assets/fonts/`) para o Playwright não depender da rede.

Migração: `PACK_SCHEMA_VERSION` vai para `institute-carousel-v3` e ganha `family` (default `didatico` para Packs existentes, que é o mais próximo do layout atual).

---

## 7. Validação determinística (sem tokens)

Estende `validate_pack_contract`:

1. `slides[0].role == 'cover'` e `slides[-1].role == 'cta'`.
2. Pelo menos um entre `mechanism | explanation | steps` nas posições 3–5.
3. Máx. 3 slides com foto; nunca dois full-bleed seguidos; máx. 2 fundos escuros seguidos.
4. Sem emoji em qualquer campo.
5. Contraste calculado texto/fundo ≥ 4,5:1 (corpo) e ≥ 3:1 (display) — inclusive sobre foto, considerando `overlayStrength`.
6. Nenhuma caixa de texto excede sua área medida no degrau S.
7. `focalPoint` do retrato nunca sob um bloco de texto; margem mínima de 40px entre o texto e o rosto.
8. **Léxico proibido** quando `evidenceLevel != 'trial'`: `cura`, `garantido`, `milagre`, `comprovado`, `elimina`, `previne` — e nenhuma construção causal (`causa`, `provoca`) para `evidenceLevel: 'observational'`; usar `associação`, `relação`, `favorece`.
9. O renderer nunca altera conteúdo clínico: destaque tipográfico não pode ser aplicado a uma negação (“não previne”) de forma a esconder o “não”.

---

## 8. Uso de tokens Anthropic

Usar: simplificar linguagem, ordenar narrativa, atribuir `role`, decidir quantidade de conteúdo, decidir se um slide pede foto, recomendar família, checar repetição e precisão médica, reescrever um campo específico em estouro.

Não usar: desenhar pixels, calcular dimensões, escolher margens, gerar HTML/CSS, renderizar PNG, repetir conteúdo para as três famílias, validar o que já é determinístico (§7).

Cache key:

```
sha256(contentHash + promptVersion + carouselDsVersion + brandProfileId + format + anthropicModel)
```

Trocar de família **não** altera a chave — a família não entra na geração de conteúdo.

---

## 9. UI do editor

Na aba **Carrossel**, acima da grade:

- três cartões — **Editorial**, **Didático**, **Storytelling** — cada um com miniatura real do slide 1 do pack atual, uma linha de descrição e uma de “quando usar”;
- **Aplicar modelo** (local, instantâneo, sem token);
- **Recomendar modelo com Claude** (uma chamada; devolve `recommendedFamily` + motivo; badge no cartão sugerido);
- **Visualizar carrossel** (viewer 4:5 em tela cheia, navegação por teclado);
- **Salvar PNGs** (zip 1080×1350, `carrossel-01…07.png`).

Cada item da grade mostra o artboard real com um rótulo `SLIDE n · role · variante`. Foto: arraste para reposicionar o focal point, slider de overlay, botão trocar foto. Nada de `<select>` de foto ao lado de um formulário.

Não redesenhar o resto do app.

---

## 10. Ordem de implementação (slices testáveis)

1. **Contrato** — tipos + zod + `LAYOUT_TO_ROLE` + migração v2→v3 com testes de Packs salvos (estender `tests/test_pack_context.py`).
2. **Design system** — `design-system.ts` + `density.ts` com testes de tabela dos degraus.
3. **Artboard + família `didatico`** — a mais próxima do atual; preview no editor substituindo o card.
4. **Paridade de export** — `api/slides.py` renderiza o mesmo bundle; teste comparando o DOM do preview e o do export.
5. **Famílias `editorial` e `storytelling`** — variante por papel, com snapshot de cada papel.
6. **Fotos** — `focalPoint`, `fit`, `position`, `overlayStrength` no schema, reposicionamento no editor.
7. **Validação** — regras §7, incluindo contraste e léxico, com testes.
8. **UI de seleção de modelo** + recomendação por Claude + cache.

Concluir um slice, testar, corrigir, seguir para o próximo. Sem redesign da interface inteira.
