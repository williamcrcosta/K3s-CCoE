# Ollama + Open WebUI — IA Local

Assistente de IA multimodal para:
- 🏗️ **Orquestração de infra** (kubectl, helm, troubleshooting)
- 💻 **Código Terraform** (IaC, módulos AWS/Azure/GCP)
- ✍️ **Assistente de blog** (escrita criativa, SEO, revisão)

---

## Arquitetura

```
Usuário → https://ai.wcrpc.lan
        → Open WebUI (interface web)
        → Ollama API (localhost:11434)
        → Modelo (llama3/codellama/mistral)
```

---

## Requisitos

| Recurso | Mínimo | Recomendado |
|---|---|---|
| RAM | 4GB | 8GB+ |
| CPU | 2 cores | 4 cores |
| Storage | 20GB | 50GB+ |
| GPU | Opcional | NVIDIA (acelera 10x) |

**Seu cluster atual:** 12GB RAM disponível, 8 CPU, 50GB+ storage ✅

---

## Deploy

### 1. Aplicar manifests
```bash
kubectl apply -k apps/ollama/
```

### 2. Aguardar pods Ready
```bash
kubectl wait --for=condition=ready pod -l app=ollama -n ollama --timeout=120s
kubectl wait --for=condition=ready pod -l app=open-webui -n ollama --timeout=120s
```

### 3. Baixar modelos (~30 minutos)
```bash
./apps/ollama/setup-models.sh
```

Ou manualmente:
```bash
kubectl exec -n ollama deployment/ollama -- ollama pull llama3:8b
kubectl exec -n ollama deployment/ollama -- ollama pull codellama:7b
kubectl exec -n ollama deployment/ollama -- ollama pull mistral:7b
```

### 4. Acessar
```
https://ai.wcrpc.lan
```

---

## Modelos Disponíveis

| Modelo | Tamanho | Uso |
|---|---|---|
| `llama3:8b` | ~4.7GB | Geral, infra, kubectl, troubleshooting |
| `codellama:7b` | ~3.8GB | Código Terraform, Python, YAML |
| `mistral:7b` | ~4.1GB | Escrita criativa, blog, revisão de texto |

**Total:** ~12.6GB de modelos

---

## Uso por Caso

### 🔧 Orquestração de Infra
**Prompt exemplo:**
```
Gere um manifest Kubernetes para um Deployment nginx 
com 3 réplicas, HPA baseado em CPU 70%, e ingress 
para nginx.wcrpc.lan
```

### 💻 Código Terraform
**Prompt exemplo:**
```
Crie um módulo Terraform para AWS VPC com:
- 2 AZs
- Public e private subnets
- NAT Gateway
- Tags padronizadas
```

### ✍️ Assistente de Blog
**Prompt exemplo:**
```
Revise este texto sobre Kubernetes, melhore a clareza 
e sugira 5 títuloscatchy:
[COLE SEU TEXTO AQUI]
```

---

## Otimizações para seu Cluster

Devido à RAM limitada (12GB total):

1. **OLLAMA_MAX_LOADED_MODELS=1** — Apenas 1 modelo na RAM por vez
2. **OLLAMA_KEEP_ALIVE=5m** — Descarrega após 5min de inatividade
3. **Modelos 7B-8B** — Menor que 13B/70B (que precisam de 32GB+)

Para melhor performance, adicione uma GPU RTX 3060+ no k8s-cp futuramente.

---

## Comandos Úteis

```bash
# Ver modelos disponíveis
kubectl exec -n ollama deployment/ollama -- ollama list

# Remover um modelo
kubectl exec -n ollama deployment/ollama -- ollama rm mistral:7b

# Ver uso de recursos
kubectl top pod -n ollama

# Logs
kubectl logs -n ollama deployment/ollama -f
kubectl logs -n ollama deployment/open-webui -f
```

---

## Troubleshooting

### Pod fica em OOMKilled
- Reduzir `limits.memory` no deployment para 4Gi
- Usar modelo menor (llama3:3b em vez de 8b)

### Modelo lento para responder
- Normal em CPU — sem GPU pode levar 10-30s por resposta
- Respostas curtas são mais rápidas

### WebUI não conecta no Ollama
```bash
kubectl exec -n ollama deployment/open-webui -- \
  curl -s http://ollama:11434/api/tags
```

---

## Integração com outros apps

### Usar API diretamente
```bash
curl http://ollama.ollama.svc.cluster.local:11434/api/generate -d '{
  "model": "llama3:8b",
  "prompt": "Liste comandos kubectl úteis"
}'
```

---

## Evoluções Futuras

- [ ] GPU NVIDIA no k8s-cp (aceleração 10x)
- [ ] Modelo maior (llama3:70b) com GPU
- [ ] Integração com Zabbix (alertas com contexto IA)
- [ ] RAG com documentação do cluster
