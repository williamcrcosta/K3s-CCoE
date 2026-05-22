# K3s Homelab — Documentação de Arquitetura

> Cluster Kubernetes de alta disponibilidade para homelab, gerenciado por GitOps via ArgoCD.

---

## Topologia

```
Internet
    │
    └── Rede Local: 192.168.159.0/24
            │
            ├── k8s-cp      192.168.159.128  (Control Plane + Worker)
            │     ├── OS: Ubuntu 24.04.1 LTS
            │     ├── K3s: v1.36.0+k3s1
            │     └── Runtime: containerd 2.1.5
            │
            └── k8s-worker  192.168.159.129  (Worker)
                  ├── OS: Ubuntu 24.04.4 LTS
                  ├── K3s: v1.36.0+k3s1
                  └── Runtime: containerd 2.1.5
```

---

## Stack de Infraestrutura

| Componente | Tecnologia | Função |
|---|---|---|
| Container Orchestration | K3s v1.36 | Kubernetes leve para homelab |
| GitOps | ArgoCD | Reconciliação contínua via Git |
| Ingress Controller | Traefik (K3s built-in) | Roteamento HTTP/HTTPS |
| Storage | Longhorn | Block storage distribuído com replicação |
| DNS Interno | Technitium | Resolução DNS para `*.wcrpc.lan` |
| Certificados | cert-manager + Self-signed CA | TLS interno |
| Secrets | Sealed Secrets | Secrets cifrados no Git |

---

## Aplicações

| App | URL | Namespace | Storage |
|---|---|---|---|
| ArgoCD | https://argocd.wcrpc.lan | `platform-argocd` | — |
| Grafana | https://grafana.wcrpc.lan | `monitoring` | Longhorn 5Gi |
| Prometheus | interno | `monitoring` | Longhorn 20Gi |
| Zabbix | https://zabbix.wcrpc.lan | `zabbix` | Longhorn 10Gi (PostgreSQL) |
| Longhorn UI | https://longhorn.wcrpc.lan | `longhorn-system` | — |
| Kubernetes Dashboard | https://kubernetes-dashboard.wcrpc.lan | `kubernetes-dashboard` | — |
| Technitium DNS | https://dns.wcrpc.lan / UDP:53 | `dns` | Longhorn 2Gi |

---

## Arquitetura de Storage

```
Longhorn (distribuído entre os 2 nodes)
├── technitium-data          2Gi   (DNS config)
├── monitoring-grafana       5Gi   (Grafana DB)
├── prometheus-db            20Gi  (Prometheus TSDB)
└── postgresql-data-zabbix   10Gi  (Zabbix PostgreSQL)

Replicação: 2 réplicas por volume (k8s-cp + k8s-worker)
StorageClass default: longhorn
```

---

## Arquitetura de Rede

```
Cliente → 192.168.159.128:443 (NodePort Traefik)
        → Traefik IngressController
        → Service ClusterIP
        → Pod

DNS: *.wcrpc.lan → 192.168.159.128 (Technitium)
     Fallback: 1.1.1.1, 8.8.8.8

NodePorts expostos:
  - 30080: Traefik HTTP
  - 30443: Traefik HTTPS
  - 30053/UDP: Technitium DNS
  - 30081: Zabbix Server (active checks)
  - 30082: Zabbix Web (NodePort direto)
```

---

## Arquitetura GitOps

```
GitHub (williamcrcosta/K3s-CCoE)
    │
    └── ArgoCD (App of Apps pattern)
            │
            ├── clusters/homelab/root.yml          ← Root App
            ├── clusters/homelab/kustomization.yaml
            └── clusters/homelab/apps/
                    ├── argocd.yaml
                    ├── cert-manager.yaml
                    ├── longhorn.yaml
                    ├── monitoring.yaml
                    ├── sealed-secrets.yaml
                    ├── technitium.yaml
                    ├── zabbix.yaml
                    └── kubernetes-dashboard.yaml
```

### Fluxo de Deploy
1. Push no branch `main`
2. ArgoCD detecta mudança (polling a cada 3min ou webhook)
3. ArgoCD reconcilia o estado do cluster com o Git
4. Helm/Kustomize aplicam os manifests

---

## Estrutura do Repositório

```
K3s-CCoE/
├── README.md                        ← Este arquivo
├── MIGRATION_PLAN.md                ← Histórico de migrações
├── DISASTER_RECOVERY.md             ← Plano de recuperação
├── apps/
│   ├── technitium/                  ← Manifests Technitium DNS
│   └── kubernetes-dashboard/        ← Manifests K8s Dashboard
├── infra/
│   ├── argocd/                      ← Patches ArgoCD
│   ├── cert-manager/                ← ClusterIssuers
│   ├── longhorn/                    ← Ingress Longhorn
│   ├── monitoring/                  ← Values extras Prometheus
│   ├── sealed-secrets/              ← App Sealed Secrets
│   └── zabbix/                      ← Ingress + values Zabbix
├── clusters/
│   └── homelab/
│       ├── root.yml                 ← App of Apps entry point
│       ├── kustomization.yaml
│       ├── projects/
│       │   └── platform.yaml        ← ArgoCD Project
│       └── apps/                    ← ArgoCD Application manifests
└── secrets/                         ← Sealed Secrets (cifrados)
```

---

## Monitoração

