# Plano de Migração — GitOps com ArgoCD

## Objetivo
Migrar todos os recursos do cluster para serem gerenciados pelo ArgoCD via GitOps,
eliminando recursos aplicados manualmente (`kubectl apply`).

## Status: ✅ CONCLUÍDO

---

## Resultado Final

| App | Namespace | ArgoCD | Storage | Versão |
|---|---|---|---|---|
| ArgoCD | `platform-argocd` | ✅ self-managed | — | v2.x |
| Longhorn | `longhorn-system` | ✅ | — | v1.x |
| Cert Manager | `cert-manager` | ✅ | — | v1.14.5 |
| Sealed Secrets | `kube-system` | ✅ | — | latest |
| Technitium DNS | `dns` | ✅ | Longhorn 2Gi | latest |
| Monitoring (Grafana + Prometheus) | `monitoring` | ✅ | Longhorn 5Gi + 20Gi | kube-prometheus-stack |
| **K3s** | — | — | — | **v1.36.0+k3s1** |
| Zabbix | `zabbix` | ✅ | Longhorn 10Gi | 7.0.26 |
| Kubernetes Dashboard | `kubernetes-dashboard` | ✅ | — | latest |

---

## Histórico de Etapas Concluídas

### Fase 1 — GitOps Base
- [x] ArgoCD instalado e self-managed via Git
- [x] Projeto `platform` criado no ArgoCD
- [x] Root App (App of Apps) configurado
- [x] Todos os apps migrados para ArgoCD

### Fase 2 — Infraestrutura
- [x] Longhorn instalado como StorageClass default
- [x] `local-path` removido como default
- [x] Cert-manager com ClusterIssuer self-signed via GitOps
- [x] Sealed Secrets para senhas/TLS no Git

### Fase 3 — Networking
- [x] Traefik como ingress controller (K3s default)
- [x] Technitium DNS como DNS server interno
- [x] Ingresses criados para todos os serviços
- [x] TLS self-signed em todos os ingresses

### Fase 4 — Migração de Storage (local-path → Longhorn)
- [x] Grafana PVC migrado para Longhorn (5Gi)
- [x] Prometheus PVC migrado para Longhorn (20Gi)
- [x] Zabbix PostgreSQL PVC migrado para Longhorn (10Gi)
- [x] Dados do Zabbix restaurados (394 hosts, 17931 items)

### Fase 5 — Zabbix
- [x] Zabbix Agent configurado em k8s-cp e k8s-worker
- [x] Zabbix atualizado para 7.0.26
- [x] Frontend conectando ao server corretamente

---

## Melhorias Futuras

| Item | Prioridade | Descrição |
|---|---|---|
| AlertManager receivers | Alta | Configurar notificações Telegram/email |
| Backup externo Longhorn | Alta | S3 ou NFS para backup dos volumes |
| Resource limits | Média | Definir requests/limits para todos os pods |
| Network Policies | Média | Isolar namespaces por política |
| Zabbix monitorar K3s | Média | Templates para monitorar nodes e pods |
| Grafana dashboards no Git | Média | Persistir dashboards como ConfigMaps |
| Let's Encrypt | Baixa | Migrar para certificados públicos válidos |
| Multi-cluster | Baixa | Expandir para segundo cluster |


---

## Melhorias Futuras

| Item | Prioridade | Descrição |
|---|---|---|
| **LLM/AI (Ollama)** | Alta | Deploy modelos de IA locais (llama3, mistral) |
| AlertManager receivers | Alta | Configurar notificações Telegram/email |
| Backup externo Longhorn | Alta | S3 ou NFS para backup dos volumes |
| Resource limits | Média | Definir requests/limits para todos os pods |
| Network Policies | Média | Isolar namespaces por política |
| Zabbix monitorar K3s | Média | Templates para monitorar nodes e pods |
| Grafana dashboards no Git | Média | Persistir dashboards como ConfigMaps |
| Let's Encrypt | Baixa | Migrar para certificados públicos válidos |
| Multi-cluster | Baixa | Expandir para segundo cluster |

---

## Log de Atualizações

| Data | Componente | De | Para |
|---|---|---|---|
| 2026-05-20 | K3s | v1.34.3+k3s1 | **v1.36.0+k3s1** |
| 2026-05-20 | kube-prometheus-stack | 81.5.0 | **82.2.0** |
| 2026-05-19 | Zabbix | 7.0.23 | **7.0.26** |
| 2026-05-19 | Storage | local-path | **Longhorn** (PVCs migrados) |


---

## Evoluções de IA — Análise de Impactos

### 1. Web Search Tools no Open WebUI

**Objetivo:** Adicionar capacidade de busca em tempo real ao modelo local via DuckDuckGo/Brave Search APIs.

**Impactos Positivos:**
| Aspecto | Descrição |
|---|---|
| **Dados atualizados** | Modelo acessa informações pós-2024 (treinamento dos modelos) |
| **Privacidade parcial** | Queries de busca saem, mas prompts/locais ficam no cluster |
| **Custo** | DuckDuckGo gratuito; Brave Search tem tier gratuito |
| **Integração** | Funciona com todos os modelos locais (llama3, mistral, etc) |

**Impactos Negativos:**
| Aspecto | Descrição |
|---|---|
| **Privacidade reduzida** | Termos de busca expostos à API externa |
| **Latência** | +2-5s por query (busca web + processamento LLM) |
| **Rate limits** | APIs gratuitas têm limites diários (ex: 100-1000 queries) |
| **Dependência externa** | Se API cai, funcionalidade offline fica indisponível |
| **Configuração** | Requer API keys e setup de tools no WebUI |

**Alternativas Consideradas:**
| Opção | Custo | Privacidade | Facilidade |
|---|---|---|---|
| DuckDuckGo API | Grátis | Média | Fácil |
| Brave Search API | Grátis (limitado) | Média | Fácil |
| Google Custom Search | Pago | Baixa | Média |
| Perplexity Pro | ~R$60/mês | Baixa | Plug-and-play |

**Recomendação:** Implementar com **DuckDuckGo** (gratuito, sem login) para uso ocasional. Manter 100% offline como default.

**Status:** 🔄 Análise de requisitos

---

### 2. RAG com Documentação do Cluster

**Objetivo:** Indexar documentação K3s, manifests do GitOps, runbooks para consulta via IA.

**Impactos:**
- **Positivo:** Assistente responde sobre ARQUITETURA ESPECÍFICA do seu cluster
- **Negativo:** Requer embedding models (mais RAM/GPU)
- **Tecnologia:** ChromaDB/Pinecone + embeddings local (nomic-embed-text)

**Status:** 📋 Backlog

