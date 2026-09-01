# Runbook de rollback Admin/APK

1. Congele a janela e registre o SHA/digest ativo.
2. Restaure `infra/docker-compose.pages-rgb.prod.yml` e `infra/Caddyfile.pages-rgb` para o último SHA aprovado; execute `docker compose config` antes de aplicar.
3. Mantenha a migration compatível: não faça downgrade destrutivo do banco. Se necessário, restaure snapshot somente após aprovação do responsável pelo banco.
4. Suba API, aguarde `/api/v1/health/live` e `/ready`, depois admin e Caddy; valide `/admin/login`, assets `/_next/*`, `/api` e `/docs`.
5. Revogue sessões administrativas e rotacione secrets somente se houver suspeita de comprometimento.
6. Para desabilitar o painel sem interromper o gateway, remova apenas o handler `/admin*`/serviço admin e mantenha a API.
7. Registre causa, SHA anterior/novo, resultado dos smoke tests e plano de correção.
