# Disaster Recovery — RKE2 Homelab

Plano completo para reconstruir o cluster RKE2 do zero ou recuperar de falhas.

> **Histórico:** este DR foi atualizado para refletir a migração K3s → RKE2. O DR antigo do K3s permanece no histórico do Git (`git log`).

---

## Cenários

| Cenário | Tempo Estimado | Dificuldade |
|---|---|---|
| Pod/Deployment com problema | < 5 min | Baixa |
| Node reiniciado | < 10 min | Baixa |
| PVC corrompido | 15–30 min | Média |
| Perda do node worker | 20–40 min | Média |
| Perda do node control plane | 1–2h | Alta |
| Reconstrução completa do zero | 2–4h | Alta |

---

## Configuração base do kubectl

Em qualquer node RKE2:

```bash
export PATH=$PATH:/var/lib/rancher/rke2/bin
export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
```

> Adicionar ao `~/.bashrc` para persistir.

---

## Cenário 1 — Node Reiniciado (mais comum)

Após ligar as VMs, o cluster sobe automaticamente. Aguarde ~3 minutos e verifique:

```bash
~/cluster-health.sh
```

Se algum app estiver `Degraded`, force o sync:

```bash
kubectl annotate application <app> -n platform-argocd argocd.argoproj.io/refresh=hard --overwrite
```

Se o Longhorn tiver volumes `degraded` (normal após reboot, aguarda réplicas):

```bash
kubectl get volumes.longhorn.io -n longhorn-system
# Aguarda todos ficarem "healthy" — pode levar 5-10 minutos
```

---

## Cenário 2 — Perda do Node Worker (rke2-worker-01 / 192.168.50.21)

### Impacto

- Pods que estavam no worker são recriados no control plane
- Volumes Longhorn ficam `degraded` (1 réplica) mas continuam funcionando
- Cluster operacional com capacidade reduzida

### Recuperação

1. **Reinstalar Rocky Linux 9.8** na VM
2. **Preparar a VM:**

```bash
# Desabilitar swap
swapoff -a
sed -i '/swap/d' /etc/fstab

# Instalar dependências (Longhorn requer iscsi)
dnf install -y curl wget iscsi-initiator-utils nfs-utils
systemctl enable iscsid --now

# Configurar hostname
hostnamectl set-hostname rke2-worker-01
```

3. **Obter token do control plane:**

```bash
cat /var/lib/rancher/rke2/server/node-token  # rodar no rke2-cp-01
```

4. **Instalar RKE2 agent no novo worker:**

```bash
mkdir -p /etc/rancher/rke2
cat > /etc/rancher/rke2/config.yaml << 'RKE2CONF'
server: https://192.168.50.20:9345
token: <TOKEN_DO_PASSO_ANTERIOR>
node-name: rke2-worker-01
node-label:
  - "node.longhorn.io/create-default-disk=true"
RKE2CONF

curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE="agent" sh -
systemctl enable rke2-agent --now
```

5. **Verificar que o node entrou no cluster:**

```bash
kubectl get nodes
```

6. **Reinstalar Zabbix Agent:**

```bash
# No novo worker (Rocky Linux 9 / RHEL 9)
rpm -Uvh https://repo.zabbix.com/zabbix/7.0/rhel/9/x86_64/zabbix-release-7.0-2.el9.noarch.rpm
dnf install -y zabbix-agent2

# Configurar
cat > /etc/zabbix/zabbix_agent2.conf << 'ZCONF'
Server=192.168.50.20,192.168.50.21,10.42.0.0/16
ServerActive=192.168.50.20:30081
Hostname=rke2-worker-01
ZCONF

systemctl enable --now zabbix-agent2
```

7. Longhorn vai replicar os volumes automaticamente para o novo node.

---

## Cenário 3 — Perda do Node Control Plane (rke2-cp-01 / 192.168.50.20)

> ⚠️ Este é o cenário mais crítico. O Git é a fonte da verdade — tudo é recuperável.

### Pré-requisitos para recuperação

