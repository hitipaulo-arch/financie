#!/usr/bin/env python3
"""
Script para preparar a aplicação para produção.
Execute antes de fazer deploy.
"""

import os
import sys
import subprocess
from pathlib import Path

def check_requirements():
    """Verificar se os arquivos necessários existem."""
    print("📋 Verificando requisitos...")
    required_files = [
        'backend.py',
        'requirements.txt',
        'Procfile',
        'runtime.txt',
        '.env.example'
    ]
    
    for file in required_files:
        if os.path.exists(file):
            print(f"  ✅ {file}")
        else:
            print(f"  ❌ FALTANDO: {file}")
            return False
    return True

def check_environment():
    """Verificar configurações de produção."""
    print("\n🔐 Verificando segurança...")
    
    # Verificar se debug está desabilitado
    with open('backend.py', 'r', encoding='utf-8') as f:
        content = f.read()
        if 'debug=True' in content and 'if __name__' in content:
            print("  ⚠️  AVISO: Debug pode estar habilitado")
        else:
            print("  ✅ Debug desabilitado")
    
    # Verificar .env
    if os.path.exists('.env'):
        print("  ✅ Arquivo .env presente")
    else:
        print("  ❌ FALTANDO: Arquivo .env")
        print("     Copie: cp .env.example .env")
        print("     E atualize as variáveis!")
        return False
    
    return True

def check_dependencies():
    """Verificar se todas as dependências estão em requirements.txt."""
    print("\n📦 Verificando dependências...")
    
    required_packages = [
        'flask',
        'sqlalchemy',
        'marshmallow',
        'gunicorn',
        'python-dotenv',
        'requests'
    ]
    
    if os.path.exists('requirements.txt'):
        with open('requirements.txt', 'r') as f:
            content = f.read().lower()
            for pkg in required_packages:
                if pkg in content:
                    print(f"  ✅ {pkg}")
                else:
                    print(f"  ⚠️  {pkg} pode estar faltando")
    else:
        print("  ❌ requirements.txt não encontrado")
        return False
    
    return True

def create_production_checklist():
    """Criar checklist de produção."""
    print("\n" + "="*60)
    print("✅ CHECKLIST PRÉ-DEPLOYMENT")
    print("="*60)
    
    checklist = [
        ("Variáveis de ambiente configuradas", ".env atualizado"),
        ("Debug desabilitado", "FLASK_ENV=production"),
        ("HTTPS configurado", "SSL/TLS ativo"),
        ("Banco de dados criado", "PostgreSQL em produção"),
        ("Migrações executadas", "alembic upgrade head"),
        ("Backup automático configurado", "Daily backups"),
        ("Logging centralizado", "Logs em arquivo/serviço"),
        ("Rate limiting", "Já implementado"),
        ("CORS configurado", "Para domínio produção"),
        ("CSRF reabilitado", "Remover @csrf.exempt"),
    ]
    
    for i, (item, detail) in enumerate(checklist, 1):
        print(f"{i}. [ ] {item}")
        print(f"   └─ {detail}")
    
    print("\n" + "="*60)

def main():
    print("🚀 PREPARAR PARA DEPLOYMENT")
    print("="*60)
    
    # Verificações
    if not check_requirements():
        print("\n❌ Arquivos necessários não encontrados!")
        sys.exit(1)
    
    if not check_environment():
        print("\n⚠️  Configuração de segurança incompleta!")
        return False
    
    if not check_dependencies():
        print("\n⚠️  Dependências podem estar faltando!")
        print("   Execute: pip install -r requirements.txt")
    
    create_production_checklist()
    
    print("\n📝 Próximos passos:")
    print("\n1. HEROKU:")
    print("   heroku create seu-app-name")
    print("   git push heroku main")
    
    print("\n2. AZURE:")
    print("   az webapp deployment source config-zip ...")
    
    print("\n3. VPS:")
    print("   Seguir guia em DEPLOY_ONLINE.md")
    
    print("\n✅ Aplicação pronta para deployment!")

if __name__ == "__main__":
    main()
