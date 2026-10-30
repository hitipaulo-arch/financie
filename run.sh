#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Sobe o Gestor Financeiro para desenvolvimento local (Linux / macOS / WSL).
# No Windows use start_backend.bat, que faz exatamente o mesmo.
#
#   ./run.sh                  cria o venv se preciso, instala, migra e serve
#   ./run.sh --port 8080      muda a porta            (padrão: 8000)
#   ./run.sh --host 127.0.0.1 só para esta máquina    (padrão: 0.0.0.0, abre p/ a rede)
#   ./run.sh --no-browser     não abre o navegador automaticamente
#   ./run.sh --browser        abre mesmo com a saída redirecionada
#   ./run.sh --reinstall      força reinstalar as dependências
#   ./run.sh --no-migrate     pula o `alembic upgrade head`
#   ./run.sh --help
#
# Idempotente: da segunda vez em diante só sobe o servidor.
#
# Ordem de precedência das variáveis, da mais forte para a mais fraca:
#   1. o que já está no seu shell   2. o que está no .env   3. o padrão daqui
# ---------------------------------------------------------------------------
set -euo pipefail

cd "$(dirname "$0")"

# Porta 8000 de propósito: é a do startup.txt (gunicorn binda 0.0.0.0:8000), a
# que o Azure App Service espera e a deste servidor de teste. Desenvolver na
# mesma porta da produção evita a classe de surpresa "funciona aqui, falha lá".
PORTA="${PORT:-8000}"
# 0.0.0.0 atende o pedido de acessar de outros aparelhos na rede. O preço está
# dito em voz alta na hora de subir: com ENABLE_DEV_LOGIN=true qualquer pessoa na
# mesma rede entra sem autenticação. --host 127.0.0.1 fecha isso.
HOST="${FLASK_RUN_HOST:-0.0.0.0}"
REINSTALL=0
MIGRAR=1
ABRIR=auto   # auto = só se a saída for um terminal | sim | nao

while [ $# -gt 0 ]; do
  case "$1" in
    --port)       [ $# -ge 2 ] || { echo "erro: --port pede um valor" >&2; exit 2; }
                  PORTA="$2"; shift 2 ;;
    --host)       [ $# -ge 2 ] || { echo "erro: --host pede um valor" >&2; exit 2; }
                  HOST="$2"; shift 2 ;;
    --browser)    ABRIR=sim; shift ;;
    --no-browser) ABRIR=nao; shift ;;
    --reinstall)  REINSTALL=1; shift ;;
    --no-migrate) MIGRAR=0; shift ;;
    -h|--help)    # Imprime o bloco de comentário do topo, sem depender de
                  # número de linha — que muda toda vez que o cabeçalho é editado.
                  awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"
                  exit 0 ;;
    *)            echo "erro: opção desconhecida: $1" >&2; exit 2 ;;
  esac
done

