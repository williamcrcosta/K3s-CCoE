# Migração K3s → RKE2

> Plano de migração do cluster homelab K3s para RKE2, mantendo o cluster atual em paralelo durante a transição (zero downtime).

---

## Por que migrar?

O K3s foi escolhido pela simplicidade para iniciar o homelab. O RKE2 é o próximo passo natural para simular um ambiente de produção corporativo real.

### Comparativo K3s vs RKE2

| | K3s | RKE2 |
|---|---|---|
| **Foco** | Edge / IoT / homelab | Produção corporativa |
| **Binário** | Single binary (~70MB) | Componentes separados |
| **etcd** | SQLite (default) | etcd nativo sempre |
| **CIS Benchmark** | Não por padrão | Aplicado no install |
| **FIPS 140-2** | Não | Suportado |
| **NetworkPolicy** | Flannel não suporta | Canal/Calico nativo |
| **Ingress built-in** | Traefik automático | Nenhum (instala via Helm) |
| **StorageClass default** | local-path (conflita com Longhorn) | Nenhuma (controle total) |
| **Backup etcd** | Manual | `rke2 etcd-snapshot` nativo |
| **Upgrades** | Script manual | System Upgrade Controller |
| **Segurança default** | Mínima | Hardened (PSA, Audit log, SELinux) |
| **RAM mínima CP** | 512 MB | 2 GB (recomendado 4 GB) |
| **RAM mínima Worker** | 256 MB | 2 GB (recomendado 4+ GB) |

---

## Problemas do K3s resolvidos pelo RKE2

| Problema | RKE2 resolve? | Detalhe |
|---|---|---|
| 2 StorageClasses default conflitando | Sim | RKE2 não instala local-path |
| Traefik automático sem controle de versão | Sim | Instala via Helm com controle total |
| Sem suporte a NetworkPolicy (Flannel) | Sim | Canal/Calico nativo |
| Backup etcd manual e trabalhoso | Sim | `rke2 etcd-snapshot` nativo |
| Upgrades de cluster arriscados | Sim | System Upgrade Controller GitOps |
| Segurança fraca por padrão | Sim | CIS Benchmark, PSA, Audit log |
| ArgoCD StatefulSet OutOfSync loop | Não | Problema do ArgoCD v3, não da distro |
| Sealed Secrets chave presa no cluster | Parcial | Mesmo processo, mas etcd snapshot facilita |

---

## Arquitetura do novo cluster

### Topologia

```
VMware ESXi (rede local 192.168.159.0/24)
    |
    ├── rke2-cp      192.168.159.130   Control Plane
    |     ├── OS: Ubuntu 24.04 LTS
    |     ├── vCPU: 4
    |     ├── RAM: 8 GB
    |     └── Disco: 50 GB (OS + etcd)
    |
    └── rke2-worker  192.168.159.131   Worker
          ├── OS: Ubuntu 24.04 LTS
          ├── vCPU: 4
          ├── RAM: 12 GB
          ├── Disco OS: 50 GB
          └── Disco dados: 100 GB (Longhorn)
```

### Stack planejada

| Componente | Tecnologia | Obs |
|---|---|---|
| Distro | RKE2 latest stable | |
| CNI | Canal (Flannel + Calico) | default RKE2 |
| Ingress | Traefik v3 via Helm | igual ao K3s atual |
| Storage | Longhorn | via Helm, disco extra no worker |
| GitOps | ArgoCD | mesmo repo Git |
| Secrets | Sealed Secrets | importar chave do K3s |
| Certs | cert-manager + CA self-signed | mesmo setup |
| DNS | Technitium | migrar após cutover |
| Monitoring | kube-prometheus-stack | mesmo chart |

---

## Pré-requisitos

### Antes de criar as VMs
- [ ] Confirmar IPs disponíveis: `192.168.159.130` e `192.168.159.131`
- [ ] Reservar IPs no Technitium ou configurar estático nas VMs
- [ ] Garantir disco extra de 100 GB no worker para Longhorn

### Nas VMs (pós-instalação Ubuntu 24.04)
- [ ] SSH configurado do host de gestão para as novas VMs
- [ ] Acesso ao repo Git `williamcrcosta/K3s-CCoE`
- [ ] `ufw` desabilitado ou regras configuradas
- [ ] `swap` desabilitado (`swapoff -a` + remover do `/etc/fstab`)
- [ ] Horário sincronizado (`timedatectl set-ntp true`)

---

## Fase 1 — Provisionamento e instalação do RKE2

