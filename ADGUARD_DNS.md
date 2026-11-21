# DNS Local — AdGuard Home no Proxmox

## Endereços

- **UI / Admin:** http://192.168.50.25:3001/
- **Servidor DNS:**  (usar este IP como DNS nos dispositivos/roteador)

## Decisão

O PowerDNS Authoritative + Recursor foi testado no cluster RKE2, mas devido à complexidade de manutenção do backend SQLite e ausência de UI integrada, optamos por manter o **DNS primário fora do cluster**, no **AdGuard Home** rodando no Proxmox.

## Arquitetura



O AdGuard Home responde por toda a rede local e faz rewrites dos domínios  para os IPs internos dos serviços.

> **Nota:** os domínios  ainda existem como legado, mas foram desativados para navegação com HTTPS devido aos avisos de certificado no Kaspersky/navegadores.

## Configuração no AdGuard Home

### Upstreams

Em , adicione:



### DNS rewrites

Em , adicione cada registro:

| Domain | IP |
|---|---|
|  | 192.168.50.20 |
|  | 192.168.50.151 |
|  | 192.168.50.250 |
|  | 192.168.50.25 |
|  | 192.168.50.20 |
|  | 192.168.50.151 |
|  | 192.168.50.20 |
|  | 192.168.50.20 |
|  | 192.168.50.20 |
|  | 192.168.50.20 |
|  | 192.168.50.250 |
|  | 192.168.50.20 |

> **Dica:** o wildcard  continua apontando para  para compatibilidade legada, mas os certificados Let's Encrypt cobrem os domínios .

### Aplicações do ingress

Desde 21/11/2026, o Ingress NGINX atende na worker `192.168.50.21`. Os rewrites das aplicações abaixo devem apontar para esse endereço.

| Domínios | IP |
|---|---|
| `grafana.wccosta.com.br`, `prometheus.wccosta.com.br`, `zabbix.wccosta.com.br` | `192.168.50.21` |
| `vault.wccosta.com.br`, `argocd.wccosta.com.br`, `longhorn.wccosta.com.br`, `dashboard.wccosta.com.br` | `192.168.50.21` |

A tabela anterior contém entradas sem nome no Git. Confira no AdGuard os registros dos demais serviços antes de editar. Consulte o [incidente de ingress](docs/incidentes/2026-11-21-ingress-apos-upgrade-rke2.md) para o diagnóstico.

## No cluster

O Technitium ainda pode ser desativado quando o AdGuard estiver plenamente configurado e validado na rede.

### Remover o PowerDNS manualmente

Após o ArgoCD parar de gerenciar o PowerDNS, os recursos ainda ficarão no cluster. Remova via :



### Status no ArgoCD

O ArgoCD não gerencia mais o PowerDNS. O app  pode ser deletado manualmente na UI do ArgoCD com cascade.
