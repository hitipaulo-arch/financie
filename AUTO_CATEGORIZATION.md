# Auto-Categorização de Transações - Guia de Implementação

## Visão Geral

Sistema de categorização automática de transações financeiras usando aprendizado de máquina (ML) e regras baseadas em padrões.

## Arquitetura

### 1. Modelo de Dados

```python
class Category(Base):
    """Categorias de transações definidas pelo usuário."""
    __tablename__ = "categories"
    __table_args__ = (
        Index('idx_category_user', 'user_id'),
        Index('idx_category_parent', 'parent_id'),
    )
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    name = Column(String(128), nullable=False)
    icon = Column(String(32), nullable=True)  # emoji ou nome do ícone
    color = Column(String(16), nullable=True)  # hex color
    parent_id = Column(Integer, nullable=True)  # Para subcategorias
    is_system = Column(Boolean, default=False)  # Categoria padrão do sistema
    created_at = Column(DateTime, nullable=False)
    deleted_at = Column(DateTime, nullable=True)


class TransactionCategory(Base):
    """Associação entre transação e categoria."""
    __tablename__ = "transaction_categories"
    __table_args__ = (
        Index('idx_txn_category_transaction', 'transaction_id'),
        Index('idx_txn_category_category', 'category_id'),
    )
    
    id = Column(Integer, primary_key=True)
    transaction_id = Column(Integer, nullable=False)  # FK para Transaction
    category_id = Column(Integer, nullable=False)  # FK para Category
    confidence = Column(Float, nullable=True)  # 0.0 - 1.0 (confiança do ML)
    is_manual = Column(Boolean, default=False)  # True se usuário categorizou manualmente
    categorized_at = Column(DateTime, nullable=False)


class CategoryRule(Base):
    """Regras para categorização automática."""
    __tablename__ = "category_rules"
    __table_args__ = (
        Index('idx_category_rule_user', 'user_id'),
        Index('idx_category_rule_category', 'category_id'),
    )
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    category_id = Column(Integer, nullable=False)  # FK para Category
    
    # Regras baseadas em texto
    description_pattern = Column(String(512), nullable=True)  # Regex ou palavras-chave
    merchant_name = Column(String(256), nullable=True)
    
    # Regras baseadas em valores
    amount_min = Column(Float, nullable=True)
    amount_max = Column(Float, nullable=True)
    
    # Regras baseadas em tipo
    transaction_type = Column(String(16), nullable=True)  # income | expense
    
    priority = Column(Integer, default=0)  # Maior prioridade = aplica primeiro
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
```

### 2. Categorias Padrão do Sistema

