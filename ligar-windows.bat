@echo off
REM Duplo-clique neste ficheiro para ligar o projeto.
REM Precisa do Docker Desktop instalado e aberto (so isso).

cd /d "%~dp0backend"

echo A preparar o projeto... (pode demorar uns minutos na primeira vez)
docker compose up --build -d

echo A abrir a pagina no browser...
timeout /t 5 /nobreak >nul
start http://localhost:8000/docs

echo.
echo Pronto! Se a pagina nao abriu sozinha, cola isto no browser:
echo http://localhost:8000/docs
echo.
echo Para desligar o projeto, da duplo-clique em "parar-windows.bat".
pause
