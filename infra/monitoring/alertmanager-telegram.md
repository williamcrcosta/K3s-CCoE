# Alertmanager — Notificações Telegram

## Objetivo
Encaminhar alertas `critical` e `warning` do Alertmanager para um chat do Telegram.

## Configuração aplicada
A aplicação `monitoring` no ArgoCD foi atualizada para:
- Usar um receiver `telegram` no Alertmanager
- Montar o Secret `alertmanager-telegram` em `/etc/alertmanager/secrets/alertmanager-telegram/`
- Referenciar `bot_token_file` e `chat_id_file`

## Próximo passo manual
Criar o Secret `alertmanager-telegram` no namespace `monitoring` com os dados reais:

```bash
export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
kubectl -n monitoring create secret generic alertmanager-telegram \
  --from-literal=bot-token='SEU_BOT_TOKEN' \
  --from-literal=chat-id='SEU_CHAT_ID'
```

> O `chat-id` deve conter apenas o número (ex: `123456789`).

## Validação
Após criar o Secret, aguarde o ArgoCD sincronizar e teste com:

```bash
export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
kubectl -n monitoring port-forward svc/monitoring-kube-prometheus-alertmanager 9093:9093
curl -s http://localhost:9093/api/v2/status
```

## Recomendação futura
Quando o Telegram estiver validado, transformar este Secret em SealedSecret (`kubeseal`) e armazená-lo em `K3s-CCoE/secrets/` para manter o GitOps completo.
