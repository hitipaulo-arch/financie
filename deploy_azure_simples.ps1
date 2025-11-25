Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "DEPLOY INTERATIVO NO AZURE - GESTOR FINANCEIRO" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""

$AppName = "meu-gestor-financeiro"
$DbName = "meu-gestor-financeiro-db"

# PASSO 1
Write-Host ""
Write-Host "PASSO 1: Verificar Conta Azure" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host "Voce precisa de uma conta Microsoft para usar o Azure." -ForegroundColor White
Write-Host ""
Write-Host "Se tem conta: Digite S" -ForegroundColor Green
Write-Host "Se nao tem: Crie em https://azure.microsoft.com (gratis)" -ForegroundColor Yellow
Write-Host ""
$HasAccount = Read-Host "Tem conta Azure? (s/n)"
if ($HasAccount -ne "s") {
    Write-Host "Por favor, crie uma conta e volte aqui!" -ForegroundColor Red
    exit
}

# PASSO 2
Write-Host ""
Write-Host "PASSO 2: Acessar Azure Portal" -ForegroundColor Green
Write-Host "==============================" -ForegroundColor Green
Write-Host "Abrindo Azure Portal..." -ForegroundColor White
Start-Process "https://portal.azure.com"
Start-Sleep -Seconds 2
Write-Host "Pressione ENTER para continuar..."
Read-Host | Out-Null

# PASSO 3
Write-Host ""
Write-Host "PASSO 3: Criar App Service" -ForegroundColor Green
Write-Host "===========================" -ForegroundColor Green
Write-Host "1. Clique em '+ Criar um recurso'" -ForegroundColor Cyan
Write-Host "2. Procure 'App Service'" -ForegroundColor Cyan
Write-Host "3. Clique em 'Criar'" -ForegroundColor Cyan
Write-Host ""
Write-Host "Preencha o formulario:" -ForegroundColor Yellow
Write-Host "  - Grupo de recursos: $ResourceGroup" -ForegroundColor Gray
Write-Host "  - Nome: $AppName" -ForegroundColor Gray
Write-Host "  - Pilha: Python 3.11" -ForegroundColor Gray
Write-Host "  - SKU: F1 (Free)" -ForegroundColor Gray
Write-Host "  - Regiao: East US" -ForegroundColor Gray
Write-Host ""
Write-Host "Clique em 'Revisar + Criar' e 'Criar'" -ForegroundColor Yellow
Write-Host "Pressione ENTER para continuar..."
Read-Host | Out-Null

# PASSO 4
Write-Host ""
Write-Host "PASSO 4: Aguardando Criacao (2-3 minutos)" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
for ($i = 1; $i -le 6; $i++) {
    Write-Host "Aguardando... ($i/6)" -ForegroundColor Yellow
    Start-Sleep -Seconds 30
}

# PASSO 5
Write-Host ""
Write-Host "PASSO 5: Criar Banco PostgreSQL" -ForegroundColor Green
Write-Host "===============================" -ForegroundColor Green
Write-Host "1. Clique em '+ Criar um recurso'" -ForegroundColor Cyan
Write-Host "2. Procure 'Azure Database for PostgreSQL'" -ForegroundColor Cyan
Write-Host "3. Selecione 'Servidor Flexivel'" -ForegroundColor Cyan
Write-Host ""
Write-Host "Preencha:" -ForegroundColor Yellow
Write-Host "  - Nome: $DbName" -ForegroundColor Gray
Write-Host "  - Grupo de recursos: meu-gestor-financeiro" -ForegroundColor Gray
Write-Host "  - Versao: 14" -ForegroundColor Gray
Write-Host "  - Admin: postgres" -ForegroundColor Gray
Write-Host "  - Senha: Crie uma senha forte (ex: Senha123!@#)" -ForegroundColor Red
Write-Host "  - SKU: B1ms (free tier)" -ForegroundColor Gray
Write-Host ""
Write-Host "Clique em 'Revisar + Criar' e 'Criar'" -ForegroundColor Yellow
Write-Host "Pressione ENTER para continuar..."
Read-Host | Out-Null

# PASSO 6
Write-Host ""
Write-Host "PASSO 6: Configurar Firewall" -ForegroundColor Green
Write-Host "============================" -ForegroundColor Green
Write-Host "1. Va para seu PostgreSQL no Portal" -ForegroundColor Cyan
Write-Host "2. Clique em 'Seguranca' > 'Firewall'" -ForegroundColor Cyan
Write-Host "3. Marque 'Permitir acesso dos servicos do Azure'" -ForegroundColor Cyan
Write-Host "4. Clique 'Salvar'" -ForegroundColor Cyan
Write-Host ""
Write-Host "Pressione ENTER para continuar..."
Read-Host | Out-Null

