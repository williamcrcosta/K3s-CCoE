# Configuração Persistente do Ollama no Windows

## Problema: Ollama perde configuração OLLAMA_HOST após reboot

## Solução: Script de inicialização persistente

### 1. Criar script de inicialização (executar uma vez no Windows)

```powershell
# PowerShell como Admin

# Criar diretório de scripts
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\ollama-scripts"

# Criar script de inicialização
$startupScript = @"
@echo off
echo Iniciando Ollama com rede aberta...
set OLLAMA_HOST=0.0.0.0:11434
set OLLAMA_KEEP_ALIVE=5m
"C:\Users\William\AppData\Local\Programs\Ollama\ollama.exe" serve
"@

$startupScript | Out-File -FilePath "$env:USERPROFILE\ollama-scripts\start-ollama-network.bat" -Encoding ASCII

# Criar atalho no Startup do Windows
$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Ollama-Network.lnk")
$Shortcut.TargetPath = "$env:USERPROFILE\ollama-scripts\start-ollama-network.bat"
$Shortcut.WorkingDirectory = "$env:USERPROFILE\ollama-scripts"
$Shortcut.Save()

Write-Host "✅ Ollama configurado para iniciar automaticamente com rede aberta!"
Write-Host "📝 Próximo reboot, Ollama já estará disponível em 0.0.0.0:11434"
```

### 2. Desabilitar Ollama original (para não conflitar)

```powershell
# Remover ollama original do startup (se existir)
Remove-Item "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Ollama.lnk" -ErrorAction SilentlyContinue
```

### 3. Testar após criar script

```powershell
# Executar script manualmente para testar
& "$env:USERPROFILE\ollama-scripts\start-ollama-network.bat"
```

---

## Alternativa: Variável de ambiente persistente (mais limpa)

```powershell
# PowerShell como Admin

# Definir permanentemente no sistema
[Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0:11434", "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE", "5m", "Machine")

# Configurar Ollama para iniciar como serviço (se ainda não for)
# Isso garante que ele sempre use as variáveis
```

---

## Resumo Pós-Reboot

**Automaticamente:**
1. Ollama inicia com `OLLAMA_HOST=0.0.0.0:11434`
2. Cluster K3s sobe (Longhorn, ArgoCD, WebUI)
3. Open WebUI reconecta no Ollama

**Manualmente (se não funcionar):**
1. Verificar se Ollama está rodando no Windows
2. Executar script de inicialização
3. Reiniciar deployment no K3s (se necessário)

