#!/bin/bash
# Script para deploy automático no Heroku
# Execute: bash deploy_heroku.sh

set -e

echo "🚀 DEPLOYMENT NO HEROKU"
echo "======================================"

APP_NAME="gestor-financeiro-$(date +%s | tail -c 5)"

echo "1️⃣  Checando se Heroku CLI está instalado..."
if ! command -v heroku &> /dev/null; then
    echo "❌ Heroku CLI não encontrada"
    echo "Instale em: https://devcenter.heroku.com/articles/heroku-cli"
    exit 1
fi

echo "✅ Heroku CLI encontrada"

echo ""
echo "2️⃣  Fazendo login no Heroku..."
heroku login

echo ""
echo "3️⃣  Criando aplicação..."
heroku create $APP_NAME

echo ""
echo "4️⃣  Adicionando banco de dados PostgreSQL..."
heroku addons:create heroku-postgresql:mini --app $APP_NAME

echo ""
echo "5️⃣  Configurando variáveis de ambiente..."
heroku config:set FLASK_ENV=production --app $APP_NAME
heroku config:set FLASK_DEBUG=0 --app $APP_NAME
heroku config:set SECRET_KEY="sua-chave-secreta-aqui" --app $APP_NAME
heroku config:set SESSION_COOKIE_SECURE=true --app $APP_NAME

echo ""
echo "6️⃣  Fazendo deploy..."
git add .
git commit -m "Deploy para Heroku: $(date)"
git push heroku main

echo ""
echo "✅ DEPLOYMENT CONCLUÍDO!"
echo ""
echo "URL da aplicação:"
echo "https://${APP_NAME}.herokuapp.com"
echo ""
echo "Próximos passos:"
echo "1. Aguarde 2-3 minutos para inicialização"
echo "2. Acesse a URL acima"
echo "3. Verifique logs: heroku logs --tail --app $APP_NAME"
echo ""