- Acesso ao repositório Git: `https://github.com/williamcrcosta/K3s-CCoE`
- Backup do token RKE2 (se disponível): `/var/lib/rancher/rke2/server/node-token`
- Backup dos Sealed Secrets keys (se disponível): ver seção abaixo

### Passo a Passo — Reconstrução do Control Plane

#### 1. Preparar a VM

```bash
# Rocky Linux 9.8 limpo
# Configurar IP estático: 192.168.50.20
# Hostname: rke2-cp-01
hostnamectl set-hostname rke2-cp-01

# Desabilitar swap
swapoff -a
sed -i '/swap/d' /etc/fstab

# Instalar dependências
dnf install -y curl wget iscsi-initiator-utils nfs-utils
systemctl enable iscsid --now
```

#### 2. Instalar RKE2

```bash
mkdir -p /etc/rancher/rke2
cat > /etc/rancher/rke2/config.yaml << 'RKE2CONF'
node-name: rke2-cp-01
cni: canal
tls-san:
  - 192.168.50.20
  - rke2-cp-01
  - rke2-cp-01.wcrpc.lan
disable:
  - rke2-ingress-nginx
cluster-cidr: 10.42.0.0/16
service-cidr: 10.43.0.0/16
RKE2CONF

curl -sfL https://get.rke2.io | sh -
systemctl enable rke2-server --now

# Aguardar node ficar Ready
export PATH=$PATH:/var/lib/rancher/rke2/bin
export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
kubectl get nodes
```

> **Nota:** O NGINX Ingress Controller é desabilitado no install pois é gerenciado pelo RKE2 built-in. Não precisa desabilitar no RKE2; o control plane já vem com ele. Se quiser desabilitar, mantenha a linha `disable: rke2-ingress-nginx` e instale via Helm.

#### 3. Instalar ArgoCD

```bash
kubectl create namespace platform-argocd
kubectl apply -n platform-argocd \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.3.1/manifests/install.yaml

# Aguardar pods ficarem Running
kubectl wait --for=condition=available deployment/argocd-server \
  -n platform-argocd --timeout=120s
```

#### 4. Aplicar Root App (App of Apps)

```bash
kubectl apply -f https://raw.githubusercontent.com/williamcrcosta/K3s-CCoE/main/clusters/rke2/root.yml
```

O ArgoCD vai:
- Criar todos os namespaces
- Instalar Longhorn, cert-manager, Sealed Secrets
- Instalar Technitium, Monitoring, Zabbix, K8s Dashboard
- Aplicar todos os ingresses e configurações

#### 5. Aguardar sincronização

```bash
# Acompanhar progresso (pode levar 10-20 minutos)
kubectl get applications -n platform-argocd -w
```

#### 6. Restaurar Sealed Secrets Keys (se perdeu o control plane)

> Se não tiver backup das keys, os Sealed Secrets existentes **não funcionarão**.
> Será necessário recriar os secrets e resselar.

```bash
# Se tiver backup das keys:
kubectl apply -f sealed-secrets-keys-backup.yaml

# Restartar o controller para carregar as novas keys
kubectl rollout restart deployment/sealed-secrets-controller -n kube-system
```

#### 7. Restaurar dados do Zabbix (se necessário)

```bash
# Copiar backup para o pod
kubectl cp /home/william/zabbix_final_backup_<DATA>.sql \
  zabbix/zabbix-postgresql-0:/tmp/restore.sql

# Dropar schema e restaurar
kubectl exec -n zabbix zabbix-postgresql-0 -- \
  psql -U zabbix -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

kubectl exec -n zabbix zabbix-postgresql-0 -- \
  psql -U zabbix -d zabbix -f /tmp/restore.sql

# Scale up dos serviços
kubectl scale deployment zabbix-zabbix-server zabbix-zabbix-web -n zabbix --replicas=1
```

#### 8. Reconectar worker ao novo control plane

```bash
# No rke2-cp-01 — obter token
ssh rke2-cp-01 "cat /var/lib/rancher/rke2/server/node-token"

# No rke2-worker-01 — atualizar config e reiniciar agent
# Editar /etc/rancher/rke2/config.yaml com novo token se necessário
systemctl restart rke2-agent
```

