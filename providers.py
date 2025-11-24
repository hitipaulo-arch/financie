"""Abstração de provedores Open Finance.

BaseProvider define a interface mínima para integração.
SimulatedProvider implementa comportamento estático usado em testes/demonstração.
"""
from __future__ import annotations
from typing import List, Dict
from datetime import date

class BaseProvider:
    name: str = "base"

    def fetch_transactions(self, local_user_id: str) -> List[Dict]:
        """Retorna lista de transações no formato dict.
        Cada dict deve conter: description, amount, type, date (YYYY-MM-DD).
        """
        raise NotImplementedError

    def sync(self, local_user_id: str) -> Dict:
        """Orquestra a sincronização retornando estrutura padronizada."""
        txns = self.fetch_transactions(local_user_id)
        return {"transactions": txns, "source": self.name}

class SimulatedProvider(BaseProvider):
    name = "open_finance_simulated"

    def fetch_transactions(self, local_user_id: str) -> List[Dict]:
        # Ignora local_user_id na simulação; em produção usar para mapear external IDs.
        today = date.today().isoformat()
        return [
            {"description": "Depósito Open Finance", "amount": 987.65, "type": "income", "date": today},
            {"description": "Supermercado Open Finance", "amount": 152.30, "type": "expense", "date": today},
            {"description": "Boleto Energia", "amount": 210.15, "type": "expense", "date": today},
        ]
