# Biblioteca local de conteudo

Use:

```bash
.venv/bin/python tools/organize_content_library.py
```

O comando recria `content/biblioteca/` como uma biblioteca humana por projeto:

```text
content/biblioteca/
  2026-08-10_o-ser-humano-esta-sendo-domesticado/
    00-resumo/INDEX.md
    01-packs/
    02-videos-produzidos/
    03-edicao-local/
    04-pos-producao/
    05-cortes/
    06-assets/
    07-uploads-e-fontes/
    08-relatorios-exportados/
```

A biblioteca usa atalhos relativos para os arquivos reais em `content/` e
`data/`. Isso facilita achar tudo por data e titulo sem quebrar os caminhos que
o app usa internamente.

Não apague os arquivos originais só porque eles aparecem na biblioteca. A
biblioteca é um índice de trabalho; os originais continuam sendo a fonte usada
pela API.
