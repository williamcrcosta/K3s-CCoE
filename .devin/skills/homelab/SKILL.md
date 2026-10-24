---
name: homelab
description: Contexto completo do homelab RKE2 — topologia, storage Longhorn, apps GitOps, bancos, procedimentos operacionais e regras de seguranca
---

# Homelab RKE2 — Contexto do Ambiente

Use este contexto para qualquer tarefa neste repo (`/root/K3s-CCoE`) ou no cluster. Repo = fonte GitOps; **sempre valide o estado real do cluster antes de agir** — docs podem estar desatualizados.

## Topologia

| Componente | Hostname | IP | Papel | Notas |
|---|---|---|---|---|
| Control plane | `rke2-cp-01` | 192.168.50.20 | etcd + apiserver + scheduler | VMID Proxmox 500, ~8.5Gi RAM, disco 50G (~69% usado) |
| Worker | `rke2-worker-01` | 192.168.50.21 | workloads | VMID 501, disco SO 50G (**~84% usado — vigiar**) + **disco dedicado Longhorn 100G (sdb, UUID `d74be7e2-b99e-4899-a2a8-ea5cc040eab9`)** |
| PostgreSQL | `rke2-pgdb` | 192.168.50.30 | PG 16 compartilhado | sem SSH a partir do CP — SQL via pod efêmero `postgres:16` no ns do app (ver seção Bancos) |
| Proxmox host | `pve` | 192.168.50.250 | hypervisor + NFS backup | PVE **9.2.20**; exporta `/var/lib/vz/longhorn-backup` via NFS |

Versões atuais: RKE2 `v1.35.8+rke2r1`, Rocky Linux 9.8, kernel `5.14.0-687.49.1.el9_8`.

## Acesso ao cluster

```bash
export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
K=/var/lib/rancher/rke2/bin/kubectl    # kubectl fica neste path no CP
```

Execuções nesta sessão rodam **no CP** (root). ~~Worker acessível via `ssh root@192.168.50.21`~~ — **SSH CP→worker quebrado (publickey denied, 2026-10-24)** — pendente reparo.

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
| Zabbix 7 (prod) | `zabbix` | chart 7.1.0, img ubuntu-7.0.32 | NodePort **30082**, ingress `zabbix.wccosta.com.br`, PG externo; dbversion `07000000/07000030` |
| sealed-secrets | `kube-system` | chart 2.18.5 | SealedSecrets para credenciais (kubeseal local); repo bitnami-labs **morto** |
| kubernetes-dashboard | `kubernetes-dashboard` | — | |

Apps com manifests prontos mas **desativados** (comentados em `clusters/homelab/kustomization.yaml`): `ollama` (ns `ollama`), `powerdns` + `technitium` (ns `dns`), `observability`, **`loki` + `alloy`** (desativados 2026-09 em `a3c3f72` — "não utilizados"; manifests e datasource no Grafana continuam no repo) — sources em `apps/` na raiz do repo. `clusters/homelab/apps/observability.yaml` e `clusters/homelab/apps/longhorn.yaml` são arquivos vazios (Longhorn é deployado via `infra/longhorn` no kustomization, não via Application).

## Storage — Longhorn

- `default-data-path`: `/var/lib/longhorn` → **no worker isto é o disco sdb de 100G montado via fstab por UUID + `nofail`** (nunca usar `/dev/sdX` — ver Cenário 13 do DISASTER_RECOVERY.md)
- **CP tem scheduling DESATIVADO** (`allowScheduling=false`): disco de 50G não comporta réplica de 20Gi + reserva (settings: `storage-minimal-available-percentage=25`, `storage-reserved=30`, `over-provisioning=100`)
- Consequência: **as 2 réplicas do Prometheus ficam no worker = redundância falsa** (mesmo node). Reboot do worker = volume faulted, dados preservados no disco, recupera sozinho
- Volume Prometheus: `pvc-484de07c-bcfe-48a0-9ddd-c215e43592e1` (20Gi, único volume Longhorn — PVC antigo `pvc-6d11925f` não existe mais)
- **Backup funciona**: backup-target = NFS `nfs://192.168.50.250:/var/lib/vz/longhorn-backup`; `recurringJob daily-backup` (13h, retain 7) completando diariamente
- NFS `/mnt/longhorn-backup` (do Proxmox) existe no fstab do worker com `nofail,_netdev`

## Bancos (rke2-pgdb, PG 16)

- Sem SSH do CP pro pgdb — consulte via pod efêmero com credencial do secret do app:
  `kubectl run -n zabbix tmp-psql --rm -i --image=postgres:16 --restart=Never --env="PGPASSWORD=$(kubectl get secret -n zabbix zabbix-db-access -o jsonpath='{.data.password}' | base64 -d)" -- psql -h 192.168.50.30 -U zabbix -d zabbix -c "SQL"`
- Databases: `grafana`, `zabbix`, `keycloak` (reservado); `zabbix8` removido (PoC desfeito 2026-09-20 — DB e pg_hba já limpos)
- DB `zabbix`: dbversion `07000000/07000030` (limpo, sem drift — apto p/ upgrade major futuro)
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
7. Reboot do CP derruba a API do cluster; apps no worker sobrevivem **mas pods API-dependentes crashloopem** (kube-state-metrics, csi-provisioner, cainjector, dashboard acumulam restarts a cada reboot — exit≠0 ao perder contato com apiserver). Zabbix roda no worker, não no CP
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

- Resource limits: restam 12 containers sem requests/limits (fora kube-system) — LimitRange mitigou os 65/75 originais
- **PG sem backup** (item 4 IMPROVEMENTS aberto) — grafana/zabbix só existem no pgdb
- **etcd snapshots só no disco do CP** (cron 12h ok) — sem cópia off-site; se disco do CP morrer, snapshots morrem junto
- Template `Proxmox VE by HTTP` (host `pve`): `diskread/diskwrite` ausentes na API pra VM stopped → spam de erro; fix = "Custom on fail" nos item prototypes
- Template `Kubernetes cluster state by HTTP` (hosts `k8s-rke2`, `k8s-rke2-nodes`, `srvawx01`): falta macro `{$KUBE.API.TOKEN}` → erros `api_token`
- Upgrade pendente: kube-prometheus-stack 91.4.1 → 92.x; RKE2 v1.35 (minor mais velho suportado) → v1.36/37
- Upgrades de plataforma concluídos 2026-09-20: Longhorn 1.12.1, cert-manager 1.21.2, kube-prometheus-stack 91.4.1, ArgoCD v3.5.3 (self-managed via `infra/argocd/kustomization.yaml` — upgrade = bump da tag do install.yaml remoto); Zabbix → 7.0.32 em 2026-10-24
- TLS no PG: em standby — `Certificate pgdb-tls` já emitido via LE; pendente decidir distribuição pro pgdb (ver item 6 do IMPROVEMENTS.md: pull via API k8s vs ca-server/step-ca no Proxmox)
- Tags flutuantes menores: `postgres:16` (cronjob nodesclean), `busybox`
- `infra/sealed-secrets/application.yaml` aponta pra repo Helm morto; `infra/zabbix/values.yaml` não entra no kustomization (valores efetivos são inline da Application); secrets Grafana duplicados em `infra/monitoring/` e `infra/monitoring-secrets/`

## Docs do repo

- `IMPROVEMENTS.md` — roadmap de melhorias
- `DISASTER_RECOVERY.md` — cenários de DR numerados (Cenário 13 = incidente fstab/emergency mode)
- `RKE2_MIGRATION_STATUS.md` — histórico da migração + incidentes
- `README.md` — inventário de apps/acessos