- **Prometheus** — coleta métricas de todos os nodes e pods via kube-prometheus-stack 82.2.0
- **Grafana** — dashboards automáticos: Kubernetes, Nodes, Pods, Storage
- **Zabbix** — monitoração tradicional dos nodes (CPU, RAM, disco, rede)
  - Agent instalado em `k8s-cp` e `k8s-worker`
  - 394 hosts monitorados, 17.931 items ativos

---

## Evoluções Futuras

### Curto Prazo
- **AlertManager** — notificações via Telegram para alertas críticos
- **Backup externo Longhorn** — snapshots para S3/NFS fora do cluster
- **Grafana dashboards no Git** — persistir como ConfigMaps para não perder após recriação

### Médio Prazo
- **Resource limits** — definir `requests` e `limits` para todos os pods
- **Network Policies** — isolar namespaces (zabbix não acessa monitoring, etc.)
- **Zabbix templates K3s** — monitorar pods, PVCs e nodes via Zabbix
- **Let's Encrypt** — migrar para certificados públicos válidos com DNS challenge

### Longo Prazo
- **Segundo cluster** — expandir para multi-cluster com ArgoCD gerenciando ambos
- **Velero** — backup completo do cluster (namespaces, secrets, PVCs)
- **CI/CD pipeline** — GitHub Actions para validar manifests antes do merge

---

## Manutenção

### Health Check rápido
```bash
~/cluster-health.sh
```

### Ver status ArgoCD
```bash
kubectl get applications -n platform-argocd
```

### Ver volumes Longhorn
```bash
kubectl get volumes.longhorn.io -n longhorn-system
```

### Forçar sync de um app
```bash
kubectl annotate application <app> -n platform-argocd argocd.argoproj.io/refresh=hard --overwrite
```


---

## Troubleshooting

### ArgoCD v3.x — StatefulSet `OutOfSync` loop infinito

**Sintoma:** App ArgoCD com `OutOfSync` em loop (`autoHealAttemptsCount` crescendo continuamente) mesmo após sync bem-sucedido. Apenas StatefulSets com `volumeClaimTemplates` afetados.

**Causa:** O ArgoCD v3.0.0 tornou `serverSideDiff=true` o **default** (breaking change). Com essa configuração, o diff é calculado via SSA dry-run, que sempre retorna campos injetados pelo Kubernetes como drift — e o `ignoreDifferences` **não é honrado** nesse fluxo.

Campos injetados pelo Kubernetes que causam o drift (não presentes no Helm chart):
- `spec.persistentVolumeClaimRetentionPolicy`
- `spec.podManagementPolicy`
- `spec.revisionHistoryLimit`
- `spec.updateStrategy`

**Fix 1 — desabilitar serverSideDiff globalmente em `infra/argocd/argocd-cm-patch.yaml`:**
```yaml
data:
  server.side.diff.enabled: "false"
```

**Fix 2 — ignorar campos k8s-injected no app em `clusters/homelab/apps/zabbix.yaml`:**
```yaml
ignoreDifferences:
  - group: apps
    kind: StatefulSet
    jsonPointers:
      - /spec/persistentVolumeClaimRetentionPolicy
      - /spec/podManagementPolicy
      - /spec/revisionHistoryLimit
      - /spec/updateStrategy
    jqPathExpressions:
      - .spec.volumeClaimTemplates[]?.status
      - .spec.volumeClaimTemplates[]?.metadata.annotations
      - .spec.volumeClaimTemplates[]?.metadata.labels
      - .spec.volumeClaimTemplates[]?.spec.storageClassName
      - .spec.volumeClaimTemplates[]?.spec.volumeMode
syncPolicy:
  syncOptions:
    - RespectIgnoreDifferences=true
```

> **Nota:** A chave `controller.diff.server.side` no `argocd-cmd-params-cm` **não funciona** no ArgoCD v3.x para este propósito. O controle correto é via `server.side.diff.enabled` no `argocd-cm`.

---

## IA / LLM no Cluster

Opções para rodar modelos de IA localmente:

### 1. Ollama (recomendado para iniciar)
```yaml
# Helm chart disponível: ollama/ollama
deploy:
  image: ollama/ollama:latest
  resources:
    requests:
      memory: "4Gi"
      cpu: "2"
    limits:
      memory: "8Gi"
      cpu: "4"
  nodeSelector:
    kubernetes.io/hostname: k8s-cp  # GPU node preferencial
```
**Modelos suportados:** llama3, mistral, codellama, etc.
**Persistência:** PVC para ~/.ollama/models

### 2. LocalAI (API OpenAI-compatible)
- Drop-in replacement para API da OpenAI
- Suporta gguf, onnx, outros formatos
- Ideal para integrar com aplicativos existentes

### 3. vLLM (alta performance)
- Otimizado para throughput
- Suporta múltiplos GPUs
- Batching eficiente

### Requisitos de Hardware
| Config | Mínimo | Recomendado |
|---|---|---|
| CPU | 4 cores | 8+ cores |
| RAM | 8 GB | 16+ GB |
| GPU | Opcional | NVIDIA RTX 3060+ (12GB VRAM) |
| Storage | 20 GB | 100+ GB SSD |

### Passos para Implementar
1. **Verificar GPU:** `lspci | grep -i nvidia`
2. **Instalar NVIDIA Operator:** via Helm
3. **Deploy Ollama:** com nodeSelector para node com GPU
4. **Expor via Ingress:** ollama.wcrpc.lan
5. **Integrar com apps:** via service `ollama:11434`

