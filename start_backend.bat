@echo off
REM Script para iniciar o backend do Gestor Financeiro
echo Iniciando Backend do Gestor Financeiro...
cd /d "%~dp0"
"%~dp0..\.venv\Scripts\python.exe" "%~dp0backend.py"
pause