```python
DEFAULT_CATEGORIES = {
    "expense": [
        {"name": "Alimentação", "icon": "🍔", "color": "#FF6B6B", "subcategories": [
            "Restaurante", "Supermercado", "Delivery", "Café"
        ]},
        {"name": "Transporte", "icon": "🚗", "color": "#4ECDC4", "subcategories": [
            "Combustível", "Uber/Taxi", "Transporte Público", "Estacionamento"
        ]},
        {"name": "Moradia", "icon": "🏠", "color": "#95E1D3", "subcategories": [
            "Aluguel", "Condomínio", "Água", "Luz", "Internet", "Gás"
        ]},
        {"name": "Saúde", "icon": "💊", "color": "#F38181", "subcategories": [
            "Farmácia", "Consulta", "Plano de Saúde", "Academia"
        ]},
        {"name": "Educação", "icon": "📚", "color": "#AA96DA", "subcategories": [
            "Mensalidade", "Livros", "Cursos Online", "Material"
        ]},
        {"name": "Lazer", "icon": "🎮", "color": "#FCBAD3", "subcategories": [
            "Cinema", "Streaming", "Viagem", "Eventos"
        ]},
        {"name": "Compras", "icon": "🛍️", "color": "#FFFFD2", "subcategories": [
            "Roupas", "Eletrônicos", "Casa", "Cosméticos"
        ]},
        {"name": "Serviços", "icon": "⚙️", "color": "#A8D8EA", "subcategories": [
            "Telefone", "Assinaturas", "Seguros", "Taxas"
        ]},
    ],
    "income": [
        {"name": "Salário", "icon": "💰", "color": "#6BCB77"},
        {"name": "Freelance", "icon": "💼", "color": "#4D96FF"},
        {"name": "Investimentos", "icon": "📈", "color": "#FFD93D"},
        {"name": "Outros", "icon": "➕", "color": "#95E1D3"},
    ]
}

def initialize_categories_for_user(user_id: str, session):
    """Cria categorias padrão para novo usuário."""
    for tx_type, categories in DEFAULT_CATEGORIES.items():
        for cat_data in categories:
            category = Category(
                user_id=user_id,
                name=cat_data["name"],
                icon=cat_data.get("icon"),
                color=cat_data.get("color"),
                is_system=True,
                created_at=datetime.now(UTC)
            )
            session.add(category)
            session.flush()  # Para obter o ID
            
            # Criar subcategorias
            if "subcategories" in cat_data:
                for subcat_name in cat_data["subcategories"]:
                    subcat = Category(
                        user_id=user_id,
                        name=subcat_name,
                        parent_id=category.id,
                        is_system=True,
                        created_at=datetime.now(UTC)
                    )
                    session.add(subcat)
    
    session.commit()
```

### 3. Sistema de Regras

```python
class RuleBasedCategorizer:
    """Categorizador baseado em regras."""
    
    def __init__(self, session):
        self.session = session
        self.rules_cache = {}
    
    def categorize(self, transaction: Transaction) -> Optional[Tuple[int, float]]:
        """
        Retorna (category_id, confidence) ou None.
        """
        # Carregar regras do usuário (cache)
        user_id = transaction.user_id
        if user_id not in self.rules_cache:
            self.rules_cache[user_id] = self._load_rules(user_id)
        
        rules = self.rules_cache[user_id]
        
        # Aplicar regras por prioridade
        for rule in rules:
            if self._matches_rule(transaction, rule):
                return (rule.category_id, 1.0)  # 100% de confiança em regras
        
        return None
    
    def _load_rules(self, user_id: str) -> List[CategoryRule]:
        """Carrega regras ativas do usuário ordenadas por prioridade."""
        return self.session.query(CategoryRule).filter(
            CategoryRule.user_id == user_id,
            CategoryRule.is_active == True
        ).order_by(CategoryRule.priority.desc()).all()
    
    def _matches_rule(self, transaction: Transaction, rule: CategoryRule) -> bool:
        """Verifica se transação corresponde à regra."""
        import re
        
        # Verificar padrão de descrição
        if rule.description_pattern:
            pattern = rule.description_pattern.lower()
            desc = transaction.description.lower()
            
            if '*' in pattern or '|' in pattern:
                # Regex
                if not re.search(pattern, desc):
                    return False
            else:
                # Palavra-chave simples
                if pattern not in desc:
                    return False
        
        # Verificar merchant (se disponível)
        if rule.merchant_name:
            # TODO: Extrair merchant da descrição
            pass
        
        # Verificar valor
        if rule.amount_min is not None and transaction.amount < rule.amount_min:
            return False
        if rule.amount_max is not None and transaction.amount > rule.amount_max:
            return False
        
        # Verificar tipo
        if rule.transaction_type and transaction.type != rule.transaction_type:
            return False
        
        return True

# Exemplo de uso:
rule = CategoryRule(
    user_id="user123",
    category_id=5,  # Alimentação
    description_pattern="ifood|uber eats|rappi",
    priority=10,
    is_active=True
)
```

### 4. Sistema de ML (Opcional)

