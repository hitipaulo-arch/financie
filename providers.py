"""Abstração de provedores Open Finance.

BaseProvider define a interface mínima para integração.
SimulatedProvider implementa comportamento estático usado em testes/demonstração.
OpenFinanceProvider implementa integração real com APIs do Open Finance Brasil.
"""
from __future__ import annotations
from typing import List, Dict, Optional
from datetime import date, datetime, timedelta
import requests
import os
from logger import logger


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


class OpenFinanceProvider(BaseProvider):
    """
    Provider real para integração com Open Finance Brasil.
    
    Implementa OAuth 2.0, consulta de contas e transações conforme especificação oficial.
    Documentação: https://openfinancebrasil.atlassian.net/wiki/spaces/OF/overview
    """
    name = "open_finance_brasil"
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        certificate_path: Optional[str] = None,
        private_key_path: Optional[str] = None
    ):
        """
        Inicializa provider do Open Finance.
        
        Args:
            base_url: URL base da API da instituição (ex: https://api.banco.com.br/open-banking)
            client_id: Client ID do aplicativo registrado
            client_secret: Client Secret do aplicativo
            certificate_path: Caminho para certificado mTLS (.pem)
            private_key_path: Caminho para chave privada mTLS (.key)
        """
        self.base_url = base_url or os.getenv("OPENFINANCE_BASE_URL")
        self.client_id = client_id or os.getenv("OPENFINANCE_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("OPENFINANCE_CLIENT_SECRET")
        self.certificate_path = certificate_path or os.getenv("OPENFINANCE_CERT_PATH")
        self.private_key_path = private_key_path or os.getenv("OPENFINANCE_KEY_PATH")
        
        # Validação de configuração
        if not all([self.base_url, self.client_id, self.client_secret]):
            logger.warning(
                "Open Finance não configurado completamente",
                extra={"missing_configs": self._get_missing_configs()}
            )
        
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
    
    def _get_missing_configs(self) -> List[str]:
        """Retorna lista de configurações faltantes."""
        missing = []
        if not self.base_url:
            missing.append("OPENFINANCE_BASE_URL")
        if not self.client_id:
            missing.append("OPENFINANCE_CLIENT_ID")
        if not self.client_secret:
            missing.append("OPENFINANCE_CLIENT_SECRET")
        return missing
    
    def _get_cert_tuple(self) -> Optional[tuple]:
        """Retorna tupla (cert, key) para mTLS se configurado."""
        if self.certificate_path and self.private_key_path:
            return (self.certificate_path, self.private_key_path)
        return None
    
    def _is_token_valid(self) -> bool:
        """Verifica se token de acesso ainda é válido."""
        if not self._access_token or not self._token_expires_at:
            return False
        return datetime.now() < self._token_expires_at
    
    def _get_access_token(self, consent_id: str) -> str:
        """
        Obtém access token via OAuth 2.0 Client Credentials.
        
        Args:
            consent_id: ID do consentimento ativo
            
        Returns:
            Access token válido
            
        Raises:
            requests.HTTPError: Se falhar autenticação
        """
        # Se token ainda é válido, reutilizar
        if self._is_token_valid():
            return self._access_token
        
        logger.info("Obtendo novo access token", extra={"consent_id": consent_id})
        
        token_url = f"{self.base_url}/oauth2/token"
        
        payload = {
            "grant_type": "client_credentials",
            "scope": "accounts transactions",
            "consent_id": consent_id
        }
        
        try:
            response = requests.post(
                token_url,
                data=payload,
                auth=(self.client_id, self.client_secret),
                cert=self._get_cert_tuple(),
                timeout=30,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            
            data = response.json()
            self._access_token = data["access_token"]
            expires_in = data.get("expires_in", 3600)  # Default 1 hora
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)  # 1 min buffer
            
            logger.info("Access token obtido com sucesso", extra={"expires_in": expires_in})
            return self._access_token
            
        except requests.exceptions.RequestException as e:
            logger.error("Erro ao obter access token", extra={"error": str(e)})
            raise
    
    def _get_accounts(self, access_token: str) -> List[Dict]:
        """
        Lista contas do usuário.
        
        Args:
            access_token: Token OAuth válido
            
        Returns:
            Lista de contas com accountId, type, currency
        """
        accounts_url = f"{self.base_url}/accounts/v1/accounts"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        try:
            response = requests.get(
                accounts_url,
                headers=headers,
                cert=self._get_cert_tuple(),
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            accounts = data.get("data", [])
            
            logger.info("Contas obtidas", extra={"count": len(accounts)})
            return accounts
            
        except requests.exceptions.RequestException as e:
            logger.error("Erro ao buscar contas", extra={"error": str(e)})
            return []
    
    def _get_account_transactions(
        self,
        access_token: str,
        account_id: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> List[Dict]:
        """
        Busca transações de uma conta específica.
        
        Args:
            access_token: Token OAuth válido
            account_id: ID da conta
            from_date: Data inicial (YYYY-MM-DD)
            to_date: Data final (YYYY-MM-DD)
            
        Returns:
            Lista de transações no formato Open Finance
        """
        # Default: últimos 90 dias
        if not to_date:
            to_date = date.today().isoformat()
        if not from_date:
            from_date = (date.today() - timedelta(days=90)).isoformat()
        
        transactions_url = f"{self.base_url}/accounts/v1/accounts/{account_id}/transactions"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        params = {
            "fromBookingDate": from_date,
            "toBookingDate": to_date
        }
        
        try:
            response = requests.get(
                transactions_url,
                headers=headers,
                params=params,
                cert=self._get_cert_tuple(),
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            transactions = data.get("data", [])
            
            logger.info(
                "Transações obtidas",
                extra={"account_id": account_id, "count": len(transactions)}
            )
            return transactions
            
        except requests.exceptions.RequestException as e:
            logger.error(
                "Erro ao buscar transações",
                extra={"account_id": account_id, "error": str(e)}
            )
            return []
    
    def _normalize_transaction(self, of_transaction: Dict) -> Dict:
        """
        Converte transação do formato Open Finance para formato interno.
        
        Args:
            of_transaction: Transação no formato Open Finance
            
        Returns:
            Transação normalizada: {description, amount, type, date}
        """
        # Campos conforme especificação Open Finance Brasil
        transaction_type = of_transaction.get("type", "").upper()
        amount_value = float(of_transaction.get("amount", 0))
        
        # Determinar tipo (income ou expense) baseado em creditDebitType
        credit_debit = of_transaction.get("creditDebitType", "").upper()
        if credit_debit == "CREDIT":
            txn_type = "income"
        elif credit_debit == "DEBIT":
            txn_type = "expense"
        else:
            # Fallback: se amount for negativo, é expense
            txn_type = "expense" if amount_value < 0 else "income"
        
        # Garantir amount positivo
        amount_value = abs(amount_value)
        
        # Descrição composta
        description_parts = []
        if of_transaction.get("transactionName"):
            description_parts.append(of_transaction["transactionName"])
        if of_transaction.get("creditorName"):
            description_parts.append(f"({of_transaction['creditorName']})")
        
        description = " ".join(description_parts) or "Transação Open Finance"
        
        # Data da transação
        booking_date = of_transaction.get("bookingDate")
        if not booking_date:
            booking_date = date.today().isoformat()
        
        return {
            "description": description,
            "amount": amount_value,
            "type": txn_type,
            "date": booking_date
        }
    
    def fetch_transactions(self, local_user_id: str, consent_id: str) -> List[Dict]:
        """
        Busca transações do Open Finance para um usuário.
        
        Args:
            local_user_id: ID do usuário no sistema local
            consent_id: ID do consentimento ativo
            
        Returns:
            Lista de transações normalizadas
        """
        if not all([self.base_url, self.client_id, self.client_secret]):
            logger.error("Open Finance não configurado", extra={"user_id": local_user_id})
            raise ValueError(f"Open Finance não configurado. Configurações faltantes: {', '.join(self._get_missing_configs())}")
        
        try:
            # 1. Obter access token
            access_token = self._get_access_token(consent_id)
            
            # 2. Listar contas do usuário
            accounts = self._get_accounts(access_token)
            
            if not accounts:
                logger.warning("Nenhuma conta encontrada", extra={"user_id": local_user_id})
                return []
            
            # 3. Buscar transações de todas as contas
            all_transactions = []
            
            for account in accounts:
                account_id = account.get("accountId")
                if not account_id:
                    continue
                
                of_transactions = self._get_account_transactions(access_token, account_id)
                
                # 4. Normalizar transações
                for of_txn in of_transactions:
                    try:
                        normalized = self._normalize_transaction(of_txn)
                        all_transactions.append(normalized)
                    except Exception as e:
                        logger.warning(
                            "Erro ao normalizar transação",
                            extra={"error": str(e), "transaction": of_txn}
                        )
                        continue
            
            logger.info(
                "Sincronização Open Finance concluída",
                extra={"user_id": local_user_id, "total_transactions": len(all_transactions)}
            )
            
            return all_transactions
            
        except Exception as e:
            logger.error(
                "Erro na sincronização Open Finance",
                extra={"user_id": local_user_id, "error": str(e)}
            )
            raise
    
    def sync(self, local_user_id: str, consent_id: str) -> Dict:
        """
        Sincroniza transações do Open Finance.
        
        Args:
            local_user_id: ID do usuário local
            consent_id: ID do consentimento ativo
            
        Returns:
            Dict com transactions e source
        """
        txns = self.fetch_transactions(local_user_id, consent_id)
        return {"transactions": txns, "source": self.name}
