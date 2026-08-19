# Publicacao gratuita protegida

O fluxo temporario usa tres camadas:

1. `./dev.sh` mantem PostgreSQL, FastAPI e Vite somente no computador local.
2. Caddy escuta apenas em `127.0.0.1:8081` e exige autenticacao HTTP Basic.
3. Cloudflare Quick Tunnel publica o Caddy em uma URL HTTPS aleatoria.

## Iniciar

Em um terminal, suba o app:

```bash
./dev.sh
```

Em outro terminal, suba o gateway:

```bash
./tools/online_gateway.sh
```

O `cloudflared` exibira uma URL no formato
`https://nome-aleatorio.trycloudflare.com`. O usuario inicial e `vtr`.

## Trocar a senha

Gere um novo hash sem salvar a senha em texto puro:

```bash
caddy hash-password
```

Substitua somente o hash do usuario `vtr` em `.online/Caddyfile` e reinicie o
gateway. O diretorio `.online/` nao e versionado.

## Limites

- A URL muda quando o Quick Tunnel reinicia.
- O Mac precisa permanecer ligado e conectado a internet.
- Esta configuracao e apropriada para validacao e uso restrito. Uma URL estavel
  requer um dominio e um Cloudflare Tunnel nomeado, ou a migracao para uma VM.
