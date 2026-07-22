# Geracao de videos

## Assets da pessoa

As fotos do Dr. Guilherme ficam em:

```text
assets/personas/dr-guilherme/raw/
```

Foram recebidas 13 fotos tratadas em alta resolucao. Essas imagens estao ignoradas pelo git.

Pastas:

- `raw/`: fotos originais recebidas.
- `reference/`: melhores fotos escolhidas para avatar/modelo.
- `processed/`: recortes e versoes preparadas para upload.

## Regra de uso de imagem

Antes de usar a imagem de uma pessoa em IA, confirmar autorizacao expressa da pessoa retratada.

Para o Dr. Guilherme, o ideal e validar:

- autorizacao para criar avatar/modelo de IA;
- autorizacao para uso comercial/publicitario;
- aprovacao previa dos roteiros medicos;
- aprovacao final dos videos antes de publicar.

## MVP manual com HeyGen

Este e o caminho mais rapido para gerar alguns videos de teste:

1. Escolher 1 a 3 fotos boas em `assets/personas/dr-guilherme/raw/`.
2. Subir no HeyGen como avatar/foto/avatar de referencia, conforme a opcao disponivel no plano.
3. Copiar um roteiro aprovado da aba `Roteiros`.
4. Colar no HeyGen.
5. Gerar preview.
6. Revisar:
   - aparencia;
   - voz;
   - pronuncia;
   - cortes;
   - compliance medico.
7. Baixar o video final.
8. Colar o link na aba `Roteiros` ou `Calendario`.

## Integracao pelo app local

A tela de roteiro envia videos somente apos o clique explicito em `Enviar para producao`.
O backend cria um job local, consulta o status sob demanda e preserva o link e o preview retornados pelo HeyGen.

Para habilitar a conta nesta maquina, instale e autentique o CLI oficial uma unica vez:

```bash
curl -fsSL https://static.heygen.ai/cli/install.sh | bash
heygen auth login
```

Mantenha estas variaveis preenchidas apenas no `.env` local:

```bash
HEYGEN_API_KEY="..."
HEYGEN_DEFAULT_AVATAR_ID="..."
HEYGEN_DEFAULT_VOICE_ID="..."
```

Depois reinicie `./dev.sh`. O fluxo e manual: criar video pode consumir creditos; atualizar status apenas consulta o job ja existente.

## HeyGen API

Documentacao oficial usada:

- `GET /v3/users/me`: validar conta, creditos e billing.
- `GET /v3/avatars`: listar avatares.
- `POST /v3/videos`: criar video a partir de avatar ou imagem.
- `GET /v3/videos/{video_id}`: consultar status e links do video.

Scripts criados:

```text
heygen_check.py
heygen_create_video.py
heygen_get_video.py
integrations/heygen_client.py
```

Configurar a chave no `.env` local:

```bash
HEYGEN_API_KEY="cole_a_chave_aqui"
```

Validar conta e listar avatares:

```bash
.venv_sheets/bin/python heygen_check.py --avatars
```

Criar video de teste sem gastar credito:

```bash
.venv_sheets/bin/python heygen_create_video.py \
  --avatar-id "AVATAR_ID" \
  --title "Teste Dr Guilherme" \
  --script "Texto curto de teste." \
  --dry-run
```

Criar video real, somente depois de aprovado:

```bash
.venv_sheets/bin/python heygen_create_video.py \
  --avatar-id "AVATAR_ID" \
  --title "Teste Dr Guilherme" \
  --script "Texto aprovado."
```

Consultar video:

```bash
.venv_sheets/bin/python heygen_get_video.py VIDEO_ID
```

## Fotos recomendadas para avatar

Priorizar fotos com:

- rosto nitido;
- olhar para camera;
- boa iluminacao;
- pouca sombra no rosto;
- sem outras pessoas;
- sem cortes no topo da cabeca;
- fundo limpo;
- expressao profissional e natural.

Evitar:

- foto de corpo inteiro muito distante;
- perfil lateral;
- oculos escuros;
- boca muito aberta;
- baixa resolucao;
- imagens com texto ou marca d'agua.

## Proximo passo tecnico

Criar:

```text
generate_scripts_from_ideas.py
```

Funcao:

- ler a aba `Ideias`;
- gerar roteiro estruturado na aba `Roteiros`;
- manter status `Aguardando validacao medica`;
- nao acionar HeyGen ainda.
