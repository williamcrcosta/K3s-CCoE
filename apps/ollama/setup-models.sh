#!/bin/bash
# Script para baixar modelos no Ollama
# Uso: ./setup-models.sh

echo "Baixando modelos para Ollama..."
echo "Isso pode levar 10-30 minutos dependendo da conexão"
echo ""

OLLAMA_POD=$(kubectl get pod -n ollama -l app=ollama -o jsonpath='{.items[0].metadata.name}')

if [ -z "$OLLAMA_POD" ]; then
    echo "ERRO: Pod Ollama não encontrado"
    echo "Deploy ollama primeiro: kubectl apply -k apps/ollama/"
    exit 1
fi

echo "1. Baixando llama3:8b (modelo geral - ~4.7GB)"
kubectl exec -n ollama $OLLAMA_POD -- ollama pull llama3:8b

echo ""
echo "2. Baixando codellama:7b (código/Terraform - ~3.8GB)"
kubectl exec -n ollama $OLLAMA_POD -- ollama pull codellama:7b

echo ""
echo "3. Baixando mistral:7b (escrita criativa - ~4.1GB)"
kubectl exec -n ollama $OLLAMA_POD -- ollama pull mistral:7b

echo ""
echo "✅ Modelos baixados!"
echo ""
echo "Total: ~12.6GB de modelos"
echo ""
echo "Para usar:"
echo "  - Acesse: https://ai.wcrpc.lan"
echo "  - Selecione o modelo no dropdown"
echo ""
echo "Uso recomendado:"
echo "  - llama3:8b    → Perguntas gerais, infra, kubectl"
echo "  - codellama:7b → Código Terraform, YAML, scripts"
echo "  - mistral:7b   → Escrita criativa, blog, revisão"