# PASSO 7
Write-Host ""
Write-Host "PASSO 7: Obter String de Conexao" -ForegroundColor Green
Write-Host "=================================" -ForegroundColor Green
Write-Host "1. No PostgreSQL > 'Configuracoes' > 'Strings de conexao'" -ForegroundColor Cyan
Write-Host "2. Copie a URL de 'Aplicacoes Python'" -ForegroundColor Cyan
Write-Host ""
Write-Host "Exemplo:" -ForegroundColor Gray
Write-Host "  postgresql://postgres:senha@server.postgres.database.azure.com:5432/postgres" -ForegroundColor Gray
Write-Host ""
$DbUrl = Read-Host "Cole aqui a string de conexao (ou pressione ENTER para pular)"

# PASSO 8
Write-Host ""
Write-Host "PASSO 8: Configurar Variaveis de Ambiente" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "1. Va para seu App Service" -ForegroundColor Cyan
Write-Host "2. 'Configuracao' > 'Variaveis de ambiente'" -ForegroundColor Cyan
Write-Host "3. Clique em '+ Adicionar'" -ForegroundColor Cyan
Write-Host ""
Write-Host "Adicione:" -ForegroundColor Yellow
Write-Host "  - DATABASE_URL = (seu URL)" -ForegroundColor Gray
Write-Host "  - FLASK_ENV = production" -ForegroundColor Gray
Write-Host "  - DEBUG = False" -ForegroundColor Gray
Write-Host "  - SECRET_KEY = (gere uma chave aleatoria)" -ForegroundColor Gray
Write-Host ""
Write-Host "Clique 'Salvar'" -ForegroundColor Yellow
Write-Host "Pressione ENTER para continuar..."
Read-Host | Out-Null

# PASSO 9
Write-Host ""
Write-Host "PASSO 9: Conectar GitHub" -ForegroundColor Green
Write-Host "========================" -ForegroundColor Green
Write-Host "1. No App Service > 'Centro de Implantacao'" -ForegroundColor Cyan
Write-Host "2. Selecione 'GitHub'" -ForegroundColor Cyan
Write-Host "3. Clique 'Autorizar Azure'" -ForegroundColor Cyan
Write-Host "4. Faca login no GitHub" -ForegroundColor Cyan
Write-Host "5. Selecione seu repositorio e branch 'main'" -ForegroundColor Cyan
Write-Host "6. Clique 'Salvar'" -ForegroundColor Cyan
Write-Host ""
Write-Host "Azure fara o primeiro deploy automaticamente!" -ForegroundColor Yellow
Write-Host "Pressione ENTER para continuar..."
Read-Host | Out-Null

# PASSO 10
Write-Host ""
Write-Host "PASSO 10: Verificar Deployment" -ForegroundColor Green
Write-Host "==============================" -ForegroundColor Green
Write-Host "1. No App Service > 'Log de streaming'" -ForegroundColor Cyan
Write-Host "2. Procure por mensagens de sucesso" -ForegroundColor Cyan
Write-Host ""
Write-Host "Sucesso: Ver 'Application started'" -ForegroundColor Green
Write-Host "Erro: Ver 'Error' ou '502'" -ForegroundColor Red
Write-Host ""
Write-Host "Pressione ENTER para continuar..."
Read-Host | Out-Null

# PASSO 11
Write-Host ""
Write-Host "PASSO 11: Testar Aplicacao" -ForegroundColor Green
Write-Host "==========================" -ForegroundColor Green
Write-Host "1. App Service > 'Visao Geral'" -ForegroundColor Cyan
Write-Host "2. Copie a 'URL'" -ForegroundColor Cyan
Write-Host "3. Abra no navegador" -ForegroundColor Cyan
Write-Host ""
$AppUrl = Read-Host "Cole aqui a URL (ou ENTER para pular)"
if (![string]::IsNullOrEmpty($AppUrl)) {
    Write-Host "Abrindo..." -ForegroundColor Yellow
    Start-Process $AppUrl
    Start-Sleep -Seconds 2
}

# FINALIZAR
Write-Host ""
Write-Host "=====================================================" -ForegroundColor Green
Write-Host "PARABENS! Sua aplicacao esta online no Azure!" -ForegroundColor Green
Write-Host "=====================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Proximas etapas:" -ForegroundColor Yellow
Write-Host "  1. Criar usuario admin" -ForegroundColor Gray
Write-Host "  2. Testar endpoints da API" -ForegroundColor Gray
Write-Host "  3. Configurar dominio personalizado" -ForegroundColor Gray
Write-Host ""
Write-Host "Dica: Cada 'git push' no GitHub faz deploy automatico!" -ForegroundColor Cyan
Write-Host ""
