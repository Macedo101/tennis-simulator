#!/bin/bash
# Duplo-clique neste ficheiro para desligar o projeto.

cd "$(dirname "$0")/backend" || exit 1
docker compose down

echo "Projeto desligado."
read -p "Prime Enter para fechar esta janela..."