```python
class MLCategorizer:
    """Categorizador baseado em Machine Learning."""
    
    def __init__(self, model_path: str = "categorizer_model.pkl"):
        self.model_path = model_path
        self.model = None
        self.vectorizer = None
        self._load_model()
    
    def _load_model(self):
        """Carrega modelo treinado."""
        import pickle
        try:
            with open(self.model_path, 'rb') as f:
                data = pickle.load(f)
                self.model = data['model']
                self.vectorizer = data['vectorizer']
        except FileNotFoundError:
            logger.warning("Modelo ML não encontrado. Usando apenas regras.")
    
    def train(self, transactions: List[Transaction], categories: List[int]):
        """
        Treina o modelo com transações já categorizadas.
        
        Features:
        - Descrição (TF-IDF)
        - Valor normalizado
        - Tipo de transação
        - Dia do mês / dia da semana
        """
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.pipeline import Pipeline
        import numpy as np
        
        # Extrair features
        descriptions = [t.description for t in transactions]
        amounts = np.array([t.amount for t in transactions]).reshape(-1, 1)
        
        # TF-IDF para descrições
        self.vectorizer = TfidfVectorizer(max_features=1000, ngram_range=(1, 2))
        X_text = self.vectorizer.fit_transform(descriptions)
        
        # Combinar features
        X = np.hstack([X_text.toarray(), amounts])
        y = np.array(categories)
        
        # Treinar modelo
        self.model = RandomForestClassifier(n_estimators=100, random_state=42)
        self.model.fit(X, y)
        
        # Salvar modelo
        import pickle
        with open(self.model_path, 'wb') as f:
            pickle.dump({
                'model': self.model,
                'vectorizer': self.vectorizer
            }, f)
        
        logger.info(f"Modelo treinado com {len(transactions)} transações")
    
    def categorize(self, transaction: Transaction) -> Optional[Tuple[int, float]]:
        """
        Retorna (category_id, confidence) ou None.
        """
        if not self.model or not self.vectorizer:
            return None
        
        import numpy as np
        
        # Extrair features
        X_text = self.vectorizer.transform([transaction.description])
        X_amount = np.array([[transaction.amount]])
        X = np.hstack([X_text.toarray(), X_amount])
        
        # Predição
        category_id = self.model.predict(X)[0]
        probabilities = self.model.predict_proba(X)[0]
        confidence = float(max(probabilities))
        
        return (int(category_id), confidence)
```

### 5. Categorizador Híbrido

```python
class HybridCategorizer:
    """Combina regras e ML para melhor precisão."""
    
    def __init__(self, session):
        self.rule_categorizer = RuleBasedCategorizer(session)
        self.ml_categorizer = MLCategorizer()
    
    def categorize(self, transaction: Transaction) -> Optional[Tuple[int, float]]:
        """
        Prioridade:
        1. Regras do usuário (100% confiança)
        2. ML (se confidence > 0.8)
        3. None (usuário deve categorizar manualmente)
        """
        # Tentar regras primeiro
        result = self.rule_categorizer.categorize(transaction)
        if result:
            return result
        
        # Tentar ML
        result = self.ml_categorizer.categorize(transaction)
        if result and result[1] >= 0.8:  # Apenas alta confiança
            return result
        
        return None
```

### 6. Endpoint de Categorização

