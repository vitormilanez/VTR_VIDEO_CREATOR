# Instagram / Meta Graph API

O app usa a API oficial da Meta para publicar um video pronto como Reel ou Story. O token nunca e
enviado ao frontend.

## Pre-requisitos

- Conta profissional do Instagram. Para Stories pela API, use uma conta Business.
- App criado no Meta for Developers com o produto Instagram/API configurado.
- Permissao de leitura basica e permissao de publicacao de conteudo concedidas ao token.
- No fluxo "Instagram API with Facebook Login", a conta profissional deve estar ligada a uma
  Pagina do Facebook e o token normalmente precisa de `instagram_basic`,
  `instagram_content_publish`, `pages_show_list` e `pages_read_engagement`.
- Durante o desenvolvimento, a conta que autoriza deve ter uma funcao no app da Meta. Para contas
  externas, conclua App Review e coloque o app em modo Live.

## Variaveis locais

Adicione ao `.env` na raiz do projeto:

```dotenv
META_ACCESS_TOKEN=seu_token_de_longa_duracao
INSTAGRAM_BUSINESS_ACCOUNT_ID=1784...
META_GRAPH_API_VERSION=v23.0
```

`INSTAGRAM_BUSINESS_ACCOUNT_ID` e o ID numerico da conta profissional, nao o nome de usuario. A
versao da Graph API e configuravel porque as versoes da Meta expiram periodicamente.

Reinicie a API depois de alterar o `.env`. Em **Configuracoes**, clique em **Testar conexao**. O
app deve mostrar o `@usuario` retornado pela Meta.

## Publicar um teste

1. Gere ou atualize um video ate ele ficar com status `pronto`.
2. Abra o detalhe do video e clique em **Publicar no Instagram**.
3. Escolha Reel ou Story. Para Reel, revise a legenda e a opcao de exibir no feed.
4. Confirme **Publicar agora**.

O backend cria um container de midia, aguarda a Meta terminar de processar o arquivo e somente
entao chama `media_publish`. O historico com IDs do container e da publicacao fica anexado ao job
local do video.

## Limitacoes importantes

- A URL do video deve ser HTTPS e publicamente acessivel pela Meta durante o processamento.
- Stories publicados pela API nao recebem legenda e nao suportam stickers interativos como
  enquete, pergunta ou link.
- O app nao publica automaticamente ao apenas agendar no calendario; ha uma confirmacao explicita
  na tela do video.
- Trate o token como segredo. Nao o cole no navegador, nao o envie ao Git e revogue-o se houver
  suspeita de vazamento.
