# 🌐 search-globe

Un globe holographique 3D en pointillé dans ton terminal, avec des tendances (du jour ou **liées à tes centres d'intérêt**) et une barre de recherche qui ouvre ton navigateur.

<!-- Ajoute une capture ou un GIF ici : ![demo](docs/demo.gif) -->

## À propos de ce projet

Ce projet est **« vibecodé »** : je l'ai construit en dialoguant avec une IA (Claude) plutôt qu'en écrivant chaque ligne moi-même.
Il est réalisé **à but éducatif** : c'est un terrain de jeu pour explorer le monde de la programmation, comprendre comment fonctionnent un rendu 3D, une interface terminal ou un appel réseau, et apprendre en bidouillant.

Le code n'a donc aucune prétention de perfection. Il peut contenir des bugs ou des maladresses, et les retours, suggestions et contributions sont les bienvenus pour apprendre ensemble.

## Fonctionnalités

- **Globe 3D** en points braille : continents, graticule, balayage radar, anneaux orbitaux et satellites
- **Tendances accrochées à des villes du globe** : elles tournent avec lui, avec des étiquettes en orbite
- **3 modes de tendances** (choisis au premier lancement, modifiables à tout moment) :
  - `base` : tendances du jour Google Trends (aucune donnée personnelle)
  - `perso` : **actus et suggestions liées à ton historique**
  - `mix` : les deux en alternance
- **Barre de recherche** : tape, `Entrée`, et la recherche s'ouvre dans ton navigateur par défaut
  (nouvel onglet s'il est déjà ouvert, nouvelle fenêtre sinon)
- **Souris** : clic sur le globe → ouvre le navigateur · clic sur une tendance → la recherche ou l'article
- **Animations** : lancement, zoom au survol du globe et des tendances, loupe lumineuse + coordonnées GPS, ondes de choc au clic
- **Mode paramètres (chat)** : tape `/` (ou clique sur ⚙) : le globe se décale et un panneau de discussion s'ouvre, avec bulles, indicateur « écrit… », zone « Écrire… », puces cliquables et `/help` pour toutes les commandes
- **7 langues** : français, anglais, espagnol, allemand, russe, italien, portugais. Toute l'interface est traduite (menus, messages, assistant, aide, chat), ainsi que les actus personnalisées. Changement en direct avec `/lang es`

## Installation

Testé sur **CachyOS / Arch Linux**. Prérequis : Python 3, `numpy`, `xdg-utils`.

```bash
git clone https://github.com/suzukooooo/search-globe.git
cd search-globe
bash install.sh
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

> Après une mise à jour de `search.py`, relance `bash install.sh` : la commande `search` est une copie.

## Premier lancement

```bash
search
```

Un petit assistant te demande ta **langue**, le type de tendances que tu préfères (du jour, personnalisées ou mixtes) et ton pays. Tes choix sont enregistrés dans `~/.config/search-globe/config.json`.
Pour relancer l'assistant : `search setup`.

## Utilisation

| Action | Effet |
|---|---|
| `/` dans la barre, `F2` ou clic sur ⚙ | Ouvre le mode paramètres (chat) |
| Clic sur le globe | Ouvre le navigateur par défaut |
| Clic sur une tendance | Lance la recherche (ou ouvre l'article pour une actu) |
| Survol du globe / d'une tendance | Zoom, loupe lumineuse, coordonnées GPS |
| Texte + `Entrée` | Recherche dans le navigateur |
| `Tab` | Change de mode (base → perso → mix), enregistré |
| `Ctrl+U` | Vide la barre de recherche |
| `Échap` | Quitter (ou fermer le chat s'il est ouvert) |
| `Ctrl+C` | Quitter |

### Mode paramètres (chat)

Dans le panneau, tape une commande commençant par `/` (ou clique sur une puce) :

| Commande | Rôle |
|---|---|
| `/help` | Liste des commandes |
| `/mode base\|perso\|mix` | Type de tendances |
| `/lang fr\|en\|es\|de\|ru\|it\|pt` | Langue de l'interface et des actus (changement immédiat) |
| `/geo`, `/engine`, `/browser`, `/topics`, `/days`, `/max` | Pays, moteur, navigateur, centres d'intérêt, jours d'historique, nombre de tendances |
| `/exclude add\|remove\|list\|clear` | Masquer des sujets |
| `/history` / `/preview` | Centres d'intérêt détectés / tendances affichées |
| `/config`, `/refresh`, `/clear` | Réglages, recharger, effacer la conversation |
| `/reset oui` | Réinitialiser les réglages |
| `/exit` / `/quit` | Retour au globe / quitter |

Astuces : `Tab` complète les commandes, `↑` rappelle les précédentes, `PgUp`/`PgDn` ou la molette font défiler.

### Commandes du terminal

| Commande | Rôle |
|---|---|
| `search` | Lance l'interface |
| `search setup` | Relance l'assistant de configuration |
| `search mode base\|perso\|mix` | Change le type de tendances |
| `search lang es` | Langue (`fr`, `en`, `es`, `de`, `ru`, `it`, `pt`) |
| `search set geo US` | Pays des tendances et des actus (FR, US, BE, CH, CA…) |
| `search set engine duckduckgo` | Moteur : `google`, `duckduckgo`, `brave`, `bing`, `qwant` |
| `search set browser firefox` | Navigateur lu pour le mode perso (`auto` par défaut) |
| `search set topics 3` | Nombre de centres d'intérêt suivis (1 à 5) |
| `search set history_days 30` | Période d'historique analysée (60 jours par défaut) |
| `search set max_trends 6` | Nombre de tendances affichées (1 à 8) |
| `search exclude add <mot>` | Masque un sujet (aussi `remove`, `list`, `clear`) |
| `search history` | Montre les centres d'intérêt détectés (affichage local) |
| `search preview` | Aperçu des tendances perso sans lancer l'interface |
| `search mousetest` | Diagnostic de la souris (survol et clics) |
| `search config` | Affiche les réglages |
| `search reset` | Supprime les réglages (l'assistant se relancera) |

Options valables pour une seule session, sans rien enregistrer : `search --mode perso --geo US --engine brave --lang de`.

La langue `auto` suit celle de ton système (variable `LANG`), puis le pays choisi. Un autre code à 2 lettres (ex. `nl`) est accepté pour les actus et Wikipédia ; l'interface s'affiche alors en anglais.

## Tendances personnalisées

En mode `perso` ou `mix`, search-globe ne te montre pas « tes recherches les plus fréquentes » : il repère **tes centres d'intérêt** et cherche ce qui s'y rapporte.

Exemple : tu as cherché « resident evil requiem » et « resident evil 4 remake ».

| Étiquette | Exemple | D'où ça vient |
|---|---|---|
| ◆ actu | Resident Evil : une nouvelle bande-annonce… | Google News (clic : ouvre l'article) |
| ◇ similaire | Silent Hill, Dino Crisis… | Wikipédia (« dans la veine de… ») |
| ◈ genre | Survival horror | Catégories Wikipédia |

Comment ça marche :

1. L'historique de ton navigateur est lu **localement** (Firefox, LibreWolf, Zen, Floorp, Chrome, Chromium, Brave, Vivaldi, Edge, Opera ; Flatpak et Snap pour la plupart). Par défaut, c'est ton navigateur par défaut.
2. Les recherches faites sur Google, DuckDuckGo, Bing, Brave, Qwant, Ecosia, Startpage, Yahoo, Kagi, Yandex et YouTube sont regroupées par sujet. Les sujets récents et répétés passent devant.
3. Pour les 3 sujets principaux, l'application cherche des actus et des suggestions liées. Si le réseau est coupé, le sujet seul s'affiche.

L'extraction des sujets est une heuristique simple (les deux premiers mots utiles de chaque recherche) : elle peut se tromper, et `search exclude add <mot>` permet de masquer un sujet.

## Vie privée

- **Ton historique reste sur ta machine** : il est lu sur une copie temporaire, supprimée aussitôt. Il n'est ni envoyé, ni enregistré, et le navigateur peut rester ouvert.
- **Mais des mots-clés sortent** : en mode `perso` / `mix`, les 1 à 5 sujets détectés (ex. « resident evil ») sont envoyés à **Google News** et **Wikipédia** pour trouver des actus liées. Jamais d'URL, ni l'historique complet, ni tes autres recherches.
- **Mots sensibles ignorés par défaut** (contenu adulte, mots de passe, IBAN) : ils ne sont ni affichés, ni envoyés. Ajoute les tiens avec `search exclude add <mot>`.
- Ces sujets s'affichent à l'écran : reste en mode `base` si quelqu'un regarde ton écran. Le mode `base` n'utilise aucune donnée personnelle.
- `search history` et `search preview` montrent exactement ce qui est détecté et affiché.

## Dépannage

- **Le survol ne marche pas (pas de zoom)** : lance `search mousetest` et bouge la souris. Si aucun mouvement n'est reçu, ton terminal ne transmet pas le survol. Konsole, Kitty, Alacritty, WezTerm et Ghostty le gèrent.
- **Le clic ne marche pas** : même diagnostic, ton terminal ne transmet pas la souris.
- **Caractères bizarres** : installe une police avec les caractères braille (ex. une Nerd Font).
- **« Terminal trop petit »** : agrandis la fenêtre (minimum 64×16).
- **Tendances indisponibles** : le flux Google Trends n'a pas répondu, réessaie plus tard.
- **Mode perso vide** : lance `search history` pour voir ce qui est détecté, puis précise ton navigateur avec `search set browser firefox`.

## Crédits

- Carte du monde : [Natural Earth](https://www.naturalearthdata.com/) (domaine public), téléchargée au premier lancement puis mise en cache dans `~/.cache/search-globe/`.
- Tendances du jour : flux RSS public de Google Trends (non officiel, peut changer sans préavis).
- Actus : flux RSS de Google News. Suggestions et genres : API de Wikipédia.

## Licence

[MIT](LICENSE)
