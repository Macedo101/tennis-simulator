@echo off
REM Duplo-clique neste ficheiro para desligar o projeto.

cd /d "%~dp0backend"
docker compose down

echo Projeto desligado.
pause
