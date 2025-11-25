#!/bin/bash
# Script para deploy automático na Azure
# Execute: bash deploy_azure.sh

set -e

echo "🚀 DEPLOYMENT NA AZURE"
echo "======================================"

# Configurações
RESOURCE_GROUP="financeiro-rg"
APP_NAME="gestor-financeiro-app"
DB_NAME="financeiro-db"
LOCATION="eastus"
DB_ADMIN="admin"

echo "1️⃣  Criando grupo de recursos..."
az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION

echo "2️⃣  Criando banco de dados PostgreSQL..."
az postgres flexible-server create \
  --resource-group $RESOURCE_GROUP \
  --name $DB_NAME \
  --admin-user $DB_ADMIN \
  --admin-password "Senha@123456" \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --storage-size 32 \
  --version 14

echo "3️⃣  Criando plano de app service..."
az appservice plan create \
  --name "${APP_NAME}-plan" \
  --resource-group $RESOURCE_GROUP \
  --sku B1 \
  --is-linux

echo "4️⃣  Criando web app..."
az webapp create \
  --resource-group $RESOURCE_GROUP \
  --plan "${APP_NAME}-plan" \
  --name $APP_NAME \
  --runtime "PYTHON:3.11"

echo "5️⃣  Configurando variáveis de ambiente..."
DATABASE_URL="postgresql://${DB_ADMIN}:Senha@123456@${DB_NAME}.postgres.database.azure.com:5432/financeiro"

az webapp config appsettings set \
  --resource-group $RESOURCE_GROUP \
  --name $APP_NAME \
  --settings \
    FLASK_ENV=production \
    FLASK_DEBUG=0 \
    FLASK_SECRET_KEY="sua-chave-secreta-aqui" \
    DATABASE_URL="$DATABASE_URL" \
    SESSION_COOKIE_SECURE=true \
    SESSION_COOKIE_HTTPONLY=true

echo "6️⃣  Preparando código para deploy..."
zip -r deploy.zip . \
  -x ".venv/*" ".git/*" "__pycache__/*" "*.pyc" ".DS_Store" \
  -x "*.log" ".env" "*.db"

echo "7️⃣  Enviando código..."
az webapp deployment source config-zip \
  --resource-group $RESOURCE_GROUP \
  --name $APP_NAME \
  --src deploy.zip

echo "8️⃣  Executando migrações..."
az webapp remote-build --resource-group $RESOURCE_GROUP --name $APP_NAME

echo ""
echo "✅ DEPLOYMENT CONCLUÍDO!"
echo ""
echo "URL da aplicação:"
echo "https://${APP_NAME}.azurewebsites.net"
echo ""
echo "Próximos passos:"
echo "1. Aguarde 2-3 minutos para inicialização"
echo "2. Acesse a URL acima"
echo "3. Verifique logs: az webapp log tail --resource-group $RESOURCE_GROUP --name $APP_NAME"
echo ""
