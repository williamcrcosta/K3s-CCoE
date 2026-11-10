# Melhorias e Evoluções — Cluster RKE2

## Melhorias Arquiteturais Concluídas

### Centralização de Bancos de Dados — 2026-09-15/16

| App | Antes | Depois | Benefício |
|---|---|---|---|
| Grafana | SQLite em PVC Longhorn | PostgreSQL 16 em `rke2-pgdb` | Persistência fora do ciclo de vida dos pods |
| Zabbix | PostgreSQL em pod + PVC Longhorn | PostgreSQL 16 em `rke2-pgdb` | -50% memória no worker; sem dependência de PVC |

**Impacto imediato:** remoção do pod `zabbix-postgresql-0` liberou ~1Gi de memória no `rke2-worker-01` (90% → 44%).

### Estrutura atual de bancos

```text
rke2-pgdb (192.168.50.30) — PostgreSQL 16
├── grafana     ← Grafana 13.2.2
├── zabbix      ← Zabbix 7.0.32
└── keycloak    ← reservado
```

---

## Melhorias Planejadas — Do Menor ao Maior Risco

> **Versões verificadas em 2026-10-24** (análise completa do cluster). Zabbix em `7.0.32` LTS, chart `7.1.0` (ambos latest). Longhorn, cert-manager e ArgoCD atualizados. Pendente: kube-prometheus-stack `91.4.1 → 92.x`, RKE2 `v1.35 → v1.36+`.

### 1. Resource Limits nos Deployments — Risco Baixo — ⏳ Parcial

**Problema:** 65 de 75 containers sem `limits`/`requests` (2026-09-17) → **restam 12 containers sem requests/limits fora do kube-system** (2026-10-24). LimitRange em `infra/limitranges` cobriu a maioria.

**Benefício:** prevenção de OOM e CPU throttling.

**Ação:** adicionar `resources` nos Helm values de cada app.

```yaml
# Exemplo genérico
resources:
  requests:
    memory: 256Mi
    cpu: 100m
  limits:
    memory: 512Mi
    cpu: 500m
```

**Impacto:** nenhum se valores forem conservadores.

---

### 2. AlertManager — Notificações Telegram — ✅ Concluído

**Status:** implementado (2026-09). Receiver `telegram` configurado no `kube-prometheus-stack` e secret `alertmanager-telegram` criado no namespace `monitoring`.

**Pendente:** validar entrega de alertas e converter o secret em SealedSecret para GitOps completo (ver `infra/monitoring/alertmanager-telegram.md`).

---

### 3. Dashboard Zabbix no Grafana — ✅ Concluído

**Status:** implementado (2026-09). Dashboards `SRVAD2025 - Zabbix` e `Windows Server Advanced` em `infra/monitoring-dashboards/`.

---

### 4. Backup Externo do PostgreSQL — ✅ Coberto por vzdump (decisão 2026-10-24)

**Resolvido:** a VM `rke2-pgdb` já é coberta por vzdump do Proxmox — restore de VM inteira funciona (crash-consistent, PG recupera via WAL). Aceito o risco residual: sem restore cirúrgico por database — um `DROP DATABASE` acidental exigiria reverter a VM toda com até 24h de perda.

> ⚠️ **Atualização 2026-11-10:** a cobertura por vzdump depende do share CIFS `PVE-BACKUP` hospedado no **desktop Windows** (192.168.50.9), que dorme ~00:00–07:30. Falhas reais em 05–06/set/2026 (job das 18h com storage offline). Ver item 18.

**Se um dia quiser restore por-DB:** CronJob `pg_dump -Fc` por database (secrets `zabbix-db-access` / `grafana-db-credentials` já existem nos namespaces) → `hostPath /mnt/longhorn-backup` (NFS do Proxmox) no worker com `nodeSelector`, retenção ~7d.

---

### 5. Backup Externo Longhorn — ✅ Concluído (2026-09-20)

**Problema:** volumes Longhorn só existem no cluster.

**Benefício:** disaster recovery completo.

**Resolvido:** backup target NFS do Proxmox (`nfs://192.168.50.250:/var/lib/vz/longhorn-backup`) + `recurringJob daily-backup` (13h, retain 7) rodando diariamente — verificado 2026-10-24.

**Impacto:** precisa de storage externo (S3, NFS, etc.).

---

### 6. TLS no PostgreSQL — ⏸ Em standby (análise feita 2026-09-20)

**Problema:** conexões entre apps e `rke2-pgdb` (192.168.50.30) não cifradas.

