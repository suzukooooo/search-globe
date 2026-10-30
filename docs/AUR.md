# Publier search-globe sur l'AUR

L'AUR (Arch User Repository) permet d'installer le projet avec `yay -S search-globe` ou `paru -S search-globe`.

## 1. Préparer une release GitHub

Le PKGBUILD télécharge l'archive d'un tag. Depuis le dossier du dépôt :

```fish
git tag v2.4.0
git push origin v2.4.0
```

GitHub génère l'archive `https://github.com/VOTRE_PSEUDO/search-globe/archive/refs/tags/v2.4.0.tar.gz`.

## 2. Adapter et tester le PKGBUILD en local

```fish
cd packaging/aur
# remplace VOTRE NOM, VOTRE_PSEUDO et l'email dans PKGBUILD
sudo pacman -S --needed base-devel pacman-contrib namcap
updpkgsums                      # calcule la vraie somme sha256
makepkg -si                     # construit et installe
namcap PKGBUILD                 # vérifie le PKGBUILD
namcap search-globe-*.pkg.tar.zst
```

Teste ensuite `search --version` et `search`.

## 3. Vérifier le nom et le conflit de fichier

- Cherche `search-globe` sur https://aur.archlinux.org/packages : le nom doit être libre.
- Le PKGBUILD installe `/usr/bin/search-globe` et le raccourci `/usr/bin/search`. Vérifie qu'aucun paquet n'a déjà ce fichier : `pacman -F usr/bin/search`. En cas de conflit, supprime la ligne `ln -s` (la commande restera `search-globe`).

## 4. Créer le compte et pousser sur l'AUR

1. Crée un compte sur https://aur.archlinux.org et ajoute ta clé SSH publique (Mon compte → Clé SSH).
2. Clone le dépôt AUR (vide) et publie :

```fish
git clone ssh://aur@aur.archlinux.org/search-globe.git aur-search-globe
cd aur-search-globe
cp ../packaging/aur/PKGBUILD .
makepkg --printsrcinfo > .SRCINFO
git add PKGBUILD .SRCINFO
git commit -m "Initial import: search-globe 2.4.0"
git push origin master
```

Le fichier `.SRCINFO` est obligatoire et doit toujours correspondre au PKGBUILD.

## 5. Publier une nouvelle version

1. Nouveau tag GitHub (`v2.5.0`).
2. Dans le PKGBUILD : mets à jour `pkgver`, remets `pkgrel=1`, lance `updpkgsums`.
3. Régénère `.SRCINFO` : `makepkg --printsrcinfo > .SRCINFO`.
4. `git commit` puis `git push`.

## Bonnes pratiques

- Ne pousse jamais de binaire ni de fichier d'archive dans le dépôt AUR.
- Réponds aux commentaires et signale les paquets obsolètes (« flag out-of-date ») dès qu'une nouvelle version sort.
- Une variante `search-globe-git` (dernière version du dépôt) peut être ajoutée plus tard.
