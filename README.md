# 🌐 search-globe

Un globe holographique 3D en pointillé dans ton terminal, avec les tendances du jour et une barre de recherche qui ouvre ton navigateur.

## Fonctionnalités

- **Globe 3D** en points braille : continents, graticule, balayage radar, anneaux orbitaux et satellites
- **Tendances du jour** (Google Trends) accrochées à des villes du globe : elles tournent avec lui
- **Barre de recherche** : tape, `Entrée`, et la recherche s'ouvre dans ton navigateur par défaut
  (nouvel onglet s'il est déjà ouvert, nouvelle fenêtre sinon)
- **Souris** : clic sur le globe → ouvre le navigateur · clic sur une tendance → la recherche · survol → loupe lumineuse et coordonnées GPS
- Animations de lancement, ondes de choc au clic, effets de survol

## Installation

Testé sur **CachyOS / Arch Linux**. Prérequis : Python 3, `numpy`, `xdg-utils`.

```bash
git clone https://github.com/suzukooooo/search-globe.git
cd search-globe
./install.sh
```

Le script installe les dépendances manquantes (via `pacman`) et copie la commande dans `~/.local/bin/search`.
Si ce dossier n'est pas dans ton `PATH` :

```fish
fish_add_path ~/.local/bin          # fish
```
```bash
export PATH="$HOME/.local/bin:$PATH"   # bash / zsh (dans ~/.bashrc ou ~/.zshrc)
```

Installation manuelle :

```bash
sudo pacman -S python-numpy xdg-utils
install -m755 search.py ~/.local/bin/search
```

## Utilisation

```bash
search                         # tendances France, moteur Google
search --geo US                # tendances d'un autre pays (FR, US, BE, CH, CA…)
search --engine duckduckgo     # google | duckduckgo | brave | bing | qwant
```

Réglages permanents (fish) :

```fish
set -Ux SEARCH_GEO FR
set -Ux SEARCH_ENGINE google
```

| Action | Effet |
|---|---|
| Clic sur le globe | Ouvre le navigateur par défaut |
| Clic sur une tendance | Lance la recherche |
| Texte + `Entrée` | Recherche dans le navigateur |
| `Ctrl+U` | Vide la barre de recherche |
| `Échap` / `Ctrl+C` | Quitter |

## Dépannage

- **Le clic ne marche pas** : ton terminal ne transmet pas la souris. Essaie Konsole, Kitty, Alacritty, WezTerm ou Ghostty.
- **Caractères bizarres** : installe une police avec les caractères braille (ex. une Nerd Font).
- **« Terminal trop petit »** : agrandis la fenêtre (minimum 64×16).
- **Tendances indisponibles** : le flux Google Trends n'a pas répondu, réessaie plus tard.

## Crédits

- Carte du monde : [Natural Earth](https://www.naturalearthdata.com/) (domaine public), téléchargée au premier lancement puis mise en cache dans `~/.cache/search-globe/`.
- Tendances : flux RSS public de Google Trends (non officiel, peut changer sans préavis).

## Licence

[MIT](LICENSE)
