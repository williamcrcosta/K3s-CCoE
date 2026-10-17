# Incidente: Congelamento do etcd e indisponibilidade do plano de controle RKE2

**Data do incidente:** 2026-10-11 (BRT / UTC-3); segunda degradação em 15–16/out durante restore Longhorn
**Nó afetado:** `rke2-cp-01` (192.168.50.20) — control-plane + etcd
**Duração da indisponibilidade:** ~4 dias (de 11/out até a recuperação em 15/out)
**Causa raiz:** Latência de I/O/fsync do etcd causada pela saturação do thin pool LVM do Proxmox (**89,8% cheio**, ~0G livres no VG) + snapshots LVM antigos segurando blocos + SSD SATA único compartilhado por todas as VMs, em VM com recursos escassos (2 vCPUs / 7,5 GiB RAM, depois 15 GiB / 4 vCPUs)
**Ação corretiva:** Restauração de snapshot do etcd via `rke2 server --cluster-reset --cluster-reset-restore-path`; liberação do thin pool (snapshots LVM + `discard=on` + `fstrim`); taint `NoSchedule` no CP
**Resultado:** Cluster recuperado, Prometheus restaurado do backup Longhorn (363 blocos TSDB), thin pool em 46%

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
   Porque o **thin pool LVM do Proxmox (`pve/data`) estava em 89,82%** sobre um único SSD SATA de 720GB compartilhado por todas as VMs — snapshots LVM antigos (`pre-update-2026-09-13`, `pre-dnf-update`) seguravam ~150G de blocos, e os discos das VMs não tinham `discard=on`, então espaço liberado dentro das VMs nunca voltava ao pool. Adicionalmente, a VM `rke2-cp-01` tinha só **2 vCPUs e 7,5 GiB de RAM** rodando etcd + apiserver + Longhorn + observabilidade, com swap em uso. (Verificado em 16/out: SMART do SSD saudável, zero erros SATA — o problema era saturação do pool, não disco defeituoso.)

5. **Por que o thin pool e o control-plane estavam nesse estado?**
   Porque o cluster foi dimensionado como homelab de baixo custo, sem separação de plano de controle/dados, sem TRIM configurado e sem monitoramento do thin pool do hipervisor. Com o tempo, snapshots de manutenção ficaram esquecidos e workloads pesados foram adicionados ao CP até o etcd perder a capacidade de responder a tempo.

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
- **Prometheus:** buraco de ~18 dias de métricas (22/set–10/out o pod já estava quebrado com I/O error; 10/out–16/out durante a recuperação). Histórico anterior restaurado do backup (ver seção 8).

## 8. Segunda degradação e restauração do Prometheus (15–16/out)

Durante a tentativa de restaurar o volume do Prometheus (`pvc-6d11925f`, que estava `faulted` por I/O errors) a partir do backup NFS, o etcd **voltou a congelar** — o download de ~20G saturou o mesmo thin pool e o CP com 2 vCPUs não sobreviveu à contenção (`st`/`wa` ~46%).

Sequência executada:

1. **Upgrade da VM** `rke2-cp-01`: 2 vCPUs/7,5 GiB → **4 vCPUs/15 GiB** (via Proxmox, VMID 500). Reboots controlados de worker e CP.
2. **Restore Longhorn** do backup `backup-347ef2fbe9aa4605` (10/out 13:00 UTC, NFS `192.168.50.250:/var/lib/vz/longhorn-backup`) em volume separado `prometheus-restored`.
3. **Cópia in-place:** como StatefulSet + ArgoCD recriavam a PVC vazia em loop, o caminho vencedor foi montar o volume restaurado read-only no CP (`/mnt/prom-src`) e copiar `prometheus-db/` para dentro do globalmount do volume vivo (`pvc-484de07c-...`).
   - A 1ª cópia falhou com I/O errors (pool ainda saturado); re-executada com sucesso após liberação do pool.
   - `wal/`, `chunks_head/`, `lock` e `queries.active` foram **descartados** — o backup continha segmentos de WAL não-sequenciais que impediam o boot do TSDB.
   - 66 blocos com `meta.json` truncado (da cópia interrompida) foram re-copiados; 1 bloco (`01KTD07T...`) já vinha corrompido no backup e foi descartado.
4. **Resultado:** `prometheus-0` `2/2 Running`, **363 blocos TSDB íntegros**, histórico consultável desde ~11/set.

## 9. Causa raiz final — thin pool LVM saturado

Diagnóstico no host `pve` (16/out) revelou a verdadeira causa da latência:

