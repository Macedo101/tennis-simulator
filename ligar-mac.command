#!/bin/bash
# Duplo-clique neste ficheiro para ligar o projeto.
# Precisa do Docker Desktop instalado e aberto (só isso).

cd "$(dirname "$0")/backend" || exit 1

echo "A preparar o projeto... (pode demorar uns minutos na primeira vez)"
docker compose up --build -d

echo "A abrir a página no browser..."
sleep 5
open "http://localhost:8000/docs"

echo ""
echo "Pronto! Se a página não abriu sozinha, cola isto no browser:"
echo "http://localhost:8000/docs"
echo ""
echo "Para desligar o projeto, dá duplo-clique em 'parar-mac.command'."
read -p "Prime Enter para fechar esta janela..."
