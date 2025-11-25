#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Deploy interativo no Azure para Gestor Financeiro
    
.DESCRIPTION
    Este script guia você através de todo o processo de deployment no Azure
    passo a passo de forma interativa.
#>

Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║      🚀 DEPLOY INTERATIVO NO AZURE - GESTOR FINANCEIRO      ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Variáveis
$AppName = "meu-gestor-financeiro"
$DbName = "meu-gestor-financeiro-db"
$ResourceGroup = "meu-gestor-financeiro"
$Region = "eastus"
$PythonVersion = "3.11"

function Show-Step($number, $title) {
    Write-Host ""
    Write-Host "╔═══════════════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║ PASSO $number : $title" -ForegroundColor Green
    Write-Host "╚═══════════════════════════════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""
}

function Ask-Continue {
    Write-Host "Pressione ENTER para continuar..." -ForegroundColor Yellow
    Read-Host | Out-Null
}

function Open-Link($url, $description) {
    Write-Host "Abrindo: $description" -ForegroundColor Cyan
    Write-Host "URL: $url" -ForegroundColor Gray
    Start-Process $url
    Start-Sleep -Seconds 2
}

# PASSO 1
Show-Step 1 "Verificar Conta Azure"
Write-Host "Você precisa de uma conta Microsoft para usar o Azure." -ForegroundColor White
Write-Host ""
Write-Host "✅ Se já tem conta: Prossiga" -ForegroundColor Green
Write-Host "❌ Se não tem: Crie em https://azure.microsoft.com (grátis)" -ForegroundColor Yellow
Write-Host ""
$HasAccount = Read-Host "Tem conta Azure? (s/n)"
if ($HasAccount -ne "s") {
    Write-Host "Por favor, crie uma conta e volte aqui!" -ForegroundColor Red
    exit
}

# PASSO 2
Show-Step 2 "Acessar Azure Portal"
Write-Host "Vou abrir o Azure Portal para você..." -ForegroundColor White
Open-Link "https://portal.azure.com" "Azure Portal"
Ask-Continue

# PASSO 3
Show-Step 3 "Criar Recurso (App Service)"
Write-Host "Siga estos passos no Azure Portal:" -ForegroundColor White
Write-Host ""
Write-Host "1. Clique em '+ Criar um recurso'" -ForegroundColor Cyan
Write-Host "2. Procure 'App Service'" -ForegroundColor Cyan
Write-Host "3. Clique em 'Criar'" -ForegroundColor Cyan
Write-Host ""
Write-Host "Preencha o formulário:" -ForegroundColor Yellow
Write-Host "  • Grupo de recursos: $ResourceGroup" -ForegroundColor Gray
Write-Host "  • Nome: $AppName" -ForegroundColor Gray
Write-Host "  • Pilha de tempo de execução: Python 3.11" -ForegroundColor Gray
Write-Host "  • SKU: F1 (Free)" -ForegroundColor Gray
Write-Host "  • Região: $Region" -ForegroundColor Gray
Write-Host ""
Write-Host "Clique em 'Revisar + Criar' e 'Criar'" -ForegroundColor Yellow
Ask-Continue

# PASSO 4
Show-Step 4 "Aguardar Criação (2-3 minutos)"
Write-Host "Azure está criando seu App Service..." -ForegroundColor White
Write-Host "Você pode monitorar em: https://portal.azure.com/microsoft.onmicrosoft.com" -ForegroundColor Gray
Write-Host ""
$i = 0
while ($i -lt 6) {
    Write-Host "⏳ Aguardando..." -ForegroundColor Yellow
    Start-Sleep -Seconds 30
    $i++
}

# PASSO 5
Show-Step 5 "Criar Banco de Dados PostgreSQL"
Write-Host "Siga estos passos:" -ForegroundColor White
Write-Host ""
Write-Host "1. Clique em '+ Criar um recurso'" -ForegroundColor Cyan
Write-Host "2. Procure 'Azure Database for PostgreSQL'" -ForegroundColor Cyan
Write-Host "3. Selecione 'Servidor Flexível'" -ForegroundColor Cyan
Write-Host ""
Write-Host "Preencha:" -ForegroundColor Yellow
Write-Host "  • Nome: $DbName" -ForegroundColor Gray
Write-Host "  • Grupo de recursos: $ResourceGroup" -ForegroundColor Gray
Write-Host "  • Versão: 14" -ForegroundColor Gray
Write-Host "  • Admin: postgres" -ForegroundColor Gray
Write-Host "  • Senha: Crie uma senha forte!" -ForegroundColor Red
Write-Host "  • SKU: B1ms (free tier)" -ForegroundColor Gray
Write-Host ""
Write-Host "Clique em 'Revisar + Criar' e 'Criar'" -ForegroundColor Yellow
Ask-Continue

