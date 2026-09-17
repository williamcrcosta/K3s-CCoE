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
├── grafana     ← Grafana 12.3.3
├── zabbix      ← Zabbix 7.0.29
└── keycloak    ← reservado
```

---

## Melhorias Planejadas — Do Menor ao Maior Risco

### 1. Resource Limits nos Deployments — Risco Baixo

**Problema:** ~30 containers sem `limits`/`requests` definidos.

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

### 2. AlertManager — Notificações Telegram — Risco Baixo

**Problema:** alertas só visíveis no Prometheus.

**Benefício:** notificações em tempo real para alertas críticos.

**Ação:** configurar `alertmanager.config` no `kube-prometheus-stack` com Telegram.

**Impacto:** nenhum. Já está parcialmente configurado, só precisa do `bot_token` e `chat_id`.

---

### 3. Dashboard Zabbix no Grafana — Risco Baixo

**Problema:** dashboard `SRVAD2025 - Zabbix` é muito básico.

**Benefício:** melhor observabilidade da VM Windows.

**Ação:** adicionar painéis de disco, rede, serviços, triggers.

**Impacto:** nenhum.

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

### 5. Backup Externo Longhorn — Risco Médio

**Problema:** volumes Longhorn só existem no cluster.

**Benefício:** disaster recovery completo.

**Ação:** configurar `recurringJobs` para S3/NFS no Longhorn.

```yaml
# Configuração no Longhorn UI ou manifesto
recurringJobs:
  - name: backup
    task: backup
    retain: 7
```

**Impacto:** precisa de storage externo (S3, NFS, etc.).

---

### 6. TLS no PostgreSQL — Risco Médio

**Problema:** conexões entre apps e `rke2-pgdb` não cifradas.

**Benefício:** segurança das credenciais em trânsito.

**Ação:** habilitar TLS no PostgreSQL + certificados nos secrets.

**Impacto:** pode quebrar apps se mal configurado. Requer teste.

---

### 7. Atualizar kube-prometheus-stack — Risco Médio

**Versão atual:** `82.2.0`  
**Última:** `88.6.2`

**Benefício:** bugfixes, novos dashboards, Grafana 12.11.

**Ação:** atualizar `targetRevision` em `clusters/homelab/apps/monitoring.yaml`.

**Impacto:** pode quebrar configurações de dashboards ou Prometheus. Requer backup e teste.

---

### 8. Atualizar Longhorn — Risco Alto

**Versão atual:** `v1.7.2`  
**Última:** `v1.12.1`

**Benefício:** V2 Data Engine, melhorias de resiliência.

**Ação:** atualizar chart no ArgoCD.

**Impacto:** upgrade de storage é sempre arriscado. Requer backup de todos os volumes antes.

---

### 9. Atualizar ArgoCD — Risco Alto

**Versão atual:** `v3.3.1`  
**Última:** `v3.5.2`

**Benefício:** novas features, security fixes.

**Ação:** atualizar chart no ArgoCD.

**Impacto:** pode quebrar Application definitions. Requer leitura de release notes.

---

### 10. Atualizar cert-manager — Risco Alto

**Versão atual:** `v1.14.5` **EOL**  
**Última:** `v1.21.1`

**Benefício:** ACME ARI, security fixes, novas features.

**Ação:** atualizar chart + CRDs.

**Impacto:** breaking changes de RBAC e métricas. Requer atenção.

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
| 2 | AlertManager | 1h | Notificações críticas |
| 3 | Dashboard Zabbix | 30min | Melhor visibilidade |
| 4 | Backup PostgreSQL | 1h | Proteção de dados |
| 5 | Backup Longhorn | 2h | DR completo |
| 6 | TLS PostgreSQL | 1h | Segurança |
| 7 | kube-prometheus-stack | 2h | Updates + segurança |
| 8 | Longhorn | 4h | Storage moderno |
| 9 | ArgoCD | 2h | Updates + segurança |
| 10 | cert-manager | 3h | EOL resolvido |
| 11 | Multi-cluster | dias | DR real |
