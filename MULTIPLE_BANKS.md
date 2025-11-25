# Suporte a Múltiplos Bancos - Guia de Implementação

## Visão Geral

Este documento descreve a arquitetura para suportar conexões simultâneas com múltiplos bancos via Open Finance Brasil.

## Arquitetura Atual

Atualmente, a aplicação suporta:
- ✅ Um único provider por configuração (SimulatedProvider ou OpenFinanceProvider)
- ✅ Múltiplos consentimentos (Consents) por usuário
- ✅ Campo `provider` no modelo Consent identificando a instituição

## Arquitetura Proposta - Múltiplos Bancos

### 1. Nova Tabela: BankConnection

```python
class BankConnection(Base):
    """Armazena configurações para múltiplas instituições bancárias."""
    __tablename__ = "bank_connections"
    __table_args__ = (
        Index('idx_bank_connection_user', 'user_id'),
        Index('idx_bank_connection_status', 'status'),
    )
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    bank_name = Column(String(128), nullable=False)  # "Banco do Brasil", "Nubank", etc.
    bank_code = Column(String(32), nullable=False)   # Código ISPB da instituição
    
    # Configurações específicas do banco
    base_url = Column(String(512), nullable=False)
    client_id = Column(String(256), nullable=False)
    client_secret = Column(String(512), nullable=False)  # Criptografado
    cert_path = Column(String(512), nullable=True)
    key_path = Column(String(512), nullable=True)
    
    status = Column(String(32), nullable=False)  # active | inactive | error
    last_sync = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    deleted_at = Column(DateTime, nullable=True)
```

### 2. Provider Factory

```python
class ProviderFactory:
    """Factory para criar providers específicos de cada banco."""
    
    @staticmethod
    def create_provider(bank_connection: BankConnection):
        """Cria um OpenFinanceProvider para uma conexão bancária específica."""
        if bank_connection.status != 'active':
            raise ValueError(f"Bank connection {bank_connection.bank_name} is not active")
        
        return OpenFinanceProvider(
            base_url=bank_connection.base_url,
            client_id=bank_connection.client_id,
            client_secret=bank_connection.client_secret,
            cert_path=bank_connection.cert_path,
            key_path=bank_connection.key_path
        )
    
    @staticmethod
    def get_all_providers_for_user(user_id: str, session) -> Dict[str, OpenFinanceProvider]:
        """Retorna todos os providers ativos de um usuário."""
        connections = session.query(BankConnection).filter(
            BankConnection.user_id == user_id,
            BankConnection.status == 'active',
            BankConnection.deleted_at.is_(None)
        ).all()
        
        return {
            conn.bank_code: ProviderFactory.create_provider(conn)
            for conn in connections
        }
```

### 3. Sincronização Multi-Banco

```python
@app.route("/api/users/<user_id>/openfinance/sync-all", methods=["POST"])
@limiter.limit("10 per hour")
def open_finance_sync_all(user_id):
    """
    Sincroniza transações de todos os bancos conectados pelo usuário.
    
    Resposta:
    {
        "status": "success",
        "banks_synced": 3,
        "total_imported": 45,
        "results": [
            {
                "bank": "Banco do Brasil",
                "bank_code": "00000000",
                "imported": 15,
                "skipped": 2,
                "status": "success"
            },
            {
                "bank": "Nubank",
                "bank_code": "18236120",
                "imported": 30,
                "skipped": 0,
                "status": "success"
            },
            {
                "bank": "Inter",
                "bank_code": "00416968",
                "imported": 0,
                "skipped": 0,
                "status": "error",
                "error": "OAuth token expired"
            }
        ]
    }
    """
    start_time = time.time()
    
    # Obter todos os providers do usuário
    providers = ProviderFactory.get_all_providers_for_user(user_id, session_db)
    
    if not providers:
        return jsonify({"error": "no_active_banks"}), 404
    
    results = []
    total_imported = 0
    total_skipped = 0
    
    for bank_code, provider in providers.items():
        try:
            # Buscar consent ativo para este banco
            consent = session_db.query(Consent).filter(
                Consent.user_id == user_id,
                Consent.provider == bank_code,
                Consent.status == "active",
                Consent.deleted_at.is_(None)
            ).first()
            
            if not consent:
                results.append({
                    "bank_code": bank_code,
                    "status": "skipped",
                    "error": "no_active_consent"
                })
                continue
            
            # Sincronizar
            result = provider.sync(local_user_id=user_id, consent_id=consent.consent_id)
            
            # Processar transações (mesmo código do endpoint sync individual)
            imported, skipped = process_transactions(result, user_id, session_db)
            
            total_imported += imported
            total_skipped += skipped
            
            results.append({
                "bank_code": bank_code,
                "imported": imported,
                "skipped": skipped,
                "status": "success"
            })
            
            # Atualizar last_sync
            bank_conn = session_db.query(BankConnection).filter(
                BankConnection.user_id == user_id,
                BankConnection.bank_code == bank_code
            ).first()
            if bank_conn:
                bank_conn.last_sync = datetime.now(UTC)
                session_db.commit()
                
        except Exception as e:
            logger.error(f"Erro na sync do banco {bank_code}", extra={
                "user_id": user_id,
                "bank_code": bank_code,
                "error": str(e)
            })
            results.append({
                "bank_code": bank_code,
                "status": "error",
                "error": str(e)
            })
    
    duration_ms = (time.time() - start_time) * 1000
    
    return jsonify({
        "status": "success",
        "banks_synced": len([r for r in results if r["status"] == "success"]),
        "total_imported": total_imported,
        "total_skipped": total_skipped,
        "results": results,
        "duration_ms": round(duration_ms, 2)
    }), 200
```

