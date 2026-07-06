# RKE2 Homelab — Documentação de Arquitetura

> Cluster Kubernetes hardened para homelab, gerenciado por GitOps via ArgoCD. Migrado de K3s para RKE2 para simular um ambiente corporativo real.

---

## Topologia

```
Internet
    │
    └── Rede Local: 192.168.50.0/24
            │
            ├── rke2-cp-01      192.168.50.20  (Control Plane)
            │     ├── OS: Rocky Linux 9.8 (Blue Onyx)
            │     ├── RKE2: v1.35.6+rke2r1
            │     └── Runtime: containerd
            │
            └── rke2-worker-01  192.168.50.21  (Worker)
                  ├── OS: Rocky Linux 9.8 (Blue Onyx)
                  ├── RKE2: v1.35.6+rke2r1
                  └── Runtime: containerd
```

> **Histórico:** este cluster foi migrado de K3s (Ubuntu 24.04, IPs `192.168.159.128/129`) para RKE2. Ver `RKE2_MIGRATION.md` (plano) e `RKE2_MIGRATION_STATUS.md` (status real).

---

## Stack de Infraestrutura

| Componente | Tecnologia | Função |
|---|---|---|
| Container Orchestration | RKE2 v1.35.6+rke2r1 | Kubernetes hardened para homelab/enterprise |
| CNI | Canal (Flannel + Calico) | Rede com suporte nativo a NetworkPolicy |
| GitOps | ArgoCD v3.3.1 | Reconciliação contínua via Git |
| Ingress Controller | NGINX Ingress Controller (RKE2 hardened) | Roteamento HTTP/HTTPS |
| Storage | Longhorn v1.7.2 | Block storage distribuído com replicação |
| DNS Interno | Technitium | Resolução DNS para `*.wcrpc.lan` |
| Certificados | cert-manager v1.14.5 + Self-signed CA | TLS interno |
| Secrets | Sealed Secrets v0.26.3 | Secrets cifrados no Git |

---

## Aplicações

| App | URL | Namespace | Storage |
|---|---|---|---|
| ArgoCD | https://argocd.wcrpc.lan | `platform-argocd` | — |
| Grafana | https://grafana.wcrpc.lan | `monitoring` | Longhorn 5Gi |
| Prometheus | https://prometheus.wcrpc.lan | `monitoring` | Longhorn 20Gi |
| Zabbix | https://zabbix.wcrpc.lan | `zabbix` | Longhorn 10Gi (PostgreSQL) |
| Longhorn UI | https://longhorn.wcrpc.lan | `longhorn-system` | — |
| Kubernetes Dashboard | https://dashboard.wcrpc.lan | `kubernetes-dashboard` | — |
| Technitium DNS | https://technitium.wcrpc.lan / UDP:53 | `dns` | Longhorn 2Gi |
| Ollama / Open WebUI | https://ai.wcrpc.lan | `ollama` | Longhorn 20Gi+ |

---

## Arquitetura de Storage

```
Longhorn (distribuído entre os 2 nodes)
├── technitium-data          2Gi   (DNS config)
├── monitoring-grafana       5Gi   (Grafana DB)
├── prometheus-db            20Gi  (Prometheus TSDB)
├── postgresql-data-zabbix   10Gi  (Zabbix PostgreSQL)
├── ollama-models            20Gi  (Modelos Ollama)
└── ollama-webui-data         5Gi  (Open WebUI)

Replicação: 2 réplicas por volume (rke2-cp-01 + rke2-worker-01)
StorageClass default: longhorn
```

---

## Arquitetura de Rede

```
Cliente → 192.168.50.20:443 (NodePort NGINX / LoadBalancer)
        → NGINX Ingress Controller (RKE2 hardened)
        → Service ClusterIP
        → Pod

DNS: *.wcrpc.lan → 192.168.50.20 (Technitium)
     Fallback: 1.1.1.1, 8.8.8.8

NodePorts expostos:
  - 80/443: NGINX HTTP/HTTPS
  - 30053/UDP: Technitium DNS
  - 30081: Zabbix Server (active checks)
  - 30082: Zabbix Web (NodePort direto)
```

> **Histórico:** no K3s o ingress era Traefik (NodePorts 30080/30443). No RKE2 usamos NGINX Ingress Controller hardened.

---

## Arquitetura GitOps

```
GitHub (williamcrcosta/K3s-CCoE)
    │
    └── ArgoCD (App of Apps pattern)
            │
            ├── clusters/rke2/root.yml          ← Root App (RKE2)
            ├── clusters/rke2/kustomization.yaml
            └── clusters/rke2/apps/
                    ├── argocd.yaml
                    ├── cert-manager.yaml
                    ├── longhorn.yaml
                    ├── monitoring.yaml
                    ├── sealed-secrets.yaml
                    ├── technitium.yaml
                    ├── zabbix.yaml
                    ├── kubernetes-dashboard.yaml
                    └── ollama.yaml
```

