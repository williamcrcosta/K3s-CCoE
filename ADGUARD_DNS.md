# DNS Local — AdGuard Home no Proxmox

## Decisão

O PowerDNS Authoritative + Recursor foi testado no cluster RKE2, mas devido à complexidade de manutenção do backend SQLite e ausência de UI integrada, optamos por manter o **DNS primário fora do cluster**, no **AdGuard Home** rodando no Proxmox.

## Arquitetura

```
Internet / Rede Local
        |
    [AdGuard Home no Proxmox]
        |
   +----+----+
   |         |
upstream   rewrites wcrpc.lan
1.1.1.1    192.168.50.20
```

O AdGuard Home responde por toda a rede local e faz rewrites dos domínios `*.wcrpc.lan` para o IP do ingress do cluster (RKE2).

## Configuração no AdGuard Home

### Upstreams

Em `Settings > DNS settings > Upstream DNS servers`, adicione:

```
1.1.1.1
8.8.8.8
```

### DNS rewrites

Em `Filters > DNS rewrites`, adicione cada registro:

| Domain | IP |
|---|---|
| `argocd.wcrpc.lan` | 192.168.50.20 |
| `dashboard.wcrpc.lan` | 192.168.50.20 |
| `grafana.wcrpc.lan` | 192.168.50.20 |
| `longhorn.wcrpc.lan` | 192.168.50.20 |
| `powerdns.wcrpc.lan` | 192.168.50.20 |
| `prometheus.wcrpc.lan` | 192.168.50.20 |
| `technitium.wcrpc.lan` | 192.168.50.20 |
| `zabbix.wcrpc.lan` | 192.168.50.20 |

> **Dica:** se o AdGuard Home suportar, pode substituir as entradas acima por um único wildcard `*.wcrpc.lan` apontando para `192.168.50.20`.

## No cluster

O Technitium ainda pode ser desativado quando o AdGuard estiver plenamente configurado e validado na rede.

### Remover o PowerDNS manualmente

Após o ArgoCD parar de gerenciar o PowerDNS, os recursos ainda ficarão no cluster. Remova via `kubectl`:

```bash
export PATH=$PATH:/var/lib/rancher/rke2/bin
export KUBECONFIG=/etc/rancher/rke2/rke2.yaml

kubectl delete deployment powerdns-auth powerdns-recursor -n dns
kubectl delete svc powerdns-auth powerdns-recursor -n dns
kubectl delete ingress powerdns -n dns
kubectl delete pvc powerdns-auth-data -n dns
kubectl delete configmap powerdns-auth-schema -n dns
```

### Status no ArgoCD

O ArgoCD não gerencia mais o PowerDNS. O app `powerdns` pode ser deletado manualmente na UI do ArgoCD com cascade.
