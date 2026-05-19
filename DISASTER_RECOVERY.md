# Disaster Recovery — K3s Homelab

Plano completo para reconstruir o cluster do zero ou recuperar de falhas.

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

## Cenário 2 — Perda do Node Worker (k8s-worker / 192.168.159.129)

### Impacto
- Pods que estavam no worker são recriados no control plane
- Volumes Longhorn ficam `degraded` (1 réplica) mas continuam funcionando
- Cluster operacional com capacidade reduzida

### Recuperação
1. **Reinstalar Ubuntu 24.04** na VM
2. **Instalar K3s agent:**
```bash
# Obter token do control plane
cat /var/lib/rancher/k3s/server/node-token  # rodar no k8s-cp

# Instalar no novo worker (substituir TOKEN e CP_IP)
curl -sfL https://get.k3s.io | K3S_URL=https://192.168.159.128:6443 \
  K3S_TOKEN=<TOKEN> sh -
```
3. **Verificar que o node entrou no cluster:**
```bash
kubectl get nodes
```
4. **Reinstalar Zabbix Agent:**
```bash
# No novo worker
wget https://repo.zabbix.com/zabbix/7.0/ubuntu/pool/main/z/zabbix-release/zabbix-release_7.0-2+ubuntu24.04_all.deb
dpkg -i zabbix-release_7.0-2+ubuntu24.04_all.deb
apt update && apt install -y zabbix-agent2

# Configurar
cat > /etc/zabbix/zabbix_agent2.conf << 'ZCONF'
Server=192.168.159.128,192.168.159.129,10.42.0.0/16
ServerActive=192.168.159.128:30081
Hostname=k8s-worker
ZCONF

systemctl enable --now zabbix-agent2
```
5. Longhorn vai replicar os volumes automaticamente para o novo node.

---

## Cenário 3 — Perda do Node Control Plane (k8s-cp / 192.168.159.128)

> ⚠️ Este é o cenário mais crítico. O Git é a fonte da verdade — tudo é recuperável.

### Pré-requisitos para recuperação
- Acesso ao repositório Git: `https://github.com/williamcrcosta/K3s-CCoE`
- Backup do token K3s (se disponível): `/var/lib/rancher/k3s/server/node-token`
- Backup dos Sealed Secrets keys (se disponível): ver seção abaixo

### Passo a Passo — Reconstrução do Control Plane

#### 1. Preparar a VM
```bash
# Ubuntu 24.04 limpo
# Configurar IP estático: 192.168.159.128
# Hostname: k8s-cp
hostnamectl set-hostname k8s-cp
```

#### 2. Instalar K3s
```bash
curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION="v1.34.3+k3s1" sh -s - \
  --disable traefik \
  --write-kubeconfig-mode 644

# Aguardar node ficar Ready
kubectl get nodes
```

> **Nota:** O Traefik é desabilitado no install pois é gerenciado pelo ArgoCD.
> Se quiser Traefik gerenciado pelo K3s (mais simples), remova `--disable traefik`.

#### 3. Instalar ArgoCD
```bash
kubectl create namespace platform-argocd
kubectl apply -n platform-argocd \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Aguardar pods ficarem Running
kubectl wait --for=condition=available deployment/argocd-server \
  -n platform-argocd --timeout=120s
```

#### 4. Aplicar Root App (App of Apps)
```bash
kubectl apply -f https://raw.githubusercontent.com/williamcrcosta/K3s-CCoE/main/clusters/homelab/root.yml
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
kubectl rollout restart deployment/sealed-secrets -n kube-system
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
# No worker — obter novo token do cp
ssh k8s-cp "cat /var/lib/rancher/k3s/server/node-token"

# Atualizar config do agent no worker
# Editar /etc/systemd/system/k3s-agent.service.env com novo token se necessário
systemctl restart k3s-agent
```

---

## Cenário 4 — Reconstrução Completa do Zero (ambos os nodes)

Seguir o **Cenário 3** para o control plane, depois o **Cenário 2** para o worker.

### Ordem de instalação
1. k8s-cp — Ubuntu + K3s server
2. k8s-worker — Ubuntu + K3s agent
3. ArgoCD no k8s-cp
4. Root App → tudo sobe automaticamente

---

## Backups Importantes

### Onde estão os backups
```
/home/william/zabbix_final_backup_<DATA>.sql   ← Dados do Zabbix
/home/william/grafana_backup_<DATA>.tar.gz     ← Dados do Grafana
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