```python
@app.route("/api/users/<user_id>/transactions/<int:tx_id>/categorize", methods=["POST"])
def categorize_transaction(user_id, tx_id):
    """
    Categoriza uma transação.
    
    Modos:
    - auto: Usa sistema híbrido (regras + ML)
    - manual: Usuário define categoria
    
    Payload:
    {
        "mode": "manual",  # ou "auto"
        "category_id": 5,  # apenas para modo manual
        "create_rule": true  # Criar regra automática baseada nesta categorização
    }
    """
    data = request.get_json()
    mode = data.get("mode", "auto")
    
    # Buscar transação
    transaction = session_db.query(Transaction).filter(
        Transaction.id == tx_id,
        Transaction.user_id == user_id,
        Transaction.deleted_at.is_(None)
    ).first()
    
    if not transaction:
        return jsonify({"error": "transaction_not_found"}), 404
    
    if mode == "manual":
        category_id = data.get("category_id")
        if not category_id:
            return jsonify({"error": "category_id_required"}), 400
        
        # Criar associação
        txn_cat = TransactionCategory(
            transaction_id=tx_id,
            category_id=category_id,
            confidence=1.0,
            is_manual=True,
            categorized_at=datetime.now(UTC)
        )
        session_db.add(txn_cat)
        
        # Criar regra automática (opcional)
        if data.get("create_rule"):
            # Extrair padrão da descrição
            words = transaction.description.lower().split()
            pattern = "|".join(words[:3])  # Primeiras 3 palavras
            
            rule = CategoryRule(
                user_id=user_id,
                category_id=category_id,
                description_pattern=pattern,
                transaction_type=transaction.type,
                priority=5,
                is_active=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC)
            )
            session_db.add(rule)
        
        session_db.commit()
        
        return jsonify({
            "status": "categorized",
            "category_id": category_id,
            "confidence": 1.0,
            "method": "manual"
        }), 200
    
    else:  # auto
        categorizer = HybridCategorizer(session_db)
        result = categorizer.categorize(transaction)
        
        if not result:
            return jsonify({"error": "no_category_found", "suggestion": None}), 404
        
        category_id, confidence = result
        
        # Criar associação
        txn_cat = TransactionCategory(
            transaction_id=tx_id,
            category_id=category_id,
            confidence=confidence,
            is_manual=False,
            categorized_at=datetime.now(UTC)
        )
        session_db.add(txn_cat)
        session_db.commit()
        
        return jsonify({
            "status": "categorized",
            "category_id": category_id,
            "confidence": confidence,
            "method": "auto"
        }), 200


@app.route("/api/users/<user_id>/transactions/categorize-all", methods=["POST"])
def categorize_all_transactions(user_id):
    """Categoriza em lote todas as transações não categorizadas."""
    categorizer = HybridCategorizer(session_db)
    
    # Buscar transações sem categoria
    uncategorized = session_db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.deleted_at.is_(None),
        ~Transaction.id.in_(
            session_db.query(TransactionCategory.transaction_id)
        )
    ).all()
    
    categorized_count = 0
    skipped_count = 0
    
    for txn in uncategorized:
        result = categorizer.categorize(txn)
        if result:
            category_id, confidence = result
            txn_cat = TransactionCategory(
                transaction_id=txn.id,
                category_id=category_id,
                confidence=confidence,
                is_manual=False,
                categorized_at=datetime.now(UTC)
            )
            session_db.add(txn_cat)
            categorized_count += 1
        else:
            skipped_count += 1
    
    session_db.commit()
    
    return jsonify({
        "status": "completed",
        "categorized": categorized_count,
        "skipped": skipped_count,
        "total": len(uncategorized)
    }), 200
```

## Melhorias Futuras

1. **Aprendizado Contínuo**: Retreinar modelo periodicamente com novas categorizações manuais
2. **Detecção de Merchant**: Extrair nome do estabelecimento da descrição
3. **Categorias Sugeridas**: Sugerir novas categorias baseadas em padrões não cobertos
4. **Análise de Gastos**: Relatórios por categoria, tendências, orçamentos
5. **Tags**: Sistema de tags além de categorias (ex: #trabalho, #urgente)

## Dependências

```bash
pip install scikit-learn pandas numpy
```

## Exemplo de Uso

```python
# 1. Criar categorias padrão ao registrar usuário
initialize_categories_for_user("user123", session)

# 2. Usuário categoriza manualmente algumas transações
POST /api/users/user123/transactions/1/categorize
{
    "mode": "manual",
    "category_id": 5,
    "create_rule": true
}

# 3. Sistema aprende e categoriza automaticamente novas transações
POST /api/users/user123/transactions/categorize-all

# 4. Retreinar modelo com dados do usuário
# (executar periodicamente em background)
```