**Estado atual:** `Certificate` `pgdb-tls` (`pgdb.wccosta.com.br`, issuer `letsencrypt-wccosta`) já commitado em `infra/cert-manager/certificates.yaml` — cert fica emitido no secret `cert-manager/pgdb-tls`, inerte até uso.

**Clientes a atualizar quando ativar:**
- Grafana (`clusters/homelab/apps/monitoring.yaml`): `GF_DATABASE_SSL_MODE=verify-ca` + `GF_DATABASE_CA_CERT_PATH` — `verify-ca` valida a cadeia sem checar hostname, então o host pode seguir `192.168.50.30`
- Zabbix (`clusters/homelab/apps/zabbix.yaml`): `extraEnv` no `zabbixServer` com `ZBX_DBTLSCONNECT=verify_ca`/`ZBX_DBTLSCAFILE`; web frontend com `ZBX_DB_ENCRYPTION=true` (verificar env vars exatas da imagem `zabbix-web-nginx-pgsql`)
- PG: `ssl=on` + `ssl_cert_file`/`ssl_key_file` (reload recarrega certs, sem restart); `pg_hba` mantém `host` na transição → endurecer pra `hostssl` no fim

**Questão em aberto — distribuição do cert para o pgdb (VM fora do cluster).** LE renova a cada ~60d, então precisa de automação. Opções analisadas:

| Opção | Como funciona | Observação |
|---|---|---|
| **A) Pull via API do k8s** | SA + Role (`resourceNames: [pgdb-tls]`) + timer systemd no pgdb que faz GET no apiserver, grava cert/key e `pg_reload_conf()` | Escala p/ outras VMs; sem SSH extra |
| **B) `ca-server` (container no Proxmox)** | Se for step-ca/ACME: `step ca certificate` ou certbot direto no pgdb — cert nasce no destino, renovação automática, sem cluster | **Verificar o que é o ca-server** (`step version`/`pct list` no PVE). Se for step-ca, é a melhor opção |
| **C) CA interna no cluster** | `wcrpc-ca-issuer` já existe (CA `wcrpc.lan` até 2036) — emitir cert com IP SAN `192.168.50.30`, `duration` de anos | Cópia rara pro pgdb, mas CA precisa ser montado nos clientes |

**Decisão pendente:** confirmar se `ca-server` é step-ca (opção B) — senão, opção A com cert LE já emitido.

---

### 7. Atualizar kube-prometheus-stack — ✅ Concluído (2026-09-20)

**Versão atual:** `91.4.1` (de `82.2.0`) — Grafana `13.2.2`, Prometheus `v3.14.0`, Alertmanager `v0.34.0`

**Resolvido:** salto direto habilitando `crds.upgradeJob.enabled` no chart (job PreSync aplica os CRDs do prometheus-operator antes do operator subir — resolve a classe de problema do Longhorn 1.10). O Grafana crashou por drift de schema no PG externo (criado por restore, sem sequences e com `success` bigint nas tabelas `*_migration_log`) — corrigido com DDL, ver Cenário 14 em `DISASTER_RECOVERY.md`.

---

### 8. Atualizar Longhorn — ✅ Concluído (2026-09-20)

**Versão atual:** `v1.12.1` (de `v1.7.2`)

**Resolvido:** upgrade em hops `1.7.2 → 1.8.2 → 1.9.2 → 1.10.2 → 1.11.3 → 1.12.1`. O hop 1.10 exigiu aplicar CRDs manualmente + `ignoreDifferences` em `/spec/conversion` (ver Adendo 3 do Cenário 13 em `DISASTER_RECOVERY.md`).

---

### 9. Atualizar ArgoCD — ✅ Concluído (2026-09-20)

**Versão atual:** `v3.5.3` (de `v3.3.1`)

**Resolvido:** upgrade self-managed em hops `v3.3.1 → v3.4.9 → v3.5.3` — só bump da tag do `install.yaml` remoto em `infra/argocd/kustomization.yaml`; o próprio ArgoCD aplicou seus manifests novos. Breaking changes 3.4/3.5 não se aplicam (sem cluster generators, sem OCI repos HTTP, sem impersonation). Backup do estado salvo antes em `/tmp/argocd-backup` no CP.

---

### 10. Atualizar cert-manager — ✅ Concluído (2026-09-20)

**Versão atual:** `v1.21.2` (de `v1.14.5`, que estava EOL)

**Resolvido:** upgrade em hops minor-a-minor `1.14.5 → 1.15.5 → 1.16.5 → 1.17.4 → 1.18.6 → 1.19.6 → 1.20.4 → 1.21.2` via GitOps. CRDs sobem com o chart (`installCRDs: true`). Todos os certs/issuers seguem Ready.

---

