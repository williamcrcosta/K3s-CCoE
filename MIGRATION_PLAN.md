# Plano de Migração — GitOps com ArgoCD

## Objetivo
Migrar todos os recursos do cluster para serem gerenciados pelo ArgoCD via GitOps,
eliminando recursos aplicados manualmente (`kubectl apply`).

## Estado Atual

| Namespace | App | Gerenciado pelo ArgoCD? |
|---|---|---|
| `longhorn-system` | Longhorn | ✅ Sim (`infra/longhorn`) |
| `dns` | Technitium | ✅ Sim (`apps/technitium`) |
| `cert-manager` | Cert Manager | ✅ Sim (`apps/cert-manager.yaml`) |
| `platform-argocd` | ArgoCD | ✅ Sim (self-managed) |
| `apps` | Whoami | ✅ Sim (`apps/whoami`) |
| `monitoring` | kube-prometheus-stack (Grafana + Prometheus) | ❌ Manual |
| `zabbix` | Zabbix + PostgreSQL | ❌ Manual |
| `kubernetes-dashboard` | Kubernetes Dashboard | ❌ Manual |

---

## Fase 1 — Observabilidade (monitoring)
**Apps:** Grafana, Prometheus, AlertManager, kube-state-metrics, node-exporter
**Helm chart:** `kube-prometheus-stack` (prometheus-community)
**Risco:** Baixo — stateless exceto PVC do Prometheus

### Passos
1. Exportar values atuais: `helm get values monitoring -n monitoring`
2. Criar `infra/monitoring/application.yaml` com o chart `kube-prometheus-stack`
3. Criar `infra/monitoring/kustomization.yaml`
4. Adicionar em `clusters/homelab/apps/monitoring.yaml`
5. Referenciar em `clusters/homelab/kustomization.yaml`
6. Commit + push → ArgoCD sincroniza
7. Validar Grafana (`https://grafana.wcrpc.lan`) e Prometheus (`https://prometheus.wcrpc.lan`)

---

## Fase 2 — Zabbix
**Apps:** Zabbix Server, Zabbix Web, Zabbix Webservice, PostgreSQL, CronJob nodesclean
**Helm chart:** `zabbix-community/zabbix` ou manifestos próprios
**Risco:** Médio — tem PVC com dados do PostgreSQL (requer backup antes)

### Passos
1. **Backup do banco:** `kubectl exec -n zabbix zabbix-postgresql-0 -- pg_dump zabbix > zabbix_backup.sql`
2. Exportar values atuais: `helm get values zabbix -n zabbix`
3. Criar `infra/zabbix/application.yaml`
4. Criar `infra/zabbix/kustomization.yaml`
5. Adicionar em `clusters/homelab/apps/zabbix.yaml`
6. Referenciar em `clusters/homelab/kustomization.yaml`
7. Commit + push → ArgoCD sincroniza
8. Validar Zabbix (`https://zabbix.wcrpc.lan`)

---

## Fase 3 — Kubernetes Dashboard
**Apps:** kubernetes-dashboard, dashboard-metrics-scraper
**Helm chart:** `kubernetes-dashboard/kubernetes-dashboard`
**Risco:** Baixo — stateless

### Passos
1. Exportar values atuais: `helm get values kubernetes-dashboard -n kubernetes-dashboard`
2. Criar `apps/kubernetes-dashboard/application.yaml`
3. Criar `apps/kubernetes-dashboard/kustomization.yaml`
4. Migrar IngressRoute (`dashboard.wcrpc.lan`) para o repo
5. Adicionar em `clusters/homelab/apps/kubernetes-dashboard.yaml`
6. Referenciar em `clusters/homelab/kustomization.yaml`
7. Commit + push → ArgoCD sincroniza
8. Validar Dashboard (`https://dashboard.wcrpc.lan`)

---

## Fase 4 — Limpeza e validação final
1. Verificar que todos os recursos têm label `argocd.argoproj.io/managed-by`
2. Remover recursos órfãos criados manualmente (ingresses, secrets avulsos)
3. Adicionar `ignoreDifferences` onde necessário (ex: CRDs com drift)
4. Documentar senhas/secrets sensíveis num Secret Manager ou Sealed Secrets
5. Testar `selfHeal`: deletar um pod manualmente e confirmar que o ArgoCD recria

---

## Estrutura alvo do repositório

```
K3s-CCoE/
├── apps/
│   ├── whoami/
│   ├── technitium/
│   └── kubernetes-dashboard/
├── infra/
│   ├── longhorn/
│   ├── monitoring/
│   └── zabbix/
└── clusters/
    └── homelab/
        ├── kustomization.yaml
        ├── projects/
        │   └── platform.yaml
        └── apps/
            ├── cert-manager.yaml
            ├── technitium.yaml
            ├── monitoring.yaml
            ├── zabbix.yaml
            └── kubernetes-dashboard.yaml
```

---

## Notas importantes
- **Fase 1 primeiro** — monitoring não tem dados críticos, bom para validar o processo
- **Backup antes da Fase 2** — PostgreSQL do Zabbix tem dados históricos
- Ingresses manuais criados hoje (ArgoCD, Longhorn) devem ser incluídos nos manifestos das respectivas apps durante a migração
- O `wcrpc-tls` Secret precisa ser gerenciado (Sealed Secrets ou cert-manager ClusterIssuer)