### 4. Endpoints de Gerenciamento

```python
# Listar bancos conectados
@app.route("/api/users/<user_id>/banks", methods=["GET"])
def list_user_banks(user_id):
    connections = session_db.query(BankConnection).filter(
        BankConnection.user_id == user_id,
        BankConnection.deleted_at.is_(None)
    ).all()
    
    return jsonify({
        "banks": [
            {
                "id": conn.id,
                "bank_name": conn.bank_name,
                "bank_code": conn.bank_code,
                "status": conn.status,
                "last_sync": conn.last_sync.isoformat() if conn.last_sync else None
            }
            for conn in connections
        ]
    })

# Adicionar novo banco
@app.route("/api/users/<user_id>/banks", methods=["POST"])
def add_user_bank(user_id):
    """
    Payload:
    {
        "bank_name": "Banco do Brasil",
        "bank_code": "00000000",
        "base_url": "https://api.bb.com.br/open-banking",
        "client_id": "...",
        "client_secret": "...",
        "cert_path": "/path/to/cert.pem",
        "key_path": "/path/to/key.pem"
    }
    """
    data = request.get_json()
    
    # Criptografar client_secret antes de armazenar
    # TODO: Implementar criptografia com Fernet ou similar
    
    connection = BankConnection(
        user_id=user_id,
        bank_name=data['bank_name'],
        bank_code=data['bank_code'],
        base_url=data['base_url'],
        client_id=data['client_id'],
        client_secret=data['client_secret'],  # Deve ser criptografado
        cert_path=data.get('cert_path'),
        key_path=data.get('key_path'),
        status='active',
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC)
    )
    
    session_db.add(connection)
    session_db.commit()
    
    return jsonify({"id": connection.id, "status": "created"}), 201

# Remover banco
@app.route("/api/users/<user_id>/banks/<int:bank_id>", methods=["DELETE"])
def remove_user_bank(user_id, bank_id):
    connection = session_db.query(BankConnection).filter(
        BankConnection.id == bank_id,
        BankConnection.user_id == user_id,
        BankConnection.deleted_at.is_(None)
    ).first()
    
    if not connection:
        return jsonify({"error": "bank_not_found"}), 404
    
    # Soft delete
    connection.deleted_at = datetime.now(UTC)
    session_db.commit()
    
    return jsonify({"status": "deleted"}), 200
```

## Benefícios

### 1. **Visão Consolidada**
Usuário pode ver todas as transações de múltiplos bancos em um único lugar.

### 2. **Sincronização Paralela**
```python
import concurrent.futures

def sync_all_parallel(user_id, providers, session_db):
    """Sincroniza todos os bancos em paralelo."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_bank = {
            executor.submit(sync_single_bank, bank_code, provider, user_id): bank_code
            for bank_code, provider in providers.items()
        }
        
        results = []
        for future in concurrent.futures.as_completed(future_to_bank):
            bank_code = future_to_bank[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.error(f"Erro na sync paralela: {bank_code}", extra={"error": str(e)})
                results.append({"bank_code": bank_code, "status": "error", "error": str(e)})
        
        return results
```

### 3. **Gestão Centralizada**
Dashboard mostrando status de todas as conexões bancárias.

## Migração para Produção

### Checklist:
- [ ] Implementar criptografia de credenciais (Fernet, AWS KMS, etc.)
- [ ] Adicionar tabela BankConnection ao banco
- [ ] Criar migração Alembic para nova tabela
- [ ] Implementar ProviderFactory
- [ ] Atualizar endpoints de sync para suportar múltiplos bancos
- [ ] Adicionar testes para sync multi-banco
- [ ] Documentar processo de onboarding de novos bancos
- [ ] Implementar cache de providers para evitar recriação
- [ ] Adicionar monitoramento de health de cada conexão bancária

## Exemplo de Uso

```python
# 1. Usuário adiciona Banco do Brasil
POST /api/users/user123/banks
{
    "bank_name": "Banco do Brasil",
    "bank_code": "00000000",
    ...
}

# 2. Usuário adiciona Nubank
POST /api/users/user123/banks
{
    "bank_name": "Nubank",
    "bank_code": "18236120",
    ...
}

# 3. Criar consentimentos para cada banco
POST /api/users/user123/openfinance/consents
{
    "provider": "00000000"  # Banco do Brasil
}

POST /api/users/user123/openfinance/consents
{
    "provider": "18236120"  # Nubank
}

# 4. Sincronizar todos os bancos de uma vez
POST /api/users/user123/openfinance/sync-all

# Resposta:
{
    "status": "success",
    "banks_synced": 2,
    "total_imported": 45,
    "results": [...]
}
```

## Referências

- [Open Finance Brasil - Lista de Participantes](https://openbankingbrasil.org.br/participantes)
- [Códigos ISPB dos Bancos](https://www.bcb.gov.br/pom/spb/estatistica/port/ASTR003.pdf)
