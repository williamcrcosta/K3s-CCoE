# Métricas do Control-Plane RKE2 no Prometheus

## Problema
O kube-prometheus-stack tenta coletar métricas de etcd, kube-controller-manager e kube-scheduler no IP do node. Por padrão, o RKE2 hardened expõe essas métricas apenas em `127.0.0.1`, resultando em targets DOWN no Prometheus.

## Solução
Atualizar `/etc/rancher/rke2/config.yaml` com este conteúdo e reiniciar o `rke2-server`.

## Aplicação
```bash
cp /root/K3s-CCoE/infra/rke2-cp-metrics/rke2-config.yaml /etc/rancher/rke2/config.yaml
systemctl restart rke2-server
```

## Validação
```bash
export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
kubectl -n monitoring get servicemonitor monitoring-kube-prometheus-kube-etcd
kubectl -n monitoring get servicemonitor monitoring-kube-prometheus-kube-controller-manager
kubectl -n monitoring get servicemonitor monitoring-kube-prometheus-kube-scheduler
# Aguardar até os targets ficarem UP no Prometheus
```

## Nota de segurança
Os endpoints de métricas ainda exigem autenticação (client cert ou service account token). O kube-prometheus-stack já envia o bearer token do Prometheus. Apenas a conectividade de rede é alterada.
