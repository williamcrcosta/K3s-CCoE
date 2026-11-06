---
name: wccosta-cert
description: Documentacao e operacao do certificado Let's Encrypt wccosta.com.br (SAN, Azure DNS)
argument-hint: "[acao]"
allowed-tools:
  - read
  - grep
  - glob
  - exec
triggers:
  - user
---

Voce e um assistente de infraestrutura. O usuario mantem um certificado SAN Let's Encrypt chamado `san-wccosta-fullchain` para o dominio publico `wccosta.com.br`, usado em servicos internos.

## Contexto do certificado

- Dominio base: `wccosta.com.br`
- Emissor: Let's Encrypt (ECDSA)
- Metodo de validacao: DNS-01 via Azure DNS
- Tipo: SAN (sem wildcard)
- Validade: aproximadamente 90 dias, renovacao automatica
- Arquivos no `ca-server` (CT 101):
  - `/etc/letsencrypt/live/san-wccosta-fullchain/fullchain.pem`
  - `/etc/letsencrypt/live/san-wccosta-fullchain/privkey.pem`

## Dominios SAN cobertos

- `cameras.wccosta.com.br` -> 192.168.50.151 (Caddy/SRS)
- `proxmox.wccosta.com.br` -> 192.168.50.250 (Proxmox VE)
- `adguard.wccosta.com.br` -> 192.168.50.25 (AdGuard Home)
- `dashboard.wccosta.com.br` -> 192.168.50.20 (Kubernetes Dashboard)
- `longhorn.wccosta.com.br` -> 192.168.50.20 (Longhorn UI)
- `grafana.wccosta.com.br` -> 192.168.50.20 (Grafana)
- `prometheus.wccosta.com.br` -> 192.168.50.20 (Prometheus)
- `argocd.wccosta.com.br` -> 192.168.50.20 (ArgoCD)
- `zabbix.wccosta.com.br` -> 192.168.50.20 (Zabbix)
- `pfsense-fw01.wccosta.com.br` -> IP do pfSense

## Operacao no RKE2 (cert-manager)

O RKE2 usa `cert-manager` com `ClusterIssuer letsencrypt-wccosta` para emissao automatica.

### Verificar certificados

```bash
export PATH="$PATH:/var/lib/rancher/rke2/bin"
export KUBECONFIG=/etc/rancher/rke2/rke2.yaml

kubectl get certificate -A
kubectl get certificaterequest -A
kubectl describe certificate wccosta-tls -n <NAMESPACE>
```

### Forcar refresh do ArgoCD

```bash
kubectl -n platform-argocd annotate app <NOME_DO_APP> argocd.argoproj.io/refresh=hard --overwrite
```

## Operacao externa (CT 101)

O certificado SAN manual e emitido com `certbot` no container `ca-server` (CT 101).

### Renovar manualmente

```bash
/opt/certbot/bin/certbot certonly \
  --authenticator dns-azure \
  --dns-azure-config /etc/letsencrypt/azure.ini \
  --cert-name san-wccosta-fullchain \
  -d cameras.wccosta.com.br \
  -d adguard.wccosta.com.br \
  -d dashboard.wccosta.com.br \
  -d grafana.wccosta.com.br \
  -d longhorn.wccosta.com.br \
  -d pfsense-fw01.wccosta.com.br \
  -d prometheus.wccosta.com.br \
  -d argocd.wccosta.com.br \
  -d proxmox.wccosta.com.br \
  -d zabbix.wccosta.com.br \
  --agree-tos -n
```

> Ao adicionar um novo dominio, inclua todos os dominios existentes novamente.

### Copiar certificado para servicos externos

```bash
pct exec 101 -- cat /etc/letsencrypt/live/san-wccosta-fullchain/fullchain.pem > /tmp/wccosta-fullchain.pem
pct exec 101 -- cat /etc/letsencrypt/live/san-wccosta-fullchain/privkey.pem > /tmp/wccosta-privkey.pem
```

Depois copie para o destino (Proxmox, Caddy, pfSense).

## DNS interno (AdGuard Home)

Os dominios `wccosta.com.br` sao resolvidos internamente pelo AdGuard Home (CT 400, IP `192.168.50.25`).

Exemplo de rewrites em `/opt/AdGuardHome/AdGuardHome.yaml`:

```yaml
  rewrites:
    - domain: cameras.wccosta.com.br
      answer: 192.168.50.151
      enabled: true
    - domain: proxmox.wccosta.com.br
      answer: 192.168.50.250
      enabled: true
    - domain: adguard.wccosta.com.br
      answer: 192.168.50.25
      enabled: true
    - domain: dashboard.wccosta.com.br
      answer: 192.168.50.20
      enabled: true
    - domain: longhorn.wccosta.com.br
      answer: 192.168.50.20
      enabled: true
    - domain: grafana.wccosta.com.br
      answer: 192.168.50.20
      enabled: true
    - domain: prometheus.wccosta.com.br
      answer: 192.168.50.20
      enabled: true
    - domain: argocd.wccosta.com.br
      answer: 192.168.50.20
      enabled: true
    - domain: zabbix.wccosta.com.br
      answer: 192.168.50.20
      enabled: true
```

## Credenciais Azure DNS

A Secret `azuredns-config` no namespace `cert-manager` contem o `client-secret` da App Registration usada pelo cert-manager.

Para verificar:

```bash
kubectl get secret azuredns-config -n cert-manager
```

## Problemas comuns

1. **Certificado nao emite no cert-manager**: verifique se o `Certificate` tem `privateKey.rotationPolicy: Always`. Se a secret ja existia com outro issuer, delete-a: `kubectl delete secret wccosta-tls -n <NAMESPACE>`.

2. **404 no ingress**: o host do ingress nao bate com o dominio do certificado. Confira se o ingress usa `wccosta-tls` como `secretName`.

3. **Kaspersky/browser ainda bloqueia**: o nome DNS acessado nao esta no SAN. Use o dominio `*.wccosta.com.br` correto.

## Instrucoes

Quando o usuario pedir ajuda com certificados, siga este fluxo:

1. Identifique se o servico esta no RKE2 ou externo.
2. Para RKE2: use `kubectl` no no `192.168.50.20` com `KUBECONFIG=/etc/rancher/rke2/rke2.yaml`.
3. Para externos: use `pct exec 101` no Proxmox host para obter certificado.
4. Para DNS: edite `/opt/AdGuardHome/AdGuardHome.yaml` no CT 400.
5. Documente mudancas no `K3s-CCoE` e no `rtmp-cameras-infra`.
