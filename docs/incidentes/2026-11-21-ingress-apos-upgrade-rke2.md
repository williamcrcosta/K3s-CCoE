# 21/11/2026 — Acesso ao ingress após upgrade do RKE2

## Impacto

As URLs internas das aplicações recusaram conexão HTTPS após a manutenção. A API do Kubernetes estava pronta e os dois nós estavam `Ready`.

## Causa

O DNS do Grafana ainda resolvia para `192.168.50.20`. Antes da manutenção, o ingress tinha um pod nesse nó. O control plane já tinha o taint `node-role.kubernetes.io/control-plane=true:NoSchedule`, documentado no [incidente de etcd](2026-10-11-rke2-etcd-timeout.md). O taint permite que pods existentes continuem rodando. Após a recriação do DaemonSet, o template sem tolerância correspondente passou a agendar o ingress somente na worker, em `192.168.50.21`.

## Recuperação e validação

- Upgrade e reboot sequenciais da worker e do control plane. Ambos voltaram com RKE2 `v1.35.10+rke2r1` e kernel `5.14.0-741.24.1.el9_9.x86_64`. Houve snapshot do etcd antes do upgrade do CP.
- O teste por HTTPS com `curl --resolve` para a worker retornou `302 /login` no Grafana.
- Os [rewrites do AdGuard](../../ADGUARD_DNS.md#aplicações-do-ingress) passaram a apontar para a worker. O operador confirmou o retorno das aplicações.
- Durante a janela, o volume do Prometheus ficou `degraded` e voltou a `healthy` após reconstrução. A causa do detach inicial ficou em aberto. As duas réplicas estavam no mesmo disco da worker.

## Acompanhamento

Testar as URLs por DNS normal de fora do cluster após cada reboot. Planejar a distribuição das réplicas Longhorn entre nós e a redundância do acesso ao ingress.
