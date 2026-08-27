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

## No cluster

O Technitium ainda pode ser desativado quando o AdGuard estiver plenamente configurado e validado na rede.

### Remover o PowerDNS manualmente

Após o ArgoCD parar de gerenciar o PowerDNS, os recursos ainda ficarão no cluster. Remova via :



### Status no ArgoCD

O ArgoCD não gerencia mais o PowerDNS. O app  pode ser deletado manualmente na UI do ArgoCD com cascade.
