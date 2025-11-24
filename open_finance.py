"""Serviço de integração Open Finance (simulado).

Este módulo abstrai a lógica de autenticação e coleta de dados de instituições
financeiras via Open Finance Brasil. Atualmente implementa uma simulação;
para produção substituir chamadas em `fetch_transactions` por requisições
HTTP reais usando `requests` ou um client especializado.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict
import os
import time

import requests  # já presente em requirements

OPEN_FINANCE_BASE_URL = os.getenv("OPEN_FINANCE_BASE_URL", "https://api.openfinance.local")
OPEN_FINANCE_CLIENT_ID = os.getenv("OPEN_FINANCE_CLIENT_ID", "demo")
OPEN_FINANCE_CLIENT_SECRET = os.getenv("OPEN_FINANCE_CLIENT_SECRET", "demo")


@dataclass
class OFTransaction:
    description: str
    amount: float
    type: str  # income | expense
    date: str  # ISO date

    def to_dict(self) -> Dict:
        return {
            "description": self.description,
            "amount": self.amount,
            "type": self.type,
            "date": self.date,
        }


def get_access_token() -> str:
    """Obtém token de acesso.
    Simulado: em produção, implementar client credentials ou fluxo consentido.
    """
    # Exemplo de chamada (comentado):
    # resp = requests.post(f"{OPEN_FINANCE_BASE_URL}/oauth/token", data={
    #     "client_id": OPEN_FINANCE_CLIENT_ID,
    #     "client_secret": OPEN_FINANCE_CLIENT_SECRET,
    #     "grant_type": "client_credentials"
    # })
    # resp.raise_for_status()
    # return resp.json()["access_token"]
    return f"simulated-token-{int(time.time())}"  # token dummy


def fetch_transactions(external_user_id: str) -> List[OFTransaction]:
    """Busca transações do usuário em instituições financeiras.
    Simulado: retorna lista fixa; substituir por integração real.
    """
    # Exemplo real (comentado):
    # token = get_access_token()
    # headers = {"Authorization": f"Bearer {token}"}
    # resp = requests.get(f"{OPEN_FINANCE_BASE_URL}/users/{external_user_id}/transactions", headers=headers, timeout=10)
    # resp.raise_for_status()
    # data = resp.json()
    # Mapear campos conforme retorno real
    from datetime import date
    today = date.today().isoformat()
    return [
        OFTransaction(description="Depósito Open Finance", amount=987.65, type="income", date=today),
        OFTransaction(description="Supermercado Open Finance", amount=152.30, type="expense", date=today),
        OFTransaction(description="Boleto Energia", amount=210.15, type="expense", date=today),
    ]


def sync_user_transactions(local_user_id: str) -> Dict:
    """Orquestra sincronização: busca no OF e devolve estrutura para inserir.
    Retorna dict com chave `transactions` contendo lista pronta para persistência.
    """
    of_txns = fetch_transactions(external_user_id=local_user_id)
    return {"transactions": [t.to_dict() for t in of_txns], "source": "open_finance_simulated"}
