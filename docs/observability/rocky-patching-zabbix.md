# Atualizações Rocky Linux no Zabbix

## Coleta validada

O piloto em `rke2-worker-01` usa o coletor local `/usr/local/sbin/zabbix-rocky-updates`. O RPM fornece as versões instaladas. O DNF fornece as versões disponíveis e os avisos de segurança, correções e melhorias. Cada pacote e arquitetura recebe a maior severidade aplicável. Pacotes sem aviso aplicável ficam em **Sem classificação**.

| Item | Valor |
|---|---|
| Tipo | Zabbix agent (active) |
| Chave | `vfs.file.contents[/var/lib/zabbix/rocky-updates/report.txt]` |
| Tipo de informação | Texto |

O histórico mostra as versões lado a lado. Use **Coleta UTC** para verificar quando o DNF gerou o relatório. O horário do item registra quando o agente leu o arquivo.

## Aplicação manual

1. Faça a prévia na VM. Use `dnf --sec-severity=Critical --assumeno upgrade-minimal` para críticos ou `dnf --refresh --assumeno upgrade` para a transação completa. Revise instalações, upgrades, substituições e remoções.
2. Atualize e reinicie uma VM por vez na janela aprovada. Antes do upgrade do control plane, confirme a saúde da worker e gere um snapshot com `rke2 etcd-snapshot save --name pre-upgrade-cp`.
3. Confira o kernel padrão com `grubby --default-kernel` antes do reboot e o kernel em execução com `uname -r` após o retorno.
4. Valide a API em `/readyz`, ambos os nós, os volumes Longhorn e as URLs a partir de outra máquina por DNS normal.
5. Execute o coletor novamente e confira a nova **Coleta UTC** no Zabbix.

A execução de prévias por SSH via Zabbix ficou como proposta. Nesta janela, a prévia e a instalação foram feitas pelo terminal.
