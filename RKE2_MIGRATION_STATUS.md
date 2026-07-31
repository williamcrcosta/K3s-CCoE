# Migração K3s → RKE2 — Status e Evoluções

> Documento de acompanhamento da migração real do cluster homelab, listando melhorias implementadas, inconsistências encontradas no repo e próximos passos. **Nenhum arquivo antigo foi apagado.**

---

## 1. Resumo Executivo

| Item | Valor |
|---|---|
| **Distro anterior** | K3s v1.36.0+k3s1 |
| **Distro atual** | RKE2 v1.35.6+rke2r1 |
| **Motivo da migração** | Aproximar o homelab de um ambiente corporativo real (etcd nativo, hardening, NetworkPolicy, backup etcd nativo) |
| **Estado geral** | Cluster operacional. Repo Git atualizado para refletir o RKE2; ainda há ajustes operacionais pendentes (Technitium pending, Zabbix sync status). |
| **Data do levantamento** | 2026-07-05 |
| **Última atualização** | 2026-07-05 |

---

## 2. Topologia Real do Cluster RKE2

```
Rede local: 192.168.50.0/24

├── rke2-cp-01      192.168.50.20   (Control Plane)
│     ├── OS: Rocky Linux 9.8 (Blue Onyx)
│     └── Kubelet: v1.35.6+rke2r1
│
└── rke2-worker-01  192.168.50.21   (Worker)
      ├── OS: Rocky Linux 9.8 (Blue Onyx)
      └── Kubelet: v1.35.6+rke2r1
```

> **Nota:** as VMs finais são `.20` e `.21`. O plano original `RKE2_MIGRATION.md` previa `.130`/`.131` e Ubuntu 24.04; a realidade final foi Rocky Linux 9.8 nos IPs `.20`/`.21`.

---

## 3. Comparativo K3s vs RKE2 — Melhorias Conquistadas

| Aspecto | K3s (antes) | RKE2 (atual) | Benefício |
|---|---|---|---|
| **etcd** | SQLite (default) | etcd nativo sempre | Consistência, HA, snapshots nativos |
| **CNI** | Flannel (sem NetworkPolicy) | Canal (Flannel + Calico) | NetworkPolicy suportado nativamente |
| **Ingress** | Traefik built-in automático | NGINX Ingress Controller (hardened) | Controle de versão, hardening, padrão corporativo |
| **StorageClass default** | `local-path` (conflitava com Longhorn) | Apenas `longhorn` | Sem conflitos, controle total |
| **Backup etcd** | Manual | `rke2 etcd-snapshot save` | Backup nativo, restauração simples |
| **Segurança** | Básica | CIS Benchmark, PSA, audit logs, SELinux | Ambiente hardened |
| **OS** | Ubuntu 24.04 (plano) | Rocky Linux 9.8 | Distro mais próxima de produção enterprise |
| **Upgrade** | Script manual | System Upgrade Controller (opcional) | Upgrades controlados via GitOps |

---

## 4. Stack Atual Detalhada

| Componente | Namespace | Versão/Imagem | Status no ArgoCD |
|---|---|---|---|
| **ArgoCD** | `platform-argocd` | `v3.3.1` | Synced / Healthy |
| **Longhorn** | `longhorn-system` | `v1.7.2` | Synced / Healthy |
| **Cert-manager** | `cert-manager` | `v1.14.5` | Synced / Healthy |
| **Cert-manager-config** | `cert-manager` | — | Synced / Healthy |
| **Sealed Secrets** | `kube-system` | `0.26.3` | Synced / Healthy |
| **Kubernetes Dashboard** | `kubernetes-dashboard` | latest | Synced / Healthy |
| **Monitoring** | `monitoring` | Chart `82.2.0` / Operator `v0.89.0` | Synced / Healthy |
| **Technitium DNS** | `dns` | latest | Synced / **Degraded** |
| **Zabbix** | `zabbix` | `7.0.27` | **Unknown** / Healthy |
| **root-homelab** | `platform-argocd` | — | **OutOfSync** / Healthy |

> **Atenção:** o app `root-homelab` foi redirecionado no repo para apontar para `clusters/rke2`. O status `OutOfSync` deve ser resolvido após o próximo sync do ArgoCD (ou pode exigir refresh hard).

### Ingresses expostos (NGINX)

| Aplicação | Host |
|---|---|
| ArgoCD | `argocd.wcrpc.lan` |
| Grafana | `grafana.wcrpc.lan` |
| Prometheus | `prometheus.wcrpc.lan` |
| Longhorn UI | `longhorn.wcrpc.lan` |
| Kubernetes Dashboard | `dashboard.wcrpc.lan` |
| Technitium | `technitium.wcrpc.lan` |
| Zabbix | `zabbix.wcrpc.lan` |

