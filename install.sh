#!/usr/bin/env bash
# Installe la commande `search` dans ~/.local/bin
set -euo pipefail

DEST="${HOME}/.local/bin"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! python3 -c "import numpy" 2>/dev/null; then
  echo "→ numpy est manquant."
  if command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --needed python-numpy
  else
    echo "Installe numpy (ex : pip install --user numpy) puis relance ce script."
    exit 1
  fi
fi

if ! command -v xdg-open >/dev/null 2>&1; then
  echo "→ xdg-open est manquant (nécessaire pour ouvrir le navigateur)."
  command -v pacman >/dev/null 2>&1 && sudo pacman -S --needed xdg-utils
fi

mkdir -p "$DEST"
install -m755 "$DIR/search.py" "$DEST/search"
echo "✔ Installé : $DEST/search"

case ":$PATH:" in
  *":$DEST:"*) echo "Lance simplement :  search" ;;
  *) echo "⚠ $DEST n'est pas dans ton PATH."
     echo "  fish :  fish_add_path ~/.local/bin"
     echo "  bash/zsh :  export PATH=\"\$HOME/.local/bin:\$PATH\"  (à mettre dans ~/.bashrc ou ~/.zshrc)" ;;
esac
