# Incidente: Congelamento do etcd e indisponibilidade do plano de controle RKE2

**Data do incidente:** 2026-10-11 (BRT / UTC-3)
**Nó afetado:** `rke2-cp-01` (192.168.50.20) — control-plane + etcd
**Duração da indisponibilidade:** ~4 dias (de 11/out até a recuperação em 15/out)
**Causa raiz:** Latência crônica de I/fsync do etcd em ambiente com recursos escassos (VM 2 vCPUs / 7,5 GiB RAM / storage do hipervisor sobrecarregado)
**Ação corretiva:** Restauração de snapshot do etcd via `rke2 server --cluster-reset --cluster-reset-restore-path`
**Resultado:** Cluster recuperado e operacional

---

## 1. Resumo executivo

Em **11 de outubro de 2026, por volta de 04:30 BRT**, o etcd do nó `rke2-cp-01` congelou porque as operações de `fsync` e aplicação de entradas do raft passaram a exceder os limites de tempo. O etcd ainda aceitava conexões TCP na porta `2379`, mas não conseguia processar requisições — leituras linearizadas e aplicações de índice demoravam **15–19 segundos**.

Como o `rke2-server` depende de leases armazenados no etcd para eleger líderes e reconciliar o datastore local, o processo principal perdeu a eleição (`leaderelection lost`), saiu com erro (`status=1/FAILURE`) e entrou em um loop de reinicialização. Os pods estáticos (kube-apiserver, etcd, scheduler) continuaram rodando por conta de `containerd-shim` órfãos, mas o plano de controle estava efetivamente morto.

Não houve alteração manual no dia 11/out — **não foi uma mudança de configuração ou atualização que derrubou o cluster**. Foi a degradação progressiva do ambiente de virtualização/storage.

## 2. Linha do tempo (BRT)

| Horário | Evento | Evidência |
|---|---|---|
| **Sep 22** | VM `rke2-cp-01` ligada; etcd começa a registrar `apply request took too long` (~200–500 ms) | `dmesg` (boot), `/var/log/pods/.../etcd/5.log` |
| **Oct 4–5** | `clocksource: timekeeping watchdog` e `hrtimer: interrupt took 4.3 ms` — sinais de atraso de CPU no hipervisor | `dmesg -T` |
| **Oct 10** | `apply request took too long` passa para ~350–720 ms; latência cresce | `etcd/6.log` |
| **Oct 11 04:07–04:28** | `rke2` reconcilia `ETCDSnapshotFile` normalmente | `/var/log/messages` |
| **Oct 11 04:29:32–40** | Vários `containerd` scopes são finalizados (consumindo CPU) | `/var/log/messages` |
| **Oct 11 04:29:38** | Primeiro timeout no etcd: `etcdserver: request timed out` | `/var/log/messages` |
| **Oct 11 04:29:54** | Falha ao renovar leases `rke2-etcd` e `rke2` (`context deadline exceeded`) | `/var/log/messages` |
| **Oct 11 04:30:23** | Última linha do log do etcd — `apply request took too long` de ~10 s | `etcd/6.log` |
| **Oct 11 04:30:24** | `leaderelection lost for rke2` | `/var/log/messages` |
| **Oct 11 04:30:44** | `rke2-server.service` principal sai com `status=1/FAILURE` | `/var/log/messages` |
| **Oct 11 04:30:49+** | Loop de reinício do `rke2-server` começa; contador cresce até ~25.623 | `/var/log/messages`, `systemctl` |
| **Oct 14 07:53** | Journalctl mostra loop de restart já em ~17.796 | `journalctl` |
| **Oct 15 20:16** | Restauração do snapshot `etcd-snapshot-rke2-cp-01-1791687613` concluída | Execução manual |
| **Oct 15 20:17:59** | `rke2-server` sobe e cluster volta a `Ready` | `systemctl`, `kubectl get nodes` |

## 3. Sintomas observados

- `kubectl get nodes` e qualquer chamada à API retornavam `context deadline exceeded` / `Timeout`.
- `etcdctl endpoint health` falhava: `127.0.0.1:2379 is unhealthy`.
- `rke2-server.service` em `activating (auto-restart)` com contador de restart na casa dos milhares.
- O etcd continuava escutando em `2379/2380` e `kube-apiserver` em `6443`, mas sem resposta.
- `/proc/<pid>/stack` do etcd mostrava `futex_do_wait` — processo vivo, mas travado.
- `vmstat` mostrava **30% de I/O wait** e **swap ativo (~1 GiB)**.
- `free -h`: **7,1 GiB usados / 7,5 GiB**, ~200 MiB livres.
- `dmesg -T` registrava `kvm-clock retried 1 times before success` e `hrtimer: interrupt took 4307594 ns`.

## 4. Evidência de que não houve alteração manual

- `last -F`: último login `root` em **27/setembro**; nenhum acesso em outubro.
- `dnf history`: último `update -y` em **19/setembro**; nenhuma instalação em outubro.
- `crontab -l`: vazio; só timers padrão (`dnf-makecache`, `logrotate`, `systemd-tmpfiles-clean`).
- `find /etc /var -newermt "2026-10-10" ! -newermt "2026-10-13"`: apenas rotações normais de tokens de service account do kubelet; nenhuma mudança de configuração.
- `ls -lt /var/lib/rancher/rke2/server/db/snapshots/`: snapshot mais recente em **11/out 00:00 BRT**.

## 5. Os 5 Porquês

1. **Por que o cluster ficou indisponível?**
   Porque o `rke2-server` entrou em um loop de reinício e não conseguiu mais fazer o bootstrap, pois o etcd local não respondia.

