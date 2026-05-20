# Pós-Reboot — Como Tudo Volta a Funcionar

## Após ligar o PC:

### 1. Windows (Host com GPU)

**Opção A: Iniciar Ollama manualmente**
```powershell
# PowerShell como Admin
$env:OLLAMA_HOST="0.0.0.0:11434"
ollama serve
```

**Opção B: Criar atalho automático (recomendado)**
```powershell
# Criar script de inicialização
$script = @"
@echo off
set OLLAMA_HOST=0.0.0.0:11434
start "" "C:\Users\William\AppData\Local\Programs\Ollama\ollama.exe" serve
"@
$script | Out-File -FilePath "$env:USERPROFILE\start-ollama.bat" -Encoding ASCII

# Adicionar ao Startup do Windows
$startupPath = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
Copy-Item "$env:USERPROFILE\start-ollama.bat" $startupPath
```

**Opção C: Serviço Windows (avançado)**
```powershell
# Criar serviço Windows para Ollama
# Baixar NSSM (Non-Sucking Service Manager)
# Configurar serviço para iniciar automaticamente
```

### 2. Verificar se Ollama está no ar
```powershell
# Teste local
curl http://localhost:11434/api/tags

# Deve mostrar os modelos
```

---

### 3. Cluster K3s (VMs)

O cluster sobe automaticamente, mas verifique:

```bash
# No k8s-cp
~/cluster-health.sh

# Se Open WebUI estiver com erro:
kubectl rollout restart deployment open-webui -n ollama
```

---

### 4. Testar Conectividade

No **k8s-cp**:
```bash
curl http://192.168.159.1:11434/api/tags
# Deve retornar lista de modelos
```

---

### 5. Acessar
```
https://ai.wcrpc.lan
```

---

## Checklist Visual (após ligar PC)

- [ ] Ollama iniciou no Windows (ícone na bandeja)
- [ ] Pods do cluster estão Running
- [ ] curl para 192.168.159.1:11434 funciona
- [ ] https://ai.wcrpc.lan carrega