---

## 5. Evoluções Implementadas

### 5.1 Infraestrutura

- **etcd nativo**: substituiu o SQLite do K3s, possibilitando HA e snapshots.
- **Canal como CNI**: habilita NetworkPolicy no cluster.
- **NGINX Ingress Controller hardened**: substituiu o Traefik built-in do K3s.
- **Longhorn como única StorageClass default**: sem conflito com `local-path`.

### 5.2 Segurança

- CIS Benchmark aplicado na instalação do RKE2.
- PSA (Pod Security Admission) e audit logs ativos por padrão.
- SELinux em modo enforcing (comportamento default RKE2).

### 5.3 GitOps

- ArgoCD `v3.3.1` operacional e self-managed.
- Estrutura `clusters/rke2/` criada no repo.
- App of Apps (`root-homelab`) redirecionado para `clusters/rke2`.
- Sealed Secrets `0.26.3` mantendo secrets cifrados no Git.

### 5.4 Aplicações

- Zabbix atualizado para `7.0.27`.
- kube-prometheus-stack na versão `82.2.0`.
- Cert-manager `v1.14.5`.
- Technitium DNS migrado para o RKE2.
- Kubernetes Dashboard exposto via NGINX ingress com TLS pass-through.

### 5.5 Storage

- Volumes migrados para Longhorn (Grafana 5Gi, Prometheus 20Gi, Zabbix PostgreSQL 10Gi, Technitium 2Gi).
- StorageClasses: `longhorn` (default) e `longhorn-static`.

---

## 6. Inconsistências Corrigidas no Repo

Os itens abaixo foram identificados como inconsistentes e **já foram atualizados**:

| Arquivo | Problema | Ação realizada |
|---|---|---|
| `clusters/homelab/apps/zabbix.yaml` | Indentação incorreta em `zabbixWeb` | Corrigido YAML |
| `infra/monitoring/application.yaml` | Usava `local-path` e chart `81.5.0` | Atualizado para `longhorn` e chart `82.2.0` |
| `infra/monitoring/values.yaml` | Cabeçalho `USER-SUPPLIED VALUES:` e `local-path` | Limpado e unificado com `longhorn` |
| `infra/zabbix/values.yaml` | Usava `local-path` e `7.0.23` | Atualizado para `longhorn` e `7.0.27` |
| `apps/ollama/ingress.yaml` | Usava `ingressClassName: traefik` | Migrado para `nginx` |
| `apps/kubernetes-dashboard/ingressroute.yaml` | Nome sugeria Traefik | Criado `ingress.yaml`; arquivo antigo mantido como histórico |
| `clusters/homelab/root.yml` | Apontava para `clusters/homelab` | Redirecionado para `clusters/rke2` |
| `README.md` | Descrevia topologia K3s | Reescrito para refletir RKE2 |
| `DISASTER_RECOVERY.md` | Procedimentos K3s | Reescrito para RKE2 (Rocky Linux, rke2, etcd snapshot) |
| `RKE2_MIGRATION.md` | Plano sem status de conclusão | Adicionada nota de migração concluída |

### Estrutura de clusters

- ✅ `clusters/rke2/` criado com toda a estrutura do App of Apps.
- ✅ `clusters/homelab/` mantido como histórico do K3s.
- ✅ `root-homelab` redirecionado para gerenciar `clusters/rke2`.

---

## 7. Débitos Técnicos Pendentes

### 7.1 Apps com problemas operacionais

| App | Status | Observação |
|---|---|---|
| `technitium` | Degraded | Pod `technitium-79785dc7b-v9qd9` está `Pending`. Requer investigação de afinidade, recursos ou PVC. |
| `zabbix` | Unknown | ArgoCD não consegue determinar status de sync. Possivelmente resolvido após correção do YAML; requer refresh. |
| `root-homelab` | OutOfSync | Deve sincronizar após aplicar a mudança de path para `clusters/rke2`. |

### 7.2 Melhorias ainda não implementadas

- Backup externo Longhorn (S3/NFS).
- NetworkPolicies entre namespaces.
- Resource limits/requests para todos os workloads.
- Backup etcd agendado no CP.
- Zabbix templates para monitorar nodes/pods RKE2.
- Let's Encrypt para certificados públicos.

---

## 8. Checklist de Migração — Status Real

### Fase 1 — Infraestrutura RKE2