> **Nota:** o app `root-homelab` existente no cluster foi redirecionado para `clusters/rke2`. A pasta `clusters/homelab/` permanece como histórico do K3s.

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
├── MIGRATION_PLAN.md                ← Histórico de migrações GitOps
├── RKE2_MIGRATION.md                ← Plano original de migração K3s → RKE2
├── RKE2_MIGRATION_STATUS.md         ← Status real da migração
├── DISASTER_RECOVERY.md             ← Plano de recuperação (RKE2)
├── apps/
│   ├── kubernetes-dashboard/        ← Manifests K8s Dashboard
│   ├── ollama/                      ← Manifests Ollama + Open WebUI
│   └── technitium/                  ← Manifests Technitium DNS
├── infra/
│   ├── argocd/                      ← Patches ArgoCD
│   ├── cert-manager/                ← ClusterIssuers
│   ├── longhorn/                    ← App Longhorn + ingress
│   ├── monitoring/                  ← App kube-prometheus-stack
│   ├── sealed-secrets/              ← App Sealed Secrets
│   └── zabbix/                      ← Ingress + values Zabbix
├── clusters/
│   ├── homelab/                     ← K3s histórico (não usado ativamente)
│   └── rke2/                        ← RKE2 ativo
│       ├── root.yml
│       ├── kustomization.yaml
│       ├── projects/
│       │   └── platform.yaml
│       └── apps/
└── secrets/                         ← Sealed Secrets (cifrados)
```

---

## Monitoração

- **Prometheus** — coleta métricas de todos os nodes e pods via kube-prometheus-stack 82.2.0
- **Grafana** — dashboards automáticos: Kubernetes, Nodes, Pods, Storage
- **Zabbix** — monitoração tradicional dos nodes (CPU, RAM, disco, rede)
  - Agent instalado em `rke2-cp-01` e `rke2-worker-01`
  - 394+ hosts monitorados, 17.000+ items ativos

---

## Evoluções Futuras

### Curto Prazo
- **AlertManager** — notificações via Telegram para alertas críticos
- **Backup externo Longhorn** — snapshots para S3/NFS fora do cluster
- **Grafana dashboards no Git** — persistir como ConfigMaps para não perder após recriação

### Médio Prazo
- **Resource limits** — definir `requests` e `limits` para todos os pods
- **Network Policies** — isolar namespaces (zabbix, monitoring, dns, etc.)
- **Zabbix templates RKE2** — monitorar pods, PVCs e nodes via Zabbix
- **Let's Encrypt** — migrar para certificados públicos válidos com DNS challenge

### Longo Prazo
- **Segundo cluster** — expandir para multi-cluster com ArgoCD gerenciando ambos
- **Velero** — backup completo do cluster (namespaces, secrets, PVCs)
- **CI/CD pipeline** — GitHub Actions para validar manifests antes do merge

---

## Manutenção

### Configurar kubectl no RKE2

```bash
export PATH=$PATH:/var/lib/rancher/rke2/bin
export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
```

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

### Snapshot etcd
```bash
rke2 etcd-snapshot save --name "manual-$(date +%Y%m%d-%H%M%S)"
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

**Fix 2 — ignorar campos k8s-injected no app em `clusters/rke2/apps/zabbix.yaml`:**
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

### Root cause definitivo — `managedFields` com ownership do argocd-controller

Se o loop persistir mesmo com `ignoreDifferences` correto, o problema pode estar no `managedFields` do StatefulSet.
O ArgoCD não ignora diferenças de campos que ele mesmo **possui ownership** via Server-Side Apply.

**Diagnóstico:**
```bash
kubectl get statefulset zabbix-postgresql -n zabbix --show-managed-fields -o json | \
  python3 -c "
import json,sys
d=json.load(sys.stdin)
for mf in d['metadata']['managedFields']:
    spec = mf.get('fieldsV1',{}).get('f:spec',{})
    print(f'manager={mf.get('manager')} op={mf.get('operation')} spec={[k[2:] for k in spec.keys()]}')
"
```

Se `manager=argocd-controller op=Apply` aparecer com campos como `persistentVolumeClaimRetentionPolicy`, `podManagementPolicy`, etc., o `ignoreDifferences` será ignorado.

**Solução — recriar o StatefulSet sem perda de dados:**
```bash
# 1. Pausar selfHeal
kubectl patch application zabbix -n platform-argocd --type=merge \
  -p '{"spec":{"syncPolicy":{"automated":{"selfHeal":false}}}}'

# 2. Deletar StatefulSet preservando pod e PVC
kubectl delete statefulset zabbix-postgresql -n zabbix --cascade=orphan

# 3. Reativar selfHeal — ArgoCD recria o StatefulSet limpo
kubectl patch application zabbix -n platform-argocd --type=merge \
  -p '{"spec":{"syncPolicy":{"automated":{"selfHeal":true}}}}'
kubectl annotate application zabbix -n platform-argocd argocd.argoproj.io/refresh=hard --overwrite
```

> O pod e o PVC (`postgresql-data-zabbix-postgresql-0`) são preservados. Sem perda de dados.

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
    kubernetes.io/hostname: rke2-worker-01  # GPU node preferencial
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
4. **Expor via Ingress:** ai.wcrpc.lan
5. **Integrar com apps:** via service `ollama:11434`
