@echo off
rem ---------------------------------------------------------------------------
rem Sobe o Gestor Financeiro para desenvolvimento local (Windows).
rem Em Linux/macOS/WSL use ./run.sh, que faz exatamente o mesmo.
rem
rem   start_backend.bat                 cria o venv se preciso, instala, migra, serve
rem   start_backend.bat --port 8080     muda a porta            (padrao: 5000)
rem   start_backend.bat --host 0.0.0.0  muda o bind             (padrao: 127.0.0.1)
rem   start_backend.bat --reinstall     forca reinstalar as dependencias
rem   start_backend.bat --no-migrate    pula o "alembic upgrade head"
rem   start_backend.bat --help
rem
rem DUAS REGRAS DE MANUTENCAO, aprendidas do jeito dificil:
rem   1. As mensagens sao ASCII de proposito. .bat com acento depende da
rem      codepage do console e vira texto ilegivel.
rem   2. Fluxo plano, sem "goto" dentro de bloco entre parenteses. Parenteses
rem      so em "if ... ( ... )" curtos e sem salto. Todo erro faz
rem      set MOTIVO=... e cai em :erro.
rem
rem Precedencia das variaveis, da mais forte para a mais fraca:
rem   1. o que ja esta no seu ambiente   2. o .env   3. o padrao deste script
rem ---------------------------------------------------------------------------
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "PORTA=5000"
if defined PORT set "PORTA=!PORT!"
set "HOST=127.0.0.1"
if defined FLASK_RUN_HOST set "HOST=!FLASK_RUN_HOST!"
set "REINSTALL=0"
set "MIGRAR=1"
set "VENV=.venv"
set "VPY=.venv\Scripts\python.exe"
set "CARIMBO=.venv/.requirements-sha256"

rem Veio de duplo clique? Entao a janela fecha sozinha e o erro some antes de
rem dar para ler - por isso o "pause" antes de sair.
set "INTERATIVO=0"
echo !CMDCMDLINE! | find /i "%~nx0" >nul 2>&1
if not errorlevel 1 set "INTERATIVO=1"

rem ---------------------------------------------------------------------------
rem Argumentos
rem ---------------------------------------------------------------------------
:args
if "%~1"=="" goto fim_args
if /i "%~1"=="--port" goto arg_port
if /i "%~1"=="--host" goto arg_host
if /i "%~1"=="--reinstall" goto arg_reinstall
if /i "%~1"=="--no-migrate" goto arg_no_migrate
if /i "%~1"=="--help" goto ajuda
if /i "%~1"=="-h" goto ajuda
set "MOTIVO=opcao desconhecida: %~1"
goto erro

:arg_port
if not "%~2"=="" goto arg_port_ok
set "MOTIVO=--port pede um valor"
goto erro
:arg_port_ok
set "PORTA=%~2"
shift
shift
goto args

:arg_host
if not "%~2"=="" goto arg_host_ok
set "MOTIVO=--host pede um valor"
goto erro
:arg_host_ok
set "HOST=%~2"
shift
shift
goto args

:arg_reinstall
set "REINSTALL=1"
shift
goto args

:arg_no_migrate
set "MIGRAR=0"
shift
goto args

:fim_args

rem ---------------------------------------------------------------------------
rem 1. Python (o projeto exige 3.10 ou mais novo; veja requirements.txt)
rem ---------------------------------------------------------------------------
set "PY="
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY goto py_ok
python -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto py_ok
set "MOTIVO=Python nao encontrado. Instale de https://www.python.org/downloads/ marcando 'Add python.exe to PATH'"
goto erro

:py_ok
%PY% -c "import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto py_versao_ok
set "MOTIVO=e preciso Python 3.10 ou mais novo"
goto erro

:py_versao_ok
for /f "delims=" %%v in ('%PY% -V 2^>^&1') do echo ==^> %%v

rem ---------------------------------------------------------------------------
rem 2. Ambiente virtual
rem ---------------------------------------------------------------------------
if exist "%VPY%" goto venv_ok
echo ==^> criando o ambiente virtual em %VENV%
%PY% -m venv %VENV%
if not errorlevel 1 goto venv_ok
set "MOTIVO=falha ao criar o ambiente virtual"
goto erro

:venv_ok
if exist "%VPY%" goto venv_confere_ok
set "MOTIVO=%VPY% nao existe - apague a pasta %VENV% e rode de novo"
goto erro
:venv_confere_ok

rem ---------------------------------------------------------------------------
rem 3. Dependencias - reinstala so quando requirements.txt mudou
rem    A checagem e o mesmo one-liner Python nos dois scripts, de proposito:
rem    nada de certutil/sha256sum, que diferem entre Windows e Unix. Os
rem    caminhos vao por argv, entao o codigo nao tem literal entre aspas -
rem    se tivesse, as aspas duplas brigariam com as do "set" e do -c.
rem ---------------------------------------------------------------------------
set "CHECA_HASH=import hashlib,pathlib,sys;h=hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest();s=pathlib.Path(sys.argv[2]);sys.exit(0 if s.exists() and s.read_text().strip()==h else 1)"
set "GRAVA_HASH=import hashlib,pathlib,sys;pathlib.Path(sys.argv[2]).write_text(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())"

if "%REINSTALL%"=="1" goto instalar
"%VPY%" -c "!CHECA_HASH!" requirements.txt "!CARIMBO!" >nul 2>&1
if errorlevel 1 goto instalar
echo ==^> dependencias em dia [--reinstall para forcar]
goto deps_ok

