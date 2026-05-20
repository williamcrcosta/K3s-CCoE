# Ollama no Windows Host com GPU AMD RX 7900 XTX

> Configuração para usar a GPU física do Windows enquanto mantém o cluster K3s em VMs.

---

## Arquitetura

```
Windows Host (192.168.159.1)
├── RX 7900 XTX 24GB → Ollama (GPU acelerada)
└── Porta 11434 aberta ←───┐
                             │
Cluster K3s                 │
├── Open WebUI (VM) ─────────┘
└── Apps usam http://192.168.159.1:11434
```

---

## 1. Instalar Ollama no Windows

### Download
```powershell
# PowerShell como Admin
# Baixar do site oficial:
# https://ollama.com/download/windows

# Ou via winget:
winget install Ollama.Ollama
```

### Verificar instalação
```powershell
ollama --version
# Deve mostrar: ollama version is x.x.x
```

---

## 2. Configurar GPU AMD (ROCm)

A RX 7900 XTX usa **AMD ROCm** para aceleração.

### Verificar se ROCm está instalado
```powershell
# Ollama já inclui ROCm para RDNA3 (7900 XTX)
# Verificar se GPU é detectada:
ollama ps
```

Se mostrar algo como:
```
NAME    ID    SIZE    PROCESSOR    UNTIL
```
Significa que a GPU está pronta!

---

## 3. Configurar Ollama para Rede Local

### Editar variáveis de ambiente do sistema
```powershell
# PowerShell como Admin
[Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0:11434", "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE", "5m", "Machine")
```

### Ou via interface gráfica:
1. `Win + R` → `sysdm.cpl` → Enter
2. Aba "Avançado" → "Variáveis de Ambiente"
3. "Novas...":
   - Nome: `OLLAMA_HOST`
   - Valor: `0.0.0.0:11434`
4. OK → OK

### Reiniciar Ollama
```powershell
# Parar Ollama
Stop-Process -Name "ollama" -Force

# Iniciar novamente
ollama serve
```

---

## 4. Liberar Firewall do Windows

### Via PowerShell (Admin)
```powershell
# Criar regra de entrada para porta 11434
New-NetFirewallRule -DisplayName "Ollama API" `
  -Direction Inbound `
  -LocalPort 11434 `
  -Protocol TCP `
  -Action Allow

# Verificar regra criada
Get-NetFirewallRule -DisplayName "Ollama API"
```

### Ou via interface:
1. `Win + R` → `wf.msc` → Enter
2. "Regras de Entrada" → "Nova Regra..."
3. Porta → TCP → 11434
4. Permitir conexão
5. Nome: "Ollama API"

---

## 5. Testar Conexão do Cluster

### Do k8s-cp, testar conectividade:
```bash
# Testar se Windows host responde
curl http://192.168.159.1:11434/api/tags
```

Se retornar lista de modelos (vazia inicialmente), funcionou!

---

## 6. Configurar Open WebUI no Cluster

### Editar deployment para apontar para Windows host
```bash
# No k8s-cp
kubectl patch deployment open-webui -n ollama --type merge -p '{
  "spec": {
    "template": {
      "spec": {
        "containers": [{
          "name": "webui",
          "env": [
            {"name": "OLLAMA_BASE_URL", "value": "http://192.168.159.1:11434"},
            {"name": "ENABLE_SIGNUP", "value": "false"},
            {"name": "DEFAULT_LOCALE", "value": "pt-BR"}
          ]
        }]
      }
    }
  }
}'
```

### Verificar se WebUI reiniciou
```bash
kubectl rollout status deployment open-webui -n ollama
```

---

## 7. Baixar Modelos (no Windows)

Com a GPU, downloads são rápidos e inferência é instantânea!

```powershell
# PowerShell normal

# Modelo geral (4.7GB)
ollama pull llama3:8b

# Modelo para código/Terraform (3.8GB)
ollama pull codellama:7b

# Modelo para escrita criativa (4.1GB)
ollama pull mistral:7b

# Opcional: Modelo maior se quiser (8.0GB)
ollama pull llama3.1:8b
```

---

## 8. Acessar e Usar

### URL de acesso
```
https://ai.wcrpc.lan
```

### Selecionar modelo no dropdown
- `llama3:8b` → Infra, kubectl, troubleshooting
- `codellama:7b` → Terraform, código, scripts
- `mistral:7b` → Blog, escrita criativa

---

## Comandos Úteis (Windows)

```powershell
# Ver modelos instalados
ollama list

# Remover modelo
ollama rm mistral:7b

# Informações do sistema
ollama ps

# Logs do Ollama
# C:\Users\<seu-usuario>\.ollama\logs\server.log

# Parar Ollama
Stop-Process -Name "ollama" -Force

# Iniciar Ollama manualmente
ollama serve
```

---

## Troubleshooting

### Erro: "cannot connect to 192.168.159.1:11434"
```powershell
# Verificar se Ollama está rodando
Get-Process | Where-Object {$_.Name -like "*ollama*"}

# Verificar porta
netstat -an | findstr 11434
# Deve mostcar: 0.0.0.0:11434 LISTENING
```

### Erro: Firewall bloqueando
```powershell
# Verificar regra
Get-NetFirewallRule -DisplayName "Ollama API"

# Se não existir, criar novamente
```

### GPU não detectada
```powershell
# Verificar drivers AMD
# Baixar últimos drivers: https://www.amd.com/support

# Testar com CPU apenas (lento mas funciona)
[Environment]::SetEnvironmentVariable("OLLAMA_GPU_OVERHEAD", "1", "Machine")
```

---

## Performance Esperada

| Modelo | Com GPU RX 7900 XTX | Sem GPU (CPU) |
|---|---|---|
| llama3:8b | ~50 tokens/s | ~5 tokens/s |
| codellama:7b | ~60 tokens/s | ~6 tokens/s |
| mistral:7b | ~55 tokens/s | ~5 tokens/s |

**Resposta típica:** 1-3 segundos (vs 20-40s em CPU)

---

## Vantagens desta Configuração

✅ **GPU 100% utilizada** — RX 7900 XTX com ROCm
✅ **Sem mudar VMs** — Cluster K3s intacto
✅ **Setup rápido** — 15 minutos
✅ **Fácil manutenção** — Atualizar Ollama no Windows é simples
✅ **24GB VRAM** — Roda modelos grandes (até 70B com quantização)

---

## Evolução Futura

Se quiser integrar ainda mais:
- Deploy **NVIDIA Device Plugin** no K3s (para futura GPU NVIDIA dedicada)
- Usar **Ollama no Windows** como backend para outros apps no cluster
- Configurar **Load Balancer** entre múltiplas GPUs (se adicionar mais)

