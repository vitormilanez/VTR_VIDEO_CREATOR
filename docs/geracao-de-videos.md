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

## Automacao futura com API

Quando a conta/API do HeyGen estiver pronta, a automacao deve seguir este fluxo:

1. Ler linhas da aba `Roteiros` com status `Aprovado para video`.
2. Enviar roteiro para o HeyGen.
3. Criar job de video.
4. Atualizar status para `Video solicitado`.
5. Consultar o job ate ficar pronto.
6. Salvar o link do video na planilha.
7. Atualizar status para `Video pronto`.

Regra: nao enviar para HeyGen sem aprovacao humana, porque isso pode gastar creditos.

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
