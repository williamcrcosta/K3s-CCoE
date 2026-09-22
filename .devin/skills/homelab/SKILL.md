---
name: homelab
description: Contexto completo do homelab RKE2 — topologia, storage Longhorn, apps GitOps, bancos, procedimentos operacionais e regras de seguranca
---

# Homelab RKE2 — Contexto do Ambiente

Use este contexto para qualquer tarefa neste repo (`/root/K3s-CCoE`) ou no cluster. Repo = fonte GitOps; **sempre valide o estado real do cluster antes de agir** — docs podem estar desatualizados.

## Topologia

| Componente | Hostname | IP | Papel | Notas |
|---|---|---|---|---|
| Control plane | `rke2-cp-01` | 192.168.50.20 | etcd + apiserver + scheduler | VMID Proxmox 500, ~6Gi RAM, disco 50G (apertado) |
| Worker | `rke2-worker-01` | 192.168.50.21 | workloads | VMID 501, disco SO 50G + **disco dedicado Longhorn 100G (sdb, UUID `d74be7e2-b99e-4899-a2a8-ea5cc040eab9`)** |
| PostgreSQL | `rke2-pgdb` | 192.168.50.30 | PG 16 compartilhado | sem SSH a partir do CP — usuario executa SQL manualmente |
| Proxmox host | `pve` | 192.168.50.250 | hypervisor + NFS backup | exporta `/var/lib/vz/longhorn-backup` via NFS |

Versões atuais: RKE2 `v1.35.8+rke2r1`, Rocky Linux 9.8, kernel `5.14.0-687.49.1.el9_8`.

## Acesso ao cluster

```bash
export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
K=/var/lib/rancher/rke2/bin/kubectl    # kubectl fica neste path no CP
```

Execuções nesta sessão rodam **no CP** (root). Worker acessível via `ssh root@192.168.50.21`.

## GitOps (ArgoCD)

- ArgoCD no namespace `platform-argocd` (`kubectl get applications -n platform-argocd`)
- Root app: `root-homelab` → path `clusters/homelab` (o path `clusters/rke2` foi **removido** — é histórico)
- Estrutura: `clusters/homelab/apps/*.yaml` = Applications; `infra/<app>/` = manifests/values; `clusters/homelab/kustomization.yaml` registra tudo
- Valide local antes de push: `kubectl kustomize clusters/homelab`

### Apps

| App | Namespace | Versão | Notas |
|---|---|---|---|
| kube-prometheus-stack | `monitoring` | chart 91.4.1 | Grafana 13.2.2, Prometheus v3.14.0; `crds.upgradeJob.enabled`; Prometheus PVC Longhorn 20Gi; Grafana usa PG externo |
| Longhorn | `longhorn-system` | 1.12.1 | ver seção Storage |
| cert-manager | `cert-manager` | v1.21.2 | — |
| Zabbix 7 (prod) | `zabbix` | chart 7.1.0, img ubuntu-7.0.x | NodePort **30082**, ingress `zabbix.wccosta.com.br`, PG externo |
| sealed-secrets | `kube-system` | — | SealedSecrets para credenciais (kubeseal local) |
| kubernetes-dashboard | `kubernetes-dashboard` | — | |
| Loki | `monitoring` | chart 7.3.0 (Loki 3.6.12) | SingleBinary, storage filesystem PVC Longhorn 20Gi, retention 30d; push/query via `loki-gateway.monitoring.svc` |
| Alloy | `monitoring` | chart 1.12.1 | DaemonSet nos 2 nodes, coleta logs de pods → Loki; datasource Loki já no Grafana |

Apps com manifests prontos mas **desativados** (comentados em `clusters/homelab/kustomization.yaml`): `ollama` (ns `ollama`), `powerdns` + `technitium` (ns `dns`) — sources em `apps/` na raiz do repo. `clusters/homelab/apps/observability.yaml` e `clusters/homelab/apps/longhorn.yaml` são arquivos vazios (Longhorn é deployado via `infra/longhorn` no kustomization, não via Application).

## Storage — Longhorn

