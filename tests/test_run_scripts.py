"""Testes dos launchers de desenvolvimento: run.sh, start_backend.bat e .gitattributes.

O repositório não tinha nenhum script de execução. O README mandava rodar
`python backend.py` depois de definir `APP_ENV` e `ENABLE_DEV_LOGIN` à mão no
shell — e sem eles o backend assume produção (fail-closed), gera uma
`FLASK_SECRET_KEY` aleatória e registra CRITICAL a cada start.

Estes testes travam as propriedades que fazem os scripts serem seguros de rodar
e de manter. O `start_backend.bat` não pode ser executado aqui (o CI é Linux),
então ele é verificado estaticamente — inclusive os rótulos de `goto`, que são o
erro mais comum de batch e que o cmd só acusa em tempo de execução.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import stat

import pytest

from tests.test_phase1_security import build_app

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_SH = os.path.join(ROOT, "run.sh")
BAT = os.path.join(ROOT, "start_backend.bat")
GITATTRIBUTES = os.path.join(ROOT, ".gitattributes")
GITIGNORE = os.path.join(ROOT, ".gitignore")


def ler(caminho, binario=False):
    modo = "rb" if binario else "r"
    kwargs = {} if binario else {"encoding": "utf-8", "errors": "replace"}
    with open(caminho, modo, **kwargs) as fh:
        return fh.read()


def codigo_batch(texto):
    """Só o que o cmd de fato executa.

    Fora `rem`, `::` e `echo`. O `echo` importa: a seção de ajuda imprime
    "Producao: gunicorn - veja startup.txt", e um teste que procure a palavra
    `gunicorn` no arquivo inteiro acharia que o script o invoca — sendo que
    gunicorn nem roda em Windows nativo.
    """
    linhas = []
    for linha in texto.splitlines():
        if re.match(r"(?i)^\s*(rem\b|::|echo\b)", linha):
            continue
        linhas.append(linha)
    return "\n".join(linhas)


def codigo_shell(texto):
    """Só o que o bash executa: fora as linhas que são inteiramente comentário.

    Comentários de linha inteira apenas — um `#` dentro de string (o one-liner
    Python que grava o .env tem vários) precisa sobreviver.
    """
    return "\n".join(l for l in texto.splitlines() if not re.match(r"^\s*#", l))


# ---------------------------------------------------------------------------
# Existência e forma
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("caminho", [RUN_SH, BAT, GITATTRIBUTES])
def test_arquivos_existem_e_nao_estao_vazios(caminho):
    assert os.path.isfile(caminho), f"{os.path.basename(caminho)} não existe"
    assert os.path.getsize(caminho) > 500, "script curto demais para ser o launcher"


def test_run_sh_e_executavel_e_tem_shebang_bash():
    modo = os.stat(RUN_SH).st_mode
    assert modo & stat.S_IXUSR, "run.sh sem bit de execução: ./run.sh daria 'Permission denied'"
    primeira = ler(RUN_SH).splitlines()[0]
    assert primeira.startswith("#!"), "falta shebang"
    assert "bash" in primeira, (
        "o script usa `${!1}` (expansão indireta) e `local`, que não são POSIX: "
        "precisa ser bash, não sh"
    )


def test_run_sh_tem_finais_de_linha_lf():
    """CRLF aqui quebra no Linux/macOS: 'bad interpreter: /bin/bash^M'."""
    dados = ler(RUN_SH, binario=True)
    assert b"\r\n" not in dados, "run.sh com CRLF não executa em Unix"


def test_bat_tem_finais_de_linha_crlf():
    """O cmd.exe resolve rótulos/goto de forma inconsistente com LF puro."""
    dados = ler(BAT, binario=True)
    assert b"\r\n" in dados, "start_backend.bat deveria usar CRLF"
    assert dados.count(b"\n") == dados.count(b"\r\n"), "finais de linha mistos no .bat"


def test_gitattributes_trava_os_finais_de_linha_dos_scripts():
    """Sem isto, quem clona no Windows converte o run.sh e quebra o Linux — em silêncio."""
    texto = ler(GITATTRIBUTES)
    assert re.search(r"^\*\.sh\s+text\s+eol=lf", texto, re.MULTILINE), "*.sh precisa ser eol=lf"
    assert re.search(r"^\*\.bat\s+text\s+eol=crlf", texto, re.MULTILINE), "*.bat precisa ser eol=crlf"


def test_gitattributes_nao_renormaliza_o_repositorio_inteiro():
    """`* text=auto` geraria um diff enorme em arquivos que não têm nada a ver."""
    texto = ler(GITATTRIBUTES)
    assert not re.search(r"^\*\s+text=auto", texto, re.MULTILINE), (
        "evite '* text=auto': há arquivo com finais mistos no repositório"
    )


# ---------------------------------------------------------------------------
# O que os dois scripts precisam fazer
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("caminho", [RUN_SH, BAT], ids=["run.sh", "start_backend.bat"])
def test_launchers_instalam_as_dependencias(caminho):
    texto = ler(caminho)
    assert "requirements.txt" in texto
    assert "pip install" in texto


@pytest.mark.parametrize("caminho", [RUN_SH, BAT], ids=["run.sh", "start_backend.bat"])
def test_launchers_rodam_as_migracoes(caminho):
    """Sem `alembic upgrade head` o app sobe com o schema antigo e falha em runtime."""
    texto = ler(caminho)
    assert "alembic upgrade head" in texto, "as migrações precisam rodar antes do servidor"


@pytest.mark.parametrize("caminho", [RUN_SH, BAT], ids=["run.sh", "start_backend.bat"])
def test_launchers_sobem_o_servidor(caminho):
    texto = ler(caminho)
    assert "backend.py" in texto


@pytest.mark.parametrize("caminho", [RUN_SH, BAT], ids=["run.sh", "start_backend.bat"])
def test_launchers_criam_venv(caminho):
    texto = ler(caminho)
    assert "-m venv" in texto
    assert ".venv" in texto


@pytest.mark.parametrize("caminho", [RUN_SH, BAT], ids=["run.sh", "start_backend.bat"])
def test_launchers_nao_tem_segredo_hardcoded(caminho):
    """A chave é gerada por `secrets.token_hex`, nunca escrita no script versionado."""
    texto = ler(caminho)
    assert "token_hex" in texto, "a FLASK_SECRET_KEY deve ser gerada"
    achados = re.findall(r"\b[0-9a-fA-F]{32,}\b", texto)
    assert not achados, f"possível segredo literal no script: {achados[:2]}"


@pytest.mark.parametrize("caminho", [RUN_SH, BAT], ids=["run.sh", "start_backend.bat"])
def test_launchers_bindam_loopback_por_padrao(caminho):
    """0.0.0.0 exporia a máquina na rede local com dev-login liberado."""
    texto = ler(caminho)
    # Cobre as duas grafias: HOST="${FLASK_RUN_HOST:-127.0.0.1}" (sh) e
    # set "HOST=127.0.0.1" (bat).
    assert re.search(r"HOST[^\n]*127\.0\.0\.1", texto), (
        "o host padrão precisa ser 127.0.0.1, não 0.0.0.0"
    )


@pytest.mark.parametrize("caminho", [RUN_SH, BAT], ids=["run.sh", "start_backend.bat"])
def test_launchers_nao_tocam_num_env_existente(caminho):
    """Criar o .env só se ele não existir; sobrescrever apagaria a configuração da pessoa."""
    texto = ler(caminho)
    assert re.search(r"(if\s+\[\s+!\s+-f\s+\.env\s+\]|if\s+exist\s+\.env)", texto), (
        "falta a guarda de existência do .env"
    )


@pytest.mark.parametrize("caminho", [RUN_SH, BAT], ids=["run.sh", "start_backend.bat"])
def test_launchers_tem_help(caminho):
    texto = ler(caminho)
    assert "--help" in texto
    assert "--port" in texto
    assert "--reinstall" in texto
    assert "--no-migrate" in texto


def test_bat_nao_usa_gunicorn():
    """gunicorn usa os.fork() e não roda em Windows nativo — só waitress ou o Flask."""
    assert "gunicorn" not in codigo_batch(ler(BAT)).lower(), (
        "start_backend.bat não pode chamar gunicorn"
    )


def test_bat_tem_todos_os_rotulos_dos_gotos():
    """`goto rotulo_inexistente` -> "The system cannot find the batch label specified".

    Só aparece em execução, e só no caminho que falha — exatamente quando a
    pessoa menos pode depurar. Verificação estática pega de graça.
    """
    texto = codigo_batch(ler(BAT))
    rotulos = set(re.findall(r"(?m)^:([A-Za-z_][A-Za-z0-9_]*)", texto))
    alvos = set(re.findall(r"(?mi)\bgoto\s+:?([A-Za-z_][A-Za-z0-9_]*)", texto))
    alvos |= set(re.findall(r"(?mi)\bcall\s+:([A-Za-z_][A-Za-z0-9_]*)", texto))
    alvos.discard("EOF")  # :EOF é implícito no cmd
    faltando = sorted(alvos - rotulos)
    assert not faltando, f"gotos/calls para rótulos inexistentes: {faltando}"


def test_bat_nao_tem_goto_dentro_de_bloco_entre_parenteses():
    """Regra que o próprio cabeçalho do script documenta: `goto` dentro de
    `if ... ( ... )` é fonte de comportamento inconsistente no cmd."""
    texto = codigo_batch(ler(BAT))
    for numero, linha in enumerate(texto.splitlines(), 1):
        if "(" in linha and re.search(r"\bgoto\b", linha, re.IGNORECASE):
            pytest.fail(f"linha {numero}: goto dentro de bloco entre parênteses: {linha.strip()}")


def test_bat_nao_tem_acentos():
    """Acento em .bat depende da codepage do console e vira texto ilegível."""
    texto = ler(BAT)
    com_acento = sorted({c for c in texto if ord(c) > 127})
    assert not com_acento, f"caracteres não-ASCII no .bat: {com_acento}"


def test_os_dois_scripts_usam_a_mesma_checagem_de_dependencias():
    """O carimbo é um hash SHA-256 calculado por Python nos dois lados.

    Se cada um usasse a ferramenta do próprio sistema (certutil vs sha256sum), os
    formatos divergiriam e o `--reinstall` implícito deixaria de funcionar ao
    trocar de máquina.
    """
    sh, bat = ler(RUN_SH), ler(BAT)
    for trecho in ("hashlib.sha256", ".requirements-sha256"):
        assert trecho in sh and trecho in bat, f"{trecho} falta em um dos scripts"
    # Só no que é executado: os dois scripts citam certutil/sha256sum em
    # comentário, justamente para explicar por que NÃO os usam.
    assert "certutil" not in codigo_batch(bat), "o .bat voltou a usar certutil"
    assert "sha256sum" not in codigo_shell(sh), "o run.sh voltou a usar sha256sum"
    assert "shasum" not in codigo_shell(sh)


# ---------------------------------------------------------------------------
# Execução real do run.sh (o CI é Linux; no Windows estes testes são pulados)
# ---------------------------------------------------------------------------
bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash não disponível")


@bash
def test_run_sh_tem_sintaxe_valida():
    r = subprocess.run(["bash", "-n", RUN_SH], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr


@bash
def test_run_sh_help_nao_sobe_servidor_nem_toca_em_nada():
    """--help tem que sair antes de criar venv, instalar ou migrar."""
    antes = {n: os.path.getmtime(os.path.join(ROOT, n))
             for n in os.listdir(ROOT) if os.path.isfile(os.path.join(ROOT, n))}
    r = subprocess.run(["bash", RUN_SH, "--help"], capture_output=True, text=True,
                       cwd=ROOT, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "--port" in r.stdout and "--reinstall" in r.stdout
    # só o bloco de comentário do topo: nada de código vazando para a ajuda
    assert "set -euo pipefail" not in r.stdout
    assert "exec " not in r.stdout
    depois = {n: os.path.getmtime(os.path.join(ROOT, n))
              for n in os.listdir(ROOT) if os.path.isfile(os.path.join(ROOT, n))}
    assert antes == depois, "--help modificou arquivos"


@bash
def test_run_sh_rejeita_opcao_desconhecida():
    r = subprocess.run(["bash", RUN_SH, "--nao-existe"], capture_output=True, text=True,
                       cwd=ROOT, timeout=60)
    assert r.returncode == 2, f"esperado 2, veio {r.returncode}: {r.stderr}"
    assert "desconhecida" in r.stderr


@bash
def test_run_sh_exige_valor_para_port_e_host():
    for flag in ("--port", "--host"):
        r = subprocess.run(["bash", RUN_SH, flag], capture_output=True, text=True,
                           cwd=ROOT, timeout=60)
        assert r.returncode == 2, f"{flag} sem valor deveria sair com 2, veio {r.returncode}"
        assert "pede um valor" in r.stderr


# ---------------------------------------------------------------------------
# O que o launcher cria precisa continuar fora do git
# ---------------------------------------------------------------------------
def test_env_e_banco_continuam_ignorados():
    """O run.sh cria .env (com uma chave secreta) e o app cria data.db."""
    texto = ler(GITIGNORE)
    for padrao in (".env", "data.db", ".venv/"):
        assert padrao in texto, f"{padrao} precisa estar no .gitignore"


def test_suite_e_imune_a_um_env_local(tmp_path):
    """Reproduz a falha real que motivou tests/conftest.py.

    `run.sh` cria um `.env` na raiz com `APP_ENV=development` e
    `ENABLE_DEV_LOGIN=true`; `backend.py` chama `load_dotenv()` no import. Sem o
    bloqueio, os dois testes de fail-closed abaixo quebravam **só na máquina de
    quem rodou o launcher** — vermelho local, verde no CI.

    O arquivo é recriado de propósito e o original (se houver) é restaurado.
    """
    alvo = os.path.join(ROOT, ".env")
    backup = ler(alvo, binario=True) if os.path.isfile(alvo) else None
    try:
        with open(alvo, "w", encoding="utf-8") as fh:
            fh.write("APP_ENV=development\n"
                     "ENABLE_DEV_LOGIN=true\n"
                     "FLASK_SECRET_KEY=chave-do-env-local\n")

        backend, app = build_app({"GF_DB_URL": f"sqlite:///{tmp_path / 'hermetico.db'}"})
        app.config["TESTING"] = False

        # Sem APP_ENV no ambiente do teste, o backend assume produção — o .env
        # não pode dizer o contrário.
        assert backend.IS_PRODUCTION is True, "o .env local vazou para o teste"
        # E o dev-login continua bloqueado, apesar de ENABLE_DEV_LOGIN=true no .env.
        resp = app.test_client().post("/auth/dev-login", json={"user_id": "invasor"})
        assert resp.status_code == 403, f"dev-login liberado pelo .env: {resp.status_code}"
    finally:
        if backup is None:
            if os.path.isfile(alvo):
                os.remove(alvo)
        else:
            with open(alvo, "wb") as fh:
                fh.write(backup)