### 1.1 Preparar as VMs (executar em ambas)

```bash
# Desabilitar swap
swapoff -a
sed -i '/swap/d' /etc/fstab

# Sincronizar horário
timedatectl set-ntp true

# Atualizar sistema
apt-get update && apt-get upgrade -y

# Instalar dependências (Longhorn requer open-iscsi)
apt-get install -y curl wget open-iscsi nfs-common
systemctl enable iscsid --now
```

### 1.2 Instalar RKE2 no Control Plane (rke2-cp)

```bash
# Criar config
mkdir -p /etc/rancher/rke2
cat > /etc/rancher/rke2/config.yaml << EOF
node-name: rke2-cp
cni: canal
tls-san:
  - 192.168.159.130
  - rke2-cp
  - rke2-cp.wcrpc.lan
disable:
  - rke2-ingress-nginx
cluster-cidr: 10.42.0.0/16
service-cidr: 10.43.0.0/16
EOF

# Instalar e iniciar
curl -sfL https://get.rke2.io | sh -
systemctl enable rke2-server --now

# Acompanhar inicialização (~2-3 min)
journalctl -u rke2-server -f
```

### 1.3 Configurar kubectl no Control Plane

```bash
export PATH=$PATH:/var/lib/rancher/rke2/bin
export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
echo 'export PATH=$PATH:/var/lib/rancher/rke2/bin' >> ~/.bashrc
echo 'export KUBECONFIG=/etc/rancher/rke2/rke2.yaml' >> ~/.bashrc

kubectl get nodes
```

### 1.4 Obter token para o Worker

```bash
# No rke2-cp:
cat /var/lib/rancher/rke2/server/node-token
```

### 1.5 Instalar RKE2 no Worker (rke2-worker)

```bash
mkdir -p /etc/rancher/rke2
cat > /etc/rancher/rke2/config.yaml << EOF
server: https://192.168.159.130:9345
token: <TOKEN_DO_PASSO_ANTERIOR>
node-name: rke2-worker
node-label:
  - "node.longhorn.io/create-default-disk=true"
EOF

curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE="agent" sh -
systemctl enable rke2-agent --now

# Verificar no CP
kubectl get nodes
```

### 1.6 Validar cluster

```bash
kubectl get nodes -o wide
kubectl get pods -A
kubectl get pods -n kube-system | grep canal
```

---

## Fase 2 — Bootstrap GitOps

### 2.1 Exportar chave do Sealed Secrets (K3s — fazer ANTES)

```bash
# No cluster K3s atual (k8s-cp):
kubectl get secret -n kube-system \
  -l sealedsecrets.bitnami.com/sealed-secrets-key \
  -o yaml > ~/sealed-secrets-master-key-backup.yaml

# GUARDAR EM LOCAL SEGURO FORA DO CLUSTER
# NAO commitar no Git
```

### 2.2 Instalar ArgoCD no RKE2

```bash
kubectl create namespace platform-argocd
kubectl apply -n platform-argocd \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.3.1/manifests/install.yaml
kubectl rollout status deployment/argocd-server -n platform-argocd --timeout=120s
kubectl -n platform-argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d
```

### 2.3 Estrutura do repo Git para multi-cluster

```
clusters/
├── homelab/          <- K3s atual (não mexer)
│   ├── root.yml
│   ├── kustomization.yaml
│   └── apps/
└── rke2/             <- Novo cluster RKE2
    ├── root.yml
    ├── kustomization.yaml
    └── apps/
```

### 2.4 Importar chave Sealed Secrets no RKE2

```bash
kubectl apply -f ~/sealed-secrets-master-key-backup.yaml
kubectl rollout restart deployment/sealed-secrets-controller -n kube-system
```

---

## Fase 3 — Migração de dados (Longhorn)

### Volumes a migrar

| Namespace | PVC | Tamanho | App |
|---|---|---|---|
| zabbix | postgresql-data-zabbix-postgresql-0 | 10 Gi | Zabbix PostgreSQL |
| monitoring | monitoring-grafana | 5 Gi | Grafana |
| monitoring | prometheus-*-db | 20 Gi | Prometheus |
| ollama | ollama-models | 20 Gi | Ollama |
| ollama | ollama-webui-data | 5 Gi | Open WebUI |
| dns | technitium-data | 2 Gi | Technitium DNS |

**Total: ~62 Gi**

### Estratégia de migração