---

## Cenário 4 — Reconstrução Completa do Zero (ambos os nodes)

Seguir o **Cenário 3** para o control plane, depois o **Cenário 2** para o worker.

### Ordem de instalação

1. rke2-cp-01 — Rocky Linux 9.8 + RKE2 server
2. rke2-worker-01 — Rocky Linux 9.8 + RKE2 agent
3. ArgoCD no rke2-cp-01
4. Root App → tudo sobe automaticamente

---

## Cenário 5 — Restore de etcd (RKE2)

Se o control plane falhar por corrupção de etcd, use o snapshot nativo do RKE2:

```bash
# Listar snapshots disponíveis
rke2 etcd-snapshot ls

# Restaurar a partir de um snapshot (precisa parar o rke2-server)
systemctl stop rke2-server
rke2 etcd-snapshot restore --snapshot-name <NOME_DO_SNAPSHOT>

# Reiniciar o serviço
systemctl start rke2-server
```

> ⚠️ O restore de etcd deve ser feito com cuidado. Sempre testar em ambiente não produtivo primeiro.

### Backup etcd agendado

```bash
# Crontab no rke2-cp-01 — snapshot diário às 02:00
0 2 * * * /usr/local/bin/rke2 etcd-snapshot save \
  --name "daily-$(date +\%Y\%m\%d)" \
  --dir /var/lib/rancher/rke2/server/db/snapshots
```

---

## Backups Importantes

### Onde estão os backups

```
/home/william/zabbix_final_backup_<DATA>.sql   ← Dados do Zabbix
/home/william/grafana_backup_<DATA>.tar.gz     ← Dados do Grafana
/var/lib/rancher/rke2/server/db/snapshots/    ← Snapshots etcd (RKE2)
```

### Fazer backup manual do Zabbix

```bash
kubectl exec -n zabbix zabbix-postgresql-0 -- \
  pg_dump -U zabbix zabbix > /home/william/zabbix_backup_$(date +%Y%m%d_%H%M%S).sql
```

### Fazer backup manual do Grafana

```bash
kubectl exec -n monitoring deployment/monitoring-grafana -c grafana -- \
  tar czf - /var/lib/grafana > /home/william/grafana_backup_$(date +%Y%m%d_%H%M%S).tar.gz
```

### Backup manual do etcd

```bash
rke2 etcd-snapshot save --name "manual-$(date +%Y%m%d_%H%M%S)"
```

### Chaves do Sealed Secrets (CRÍTICO — guardar em local seguro)

```bash
# Exportar chaves
kubectl get secret -n kube-system \
  -l sealedsecrets.bitnami.com/sealed-secrets-key \
  -o yaml > sealed-secrets-keys-backup.yaml

# ⚠️ NUNCA commitar esse arquivo no Git
# Guardar em cofre de senhas ou storage externo seguro
```

---

## Referências Rápidas

### Comandos úteis pós-reboot

```bash
# Status geral
~/cluster-health.sh

# Forçar sync de todos os apps
for app in $(kubectl get applications -n platform-argocd -o name); do
  kubectl annotate $app -n platform-argocd argocd.argoproj.io/refresh=hard --overwrite
done

# Ver eventos recentes com problema
kubectl get events -A --sort-by='.lastTimestamp' | grep -i "warning\|error" | tail -20
```

### Longhorn — comandos úteis

```bash
# Ver estado dos volumes
kubectl get volumes.longhorn.io -n longhorn-system

# Ver espaço disponível por node
kubectl get nodes.longhorn.io -n longhorn-system

# Acesso à UI
https://longhorn.wcrpc.lan
```

### RKE2 — comandos úteis

```bash
# Status do serviço CP
systemctl status rke2-server

# Status do serviço Worker
systemctl status rke2-agent

# Logs CP
journalctl -u rke2-server -f

# Snapshot etcd
rke2 etcd-snapshot save --name "manual-$(date +%Y%m%d-%H%M%S)"

# Listar snapshots
rke2 etcd-snapshot ls
```
