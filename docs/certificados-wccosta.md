# Certificados TLS wccosta.com.br

Documentacao do certificado Letras Encrypt SAN (`san-wccosta-fullchain`) utilizado nos servicos internos via DNS `wccosta.com.br`.

## Visao geral

| Item | Valor |
|---|---|
| **Dominio base** | `wccosta.com.br` |
| **Emissor** | Lets Encrypt (E5 ECDSA) |
| **Metodo de validacao** | DNS-01 via Azure DNS |
| **Tipo** | SAN (Subject Alternative Name), sem wildcard |
| **Arquivos no `ca-server` (CT 101)** | `/etc/letsencrypt/live/san-wccosta-fullchain/` |
| **Validade** | Aproximadamente 90 dias, renovacao automatica |
| **Renovacao** | `certbot` no CT 101 para ambientes externos; `cert-manager` no RKE2 |

## Dominios cobertos (SAN)

| Dominio | Servico | IP interno (AdGuard) |
|---|---|---|
| `cameras.wccosta.com.br` | Cameras (Caddy/SRS) | 192.168.50.151 |
| `proxmox.wccosta.com.br` | Proxmox VE | 192.168.50.250 |
| `adguard.wccosta.com.br` | AdGuard Home | 192.168.50.25 |
| `dashboard.wccosta.com.br` | Kubernetes Dashboard | 192.168.50.20 |
| `longhorn.wccosta.com.br` | Longhorn UI | 192.168.50.20 |
| `grafana.wccosta.com.br` | Grafana | 192.168.50.20 |
| `prometheus.wccosta.com.br` | Prometheus | 192.168.50.20 |
| `argocd.wccosta.com.br` | ArgoCD | 192.168.50.20 |
| `zabbix.wccosta.com.br` | Zabbix | 192.168.50.20 |
| `pfsense-fw01.wccosta.com.br` | pfSense | (IP conforme configuracao) |

> O trafego continua local. O AdGuard Home resolve os dominios `wccosta.com.br` para os IPs internos.