2. **Por que o etcd não respondia?**
   Porque as operações de leitura linearizável (`ReadIndex`) e aplicação de entradas do raft (`apply`) passaram a demorar **10–19 segundos**, excedendo os timeouts de contexto.

3. **Por que essas operações estavam tão lentas?**
   Porque o `fsync` do WAL e o I/O do disco local estavam com latência alta: o `vmstat` mostrava ~30% de I/O wait, swap em uso e o disco XFS estava contendo ~30 GiB de dados, incluindo etcd + Longhorn + monitoramento.

4. **Por que o disco estava lento?**
   Porque a VM `rke2-cp-01` tem **2 vCPUs e 7,5 GiB de RAM** e está rodando componentes pesados no próprio control-plane (Longhorn, Alloy, Loki, Grafana, Zabbix, kube-apiserver, etcd), enquanto o hipervisor Proxmox registrava atrasos de `kvm-clock`/`hrtimer` (contenção de CPU e storage).

5. **Por que o control-plane estava com recursos insuficientes?**
   Porque o cluster foi dimensionado como um homelab de baixo custo, sem separação de plano de controle de dados. Com o tempo, workloads de dados (Longhorn) e observabilidade (Prometheus/Loki/Grafana/Zabbix) foram adicionados ao mesmo nó, aumentando o consumo de CPU, memória e I/O até o etcd perder a capacidade de responder a tempo.

## 6. Ações de recuperação executadas

1. **Backup do estado falho** (para permitir rollback manual):
   ```bash
   cp -a /var/lib/rancher/rke2/server/db/etcd     /var/lib/rancher/rke2/server/db/etcd.bak.1792106150
   cp -a /var/lib/rancher/rke2/server/db/snapshots /var/lib/rancher/rke2/server/db/snapshots.bak.1792106150
   ```

2. **Parada e limpeza completa** de processos/órfãos:
   ```bash
   systemctl stop rke2-server
   /usr/bin/rke2-killall.sh
   ```
   (remove `containerd-shim` órfãos, desmonta mounts, limpa CNI e pod manifests).

3. **Restauração do etcd com reset de cluster** (único membro):
   ```bash
   rke2 server --cluster-reset \
     --cluster-reset-restore-path /var/lib/rancher/rke2/server/db/snapshots/etcd-snapshot-rke2-cp-01-1791687613
   ```
   (o processo restaurou o banco, desfragmentou e solicitou reinício sem `--cluster-reset`).

4. **Subida do serviço**:
   ```bash
   systemctl start rke2-server
   ```

5. **Validação**:
   - `kubectl get nodes` → `Ready` em ambos os nós.
   - `kubectl exec -n kube-system etcd-rke2-cp-01 -- etcdctl ... endpoint health` → `healthy`.
   - `kubectl get pods -A` → componentes do sistema `Running`.
   - `kubectl get pvc -A` → PVCs `Bound` e volumes Longhorn `attached/healthy`.

## 7. Impacto / dados perdidos

- **Janela de perda:** ~4 horas e 30 minutos (entre **00:00 e ~04:30 BRT** de 11/out).
  O snapshot restaurado foi gerado às **00:00 BRT** (`etcd-snapshot-rke2-cp-01-1791687613`). Como o etcd congelou às 04:30, é provável que nenhuma escrita crítica tenha sido persistida entre 00:00 e 04:30 — mas qualquer alteração feita naquele intervalo foi perdida.

- **Pods:** todos foram reiniciados pelo `rke2-killall.sh` + nova subida do `rke2-server`. Alguns levaram ~4 minutos para voltar.
- **Certificados:** novos foram gerados na restauração; os antigos foram preservados em `/var/lib/rancher/rke2/server/tls-1792106213`.

## 8. Recomendações para evitar recaída

1. **Isolar o control-plane:** remover workloads de dados (Longhorn) e observabilidade pesada (Loki, Grafana, Zabbix, Prometheus) do `rke2-cp-01`. O nó deve servir apenas etcd/apiserver/scheduler/controller-manager.
2. **Aumentar recursos do VM:** subir para pelo menos **16 GiB de RAM** e mais vCPUs (4+). Eliminar dependência de swap.
3. **Melhorar storage do etcd:** usar disco dedicado ou garantir IOPS/latência de `fsync` baixa no hipervisor; evitar compartilhamento com volumes de dados pesados.
4. **Monitorar I/O:** criar alertas para `I/O wait`, `fsync latency`, `swap`, e `etcd` (apply/request duration, `ReadIndex` timeout).
5. **Revisar `config.yaml`:** as entradas `etcd-expose-metrics`, `kube-controller-manager-arg` e `kube-scheduler-arg` geraram warnings de `Unknown flag` no `rke2`. Validar os nomes corretos para `v1.35.8+rke2r1` e corrigir.
6. **Backup/restore periódico:** manter snapshots do etcd e testar restauração regularmente; considerar snapshots para storage externo.
7. **Documentar runbooks:** manter o `DISASTER_RECOVERY.md` atualizado com este cenário (Cenário X: etcd congelado por I/O).

## 9. Arquivos e referências relevantes

- Log do etcd congelado: `/var/log/pods/kube-system_etcd-rke2-cp-01_08fdfe1c35d9b991a99aae7d68a21f00/etcd/6.log`
- Mensagens do systemd/rke2: `/var/log/messages` (rotação `messages-20261011`)
- Backup do etcd falho: `/var/lib/rancher/rke2/server/db/etcd.bak.1792106150`
- Backup dos snapshots: `/var/lib/rancher/rke2/server/db/snapshots.bak.1792106150`
- Certificados antigos (pós-restore): `/var/lib/rancher/rke2/server/tls-1792106213`
- Configuração RKE2: `/etc/rancher/rke2/config.yaml`

---

**Autor:** Devin
**Data da documentação:** 2026-10-15