- `default-data-path`: `/var/lib/longhorn` → **no worker isto é o disco sdb de 100G montado via fstab por UUID + `nofail`** (nunca usar `/dev/sdX` — ver Cenário 13 do DISASTER_RECOVERY.md)
- **CP tem scheduling DESATIVADO** (`allowScheduling=false`): disco de 50G não comporta réplica de 20Gi + reserva (settings: `storage-minimal-available-percentage=25`, `storage-reserved=30`, `over-provisioning=100`)
- Consequência: **as 2 réplicas do Prometheus ficam no worker = redundância falsa** (mesmo node). Reboot do worker = volume faulted, dados preservados no disco, recupera sozinho
- Volume Prometheus: `pvc-6d11925f-557e-4b09-9e06-579cc8f0c173`
- NFS `/mnt/longhorn-backup` (do Proxmox) existe no fstab do worker com `nofail,_netdev`

## Bancos (rke2-pgdb, PG 16)

- Databases: `grafana`, `zabbix`, `keycloak` (reservado); `zabbix8` removido (PoC desfeito 2026-09-20 — DB e pg_hba já limpos)
- DB `grafana` tinha drift de schema (criado por restore externo): sequences e tipos de `*_migration_log` corrigidos no upgrade p/ Grafana 13.2.2 — ver Cenário 14 do `DISASTER_RECOVERY.md` antes de futuros upgrades major
- `pg_hba.conf`: regras por user/db `host <db> <user> 192.168.50.0/24 scram-sha-256` — **novo user precisa de linha nova + `SELECT pg_reload_conf()`**
- Criação padrão: `CREATE USER x WITH PASSWORD '...'; CREATE DATABASE x OWNER x;` + linha pg_hba
- Credenciais vão pro cluster via **SealedSecret** (`kubeseal`), nunca plaintext no repo

## DNS / acesso externo

- Domínio `wccosta.com.br` — rewrites manuais no AdGuard (novo host precisa de registro lá)
- NodePorts ativos: 30082 (zabbix7)
- TLS via cert-manager (`wccosta-tls`/`wcrpc-tls`)

## Regras de segurança / operação

1. **Nunca** commitar secrets em plaintext — só SealedSecret
2. Antes de update de OS/RKE2: vzdump ou snapshot Proxmox + `rke2 etcd-snapshot save --name <nome>`
3. **Nunca rebootar node com volume Longhorn rebuildando** — esperar `robustness=healthy`
4. Drain no CP é inviável: ~1.8Gi livres vs ~2.4Gi de pods do worker (OOM certo); reboot direto é o procedimento aceito
5. PDBs do Longhorn travam drain normal — `--disable-eviction` se necessário
6. fstab de discos de dados: sempre `UUID=` + `nofail`; NFS: `nofail,_netdev`
7. Reboot do CP derruba Zabbix server (roda no CP) + API do cluster; apps do worker sobrevivem
8. PoC zabbix8 removido — imagem `ubuntu-trunk` quebrou por drift de DB version (07050175 vs required 07050094)

## Verificação rápida

```bash
kubectl get nodes                                          # Ready + versão
kubectl get pods -A | grep -v "Running\|Completed"         # deve ser vazio
kubectl get applications -n platform-argocd                # tudo Synced/Healthy
kubectl get volumes.longhorn.io -n longhorn-system         # attached/healthy
kubectl get replicas.longhorn.io -n longhorn-system -o wide
kubectl get nodes.longhorn.io -n longhorn-system -o yaml   # scheduling/disks
```

## Pendências conhecidas (roadmap em IMPROVEMENTS.md)

- 65/75 containers sem resource limits
- Upgrades de plataforma concluídos 2026-09-20: Longhorn 1.12.1, cert-manager 1.21.2, kube-prometheus-stack 91.4.1, ArgoCD v3.5.3 (self-managed via `infra/argocd/kustomization.yaml` — upgrade = bump da tag do install.yaml remoto)
- TLS no PG: em standby — `Certificate pgdb-tls` já emitido via LE; pendente decidir distribuição pro pgdb (ver item 6 do IMPROVEMENTS.md: pull via API k8s vs ca-server/step-ca no Proxmox)
- Tags flutuantes (`latest`, `main`) em algumas images
- `infra/sealed-secrets/application.yaml` aponta pra repo Helm morto

## Docs do repo

- `IMPROVEMENTS.md` — roadmap de melhorias
- `DISASTER_RECOVERY.md` — cenários de DR numerados (Cenário 13 = incidente fstab/emergency mode)
- `RKE2_MIGRATION_STATUS.md` — histórico da migração + incidentes
- `README.md` — inventário de apps/acessos
