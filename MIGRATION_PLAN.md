# Plano de Migração — GitOps com ArgoCD

## Objetivo
Migrar todos os recursos do cluster para serem gerenciados pelo ArgoCD via GitOps,
eliminando recursos aplicados manualmente (`kubectl apply`).

## Status: ✅ CONCLUÍDO

---

## Resultado Final

| App | Namespace | Gerenciado pelo ArgoCD | Ingress no Git |
|---|---|---|---|
| ArgoCD | `platform-argocd` | ✅ self-managed | ✅ `infra/argocd/ingress.yaml` |
| Longhorn | `longhorn-system` | ✅ | ✅ `infra/longhorn/ingress.yaml` |
| Cert Manager | `cert-manager` | ✅ | — |
| Technitium DNS | `dns` | ✅ | ✅ `apps/technitium/ingress.yaml` |
| Monitoring (Grafana + Prometheus) | `monitoring` | ✅ | ✅ helm values |
| Zabbix | `zabbix` | ✅ | ✅ helm values |
| Kubernetes Dashboard | `kubernetes-dashboard` | ✅ | ✅ `apps/kubernetes-dashboard/ingressroute.yaml` |

---

## Melhorias Pendentes

| Item | Prioridade | Status |
|---|---|---|
| Sealed Secrets (senhas/TLS no Git) | Alta | 🔄 Em progresso |
| Technitium zona DNS no Git (Job) | Média | 🔄 Em progresso |
| ArgoCD `--insecure` flag no Git | Média | 🔄 Em progresso |

---

## Estrutura do Repositório

```
K3s-CCoE/
├── apps/
│   ├── technitium/
│   └── kubernetes-dashboard/
├── infra/
│   ├── argocd/
│   ├── longhorn/
│   ├── monitoring/
│   └── zabbix/
└── clusters/
    └── homelab/
        ├── kustomization.yaml
        ├── projects/
        │   └── platform.yaml
        └── apps/
            ├── argocd.yaml
            ├── cert-manager.yaml
            ├── monitoring.yaml
            ├── zabbix.yaml
            ├── technitium.yaml
            └── kubernetes-dashboard.yaml
```
