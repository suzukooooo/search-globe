# 🌐 search-globe

Un globe holographique 3D en pointillé dans ton terminal (ou en fond de bureau), avec des tendances (du jour ou **liées à tes centres d'intérêt**) et une barre de recherche qui ouvre ton navigateur.

<!-- Ajoute une capture ou un GIF ici : ![demo](docs/demo.gif) -->

## À propos de ce projet

Ce projet est **« vibecodé »** : je l'ai construit en dialoguant avec une IA (Claude) plutôt qu'en écrivant chaque ligne moi-même.
Il est réalisé **à but éducatif** : c'est un terrain de jeu pour explorer le monde de la programmation, comprendre comment fonctionnent un rendu 3D, une interface terminal ou un appel réseau, et apprendre en bidouillant.

Le code n'a donc aucune prétention de perfection. Il peut contenir des bugs ou des maladresses, et les retours, suggestions et contributions sont les bienvenus pour apprendre ensemble.

## Fonctionnalités

- **Globe 3D** en points braille : continents, graticule, balayage radar, anneaux orbitaux et satellites
- **Tendances accrochées à des villes du globe** : elles tournent avec lui
- **3 modes de tendances** : `base` (Google Trends), `perso` (actus et suggestions liées à ton historique), `mix`
- **Consentement explicite** avant tout envoi de mots-clés, journal local des envois et **mode hors-ligne**
- **Mode paramètres (chat)** : tape `/` pour ouvrir un panneau de discussion avec `/help`
- **7 langues** : français, anglais, espagnol, allemand, russe, italien, portugais (tout est traduit)
- **6 thèmes de couleurs** : cyan, violet, matrix, amber, rose, mono
- **Mode économie** (manuel ou automatique) pour les terminaux lents ou les connexions SSH
- **Widget de bureau** façon glava : le globe transparent au fond de ton écran
- **Lancement automatique** à l'ouverture de session, et écran d'accueil à l'ouverture du terminal
- **Barre de recherche** : tape, `Entrée`, et la recherche s'ouvre dans ton navigateur par défaut
  (nouvel onglet s'il est déjà ouvert, nouvelle fenêtre sinon)
- **Souris** : clic sur le globe ou une tendance, zoom et loupe lumineuse au survol

## Installation

Testé sur **CachyOS / Arch Linux**. Prérequis : Python 3, `numpy`, `xdg-utils`.

### Depuis l'AUR (bientôt)

> ⏸️ Le paquet AUR est prêt (`packaging/aur/PKGBUILD`) mais **pas encore publié** : l'inscription à l'AUR est actuellement fermée. En attendant, utilise l'installation depuis les sources ci-dessous.

Une fois publié :

```bash
yay -S search-globe        # ou : paru -S search-globe
```

Le paquet installera `search-globe` et le raccourci `search`. Pour le publier ou le maintenir : [docs/AUR.md](docs/AUR.md).

### Depuis les sources

```bash
git clone https://github.com/VOTRE_PSEUDO/search-globe.git
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

> Après une mise à jour de `search.py`, relance `bash install.sh` : la commande `search` est une copie.

## Premier lancement

```bash
search
```

Un assistant te demande ta **langue**, le type de tendances (du jour, personnalisées ou mixtes) et ton pays. Si tu choisis un mode personnalisé, il affiche **les mots-clés exacts** qui seraient envoyés et te demande ton accord (refus par défaut). Tes choix sont enregistrés dans `~/.config/search-globe/config.json`. Pour relancer l'assistant : `search setup`.

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

### Mode paramètres (chat)

Dans le panneau, tape une commande commençant par `/` (ou clique sur une puce) :

| Commande | Rôle |
|---|---|
| `/help` | Liste des commandes |
| `/mode base\|perso\|mix` | Type de tendances |
| `/lang fr\|en\|es\|de\|ru\|it\|pt` | Langue de l'interface et des actus (immédiat) |
| `/theme cyan\|violet\|matrix\|amber\|rose\|mono` | Thème de couleurs (immédiat) |
| `/eco on\|off\|auto` | Mode économie |
| `/consent yes\|no\|log` | Envoi de mots-clés : voir ce qui part, accepter, refuser, consulter le journal |
| `/offline on\|off` | Aucune requête réseau |
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
| `search theme violet` | Thème de couleurs (sans argument : liste) |
| `search eco on\|off\|auto` | Mode économie |
| `search consent [status\|yes\|no\|log]` | Consentement d'envoi des mots-clés et journal |
| `search offline on\|off` | Mode hors-ligne |
| `search widget [start\|stop\|restart]` | Globe en fond de bureau (`--dry-run` pour voir la commande, `--area`, `--style`, `--font`, `--focusable`) |
| `search autostart on\|off\|status` | Lancer le widget à l'ouverture de session |
| `search shellhook [fish\|bash\|zsh]` | Ligne à ajouter pour afficher le globe à l'ouverture du terminal |
| `search set geo US` | Pays des tendances et des actus |
| `search set engine duckduckgo` | Moteur : `google`, `duckduckgo`, `brave`, `bing`, `qwant` |
| `search set browser firefox` | Navigateur lu pour le mode perso (`auto` par défaut) |
| `search set topics 3` / `history_days 30` / `max_trends 6` | Centres d'intérêt, jours d'historique, nombre de tendances |
| `search set widget_area\|widget_style\|widget_font\|widget_interactive` | Réglages du widget de bureau (voir plus bas) |
| `search exclude add <mot>` | Masque un sujet (aussi `remove`, `list`, `clear`) |
| `search history` / `search preview` | Centres d'intérêt détectés / aperçu des tendances perso |
| `search mousetest` | Diagnostic de la souris (survol et clics) |
| `search config` / `search reset` | Affiche / supprime les réglages |
| `search --version` | Version |

Options valables pour une seule session, sans rien enregistrer : `--mode`, `--geo`, `--engine`, `--lang`, `--theme`, `--eco`, `--offline`.

La langue `auto` suit celle de ton système (variable `LANG`), puis le pays choisi. Un autre code à 2 lettres (ex. `nl`) est accepté pour les actus et Wikipédia ; l'interface s'affiche alors en anglais.

## Thèmes

`cyan` (défaut), `violet`, `matrix`, `amber`, `rose`, `mono`. Changement immédiat avec `/theme violet`, ou `search theme violet`. Sur un terminal à 8 couleurs, chaque thème utilise une seule teinte.

## Mode économie

Pour les terminaux lents, les connexions SSH ou le widget de bureau : 12 images/s au lieu de 30, moitié moins de points, plus d'halo, d'anneaux orbitaux, de balayage radar ni d'animations d'intro.

- `search eco on` : toujours actif · `search eco off` : jamais · `search eco auto` (défaut)
- En `auto`, il s'active tout seul en session SSH, pour le widget, ou si l'affichage devient trop lent (un message l'indique).

## Tendances personnalisées

En mode `perso` ou `mix`, search-globe repère **tes centres d'intérêt** et cherche ce qui s'y rapporte.
Exemple : tu as cherché « resident evil requiem » et « resident evil 4 remake ».

| Étiquette | Exemple | D'où ça vient |
|---|---|---|
| ◆ actu | Resident Evil : une nouvelle bande-annonce… | Google News (clic : ouvre l'article) |
| ◇ similaire | Silent Hill, Dino Crisis… | Wikipédia (« dans la veine de… ») |
| ◈ genre | Survival horror | Catégories Wikipédia |

1. L'historique de ton navigateur est lu **localement** (Firefox, LibreWolf, Zen, Floorp, Chrome, Chromium, Brave, Vivaldi, Edge, Opera ; Flatpak et Snap pour la plupart). Par défaut, c'est ton navigateur par défaut.
2. Les recherches faites sur Google, DuckDuckGo, Bing, Brave, Qwant, Ecosia, Startpage, Yahoo, Kagi, Yandex et YouTube sont regroupées par sujet. Les sujets récents et répétés passent devant.
3. **Avec ton accord**, les 3 sujets principaux servent à chercher des actus et des suggestions. Sans accord, seuls les sujets détectés s'affichent, en local.

L'extraction des sujets est une heuristique simple (les deux premiers mots utiles de chaque recherche) : elle peut se tromper, et `search exclude add <mot>` permet de masquer un sujet.

## Vie privée et consentement

- **Ton historique reste sur ta machine** : il est lu sur une copie temporaire, supprimée aussitôt. Il n'est jamais envoyé ni enregistré, et le navigateur peut rester ouvert.
- **Aucun mot-clé ne part sans ton accord explicite.** Au premier lancement (ou avec `/consent`), l'application affiche les mots-clés réels qui seraient envoyés à **Google News** et **Wikipédia**. Le refus est le choix par défaut.
- **Jamais envoyés** : tes URL, ton historique complet, tes autres recherches. Comme pour tout site web, ces services voient ton adresse IP.
- **Journal local** : chaque envoi (date, hôte, mot-clé) est noté dans `~/.local/state/search-globe/sent.log`. Consulte-le avec `search consent log`.
- **Retrait à tout moment** : `search consent no` (ou `/consent no`). Sans accord, aucune actu n'est cherchée.
- **Mode hors-ligne** : `search offline on` bloque toute requête réseau (Google Trends compris). Seule la carte du monde est téléchargée une fois au tout premier lancement, puis mise en cache.
- **Mots sensibles ignorés par défaut** (contenu adulte, mots de passe, IBAN) : ni affichés, ni envoyés. Ajoute les tiens avec `search exclude add <mot>`.
- Les sujets s'affichent à l'écran : reste en mode `base` si quelqu'un regarde ton écran. Le mode `base` n'utilise aucune donnée personnelle.

## Widget de bureau (façon glava)

Un terminal ne peut pas cacher la barre du haut, mais on peut lancer le globe **dans une fenêtre sans bordure, transparente et placée sous les autres** : il flotte alors sur ton fond d'écran.

```fish
search widget --dry-run     # montre la méthode choisie et la commande exacte
search widget               # lance le widget
search widget stop          # l'arrête
```

Le widget est **grand, sombre et lumineux** pour ne pas se perdre dans le fond d'écran, et il est **interactif** : la barre de recherche, le panneau de paramètres (`/`, `F2` ou clic sur ⚙) et les clics fonctionnent comme dans le terminal. `Échap` ne le ferme pas (utilise `/quit` ou `search widget stop`).

| Réglage | Commande | Valeurs |
|---|---|---|
| Taille (pixels, toujours bornée à l'écran) | `search set widget_area 1920x1080` | `auto` (écran moins une marge), ou `LARGEURxHAUTEUR` |
| Fond | `search set widget_style glass` | `glass` (verre sombre, défaut), `clear` (transparent), `solid` |
| Taille de police | `search set widget_font 17` | `auto` ou 6 à 72 pt |
| Barre de recherche et paramètres | `search set widget_interactive on` | `on` (défaut) ou `off` (globe seul) |

Les mêmes options existent pour un lancement ponctuel : `search widget restart --area 1080x1920 --style clear --font 20`. Un écran en portrait (1080×1920) est géré : la police s'adapte pour garder assez de colonnes.

**Un seul widget à la fois** : `search widget` refuse de lancer un doublon (`search widget restart` pour le relancer). Le widget utilise sa **propre config kitty** (`~/.config/search-globe/kitty-widget.conf`), sans toucher à ton `kitty.conf`.

**Clavier** : une fenêtre de type « bureau » peut ne pas recevoir le clavier selon le bureau. Si la saisie ne répond pas, lance `search widget restart --focusable` (la fenêtre reste sous les autres mais peut prendre le focus).

**Méthodes automatiques** (terminal conseillé : [kitty](https://sw.kovidgoyal.net/kitty/)). Si la première méthode échoue, la suivante est essayée automatiquement :

| Session | Méthodes, dans l'ordre |
|---|---|
| Wayland avec layer-shell (Hyprland, Sway, KDE Plasma 6…) | 1. `kitten panel --edge=background` (couche « fond d'écran »)  2. XWayland (voir ci-dessous) |
| **GNOME sur Wayland** | **XWayland** : GNOME n'a pas de layer-shell, donc kitty tourne en fenêtre X11 transparente, puis `xprop` lui donne le type « bureau » et `wmctrl` la place sous les autres sur tous les bureaux |
| X11 (KDE, XFCE, i3…) | kitty ou alacritty transparent, puis `xprop` + `wmctrl` comme ci-dessus |

Outils pour les méthodes X11 / XWayland : `sudo pacman -S kitty xdotool wmctrl xorg-xprop`.

> ⚠️ Cette partie n'a pu être testée qu'avec de faux programmes, pas sur un vrai bureau : les options de kitty varient selon la version, et la méthode XWayland de GNOME est **expérimentale**. `search widget --dry-run` te montre les commandes exactes pour les corriger si besoin. GNOME n'offre aucun moyen officiel de placer une fenêtre sous les autres : si le globe reste au-dessus de tes fenêtres, c'est la limite du bureau, pas du projet.

**Règles de fenêtre manuelles** (classe de la fenêtre : `search-globe-widget`) :

- **GNOME** : aucune règle de fenêtre native. Essaie la méthode XWayland ci-dessus, ou passe à une session X11 (« GNOME sur Xorg ») si ton système la propose.
- **KDE Plasma** : Paramètres → Gestion des fenêtres → Règles de fenêtre → Ajouter. Classe `search-globe-widget`, puis forcer « Garder en dessous », « Ignorer la barre des tâches », « Ignorer le sélecteur de pages », « Pas de barre de titre ni de cadre », « Bureau : tous ».
- **Hyprland** :
  ```
  windowrulev2 = float, class:^(search-globe-widget)$
  windowrulev2 = noborder, class:^(search-globe-widget)$
  windowrulev2 = pin, class:^(search-globe-widget)$
  windowrulev2 = nofocus, class:^(search-globe-widget)$
  ```
- **Sway** : `for_window [app_id="search-globe-widget"] floating enable, border none, sticky enable`
- **i3** : `for_window [class="search-globe-widget"] floating enable, border none, sticky enable` (i3 ne sait pas placer une fenêtre « sous » les autres).
- La transparence demande un compositeur (inclus dans KDE, Hyprland, Sway ; `picom` pour i3).

## Lancement automatique

- **Widget à l'ouverture de session** : `search autostart on` (fichier XDG dans `~/.config/autostart`, lu par KDE, GNOME, XFCE…). Pour Hyprland, Sway, i3, la commande affiche la ligne à ajouter (`exec-once = …`). `search autostart off` pour annuler.
- **Écran d'accueil à l'ouverture du terminal** : le globe s'affiche 3 secondes (n'importe quelle touche le ferme) puis le terminal reprend. `search shellhook` affiche la ligne à copier dans `~/.config/fish/config.fish` (ou `~/.bashrc`, `~/.zshrc`).

## Dépannage

- **Le survol ne marche pas (pas de zoom)** : lance `search mousetest` et bouge la souris. Si aucun mouvement n'est reçu, ton terminal ne transmet pas le survol. Konsole, Kitty, Alacritty, WezTerm et Ghostty le gèrent.
- **Le clic ne marche pas** : même diagnostic.
- **Affichage saccadé** : `search eco on`.
- **Caractères bizarres** : installe une police avec les caractères braille (ex. une Nerd Font).
- **« Terminal trop petit »** : agrandis la fenêtre (minimum 64×16).
- **Tendances indisponibles** : le flux Google Trends n'a pas répondu, réessaie plus tard (ou vérifie que le mode hors-ligne est désactivé).
- **Mode perso sans actus** : c'est le consentement (`/consent`). Pour voir ce qui est détecté : `search history`.
- **Widget qui ne démarre pas** : `search widget --dry-run`, puis la section « Widget de bureau ». Au démarrage de session, ce que le widget affiche est noté dans `~/.local/state/search-globe/autostart.log` (et la sortie du terminal dans `widget.log`).
- **Un éditeur (nano) s'ouvre à chaque démarrage** : search-globe ne lance jamais d'éditeur. Pour trouver qui le lance, juste après la connexion : `ps -eo pid,ppid,etime,cmd | grep -E "[n]ano"` (le chemin du fichier ouvert et le processus parent indiquent l'origine), et `ls ~/.config/autostart/`.

## Crédits

- Carte du monde : [Natural Earth](https://www.naturalearthdata.com/) (domaine public), téléchargée au premier lancement puis mise en cache dans `~/.cache/search-globe/`.
- Tendances du jour : flux RSS public de Google Trends (non officiel, peut changer sans préavis).
- Actus : flux RSS de Google News. Suggestions et genres : API de Wikipédia.

## Licence

[MIT](LICENSE)
