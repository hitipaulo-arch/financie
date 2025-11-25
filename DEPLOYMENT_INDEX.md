# 📚 Índice de Documentação de Deployment

## 🚀 Comece Aqui

1. **DEPLOY_RAPIDO.md** ⭐ (Leia Primeiro!)
   - 3 opções em 3 passos
   - Guia visual
   - Mais fácil

2. **DEPLOY_ONLINE.md** (Referência Completa)
   - Detalhes técnicos
   - Comparação das opções
   - Checklist de segurança

---

## 📦 Scripts de Deployment

### Para Heroku (Mais Fácil)
```bash
bash deploy_heroku.sh
```
- Deploy em 5 minutos
- Grátis (550h/mês)
- Ideal para prototipagem

### Para Azure (Recomendado)
```bash
bash deploy_azure.sh
```
- Deploy em 10 minutos
- 1º ano grátis
- Mais confiável

### Para VPS (Máximo Controle)
Ver seção "Opção 3" em `DEPLOY_ONLINE.md`

---

## 🛠️ Preparação

```bash
# Verificar se tudo está pronto
python prepare_production.py

# Criar arquivo de configuração
cp .env.example .env
nano .env  # Editar variáveis
```

---

## 📋 Arquivos Inclusos

```
gestor-financeiro/
├── DEPLOY_RAPIDO.md          (Guia rápido) ⭐
├── DEPLOY_ONLINE.md          (Guia completo)
├── DEPLOYMENT_INDEX.md       (Este arquivo)
├── Procfile                  (Heroku)
├── runtime.txt               (Python version)
├── .env.example              (Template de env)
├── prepare_production.py      (Verificação)
├── deploy_heroku.sh          (Script Heroku)
└── deploy_azure.sh           (Script Azure)
```

---

## 🎯 Fluxo Recomendado

```
1. Leia DEPLOY_RAPIDO.md
   ↓
2. Escolha uma opção (Heroku é mais fácil)
   ↓
3. Execute prepare_production.py
   ↓
4. Configure .env
   ↓
5. Execute script de deploy (deploy_*.sh)
   ↓
6. Teste em https://seu-app.com
```

---

## ⏱️ Tempo Estimado

| Etapa | Heroku | Azure | VPS |
|-------|--------|-------|-----|
| Setup | 5 min | 10 min | 30 min |
| Deploy | 5 min | 10 min | 15 min |
| Test | 5 min | 5 min | 5 min |
| **Total** | **15 min** | **25 min** | **50 min** |

---

## 💰 Custo Mensal

- **Heroku**: $0-50 (hibernação free)
- **Azure**: $0-100 (1º ano grátis)
- **VPS**: $5-10

---

## ❓ Qual Escolher?

### Heroku
- ✅ Mais fácil
- ✅ Deploy em 1 comando
- ⚠️ Hibernação (free)
- ✅ Ideal para começar

### Azure
- ✅ Mais profissional
- ✅ 1º ano grátis
- ✅ Escalável
- ✅ Melhor custo-benefício

### VPS
- ✅ Máximo controle
- ✅ Sem hibernação
- ⚠️ Mais complexo
- ✅ Maior controle de custos

**Recomendação: Comece com Heroku (5min), depois migre para Azure quando crescer**

---

## 🔗 Links Rápidos

- 🌐 **Heroku**: https://www.heroku.com
- 🌐 **Azure**: https://azure.microsoft.com
- 🌐 **DigitalOcean**: https://www.digitalocean.com
- 📚 **Documentação Heroku**: https://devcenter.heroku.com
- 📚 **Documentação Azure**: https://learn.microsoft.com/azure/

---

## ✅ Checklist Pré-Deploy

- [ ] Leu DEPLOY_RAPIDO.md
- [ ] Escolheu uma plataforma
- [ ] Executou prepare_production.py
- [ ] Criou arquivo .env
- [ ] Atualizou variáveis de ambiente
- [ ] Verificou se backend.py está sem erros
- [ ] Fez commit de todas as mudanças

---

## 🆘 Precisa de Ajuda?

1. **Erro durante deployment**: Ver logs
   - Heroku: `heroku logs --tail`
   - Azure: `az webapp log tail --name seu-app`

2. **Conexão ao banco de dados**: Verificar DATABASE_URL
3. **Módulo não encontrado**: Executar `pip install -r requirements.txt`
4. **Porta em uso**: Mudar porta em variáveis de ambiente

---

## 📞 Próximos Passos Após Deploy

1. ✅ Testar login
2. ✅ Criar uma transação
3. ✅ Acessar Open Finance
4. ✅ Configurar domínio próprio (opcional)
5. ✅ Ativar HTTPS (automaticamente em Heroku/Azure)
6. ✅ Configurar backups automáticos
7. ✅ Monitorar performance

---

## 🎓 Aprender Mais

Consulte `DEPLOY_ONLINE.md` para:
- Detalhes técnicos de cada plataforma
- Configuração de HTTPS
- Segurança em produção
- Migrações de banco de dados
- Troubleshooting avançado

---

**Pronto para colocar online? Comece com [DEPLOY_RAPIDO.md](DEPLOY_RAPIDO.md)! 🚀**
