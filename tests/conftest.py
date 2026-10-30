"""Configuração compartilhada do pytest — carregada antes de qualquer teste.

A única coisa que este arquivo faz é importante e fácil de remover por engano,
então o motivo está escrito aqui.

`backend.py` chama `load_dotenv()` no import (linha ~41). Sem argumentos, o
python-dotenv procura um `.env` subindo a árvore a partir do diretório do
próprio `backend.py` — ou seja, a raiz do repositório.

E `run.sh` / `start_backend.bat` criam exatamente aí um `.env` com:

    APP_ENV=development
    ENABLE_DEV_LOGIN=true
    FLASK_SECRET_KEY=<gerada>

O arquivo está no `.gitignore`, então o CI nunca o vê. Resultado antes deste
conftest: quem rodava o launcher e depois os testes via **2 falhas** que não
existiam para mais ninguém.

    FAILED test_app_env_default_e_producao
    FAILED test_dev_login_bloqueado_sem_flag_em_desenvolvimento

Os dois testam o comportamento na AUSÊNCIA de uma variável (fail-closed: sem
`APP_ENV` o backend assume produção; sem `ENABLE_DEV_LOGIN` o dev-login é
bloqueado). `reload_backend()` limpa essas variáveis de `os.environ`, mas o
`load_dotenv()` do import seguinte as devolvia a partir do `.env` — a limpeza
era desfeita por baixo do teste.

Neutralizar aqui, e não dentro de `reload_backend()`, é o que cobre todo caminho
de import: qualquer módulo de teste que importe `backend` passa por este
conftest primeiro.

A suíte passa a decidir o ambiente de cada teste e nada mais. O `.env` de quem
está rodando continua valendo normalmente para `run.sh`, `start_backend.bat` e
para a aplicação — só não entra nos testes.
"""
import dotenv

# Assinatura idêntica à real; retorna False como "nada foi carregado".
dotenv.load_dotenv = lambda *args, **kwargs: False