```
Opção A — Backup/Restore via Longhorn (recomendado)
  1. Configurar S3 ou NFS como backup target no K3s Longhorn
  2. Criar snapshot + backup de cada volume
  3. No RKE2 Longhorn, restaurar os backups
  Pros: Sem downtime prolongado
  Contras: Requer storage externo (S3/NFS)

Opção B — Dump/Restore por aplicação
  1. pg_dump do PostgreSQL (Zabbix)
  2. Copiar dados Grafana/Prometheus (ou aceitar perda de histórico)
  3. Copiar modelos Ollama via rsync
  Pros: Simples, sem infraestrutura extra
  Contras: Downtime necessário por app
```

---

## Fase 4 — Cutover

```bash
# 1. Validar todas as apps no RKE2
kubectl get applications -n platform-argocd

# 2. Atualizar Technitium DNS
# *.wcrpc.lan: 192.168.159.128 (K3s) -> 192.168.159.130 (RKE2)

# 3. Validar acesso
curl -k https://argocd.wcrpc.lan
curl -k https://zabbix.wcrpc.lan
curl -k https://grafana.wcrpc.lan

# 4. Monitorar 24-48h antes de desligar K3s

# 5. Desligar K3s
# No k8s-cp:   /usr/local/bin/k3s-uninstall.sh
# No k8s-worker: /usr/local/bin/k3s-agent-uninstall.sh
```

---

## Diferenças operacionais K3s vs RKE2

| Ação | K3s | RKE2 |
|---|---|---|
| Status do serviço | `systemctl status k3s` | `systemctl status rke2-server` |
| Logs | `journalctl -u k3s` | `journalctl -u rke2-server` |
| kubeconfig | `/etc/rancher/k3s/k3s.yaml` | `/etc/rancher/rke2/rke2.yaml` |
| kubectl | no PATH automaticamente | `/var/lib/rancher/rke2/bin/kubectl` |
| Snapshot etcd | Manual | `rke2 etcd-snapshot save` |
| Restore etcd | Manual | `rke2 etcd-snapshot restore` |

### Backup etcd agendado

```bash
# Crontab no rke2-cp — snapshot diário às 02:00
0 2 * * * /usr/local/bin/rke2 etcd-snapshot save \
  --name "daily-$(date +\%Y\%m\%d)" \
  --dir /var/lib/rancher/rke2/server/db/snapshots
```

---

## Checklist

### Fase 1 — Infra
- [ ] VMs criadas no VMware com especificações corretas
- [ ] Ubuntu 24.04 instalado em ambas
- [ ] RKE2 server rodando no CP
- [ ] RKE2 agent rodando no Worker
- [ ] `kubectl get nodes` mostra ambos Ready

### Fase 2 — GitOps
- [ ] Chave Sealed Secrets exportada e guardada em segurança
- [ ] Estrutura `clusters/rke2/` criada no repo
- [ ] ArgoCD instalado no RKE2
- [ ] Apps stateless sincronizadas (cert-manager, Sealed Secrets, Dashboard)
- [ ] Traefik instalado e funcional
- [ ] TLS funcionando (wcrpc-tls secrets)

### Fase 3 — Dados
- [ ] Longhorn instalado no RKE2
- [ ] Backup strategy definida
- [ ] PostgreSQL Zabbix migrado e validado
- [ ] Grafana migrado
- [ ] Prometheus migrado
- [ ] Ollama modelos migrados

### Fase 4 — Cutover
- [ ] Todas as apps Synced Healthy no RKE2
- [ ] DNS atualizado para IPs do RKE2
- [ ] Acesso validado via browser para todas as URLs
- [ ] Zabbix agents apontando para novo IP
- [ ] K3s desligado após 48h de estabilidade

---

## Notas importantes

> **Sealed Secrets:** A chave mestra não pode ser perdida. Sem ela, nenhum SealedSecret existente pode ser decriptado. Guardar o backup em local seguro fora do cluster.

> **ArgoCD v3 StatefulSet OutOfSync:** Vai acontecer igualmente no RKE2. Aplicar as mesmas configurações do README (server.side.diff.enabled: "false", ignoreDifferences, RespectIgnoreDifferences=true, deletar StatefulSet com --cascade=orphan se necessário).

> **NetworkPolicy:** O RKE2 com Canal suporta NetworkPolicy nativamente. Considerar adicionar políticas de isolamento entre namespaces após a migração estabilizar.

> **2 StorageClasses default:** Não instalar local-path no RKE2. Usar apenas Longhorn como StorageClass default.