### 11. Segundo Cluster — Risco Alto

**Objetivo:** multi-cluster para DR.

**Ação:** instalar RKE2 em outra VM/Proxmox + ArgoCD multi-cluster.

**Impacto:** grande. Requer planejamento de rede, DNS, storage.

---

### 12. Zabbix 7.0.32 + fix de templates — ✅ Concluído (2026-10-24)

- **Bump `ubuntu-7.0.30 → 7.0.32`** (LTS): fixes de `history.get`, `nodata()`, crashes de managers no shutdown. DB no mesmo PG externo (`dbversion 07000000/07000030`, sem patch de schema).
- **Template `Proxmox VE by HTTP`**: `diskread/diskwrite` ausentes na API pra VM stopped → spam de "Preprocessing failed". Fix aplicado via UI: "Custom on fail → Set value to 0" no step JSONPath dos item prototypes `qemu` e `lxc` (diskread/diskwrite). Propagou pros itens descobertos em ~1 ciclo de LLD.
- **Templates `Kubernetes cluster state by HTTP`** (hosts `k8s-rke2`, `k8s-rke2-nodes`): faltava `{$KUBE.API.TOKEN}` + `{$KUBE.STATE.ENDPOINT.NAME}`. Criado SA `zabbix-monitor` (role `view` + ClusterRole p/ nodes/pv/storageclasses — versionado em `infra/zabbix/zabbix-monitor-rbac.yaml`; **secret do token é manual** — selfHeal apagaria `.data`). Macros corrigidas via DB direto (paste na UI truncou o JWT de 917 chars).
- **Pendente:** `srvawx01` (192.168.50.3) segue com o template linkado sem token — deslinkar na UI se não for monitorado como cluster próprio.

---

### 13. Disco do worker — ✅ Limpeza feita (2026-10-24), recorrente

**Problema:** `/` do worker chegou a **84%** — 31.3GB em `/var/lib/rancher/rke2/agent/containerd` (imagens não usadas).

**Resolvido:** `crictl rmi --prune` via `kubectl debug node` (SSH CP→worker está quebrado) → **43%** (~17GB liberados). SSH direto continua pendente de reparo.

**Recorrência:** imagens acumulam a cada upgrade. Kubelet faz GC só acima de ~85% do imagefs — considerar baixar `image-gc-high-threshold` ou podar periodicamente.

---

### 14. Crashloops de pods API-dependentes em reboot do CP — Risco Médio

**Problema:** a cada reboot do CP, pods que dependem do apiserver morrem com exit≠0 e acumulam restarts: kube-state-metrics (2412!), csi-provisioner (933), cert-manager-cainjector (875), kubernetes-dashboard (794) em 2026-10-24.

**Mitigação barata:** `startupProbe`/`livenessProbe` com `failureThreshold` alto + `resources` nos afetados — toleram a janela de API indisponível sem crashar.

**Causa raiz:** CP único — resolve de verdade só com 2º node de control-plane (relacionado ao item 11).

---

### 15. etcd snapshots off-site — Risco Baixo

**Problema:** snapshots automáticos (cron 12h) ficam só em `/var/lib/rancher/rke2/server/db/snapshots` no CP — se o disco do CP morrer, os snapshots morrem junto.

**Ação:** cron local de `rsync`/`cp` dos snapshots pro NFS do Proxmox, ou rotina `rke2 etcd-snapshot save` + copy.

---

### 16. Upgrades de versão pendentes — Risco Baixo/Médio

- `kube-prometheus-stack` **91.4.1 → 92.x** (latest 92.13.1 em 2026-10-24) — major de chart — **upgrade planejado p/ 2026-11-10/11**
- RKE2 **v1.35.8 → v1.36+** — 1.35 é o minor mais velho suportado (upstream em 1.37.x)
- Zabbix 8.0: ainda RC (8.0.0rc2 em 2026-10-21) — DB `zabbix` está limpo (`07000000/07000030`), apto pra major quando sair GA

---

### 17. Hygiene do repo — Risco Baixo

- `infra/zabbix/values.yaml` não entra no kustomization (valores efetivos são inline da Application) — alinhar ou remover
- Secrets Grafana duplicados: `infra/monitoring/grafana-secret.yaml` vs `infra/monitoring-secrets/` — consolidar
- `infra/sealed-secrets/application.yaml` usa repo bitnami-labs **morto** (chart pinned 2.18.5 ainda resolve) — migrar pra fonte OCI
- Tags flutuantes: `postgres:16` (cronjob nodesclean), `busybox`

---

### 18. Backups PVE dependem do desktop (CIFS) — Risco Médio