:instalar
echo ==^> instalando dependencias de requirements.txt
"%VPY%" -m pip install --quiet --upgrade pip
if not errorlevel 1 goto instalar_reqs
set "MOTIVO=falha ao atualizar o pip"
goto erro

:instalar_reqs
"%VPY%" -m pip install --quiet -r requirements.txt
if not errorlevel 1 goto gravar_carimbo
set "MOTIVO=falha ao instalar as dependencias"
goto erro

:gravar_carimbo
"%VPY%" -c "!GRAVA_HASH!" requirements.txt "!CARIMBO!"
if not errorlevel 1 goto deps_ok
set "MOTIVO=falha ao gravar o carimbo das dependencias"
goto erro

:deps_ok

rem ---------------------------------------------------------------------------
rem 4. .env - so e criado se nao existir; o seu nunca e tocado
rem    Sem FLASK_SECRET_KEY o backend gera uma chave aleatoria a cada start e
rem    registra CRITICAL: sessao e token CSRF morrem em todo restart.
rem ---------------------------------------------------------------------------
if exist .env goto env_existe
echo ==^> criando .env de desenvolvimento [esta no .gitignore]
set "CRIA_ENV=import secrets,pathlib,sys;pathlib.Path(sys.argv[1]).write_text('# Gerado por start_backend.bat - nao vai para o git.\n# Modelo completo e documentado: .env.example\nAPP_ENV=development\nENABLE_DEV_LOGIN=true\nFLASK_SECRET_KEY='+secrets.token_hex(32)+'\n',encoding='utf-8')"
"%VPY%" -c "!CRIA_ENV!" .env
if not errorlevel 1 goto env_ok
set "MOTIVO=nao foi possivel criar o .env"
goto erro

:env_existe
echo ==^> .env ja existe - mantido como esta

:env_ok

rem ---------------------------------------------------------------------------
rem 5. Migracoes - o banco precisa estar no schema que o codigo espera
rem ---------------------------------------------------------------------------
if "%MIGRAR%"=="0" goto migra_pulada
echo ==^> aplicando migracoes [alembic upgrade head]
"%VPY%" -m alembic upgrade head
if not errorlevel 1 goto migra_ok
set "MOTIVO=as migracoes falharam; o servidor nao deve subir com o schema errado"
goto erro

:migra_pulada
echo ==^> migracoes puladas [--no-migrate]

:migra_ok

rem ---------------------------------------------------------------------------
rem 6. Servidor
rem ---------------------------------------------------------------------------
call :definir_se_ausente APP_ENV development
call :definir_se_ausente ENABLE_DEV_LOGIN true

rem Host e porta vem sempre da linha de comando, nao do .env.
set "FLASK_RUN_HOST=!HOST!"
set "PORT=!PORTA!"

rem Espelha a resolucao do backend (APP_ENV ausente = producao; WEBSITE_SITE_NAME
rem tambem conta). Perguntar por !APP_ENV! aqui seria errado: quando o valor vem
rem do .env ele existe so para o Python, nunca para este shell. A resposta vem por
rem um arquivo em %TEMP% porque "for /f" com um -c entre aspas e fragil demais.
set "RESPOSTA=%TEMP%\gf_ambiente_%RANDOM%.tmp"
set "EM_PRODUCAO=0"
"%VPY%" -c "import os,sys,pathlib;from dotenv import load_dotenv;load_dotenv();a=(os.getenv('APP_ENV') or 'production').strip().lower();pathlib.Path(sys.argv[1]).write_text('1' if a in ('production','prod') or os.getenv('WEBSITE_SITE_NAME') else '0')" "!RESPOSTA!"
if errorlevel 1 goto servir
set /p EM_PRODUCAO=<"!RESPOSTA!"
del "!RESPOSTA!" >nul 2>&1
if not "!EM_PRODUCAO!"=="1" goto servir
echo aviso: este launcher vai subir o servidor de desenvolvimento do Flask
echo        com a aplicacao configurada para PRODUCAO. Em producao use
echo        gunicorn: veja startup.txt e deploy/README.md.

:servir
echo ==^> servidor em http://!HOST!:!PORTA!  -  Ctrl+C para parar
"%VPY%" backend.py
set "CODIGO=!ERRORLEVEL!"
if "!INTERATIVO!"=="1" pause
exit /b !CODIGO!

rem ---------------------------------------------------------------------------
rem Sub-rotinas e saidas
rem ---------------------------------------------------------------------------
:definir_se_ausente
rem %1=nome %2=valor. Precedencia: ambiente, depois .env, depois o padrao.
if defined %~1 exit /b 0
if not exist .env goto definir_valor
findstr /b /c:"%~1=" .env >nul 2>&1
if not errorlevel 1 exit /b 0
:definir_valor
set "%~1=%~2"
exit /b 0

:ajuda
echo.
echo Sobe o Gestor Financeiro para desenvolvimento local.
echo.
echo   start_backend.bat                 cria o venv se preciso, instala, migra, serve
echo   start_backend.bat --port 8080     muda a porta            [padrao: 5000]
echo   start_backend.bat --host 0.0.0.0  muda o bind             [padrao: 127.0.0.1]
echo   start_backend.bat --reinstall     forca reinstalar as dependencias
echo   start_backend.bat --no-migrate    pula o "alembic upgrade head"
echo.
echo Precedencia: ambiente, depois .env, depois o padrao deste script.
echo Producao: gunicorn - veja startup.txt e deploy/README.md.
echo.
if "!INTERATIVO!"=="1" pause
exit /b 0

:erro
echo.
echo erro: !MOTIVO!
echo.
if "!INTERATIVO!"=="1" pause
exit /b 1