# PASSO 6
Show-Step 6 "Configurar Firewall do Banco"
Write-Host "Importante: Permitir acesso do App Service ao Banco" -ForegroundColor White
Write-Host ""
Write-Host "1. Vá para seu PostgreSQL no Portal" -ForegroundColor Cyan
Write-Host "2. Clique em 'Segurança' > 'Firewall'" -ForegroundColor Cyan
Write-Host "3. Marque 'Permitir acesso dos serviços do Azure'" -ForegroundColor Cyan
Write-Host "4. Clique 'Salvar'" -ForegroundColor Cyan
Write-Host ""
Ask-Continue

# PASSO 7
Show-Step 7 "Obter String de Conexão"
Write-Host "Siga:" -ForegroundColor White
Write-Host ""
Write-Host "1. No PostgreSQL > 'Configurações' > 'Strings de conexão'" -ForegroundColor Cyan
Write-Host "2. Copie a URL de 'Aplicações Python'" -ForegroundColor Cyan
Write-Host ""
Write-Host "Deve parecer com:" -ForegroundColor Gray
Write-Host "  postgresql://postgres:senha@server.postgres.database.azure.com:5432/postgres" -ForegroundColor Gray
Write-Host ""
$DbUrl = Read-Host "Cole aqui a string de conexão"

# PASSO 8
Show-Step 8 "Configurar Variáveis de Ambiente"
Write-Host "Siga:" -ForegroundColor White
Write-Host ""
Write-Host "1. Vá para seu App Service" -ForegroundColor Cyan
Write-Host "2. 'Configuração' > 'Variáveis de ambiente'" -ForegroundColor Cyan
Write-Host "3. Clique em '+ Adicionar'" -ForegroundColor Cyan
Write-Host ""
Write-Host "Adicione estas variáveis:" -ForegroundColor Yellow
Write-Host "  • DATABASE_URL = $DbUrl" -ForegroundColor Gray
Write-Host "  • FLASK_ENV = production" -ForegroundColor Gray
Write-Host "  • DEBUG = False" -ForegroundColor Gray
Write-Host "  • SECRET_KEY = (gere uma chave aleatória de 40 caracteres)" -ForegroundColor Gray
Write-Host ""
Write-Host "Clique 'Salvar'" -ForegroundColor Yellow
Ask-Continue

# PASSO 9
Show-Step 9 "Conectar Repositório GitHub"
Write-Host "Siga:" -ForegroundColor White
Write-Host ""
Write-Host "1. No App Service > 'Centro de Implantação'" -ForegroundColor Cyan
Write-Host "2. Selecione 'GitHub' como origem" -ForegroundColor Cyan
Write-Host "3. Clique 'Autorizar Azure'" -ForegroundColor Cyan
Write-Host "4. Faça login no GitHub" -ForegroundColor Cyan
Write-Host "5. Selecione seu repositório e branch 'main'" -ForegroundColor Cyan
Write-Host "6. Clique 'Salvar'" -ForegroundColor Cyan
Write-Host ""
Write-Host "⏳ Azure fará o primeiro deploy automaticamente!" -ForegroundColor Yellow
Ask-Continue

# PASSO 10
Show-Step 10 "Verificar Deployment"
Write-Host "Acompanhe:" -ForegroundColor White
Write-Host ""
Write-Host "1. No App Service > 'Log de streaming'" -ForegroundColor Cyan
Write-Host "2. Procure por mensagens de sucesso" -ForegroundColor Cyan
Write-Host ""
Write-Host "✅ Sucesso: Vê 'Application started'" -ForegroundColor Green
Write-Host "❌ Erro: Vê 'Error' ou '502'" -ForegroundColor Red
Write-Host ""
Ask-Continue

# PASSO 11
Show-Step 11 "Testar Aplicação"
Write-Host "Siga:" -ForegroundColor White
Write-Host ""
Write-Host "1. Volte para App Service > 'Visão Geral'" -ForegroundColor Cyan
Write-Host "2. Copie a 'URL': https://seu-app.azurewebsites.net" -ForegroundColor Cyan
Write-Host "3. Abra no navegador" -ForegroundColor Cyan
Write-Host ""
$AppUrl = Read-Host "Cole aqui a URL do seu App (ex: https://seu-app.azurewebsites.net)"
Write-Host "Abrindo..." -ForegroundColor Yellow
Start-Process $AppUrl
Ask-Continue

# FINALIZAÇÃO
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║                  ✨ PARABÉNS! ✨                            ║" -ForegroundColor Green
Write-Host "║     Sua aplicação está online no Azure!                      ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "🎯 Sua aplicação: $AppUrl" -ForegroundColor Cyan
Write-Host ""
Write-Host "📱 Próximas etapas:" -ForegroundColor Yellow
Write-Host "  1. Criar usuário admin" -ForegroundColor Gray
Write-Host "  2. Testar endpoints da API" -ForegroundColor Gray
Write-Host "  3. Configurar domínio personalizado" -ForegroundColor Gray
Write-Host "  4. Ativar HTTPS" -ForegroundColor Gray
Write-Host ""
Write-Host "💡 Dica: Cada 'git push' no GitHub faz deploy automático!" -ForegroundColor Cyan
Write-Host ""