dizer()  { printf '==> %s\n' "$*"; }
falhar() { printf 'erro: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Python (o projeto exige >= 3.10; veja requirements.txt)
# ---------------------------------------------------------------------------
PY=""
for candidato in python3 python; do
  if command -v "$candidato" >/dev/null 2>&1; then PY="$candidato"; break; fi
done
[ -n "$PY" ] || falhar "python3 não encontrado no PATH"

"$PY" -c "import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)" \
  || falhar "é preciso Python 3.10 ou mais novo ($("$PY" -V 2>&1))"
dizer "$("$PY" -V 2>&1) em $(command -v "$PY")"

# ---------------------------------------------------------------------------
# 2. Ambiente virtual
# ---------------------------------------------------------------------------
VENV=".venv"
VPY="$VENV/bin/python"
if [ ! -x "$VPY" ]; then
  dizer "criando o ambiente virtual em $VENV/"
  "$PY" -m venv "$VENV" || falhar "não foi possível criar o venv"
fi
[ -x "$VPY" ] || falhar "$VPY não existe — apague $VENV/ e rode de novo"

# ---------------------------------------------------------------------------
# 3. Dependências — reinstala só quando requirements.txt mudou
#    (o carimbo é um hash; a checagem é a mesma nos dois scripts)
# ---------------------------------------------------------------------------
CHECA_HASH='import hashlib,pathlib,sys;h=hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest();s=pathlib.Path(sys.argv[2]);sys.exit(0 if s.exists() and s.read_text().strip()==h else 1)'
GRAVA_HASH='import hashlib,pathlib,sys;pathlib.Path(sys.argv[2]).write_text(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())'
CARIMBO="$VENV/.requirements-sha256"

if [ "$REINSTALL" -eq 0 ] && "$VPY" -c "$CHECA_HASH" requirements.txt "$CARIMBO"; then
  dizer "dependências em dia (--reinstall para forçar)"
else
  dizer "instalando dependências de requirements.txt"
  "$VPY" -m pip install --quiet --upgrade pip
  "$VPY" -m pip install --quiet -r requirements.txt \
    || falhar "falha ao instalar as dependências"
  "$VPY" -c "$GRAVA_HASH" requirements.txt "$CARIMBO"
fi

# ---------------------------------------------------------------------------
# 4. .env — só é criado se não existir; o seu nunca é tocado
#    Sem FLASK_SECRET_KEY o backend gera uma chave aleatória a cada start e
#    registra CRITICAL: as sessões (e o token CSRF) morrem em todo restart.
# ---------------------------------------------------------------------------
if [ ! -f .env ]; then
  dizer "criando .env de desenvolvimento (está no .gitignore)"
  CRIA_ENV='import secrets,pathlib,sys;pathlib.Path(sys.argv[1]).write_text("# Gerado por run.sh - nao vai para o git.\n# Modelo completo e documentado: .env.example\nAPP_ENV=development\nENABLE_DEV_LOGIN=true\nFLASK_SECRET_KEY="+secrets.token_hex(32)+"\n",encoding="utf-8")'
  "$VPY" -c "$CRIA_ENV" .env || falhar "não foi possível criar o .env"
else
  dizer ".env já existe — mantido como está"
fi

# ---------------------------------------------------------------------------
# 5. Migrações — o banco precisa estar no schema que o código espera
# ---------------------------------------------------------------------------
if [ "$MIGRAR" -eq 1 ]; then
  dizer "aplicando migrações (alembic upgrade head)"
  "$VPY" -m alembic upgrade head \
    || falhar "as migrações falharam; o servidor não vai subir com o schema errado"
else
  dizer "migrações puladas (--no-migrate)"
fi

# ---------------------------------------------------------------------------
# 6. Servidor
# ---------------------------------------------------------------------------
# Só define o que nem o shell nem o .env já definiram.
definir_se_ausente() {
  [ -n "${!1:-}" ] && return 0
  if [ -f .env ] && grep -q "^$1=" .env; then return 0; fi
  export "$1=$2"
}
definir_se_ausente APP_ENV development
definir_se_ausente ENABLE_DEV_LOGIN true

# Host e porta vêm sempre da linha de comando, não do .env.
export FLASK_RUN_HOST="$HOST"
export PORT="$PORTA"

# Espelha a resolução do próprio backend, em vez de o shell tentar adivinhar
# lendo o .env com grep:
#   APP_ENV       = os.getenv("APP_ENV", "production")   -> ausente = produção
#   IS_PRODUCTION = APP_ENV in ("production","prod") or WEBSITE_SITE_NAME
# `load_dotenv()` não sobrescreve o que já está no ambiente, então consultar por
# aqui devolve exatamente o que o processo vai enxergar. Perguntar por
# "$APP_ENV" diretamente seria errado: quando a variável vem do .env ela existe
# só para o Python, nunca para este shell (e `set -u` derruba o script).
esta_em_producao() {
  [ "$("$VPY" -c "import os;from dotenv import load_dotenv;load_dotenv();a=(os.getenv('APP_ENV') or 'production').strip().lower();print('1' if a in ('production','prod') or os.getenv('WEBSITE_SITE_NAME') else '0')")" = "1" ]
}

if esta_em_producao; then
  echo "aviso: este launcher vai subir o servidor de desenvolvimento do Flask" >&2
  echo "       com a aplicação configurada para PRODUÇÃO. Em produção use" >&2
  echo "       gunicorn: veja startup.txt e deploy/README.md." >&2
fi

# Espelha env_flag() do backend (1/true/yes/on), pelo mesmo motivo de
# esta_em_producao: quem lê o .env é o Python, não este shell.
dev_login_ativo() {
  [ "$("$VPY" -c "import os;from dotenv import load_dotenv;load_dotenv();v=(os.getenv('ENABLE_DEV_LOGIN') or 'false').strip().lower();print('1' if v in ('1','true','yes','on') else '0')")" = "1" ]
}

# IP que os outros aparelhos da rede vão usar. O truque do socket UDP descobre a
# interface de saída sem enviar pacote nenhum.
ip_da_rede() {
  "$VPY" -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(('8.8.8.8',80));print(s.getsockname()[0])" 2>/dev/null || true
}

LOOPBACK=0
case "$HOST" in
  127.0.0.1|localhost|::1) LOOPBACK=1 ;;
esac

# 0.0.0.0 é endereço de bind, não de destino: no Windows nem abre no navegador.
# Por isso o que se imprime (e o que se abre) é localhost, nunca $HOST cru.
dizer "servidor em http://localhost:$PORTA  —  Ctrl+C para parar"
if [ "$LOOPBACK" -eq 0 ]; then
  REDE="$(ip_da_rede)"
  if [ -n "$REDE" ]; then
    dizer "na rede local: http://$REDE:$PORTA"
  fi
  if dev_login_ativo; then
    echo "" >&2
    echo "AVISO: bind em $HOST com ENABLE_DEV_LOGIN=true." >&2
    echo "       Qualquer aparelho na mesma rede pode entrar sem autenticação e" >&2
    echo "       assumir a sessão de qualquer user_id, inclusive o de outra pessoa." >&2
    echo "       Para fechar:  ./run.sh --host 127.0.0.1" >&2
    echo "       Ou no .env:   ENABLE_DEV_LOGIN=false" >&2
    echo "" >&2
  fi
fi

deve_abrir() {
  case "$ABRIR" in
    sim) return 0 ;;
    nao) return 1 ;;
    *)   [ -t 1 ] ;;  # auto: só com terminal, para não atrapalhar em CI/redirecionamento
  esac
}

if deve_abrir; then
  dizer "abrindo o navegador assim que a porta responder"
  # Processo à parte, de propósito: o `exec` abaixo substitui este shell, então
  # não sobraria nada para abrir o navegador depois — e abrir antes dá "não foi
  # possível conectar", porque o socket ainda não está escutando.
  "$VPY" scripts/abrir_navegador.py "$PORTA" localhost >/dev/null 2>&1 &
fi

exec "$VPY" backend.py
