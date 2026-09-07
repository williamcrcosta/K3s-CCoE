# Knowledge Base — Criar um Bot do Telegram e Integrar com Alertmanager

Esse documento registra o passo a passo usado para criar o bot `@wccosta_homelab_alerts_bot` e integrá-lo ao Alertmanager. Pode ser replicado para outras necessidades.

## 1. Criar o bot no Telegram

1. Abra o Telegram e procure por **`@BotFather`** (oficial, com selo azul ✅)
2. Envie `/newbot`
3. Escolha o **nome** e o **username** (deve terminar em `bot`, ex: `meu_homelab_alerts_bot`)
4. O BotFather responde com o **bot token** no formato:

```text
123456789:ABC-DEF...xyz
```

> **Segurança**: o token dá acesso total ao bot. Guarde-o em um Secret do Kubernetes. **Não commit no Git.**

## 2. Obter o chat ID

### Opção A — via @userinfobot
1. Procure **`@userinfobot`** no Telegram
2. Clique em **Start**
3. Ele responde com seu `Id: 123456789`

### Opção B — via API do Telegram
1. No Telegram, inicie uma conversa com o bot criado
2. Envie uma mensagem (ex: `/start` ou `ola`)
3. Acesse no navegador:

```text
https://api.telegram.org/bot<SEU_BOT_TOKEN>/getUpdates
```

4. Procure no JSON retornado:

```json
"chat": {
  "id": 123456789
}
```

O `chat_id` pode ser um número positivo (usuário) ou negativo (grupo).

## 3. Criar o Secret no Kubernetes

```bash
export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
kubectl -n monitoring create secret generic alertmanager-telegram \
  --from-literal=bot-token='SEU_BOT_TOKEN' \
  --from-literal=chat-id='SEU_CHAT_ID'
```

> Para GitOps, converta em **SealedSecret** (`kubeseal`) e armazene em `K3s-CCoE/secrets/`.

## 4. Configurar o Alertmanager

Exemplo de snippet para adicionar no `values:` do `kube-prometheus-stack`:

```yaml
alertmanager:
  config:
    global:
      resolve_timeout: 5m
      telegram_api_url: https://api.telegram.org
    route:
      receiver: 'null'
      group_by:
      - namespace
      - alertname
      continue: false
      routes:
      - receiver: telegram
        matchers:
        - severity=~"critical|warning"
        continue: false
      - receiver: "null"
        matchers:
        - alertname="Watchdog"
        continue: false
      group_wait: 30s
      group_interval: 5m
      repeat_interval: 12h
    receivers:
    - name: "null"
    - name: telegram
      telegram_configs:
      - bot_token_file: /etc/alertmanager/secrets/alertmanager-telegram/bot-token
        chat_id: 123456789
        message: |
          {{ range .Alerts }}
          *Alert:* {{ .Labels.alertname }}
          *Summary:* {{ .Annotations.summary }}
          *Severity:* {{ .Labels.severity }}
          *Namespace:* {{ .Labels.namespace }}
          *Description:* {{ .Annotations.description }}
          {{ end }}
  alertmanagerSpec:
    secrets:
    - alertmanager-telegram
```

### Pontos importantes
- Use `bot_token_file` e monte o Secret via `alertmanagerSpec.secrets`.
- O `chat_id` fica direto no config porque o prometheus-operator ainda não suporta `chat_id_file`.
- O template do Alertmanager **não usa Sprig** — funções como `default` não existem.

## 5. Aplicar e validar

1. Aplique a mudança no ArgoCD (ou `kubectl apply -f monitoring.yaml`)
2. Aguarde o Alertmanager reiniciar
3. Envie um alerta de teste pela API v2:

```bash
kubectl -n monitoring port-forward svc/monitoring-kube-prometheus-alertmanager 9093:9093
curl -XPOST http://localhost:9093/api/v2/alerts \
  -H 'Content-Type: application/json' \
  -d '[{
    "labels": {"alertname":"TestTelegram","severity":"critical","namespace":"monitoring"},
    "annotations": {"summary":"Teste","description":"Funciona?"},
    "startsAt": "2026-09-07T00:00:00Z"
  }]' 
```

## 6. Boas práticas de segurança

- **Nunca** versione o bot token em plain text.
- Se o token vazar, revogue no `@BotFather` (`/revoke`) e gere um novo.
- Prefira `SealedSecret` para guardar o Secret no Git.
- A periodicidade de alertas (`group_wait`, `group_interval`, `repeat_interval`) impacta a frequência de mensagens.

## 7. Outras aplicações possíveis

O mesmo bot pode ser usado para:
- Notificações de backups concluídos ou com falha
- Alertas de certificado prestes a expirar
- Status de sincronização do ArgoCD
- Resumo diário de saúde do cluster
- Comandos de `/status` para consultar o homelab remotamente
