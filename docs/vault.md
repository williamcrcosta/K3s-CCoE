# HashiCorp Vault — bootstrap e operação

Deploy via GitOps: `clusters/homelab/apps/vault.yaml` (chart hashicorp/vault 0.34.1,
Vault CE — licença BUSL, gratuita p/ uso interno) + `infra/vault/` (ingress da UI).
Modo **standalone com storage Raft** em PVC Longhorn 10Gi (`data-vault-0`).
Sem HA — 1 réplica no worker (CP não agenda).

Consumo de secrets pelos apps: **External Secrets Operator**
(`clusters/homelab/apps/external-secrets.yaml`), que sincroniza segredos do Vault
para `Secret` nativos — apps continuam funcionando quando o Vault está sealed.

## Pré-requisito — DNS

Adicionar rewrite no AdGuard (`ADGUARD_DNS.md`):

| Domain | IP |
|---|---|
| `vault.wccosta.com.br` | 192.168.50.20 |

O cert `wccosta-tls` (ns `vault`) é emitido por DNS-01/Azure — sem exposição pública.

## 1. Inicialização (uma vez só)

Após o sync, `vault-0` sobe mas fica `0/1` (not ready) — esperado, Vault nasce sealed.

```bash
export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
K=/var/lib/rancher/rke2/bin/kubectl

$K exec -n vault vault-0 -- vault operator init \
  -key-shares=5 -key-threshold=3 -format=json > /root/vault-init.json
```

**Guardar `vault-init.json` FORA do cluster** (keepass/cofre + cópia fora do CP —
o disco do CP já é ponto único de falha dos etcd snapshots). Contém as 5 unseal
keys e o root token. Apagar do CP depois de respaldado.

## 2. Unseal

A cada restart do pod o Vault volta a sealed. Opções:

**Via UI:** https://vault.wccosta.com.br — a tela de unseal aceita as keys.

**Via CLI** (3 das 5 keys):

```bash
for i in 1 2 3; do
  $K exec -n vault vault-0 -- vault operator unseal "$(jq -r .unseal_keys_b64[$i] /root/vault-init.json)"
done
$K exec -n vault vault-0 -- vault status   # Sealed: false
```

## 3. Configuração inicial

**Estado atual (2026-11-17):** auth `userpass` habilitado com user `admin`
(policy `admin` = `path "*"` com todas as caps). **Root token já revogado** —
o `vault-init.json` serve só pras unseal keys. Para executar os comandos
abaixo, gere um token do admin (login na UI → user menu → Copy token, ou
`vault login -method=userpass username=admin`).

Quando for migrar secrets (ainda não feito):

```bash
TOK=<token-admin>
$K exec -n vault vault-0 -- env VAULT_TOKEN=$TOK vault secrets enable -path=secret kv-v2
$K exec -n vault vault-0 -- env VAULT_TOKEN=$TOK vault auth enable kubernetes

$K exec -n vault vault-0 -- env VAULT_TOKEN=$TOK vault write auth/kubernetes/config \
  kubernetes_host="https://kubernetes.default.svc:443"
```

Policy + role pro ESO (leitura em `secret/data/*`):

```bash
$K exec -n vault vault-0 -- env VAULT_TOKEN=$TOK sh -c 'vault policy write eso - <<EOF
path "secret/data/*" { capabilities = ["read"] }
EOF'

$K exec -n vault vault-0 -- env VAULT_TOKEN=$TOK vault write auth/kubernetes/role/eso \
  bound_service_account_names=external-secrets \
  bound_service_account_namespaces=external-secrets \
  policies=eso ttl=24h
```

## 4. ESO — ClusterSecretStore + exemplo

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: vault-backend
spec:
  provider:
    vault:
      server: "http://vault.vault.svc:8200"   # Vault interno é HTTP (tls_disable); TLS termina no nginx
      path: secret
      version: v2
      auth:
        kubernetes:
          mountPath: kubernetes
          role: eso
          serviceAccountRef:
            name: external-secrets
            namespaces: ["external-secrets"]
---
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: exemplo
  namespace: app-ns
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: exemplo-secret
  data:
    - secretKey: password
      remoteRef:
        key: app/exemplo
        property: password
```

## Operação / gotchas

- **Reboot do worker ou restart do pod = Vault sealed** → unseal manual (UI ou CLI).
  Secrets já sincronizados pelo ESO continuam válidos; `ExternalSecret` novos/
  refresh falham enquanto sealed.
- **Raft está no PVC Longhorn** → coberto pelo `recurringJob daily-backup` (NFS
  do Proxmox). Restore de DR = restaurar o volume + unseal com as mesmas keys.
- `vault-0` fica `0/1 Running` enquanto sealed — probes do chart dependem de
  unseal. Não é crash.
- O ingress embutido do chart está **desabilitado de propósito**: ele aponta pro
  `vault-active` (só pod unsealed recebe tráfego). O nosso `infra/vault/ingress.yaml`
  aponta pro `vault-ui` (`publishNotReadyAddresses`) — permite unseal via browser.
- Injector do Vault (`vault-agent-injector`) está **desabilitado** — escolhemos
  ESO por ser mais GitOps-friendly. Reativar = `injector.enabled: true` nos values.
- Audit log: `vault audit enable file file_path=stdout` se quiser trilha de
  auditoria (vai pros logs do pod / Loki quando reativado).

## Próximos passos naturais

- Migrar credenciais dos SealedSecrets para `secret/data/*` (postgres grafana/
  zabbix, telegram token) e trocar por ExternalSecrets.
- Secrets engine `database` no rke2-pgdb → credenciais dinâmicas com TTL/rotate
  (elimina senha estática do grafana/zabbix).
- PKI engine como CA interna alternativa/complementar ao cert-manager.
- `telemetry` + ServiceMonitor pro Prometheus.