- `pve/data` thin pool: **89,82%** (554,7G); VG sem espaço livre (`VFree 0`)
- `vm-501-disk-1` (disco Longhorn do worker): **99,84%** provisionado — escrita no topo do thin pool degradava/corrompia I/O
- 6 snapshots LVM de setembro (`pre-update-2026-09-13`, `pre-dnf-update`) segurando ~150G
- Discos sem `discard=on` → espaço liberado nas VMs nunca retornava ao pool
- SMART do SSD: saudável (0 reallocated/pending sectors); `dmesg` sem erros SATA

**Correções aplicadas:**

| Ação | Resultado |
|---|---|
| `qm delsnapshot` dos snapshots antigos (VMs 500/501) | pool 89,82% → 62,5% |
| `discard=on` nos discos virtio-scsi + reboot das VMs | TRIM passa a funcionar |
| `fstrim -av` em CP e worker | ~120G devolvidos ao pool |
| `fstrim.timer` habilitado nas VMs | trim semanal automático |
| Taint `NoSchedule` no CP | CP isolado de workloads |
| Remoção de Loki/Alloy (GitOps + cluster) | memória/disco liberados |
| Limpeza de backups Longhorn antigos no NFS | mantidos apenas o âncora 10/out + daily atual |
| Estado final do pool | **46,39%** — `vm-501-disk-1` em 25,85% |

## 10. Recomendações para evitar recaída

**Já executadas (16–17/out):**

- ✅ Isolar o CP: taint `node-role.kubernetes.io/control-plane=true:NoSchedule` aplicado em `rke2-cp-01` (workloads existentes migram ao reagendar; Prometheus já está no worker)
- ✅ Aumentar recursos: VM 500 agora com 4 vCPUs / 15 GiB RAM
- ✅ Desafogar o thin pool: snapshots LVM removidos, `discard=on` + `fstrim.timer` — pool em 46%
- ✅ Remover observabilidade não usada (Loki/Alloy) do GitOps e do cluster

**Pendentes:**

1. **Monitorar o thin pool do Proxmox** — alertar quando `pve/data` passar de ~75–80%. É a métrica que teria previsto este incidente.
2. **Alertas no cluster** para `apply request took too long`, `ReadIndex` timeout, `I/O wait > 20%`, swap em uso.
3. **Storage dedicado pro etcd** (segundo disco físico/NVMe) ou storage mais rápido — o SSD SATA único continua sendo o ponto único de contenção.
4. **Copiar snapshots do etcd para storage externo** (ex.: NFS `/mnt/longhorn-backup/etcd-snapshots/` ou rotina agendada) — hoje só existem no disco do CP.
5. **Revisar `config.yaml`:** as entradas `etcd-expose-metrics`, `kube-controller-manager-arg` e `kube-scheduler-arg` geraram warnings de `Unknown flag` no `rke2`. Validar os nomes corretos para `v1.35.8+rke2r1` e corrigir.
6. **Redundância real do etcd** — CP único continua SPOF; médio prazo considerar 3 CPs.
7. **Documentar runbooks:** adicionar ao `DISASTER_RECOVERY.md` os cenários "etcd congelado por I/O/thin pool cheio" e "restore de volume Longhorn via cópia in-place" (o caminho que funcionou quando PV/PVC e ArgoCD brigavam).

## 11. Arquivos e referências relevantes

- Log do etcd congelado: `/var/log/pods/kube-system_etcd-rke2-cp-01_08fdfe1c35d9b991a99aae7d68a21f00/etcd/6.log`
- Mensagens do systemd/rke2: `/var/log/messages` (rotação `messages-20261011`)
- Backup do etcd falho: `/var/lib/rancher/rke2/server/db/etcd.bak.1792106150` (removível após validação)
- Backup dos snapshots: `/var/lib/rancher/rke2/server/db/snapshots.bak.1792106150` (removível)
- Certificados antigos (pós-restore): `/var/lib/rancher/rke2/server/tls-1792106213` (removível)
- Configuração RKE2: `/etc/rancher/rke2/config.yaml`
- Backup Longhorn âncora do restore: `backup-347ef2fbe9aa4605` (10/out 13:00 UTC) no NFS `192.168.50.250:/var/lib/vz/longhorn-backup`
- Volume Prometheus atual: `pvc-484de07c-bcfe-48a0-9ddd-c215e43592e1` (20Gi, 2 réplicas no worker)
- Comandos de diagnóstico do pool: `lvs pve -o lv_name,data_percent`, `vgs pve`, `smartctl -a /dev/sda`

---

**Autor:** Devin
**Data da documentação:** 2026-10-15 (atualizado 2026-10-17 com a causa raiz do thin pool e a restauração do Prometheus)
