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
├── zabbix      ← Zabbix 7.0.30
└── keycloak    ← reservado
```

---

## Melhorias Planejadas — Do Menor ao Maior Risco

> **Versões verificadas em 2026-09-20.** Zabbix no último patch LTS (`7.0.30`, chart `7.1.0`); Longhorn, cert-manager, kube-prometheus-stack e ArgoCD atualizados.

### 1. Resource Limits nos Deployments — Risco Baixo

**Problema:** 65 de 75 containers sem `limits`/`requests` definidos (verificado 2026-09-17).

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

### 4. Backup Externo do PostgreSQL — Risco Médio

**Problema:** banco só existe na VM `rke2-pgdb`. Sem backup off-site.

**Benefício:** recuperação em caso de falha da VM.

**Ação:** cronjob `pg_dump` + `scp` para NFS/S3, ou CronJob no cluster.

```yaml
# CronJob de exemplo
apiVersion: batch/v1
kind: CronJob
metadata:
  name: postgres-backup
spec:
  schedule: "0 3 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: pgdump
            image: postgres:16
            command: ["pg_dump", "-h", "192.168.50.30", "-U", "backup", "-Fc", "grafana", "-f", "/backup/grafana.dump"]
```

**Impacto:** precisa de credencial e destino de backup.

---

### 5. Backup Externo Longhorn — ✅ Concluído (2026-09-20)

**Problema:** volumes Longhorn só existem no cluster.

**Benefício:** disaster recovery completo.

**Resolvido:** backup target configurado para NFS do Proxmox (`nfs://192.168.50.250:/var/lib/vz/longhorn-backup`). Backup `prometheus-pre-upgrade-172` concluído. Próximo passo opcional: `recurringJobs` automáticos.

```yaml
# Configuração no Longhorn UI ou manifesto
recurringJobs:
  - name: backup
    task: backup
    retain: 7
```

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

## Prioridade Recomendada

| Ordem | Item | Esforço | Benefício |
|---|---|---|---|
| 1 | Resource limits | 30min | Prevenção de falhas |
| ~~2~~ | ~~AlertManager~~ ✅ | ~~1h~~ | ~~Notificações críticas~~ |
| ~~3~~ | ~~Dashboard Zabbix~~ ✅ | ~~30min~~ | ~~Melhor visibilidade~~ |
| 4 | Backup PostgreSQL | 1h | Proteção de dados |
| ~~5~~ | ~~Backup Longhorn~~ ✅ | ~~2h~~ | ~~DR completo~~ |
| 6 | TLS PostgreSQL | 1h | Segurança |
| ~~7~~ | ~~kube-prometheus-stack~~ ✅ | ~~2h~~ | ~~Updates + segurança~~ |
| ~~8~~ | ~~Longhorn~~ ✅ | ~~4h~~ | ~~Storage moderno~~ |
| ~~9~~ | ~~ArgoCD~~ ✅ | ~~2h~~ | ~~Updates + segurança~~ |
| ~~10~~ | ~~cert-manager~~ ✅ | ~~3h~~ | ~~EOL resolvido~~ |
| 11 | Multi-cluster | dias | DR real |
