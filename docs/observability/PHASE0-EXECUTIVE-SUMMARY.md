# Fase 0 — Discovery Observability — Resumo Executivo

## Objetivo
Avaliar a maturidade do observability do homelab e identificar os gargalos críticos que impedem a operação como um Command Center.

## Ambiente
- Proxmox: `192.168.50.250`
- RKE2 control-plane: `rke2-cp-01` (`192.168.50.20`)
- RKE2 worker: `rke2-worker-01` (`192.168.50.21`)
- Rocky Linux 9.8, RKE2 `v1.35.6+rke2r1`, containerd `2.2.5-k3s2`
- Canal/Flannel + Calico, Longhorn `1.7.2`, ArgoCD `3.3.1`
- kube-prometheus-stack `82.2.0` (Prometheus `v3.9.1`, Grafana `12.3.3`, Alertmanager `0.31.1`)
- Zabbix `7.1.0` chart / image `ubuntu-7.0.29`

## Principais achados

### 1. RKE2 control-plane invisível para Prometheus
- `kube-controller-manager`, `kube-scheduler` e `etcd` estavam DOWN no Prometheus.
- Causa: processos RKE2 escutavam apenas em `127.0.0.1`.
- Correção: `/etc/rancher/rke2/config.yaml` com `etcd-expose-metrics: true` e `bind-address=0.0.0.0` para KCM/scheduler. **Resolvido.**

### 2. Alertmanager sem notificações
- Configuração padrão enviava tudo para receiver `null`.
- Correção: receiver `telegram` configurado no `clusters/homelab/apps/monitoring.yaml`, Secret `alertmanager-telegram` montado. **Resolvido e testado.**

### 3. Zabbix ruidoso e parcialmente cego
- Muitos hosts com active checks indisponíveis.
- Templates/itens ativos desproporcionais (31 itens ativos, 8124 inativos).
- Requer revisão de templates e hosts.

### 4. Concentração de storage Longhorn
- Todos os volumes replicados no worker.
- `rke2-cp-01` com `allowScheduling: false`.
- Risco: falha no worker perde todos os volumes.

### 5. Recursos sem requests/limits
- Grande parte dos workloads sem requests/limits.
- Risco: noisy neighbor, evictions e incapacidade de planejamento de capacidade.

### 6. Métricas e retenção inconsistentes
- Retenção do Prometheus: `30d` no cluster, `3d` ainda presente no repo antigo.
- Fontes fragmentadas: Prometheus, Zabbix, Proxmox, Longhorn, cert-manager.

## Correções já aplicadas
| Item | Status |
|------|--------|
| Targets RKE2 control-plane UP | ✅ |
| Alertmanager com Telegram | ✅ |
| Config as Code no repo `K3s-CCoE` | ✅ |
| ArgoCD `root-homelab` Synced/Healthy | ✅ |

## Pendências críticas recomendadas
1. Resolver `KubeProxyDown` (kube-proxy não aparece no Prometheus).
2. Investigar `PrometheusTSDBCompactionsFailing`.
3. Revisar e limpar Zabbix (templates, hosts, triggers).
4. Ajustar Longhorn para scheduling multi-node.
5. Adicionar requests/limits aos workloads.
6. Criar Command Center no Grafana (datasources, dashboards unificados).
7. Avaliar Loki/Alloy para logs após a base estabilizar.

## Relatório completo
O relatório completo da Fase 0 com evidências, evidências, maturidade por área e arquitetura AS-IS/TO-BE preliminar está em:

```text
/root/observability-discovery/PHASE0-REPORT.md
```

> Nota: o resumo acima foi versionado no repo; o relatório completo permanece no diretório de discovery.