**Problema (diagnóstico 2026-11-09):** as 5 storages de backup do PVE são CIFS montadas do **desktop Windows** (192.168.50.9, share `PVE-BACKUP`, domain `X870AORUSELITE`), que dorme toda madrugada (~00:00–07:30). Efeitos observados:

- **Lacuna diária de métricas** (`proxmox-pve` + `windows-desktop` down ~00:43–07:33 UTC): desktop dorme → mounts CIFS morrem → API do PVE enforca consultando status de storages → `pve-exporter` estoura o `scrape_timeout` de 10s → dashboards Proxmox/Windows sem dados de madrugada
- **Falha de backup por storage offline**: se o desktop está off na hora do job, vzdump aborta com `storage ... is not online` (aconteceu 05 e 06/set/2026 no pfSense/VM 700)
- **Risco adicional**: desktop dormir *no meio* de um backup corrompe/aborta a escrita

**Feito (2026-11-10):**
- `repeat-missed=1` nos 5 jobs vzdump — ⚠️ **atenção à semântica**: cobre apenas "missed start" (host/pvescheduler off), **NÃO retenta** job que iniciou e falhou (nosso caso storage-offline é execução com falha)
- `qm set 501 --agent enabled=1,freeze-fs=0` — fsfreeze falhava toda noite no CSI `globalmount` do Longhorn (backup já era crash-consistent; agora sem ERROR falso no log)

**Cobertura real pendente:** WoL do pve→desktop ~17:50 (`apt install wakeonlan` + cron) garante share disponível na janela 18–21h. Alternativa de hardware: PBS em mini-PC/NAS 24/7 (mantém backup off-host — melhor que disco local no pve).

### 19. Alertas cosméticos para silenciar — Risco Baixo

Levantamento 2026-11-10 — alertas permanentes que não indicam problema real:

- `KubeProxyDown` (critical): RKE2 não expõe métricas do kube-proxy (static pod em localhost) — falso positivo permanente; dashboard `Kubernetes / Proxy` fica sempre vazio pela mesma razão
- `KubeDaemonSetMisScheduled` + `KubeDaemonSetRolloutStuck` (8x): DaemonSets não agendam no CP tainted (NoSchedule) — by design
- `NodeClockNotSynchronising` (2x): flap intermitente nos 2 nodes — offset medido 0.0s em 2026-11-10; conferir `chronyc sources` se recorrente
- Datasource **Loki removido** (2026-11-10, commits `4e793d4`/`f1be0c2`): app desativado em a3c3f72 mas datasource continuava provisionado e quebrado; `infra/monitoring-dashboards/grafana-datasource-delete-loki.yaml` (deleteDatasources) garante remoção do banco do Grafana

---

## Prioridade Recomendada

| Ordem | Item | Esforço | Benefício |
|---|---|---|---|
| 1 | Resource limits (12 restantes) | 30min | Prevenção de falhas |
| ~~2~~ | ~~AlertManager~~ ✅ | ~~1h~~ | ~~Notificações críticas~~ |
| ~~3~~ | ~~Dashboard Zabbix~~ ✅ | ~~30min~~ | ~~Melhor visibilidade~~ |
| ~~4~~ | ~~Backup PostgreSQL~~ ✅ vzdump | ~~1h~~ | ~~Proteção de dados~~ |
| ~~5~~ | ~~Backup Longhorn~~ ✅ | ~~2h~~ | ~~DR completo~~ |
| 6 | TLS PostgreSQL | 1h | Segurança |
| ~~7~~ | ~~kube-prometheus-stack~~ ✅ | ~~2h~~ | ~~Updates + segurança~~ |
| ~~8~~ | ~~Longhorn~~ ✅ | ~~4h~~ | ~~Storage moderno~~ |
| ~~9~~ | ~~ArgoCD~~ ✅ | ~~2h~~ | ~~Updates + segurança~~ |
| ~~10~~ | ~~cert-manager~~ ✅ | ~~3h~~ | ~~EOL resolvido~~ |
| 11 | Multi-cluster / 2º CP | dias | DR real |
| ~~12~~ | ~~Zabbix 7.0.32 + templates~~ ✅ | ~~1h~~ | ~~Spam zerado~~ |
| ~~13~~ | ~~Disco worker~~ ✅ | ~~30min~~ | ~~84% → 43%~~ |
| 14 | Probes p/ crashloop pós-reboot | 1h | Estabilidade |
| 15 | etcd snapshots off-site | 30min | DR do CP |
| 16 | Upgrades kube-prom 92.x + RKE2 1.36 | 3h | Suporte |
| 17 | Hygiene do repo | 1h | Manutenibilidade |