- [x] RKE2 server e agent rodando
- [x] Ambos nodes `Ready`
- [x] CNI Canal, NGINX ingress, Longhorn OK
- [x] IPs finais `.20`/`.21` e Rocky Linux 9.8

### Fase 2 — GitOps

- [x] ArgoCD e Sealed Secrets funcionando
- [x] Criar `clusters/rke2/` no repo
- [x] Atualizar `root-homelab` para `clusters/rke2`
- [x] Sincronizar manifests desatualizados

### Fase 3 — Dados

- [x] Volumes Longhorn operacionais
- [ ] Backup Longhorn (S3/NFS) — prioridade alta
- [ ] Validar dados históricos preservados

### Fase 4 — Cutover

- [x] DNS `*.wcrpc.lan` apontando para RKE2
- [x] Acessos via browser validados
- [ ] Desligar K3s (se ainda existir)

---

## 9. Próximos Passos Recomendados

### Imediatos

1. **Aplicar as mudanças no cluster:** fazer commit/push e sync do ArgoCD.
2. **Investigar Technitium:** `kubectl describe pod technitium-79785dc7b-v9qd9 -n dns` e `kubectl get events -n dns`.
3. **Verificar Zabbix:** forçar refresh no ArgoCD e verificar se o status muda para Synced.
4. **Confirmar root-homelab Synced:** após aplicar o novo path, forçar refresh hard.

### Curtíssimo prazo

5. Configurar backup etcd agendado no CP.
6. Definir estratégia de backup Longhorn.
7. Implementar NetworkPolicies básicas.

### Médio prazo

8. Revisar resource limits/requests.
9. Criar Zabbix templates para RKE2.
10. Avaliar Let's Encrypt.

---

## 10. Notas de Operação RKE2

| Ação | Comando RKE2 |
|---|---|
| Status CP | `systemctl status rke2-server` |
| Status Worker | `systemctl status rke2-agent` |
| Logs CP | `journalctl -u rke2-server -f` |
| kubectl | `export PATH=$PATH:/var/lib/rancher/rke2/bin` e `export KUBECONFIG=/etc/rancher/rke2/rke2.yaml` |
| Snapshot etcd | `rke2 etcd-snapshot save --name daily-$(date +%Y%m%d)` |
| Restore etcd | `rke2 etcd-snapshot restore --snapshot-name <nome>` |

---

## 11. Referências

- `RKE2_MIGRATION.md` — plano original (mantido para histórico)
- `README.md` — documentação atualizada do RKE2
- `MIGRATION_PLAN.md` — histórico de evoluções GitOps (mantido)
- `DISASTER_RECOVERY.md` — DR atualizado para RKE2

---

> Este documento **não excluiu nenhum arquivo**. Todos os arquivos antigos foram mantidos; onde necessário, foram criados novos arquivos ou atualizações focadas para refletir o RKE2.

---

## 12. Incidente 2026-07-30 — Proxmox Crash & Recovery

### O que aconteceu
- Proxmox travou e foi desligado inesperadamente
- Worker `rke2-worker-01` entrou em emergency mode por corrupção de disco (`/dev/sda`)
- Múltiplos pods em `Terminating`/`Pending`, Zabbix postgres em `ContainerCreating` há 6h

### O que foi resolvido
| Item | Status |
|---|---|
| Worker node (`rke2-worker-01`) | ✅ Recuperado via fsck + xfs_repair |
| Cluster nodes | ✅ Ambos `Ready` |
| Longhorn volumes | ✅ Remontados automaticamente |
| Todos os pods | ✅ Running/Completed |
| ArgoCD `root-homelab` | ✅ Synced + Healthy |
| ArgoCD `zabbix` | ✅ Synced + Healthy |
| Zabbix server connection | ✅ Restaurado (`ZBX_SERVER_HOST`) |

### Fixes permanentes aplicados ao Git
1. `clusters/homelab/apps/zabbix.yaml` e `clusters/rke2/apps/zabbix.yaml`:
   - Adicionado `zabbixWeb.enabled: true` (fix nil pointer no Helm template)
   - Restaurado `extraEnv` com `ZBX_SERVER_HOST` e `ZBX_SERVER_PORT`
   - Atualizado `zabbixImageTag: ubuntu-7.0.28`
   - Removido `extraEnv` duplicado (mantido apenas o necessário)

### Lições aprendidas
- **Nunca usar `kubectl replace`** em recursos gerenciados pelo ArgoCD
- O `zabbixWeb.enabled: true` é obrigatório nos Helm values
- O `extraEnv` com `ZBX_SERVER_HOST` é obrigatório para o frontend conectar ao server
- Ver `DISASTER_RECOVERY.md` cenários 6, 7 e 8 para detalhes
