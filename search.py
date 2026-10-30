#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
search v2 : globe holographique 3D + tendances en orbite + barre de recherche.

  - Clic sur le globe        -> ouvre le navigateur par défaut
  - Clic sur une tendance    -> lance la recherche correspondante
  - Texte + Entrée           -> recherche (nouvel onglet, ou nouvelle fenêtre si fermé)
  - Survol du globe/tendance -> zoom, loupe lumineuse + coordonnées GPS
  - Mode perso               -> actus et suggestions liées à ton historique
  - Tab                      -> change de mode de tendances (base / perso / mixte)
  - /  ou  ⚙  ou  F2         -> mode paramètres (chat) : /help, /mode, /lang, /geo…
  - Échap / Ctrl+C           -> quitter

Dépendance : python-numpy  (sudo pacman -S python-numpy)
Usage : search                      lance l'interface
        search setup                reconfigure (choix des tendances, pays)
        search mode base|perso|mix  change le type de tendances
        search config | history | preview | set <clé> <valeur> | exclude … | reset
        search mousetest            diagnostic de la souris (survol, clics)
        search --help               toutes les options
"""
import argparse
import curses
import glob
import itertools
import json
import locale
import math
import os
import re
import shlex
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    import numpy as np
except ImportError:
    sys.exit("numpy est requis :  sudo pacman -S python-numpy")

UA = "Mozilla/5.0 (X11; Linux x86_64) search-globe/2.0"
LAND_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
            "master/geojson/ne_110m_land.geojson")
CACHE = (Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
         / "search-globe" / "land_1deg.json")

ENGINES = {
    "google":     ("https://www.google.com",   "https://www.google.com/search?q="),
    "duckduckgo": ("https://duckduckgo.com",   "https://duckduckgo.com/?q="),
    "brave":      ("https://search.brave.com", "https://search.brave.com/search?q="),
    "bing":       ("https://www.bing.com",     "https://www.bing.com/search?q="),
    "qwant":      ("https://www.qwant.com",    "https://www.qwant.com/?q="),
}

# Points d'ancrage des tendances sur le globe (lat, lon)
CITIES = [(48.9, 2.3), (40.7, -74.0), (35.7, 139.7), (-23.5, -46.6),
          (19.1, 72.9), (34.0, -118.2), (-33.9, 151.2), (-26.2, 28.0)]

STEP = 1.0                                   # résolution de la carte (degrés)
BIT = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))
TILT = 0.40
CT, ST = math.cos(TILT), math.sin(TILT)
MAX_TRENDS = 8
GLYPH = {"base": "▸", "news": "◆", "like": "◇", "genre": "◈"}
VERSION = "2.4.0"
WIKI_UA = f"search-globe/{VERSION} (terminal globe; educational open-source project)"


# --------------------------------------------------------------------------
#  Traductions : fr, en, es, de, ru, it, pt
# --------------------------------------------------------------------------
LANGS = ("fr", "en", "es", "de", "ru", "it", "pt")
LANG_NAMES = {"fr": "Français", "en": "English", "es": "Español", "de": "Deutsch",
              "ru": "Русский", "it": "Italiano", "pt": "Português"}
LANG_ALIASES = {"francais": "fr", "français": "fr", "french": "fr", "anglais": "en",
                "english": "en", "espagnol": "es", "espanol": "es", "español": "es",
                "spanish": "es", "allemand": "de", "deutsch": "de", "german": "de",
                "russe": "ru", "русский": "ru", "russian": "ru", "italien": "it",
                "italiano": "it", "italian": "it", "portugais": "pt", "portugues": "pt",
                "português": "pt", "portuguese": "pt"}
YES_WORDS = {"o", "oui", "y", "yes", "s", "si", "sí", "j", "ja", "д", "да", "sim"}
CUR = "fr"
S = {}


def _add(key, *vals):
    assert len(vals) == len(LANGS), key
    S[key] = vals


def set_lang(code):
    global CUR
    CUR = code if code in LANGS else "en"


def tx(key, **kw):
    row = S.get(key)
    if row is None:
        return key
    text = row[LANGS.index(CUR)]
    return text.format(**kw) if kw else text


# ---- interface principale
_add("too_small",
     "Terminal trop petit — agrandis la fenêtre.",
     "Terminal too small — enlarge the window.",
     "Ventana demasiado pequeña — agrándala.",
     "Terminal zu klein – bitte Fenster vergrößern.",
     "Терминал слишком мал — увеличьте окно.",
     "Terminale troppo piccolo — ingrandisci la finestra.",
     "Terminal muito pequeno — aumente a janela.")
_add("hint_main",
     "clic : ouvrir · Entrée : chercher · / : paramètres · Tab : mode · Échap : quitter",
     "click: open · Enter: search · / : settings · Tab: mode · Esc: quit",
     "clic: abrir · Intro: buscar · / : ajustes · Tab: modo · Esc: salir",
     "Klick: öffnen · Enter: suchen · / : Einstellungen · Tab: Modus · Esc: Ende",
     "клик: открыть · Enter: поиск · / : настройки · Tab: режим · Esc: выход",
     "clic: apri · Invio: cerca · / : impostazioni · Tab: modalità · Esc: esci",
     "clique: abrir · Enter: buscar · / : ajustes · Tab: modo · Esc: sair")
_add("hint_boot", "initialisation…", "initializing…", "iniciando…", "Initialisierung…",
     "запуск…", "avvio…", "iniciando…")
_add("hint_chat",
     "Échap : retour au globe · PgUp/PgDn : défiler · Tab : compléter",
     "Esc: back to globe · PgUp/PgDn: scroll · Tab: complete",
     "Esc: volver al globo · PgUp/PgDn: desplazar · Tab: completar",
     "Esc: zurück zum Globus · Bild↑/↓: scrollen · Tab: vervollständigen",
     "Esc: к глобусу · PgUp/PgDn: прокрутка · Tab: дополнить",
     "Esc: torna al globo · PgUp/PgDn: scorri · Tab: completa",
     "Esc: voltar ao globo · PgUp/PgDn: rolar · Tab: completar")
_add("hover_article", "↗ clic : ouvrir l'article", "↗ click: open the article",
     "↗ clic: abrir el artículo", "↗ Klick: Artikel öffnen", "↗ клик: открыть статью",
     "↗ clic: apri l'articolo", "↗ clique: abrir o artigo")
_add("hover_search", "↗ clic : rechercher « {q} »", "↗ click: search “{q}”",
     "↗ clic: buscar «{q}»", "↗ Klick: nach „{q}“ suchen", "↗ клик: искать «{q}»",
     "↗ clic: cerca «{q}»", "↗ clique: buscar «{q}»")
_add("hover_globe",
     "◉ LAT {lat}  LON {lon}  ·  clic : ouvrir le navigateur",
     "◉ LAT {lat}  LON {lon}  ·  click: open the browser",
     "◉ LAT {lat}  LON {lon}  ·  clic: abrir el navegador",
     "◉ BR {lat}  LÄ {lon}  ·  Klick: Browser öffnen",
     "◉ ШИР {lat}  ДОЛ {lon}  ·  клик: открыть браузер",
     "◉ LAT {lat}  LON {lon}  ·  clic: apri il browser",
     "◉ LAT {lat}  LON {lon}  ·  clique: abrir o navegador")
_add("dir_n", "N", "N", "N", "N", "С", "N", "N")
_add("dir_s", "S", "S", "S", "S", "Ю", "S", "S")
_add("dir_e", "E", "E", "E", "O", "В", "E", "L")
_add("dir_w", "O", "W", "O", "W", "З", "O", "O")
_add("msg_search", "↗ recherche : {q}", "↗ searching: {q}", "↗ buscando: {q}",
     "↗ Suche: {q}", "↗ поиск: {q}", "↗ ricerca: {q}", "↗ buscando: {q}")
_add("msg_browser", "↗ ouverture du navigateur", "↗ opening the browser",
     "↗ abriendo el navegador", "↗ Browser wird geöffnet", "↗ открываю браузер",
     "↗ apertura del browser", "↗ abrindo o navegador")
_add("msg_article", "↗ ouverture de l'article", "↗ opening the article",
     "↗ abriendo el artículo", "↗ Artikel wird geöffnet", "↗ открываю статью",
     "↗ apertura dell'articolo", "↗ abrindo o artigo")
_add("msg_mode", "mode : {m} (enregistré)", "mode: {m} (saved)", "modo: {m} (guardado)",
     "Modus: {m} (gespeichert)", "режим: {m} (сохранено)", "modalità: {m} (salvata)",
     "modo: {m} (salvo)")
_add("placeholder", "Rechercher sur le web…", "Search the web…", "Buscar en la web…",
     "Im Web suchen…", "Поиск в интернете…", "Cerca sul web…", "Pesquisar na web…")
_add("updated", "maj", "upd", "act.", "Stand", "обн.", "agg.", "atual.")
_add("header_base", "TENDANCES · {geo}", "TRENDS · {geo}", "TENDENCIAS · {geo}",
     "TRENDS · {geo}", "ТРЕНДЫ · {geo}", "TENDENZE · {geo}", "TENDÊNCIAS · {geo}")
_add("header_perso", "POUR VOUS · {t}", "FOR YOU · {t}", "PARA TI · {t}", "FÜR DICH · {t}",
     "ДЛЯ ВАС · {t}", "PER TE · {t}", "PARA VOCÊ · {t}")
_add("header_perso_empty",
     "TENDANCES · {geo} (historique vide)", "TRENDS · {geo} (empty history)",
     "TENDENCIAS · {geo} (historial vacío)", "TRENDS · {geo} (Verlauf leer)",
     "ТРЕНДЫ · {geo} (история пуста)", "TENDENZE · {geo} (cronologia vuota)",
     "TENDÊNCIAS · {geo} (histórico vazio)")
_add("header_mix", "MIXTE · {geo} + vous", "MIXED · {geo} + you", "MIXTO · {geo} + tú",
     "GEMISCHT · {geo} + du", "СМЕШАННЫЙ · {geo} + вы", "MISTO · {geo} + te",
     "MISTO · {geo} + você")
_add("status_sync", "synchronisation des tendances…", "syncing trends…",
     "sincronizando tendencias…", "Trends werden geladen…", "загрузка трендов…",
     "sincronizzazione tendenze…", "sincronizando tendências…")
_add("status_analyze", "analyse de ton historique…", "analyzing your history…",
     "analizando tu historial…", "Verlauf wird analysiert…", "анализ вашей истории…",
     "analisi della cronologia…", "analisando seu histórico…")
_add("status_nohist", "aucune recherche trouvée dans l'historique",
     "no searches found in the history", "no se encontraron búsquedas en el historial",
     "keine Suchen im Verlauf gefunden", "в истории нет поисковых запросов",
     "nessuna ricerca trovata nella cronologia", "nenhuma busca encontrada no histórico")
_add("status_histerr", "historique illisible", "history unreadable", "historial ilegible",
     "Verlauf nicht lesbar", "история недоступна", "cronologia illeggibile",
     "histórico ilegível")
_add("status_offline", "tendances indisponibles (hors-ligne ?)", "trends unavailable (offline?)",
     "tendencias no disponibles (¿sin conexión?)", "Trends nicht verfügbar (offline?)",
     "тренды недоступны (нет сети?)", "tendenze non disponibili (offline?)",
     "tendências indisponíveis (offline?)")
_add("d_news", "actu", "news", "noticia", "News", "новости", "notizie", "notícia")
_add("d_like", "dans la veine de {t}", "similar to {t}", "en la línea de {t}",
     "ähnlich wie {t}", "в духе {t}", "sulla scia di {t}", "na linha de {t}")
_add("d_genre", "genre", "genre", "género", "Genre", "жанр", "genere", "gênero")
_add("d_hist", "d'après ton historique", "based on your history", "según tu historial",
     "nach deinem Verlauf", "по вашей истории", "dalla tua cronologia", "pelo seu histórico")
_add("mode_base", "tendances du jour (Google Trends)", "daily trends (Google Trends)",
     "tendencias del día (Google Trends)", "Tagestrends (Google Trends)",
     "тренды дня (Google Trends)", "tendenze del giorno (Google Trends)",
     "tendências do dia (Google Trends)")
_add("mode_perso",
     "personnalisées (actus et suggestions liées à ton historique)",
     "personalized (news and suggestions based on your history)",
     "personalizadas (noticias y sugerencias según tu historial)",
     "personalisiert (News und Vorschläge nach deinem Verlauf)",
     "персональные (новости и подборки по вашей истории)",
     "personalizzate (notizie e suggerimenti dalla tua cronologia)",
     "personalizadas (notícias e sugestões pelo seu histórico)")
_add("mode_mix", "mixte (tendances du jour + tes recherches)",
     "mixed (daily trends + your interests)", "mixto (tendencias del día + tus intereses)",
     "gemischt (Tagestrends + deine Interessen)", "смешанный (тренды дня + ваши интересы)",
     "misto (tendenze del giorno + i tuoi interessi)",
     "misto (tendências do dia + seus interesses)")

# ---- erreurs / retours de commandes
_add("err_mode", "choisis : base, perso ou mix", "choose: base, perso or mix",
     "elige: base, perso o mix", "wähle: base, perso oder mix",
     "выберите: base, perso или mix", "scegli: base, perso o mix",
     "escolha: base, perso ou mix")
_add("err_geo", "code pays à 2 lettres (FR, US, BE, CH…)", "2-letter country code (FR, US, BE, CH…)",
     "código de país de 2 letras (ES, MX, FR, US…)", "Ländercode mit 2 Buchstaben (DE, AT, CH, FR…)",
     "двухбуквенный код страны (RU, US, DE, FR…)", "codice paese di 2 lettere (IT, FR, US, CH…)",
     "código de país de 2 letras (BR, PT, FR, US…)")
_add("err_engine", "choisis parmi : {l}", "choose from: {l}", "elige entre: {l}",
     "wähle aus: {l}", "выберите из: {l}", "scegli tra: {l}", "escolha entre: {l}")
_add("err_lang", "auto ou un code langue à 2 lettres (fr, en, de…)",
     "auto or a 2-letter language code (fr, en, de…)",
     "auto o un código de idioma de 2 letras (es, en, de…)",
     "auto oder ein 2-Buchstaben-Sprachcode (de, en, fr…)",
     "auto или двухбуквенный код языка (ru, en, de…)",
     "auto o un codice lingua di 2 lettere (it, en, de…)",
     "auto ou um código de idioma de 2 letras (pt, en, de…)")
_add("err_int", "entier attendu", "integer expected", "se espera un número entero",
     "Ganzzahl erwartet", "ожидается целое число", "numero intero atteso",
     "número inteiro esperado")
_add("err_range", "valeur entre {lo} et {hi}", "value between {lo} and {hi}",
     "valor entre {lo} y {hi}", "Wert zwischen {lo} und {hi}", "значение от {lo} до {hi}",
     "valore tra {lo} e {hi}", "valor entre {lo} e {hi}")
_add("ok_mode", "✔ mode : {m}", "✔ mode: {m}", "✔ modo: {m}", "✔ Modus: {m}",
     "✔ режим: {m}", "✔ modalità: {m}", "✔ modo: {m}")
_add("ok_lang", "✔ Langue : {n}", "✔ Language: {n}", "✔ Idioma: {n}", "✔ Sprache: {n}",
     "✔ Язык: {n}", "✔ Lingua: {n}", "✔ Idioma: {n}")
_add("cfg_file", "Fichier : {p}", "File: {p}", "Archivo: {p}", "Datei: {p}", "Файл: {p}",
     "File: {p}", "Arquivo: {p}")
_add("cfg_new", "(pas encore créé)", "(not created yet)", "(aún no creado)",
     "(noch nicht erstellt)", "(ещё не создан)", "(non ancora creato)", "(ainda não criado)")
_add("cfg_mode", "Mode actuel : {m}", "Current mode: {m}", "Modo actual: {m}",
     "Aktueller Modus: {m}", "Текущий режим: {m}", "Modalità attuale: {m}", "Modo atual: {m}")
_add("hist_none",
     "Aucun historique de navigateur trouvé.\nEssaie :  search set browser firefox  (ou chrome, brave, zen…)",
     "No browser history found.\nTry:  search set browser firefox  (or chrome, brave, zen…)",
     "No se encontró historial de navegador.\nPrueba:  search set browser firefox  (o chrome, brave, zen…)",
     "Kein Browserverlauf gefunden.\nVersuche:  search set browser firefox  (oder chrome, brave, zen…)",
     "История браузера не найдена.\nПопробуйте:  search set browser firefox  (или chrome, brave, zen…)",
     "Nessuna cronologia del browser trovata.\nProva:  search set browser firefox  (o chrome, brave, zen…)",
     "Nenhum histórico de navegador encontrado.\nTente:  search set browser firefox  (ou chrome, brave, zen…)")
_add("hist_src", "Sources : {s}", "Sources: {s}", "Fuentes: {s}", "Quellen: {s}",
     "Источники: {s}", "Fonti: {s}", "Fontes: {s}")
_add("hist_empty", "Aucune recherche trouvée sur les {d} derniers jours.",
     "No searches found in the last {d} days.",
     "No se encontraron búsquedas en los últimos {d} días.",
     "Keine Suchen in den letzten {d} Tagen gefunden.",
     "За последние {d} дн. поисков не найдено.",
     "Nessuna ricerca negli ultimi {d} giorni.",
     "Nenhuma busca nos últimos {d} dias.")
_add("hist_topics",
     "Centres d'intérêt détectés (ces mots-clés servent à chercher des actus) :",
     "Detected interests (these keywords are used to look up news):",
     "Intereses detectados (estas palabras clave sirven para buscar noticias):",
     "Erkannte Interessen (diese Stichwörter dienen der News-Suche):",
     "Найденные интересы (эти слова используются для поиска новостей):",
     "Interessi rilevati (queste parole chiave servono a cercare notizie):",
     "Interesses detectados (estas palavras-chave servem para buscar notícias):")
_add("hist_freq", "Recherches récentes les plus fréquentes :", "Most frequent recent searches:",
     "Búsquedas recientes más frecuentes:", "Häufigste aktuelle Suchen:",
     "Самые частые недавние запросы:", "Ricerche recenti più frequenti:",
     "Buscas recentes mais frequentes:")
_add("hist_note",
     "(Affiché uniquement ici, dans ton terminal. Masquer un sujet : search exclude add <mot>)",
     "(Shown only here, in your terminal. Hide a topic: search exclude add <word>)",
     "(Solo se muestra aquí, en tu terminal. Ocultar un tema: search exclude add <palabra>)",
     "(Nur hier im Terminal sichtbar. Thema ausblenden: search exclude add <Wort>)",
     "(Показано только здесь, в терминале. Скрыть тему: search exclude add <слово>)",
     "(Mostrato solo qui, nel tuo terminale. Nascondi un tema: search exclude add <parola>)",
     "(Mostrado apenas aqui, no seu terminal. Ocultar um tema: search exclude add <palavra>)")
_add("prev_wait", "Analyse de l'historique et recherche d'actus (quelques secondes)…",
     "Analyzing history and fetching news (a few seconds)…",
     "Analizando el historial y buscando noticias (unos segundos)…",
     "Verlauf wird analysiert, News werden gesucht (einige Sekunden)…",
     "Анализ истории и поиск новостей (несколько секунд)…",
     "Analisi della cronologia e ricerca di notizie (qualche secondo)…",
     "Analisando o histórico e buscando notícias (alguns segundos)…")
_add("prev_none", "Rien à afficher : {s}", "Nothing to show: {s}", "Nada que mostrar: {s}",
     "Nichts anzuzeigen: {s}", "Нечего показать: {s}", "Niente da mostrare: {s}",
     "Nada a mostrar: {s}")
_add("prev_topics", "Sujets : {s}", "Topics: {s}", "Temas: {s}", "Themen: {s}", "Темы: {s}",
     "Temi: {s}", "Temas: {s}")
_add("reset_ask", "Supprimer {p} ? [o/N] ", "Delete {p}? [y/N] ", "¿Eliminar {p}? [s/N] ",
     "{p} löschen? [j/N] ", "Удалить {p}? [д/Н] ", "Eliminare {p}? [s/N] ",
     "Excluir {p}? [s/N] ")
_add("reset_done",
     "✔ Réglages supprimés : l'assistant se relancera au prochain démarrage.",
     "✔ Settings deleted: the setup wizard will run at next start.",
     "✔ Ajustes eliminados: el asistente se ejecutará en el próximo inicio.",
     "✔ Einstellungen gelöscht: der Assistent startet beim nächsten Start.",
     "✔ Настройки удалены: мастер запустится при следующем старте.",
     "✔ Impostazioni eliminate: la procedura guidata si avvierà al prossimo avvio.",
     "✔ Ajustes excluídos: o assistente será executado na próxima inicialização.")
_add("reset_no", "Rien n'a été modifié.", "Nothing was changed.", "No se ha modificado nada.",
     "Nichts wurde geändert.", "Ничего не изменено.", "Nessuna modifica.", "Nada foi alterado.")
_add("exc_empty", "(aucun mot exclu)", "(no excluded words)", "(ninguna palabra excluida)",
     "(keine ausgeschlossenen Wörter)", "(нет исключённых слов)", "(nessuna parola esclusa)",
     "(nenhuma palavra excluída)")
_add("exc_cleared", "✔ liste d'exclusion vidée", "✔ exclusion list cleared",
     "✔ lista de exclusión vaciada", "✔ Ausschlussliste geleert",
     "✔ список исключений очищен", "✔ lista di esclusione svuotata",
     "✔ lista de exclusão limpa")
_add("exc_need", "✘ précise un mot ou une expression : search exclude add <mot>",
     "✘ give a word or phrase: search exclude add <word>",
     "✘ indica una palabra o expresión: search exclude add <palabra>",
     "✘ Wort oder Ausdruck angeben: search exclude add <Wort>",
     "✘ укажите слово или фразу: search exclude add <слово>",
     "✘ indica una parola o espressione: search exclude add <parola>",
     "✘ informe uma palavra ou expressão: search exclude add <palavra>")
_add("exc_added", "✔ « {w} » ne s'affichera plus dans les tendances perso",
     "✔ “{w}” will no longer appear in personalized trends",
     "✔ «{w}» ya no aparecerá en las tendencias personalizadas",
     "✔ „{w}“ erscheint nicht mehr in den persönlichen Trends",
     "✔ «{w}» больше не будет в персональных трендах",
     "✔ «{w}» non apparirà più nelle tendenze personalizzate",
     "✔ «{w}» não aparecerá mais nas tendências personalizadas")
_add("exc_removed", "✔ « {w} » retiré de la liste d'exclusion",
     "✔ “{w}” removed from the exclusion list",
     "✔ «{w}» quitada de la lista de exclusión",
     "✔ „{w}“ aus der Ausschlussliste entfernt",
     "✔ «{w}» удалено из списка исключений",
     "✔ «{w}» rimossa dalla lista di esclusione",
     "✔ «{w}» removida da lista de exclusão")
_add("mt_title", "Test souris : bouge le curseur, clique, puis Échap pour quitter.",
     "Mouse test: move the cursor, click, then Esc to quit.",
     "Prueba de ratón: mueve el cursor, haz clic y pulsa Esc para salir.",
     "Maustest: Cursor bewegen, klicken, dann Esc zum Beenden.",
     "Тест мыши: двигайте курсор, кликайте, затем Esc для выхода.",
     "Test mouse: muovi il cursore, clicca, poi Esc per uscire.",
     "Teste do mouse: mova o cursor, clique e pressione Esc para sair.")
_add("mt_counts", "mouvements reçus : {m}    clics reçus : {c}",
     "movements received: {m}    clicks received: {c}",
     "movimientos recibidos: {m}    clics recibidos: {c}",
     "Bewegungen: {m}    Klicks: {c}", "движений: {m}    кликов: {c}",
     "movimenti ricevuti: {m}    clic ricevuti: {c}",
     "movimentos recebidos: {m}    cliques recebidos: {c}")
_add("mt_ok", "✔ le survol fonctionne", "✔ hover works", "✔ el hover funciona",
     "✔ Hover funktioniert", "✔ наведение работает", "✔ l'hover funziona", "✔ o hover funciona")
_add("mt_ko", "✘ aucun mouvement reçu : ton terminal ne transmet pas le survol",
     "✘ no movement received: your terminal does not report hover",
     "✘ no se recibió movimiento: tu terminal no envía el hover",
     "✘ keine Bewegung empfangen: dein Terminal meldet kein Hover",
     "✘ движений нет: терминал не передаёт наведение",
     "✘ nessun movimento: il tuo terminale non invia l'hover",
     "✘ nenhum movimento: seu terminal não envia o hover")

# ---- assistant de premier lancement
_add("w_welcome", "Bienvenue dans search-globe !", "Welcome to search-globe!",
     "¡Bienvenido a search-globe!", "Willkommen bei search-globe!",
     "Добро пожаловать в search-globe!", "Benvenuto in search-globe!",
     "Bem-vindo ao search-globe!")
_add("w_q", "Quelles tendances veux-tu voir tourner autour du globe ?",
     "Which trends do you want to see orbiting the globe?",
     "¿Qué tendencias quieres ver girando alrededor del globo?",
     "Welche Trends sollen um den Globus kreisen?",
     "Какие тренды показывать вокруг глобуса?",
     "Quali tendenze vuoi vedere girare attorno al globo?",
     "Quais tendências você quer ver girando ao redor do globo?")
_add("w_opt1",
     "1) Tendances du jour   — Google Trends (par défaut, aucune donnée personnelle)",
     "1) Daily trends        — Google Trends (default, no personal data)",
     "1) Tendencias del día  — Google Trends (por defecto, sin datos personales)",
     "1) Tagestrends         — Google Trends (Standard, keine persönlichen Daten)",
     "1) Тренды дня          — Google Trends (по умолчанию, без личных данных)",
     "1) Tendenze del giorno — Google Trends (predefinito, nessun dato personale)",
     "1) Tendências do dia   — Google Trends (padrão, sem dados pessoais)")
_add("w_opt2",
     "2) Personnalisées      — actus et suggestions liées à ton historique (ex. « resident evil » → actus, jeux similaires…)",
     "2) Personalized        — news and suggestions from your browser history (e.g. “resident evil” → news, similar games…)",
     "2) Personalizadas      — noticias y sugerencias según tu historial (p. ej. «resident evil» → noticias, juegos similares…)",
     "2) Personalisiert      — News und Vorschläge nach deinem Browserverlauf (z. B. „resident evil“ → News, ähnliche Spiele…)",
     "2) Персональные        — новости и подборки по истории браузера (напр. «resident evil» → новости, похожие игры…)",
     "2) Personalizzate      — notizie e suggerimenti dalla cronologia (es. «resident evil» → notizie, giochi simili…)",
     "2) Personalizadas      — notícias e sugestões pelo histórico (ex.: «resident evil» → notícias, jogos parecidos…)")
_add("w_opt3", "3) Mixte               — les deux, en alternance",
     "3) Mixed               — both, alternating", "3) Mixto               — ambas, alternadas",
     "3) Gemischt            — beides im Wechsel", "3) Смешанный           — и то и другое по очереди",
     "3) Misto                — entrambe, alternate", "3) Misto                — ambas, alternadas")
_add("w_priv",
     "🔒 Ton historique est lu sur ta machine (copie temporaire supprimée) et n'est jamais envoyé.\n"
     "   Mais pour trouver des actus liées, 2-3 mots-clés de tes centres d'intérêt\n"
     "   (ex. « resident evil ») sont envoyés à Google News et Wikipédia.\n"
     "   Tu peux en masquer : search exclude add <mot>   (voir tes mots-clés : search history)",
     "🔒 Your history is read locally (temporary copy, deleted right away) and never uploaded.\n"
     "   But to find related news, 2-3 keywords from your interests\n"
     "   (e.g. “resident evil”) are sent to Google News and Wikipedia.\n"
     "   You can hide some: search exclude add <word>   (see your keywords: search history)",
     "🔒 Tu historial se lee en tu equipo (copia temporal, borrada al instante) y nunca se envía.\n"
     "   Pero para buscar noticias relacionadas, 2-3 palabras clave de tus intereses\n"
     "   (p. ej. «resident evil») se envían a Google News y Wikipedia.\n"
     "   Puedes ocultar algunas: search exclude add <palabra>   (ver tus palabras: search history)",
     "🔒 Dein Verlauf wird lokal gelesen (temporäre Kopie, sofort gelöscht) und nie hochgeladen.\n"
     "   Für passende News werden aber 2–3 Stichwörter deiner Interessen\n"
     "   (z. B. „resident evil“) an Google News und Wikipedia gesendet.\n"
     "   Du kannst welche ausblenden: search exclude add <Wort>   (Stichwörter ansehen: search history)",
     "🔒 История читается локально (временная копия, сразу удаляется) и никуда не отправляется.\n"
     "   Но для поиска связанных новостей 2–3 ключевых слова ваших интересов\n"
     "   (напр. «resident evil») отправляются в Google News и Википедию.\n"
     "   Можно скрыть: search exclude add <слово>   (ваши слова: search history)",
     "🔒 La cronologia viene letta in locale (copia temporanea, subito eliminata) e non viene mai inviata.\n"
     "   Ma per trovare notizie correlate, 2-3 parole chiave dei tuoi interessi\n"
     "   (es. «resident evil») vengono inviate a Google News e Wikipedia.\n"
     "   Puoi nasconderne: search exclude add <parola>   (vedi le parole: search history)",
     "🔒 Seu histórico é lido localmente (cópia temporária, apagada em seguida) e nunca é enviado.\n"
     "   Mas, para achar notícias relacionadas, 2-3 palavras-chave dos seus interesses\n"
     "   (ex.: «resident evil») são enviadas ao Google News e à Wikipédia.\n"
     "   Você pode ocultar algumas: search exclude add <palavra>   (ver suas palavras: search history)")
_add("w_choice", "Ton choix [1/2/3] (Entrée = 1) : ", "Your choice [1/2/3] (Enter = 1): ",
     "Tu elección [1/2/3] (Intro = 1): ", "Deine Wahl [1/2/3] (Enter = 1): ",
     "Ваш выбор [1/2/3] (Enter = 1): ", "La tua scelta [1/2/3] (Invio = 1): ",
     "Sua escolha [1/2/3] (Enter = 1): ")
_add("w_hist_ok", "✔ Historique détecté : {n}", "✔ History detected: {n}",
     "✔ Historial detectado: {n}", "✔ Verlauf gefunden: {n}", "✔ История найдена: {n}",
     "✔ Cronologia rilevata: {n}", "✔ Histórico detectado: {n}")
_add("w_hist_no",
     "⚠ Aucun historique de navigateur trouvé pour l'instant.\n  Précise ton navigateur plus tard avec :  search set browser firefox\n  (en attendant, les tendances du jour seront affichées)",
     "⚠ No browser history found for now.\n  Set your browser later with:  search set browser firefox\n  (meanwhile, daily trends will be shown)",
     "⚠ No se encontró historial de navegador por ahora.\n  Indica tu navegador luego con:  search set browser firefox\n  (mientras tanto se mostrarán las tendencias del día)",
     "⚠ Noch kein Browserverlauf gefunden.\n  Browser später festlegen mit:  search set browser firefox\n  (bis dahin werden die Tagestrends angezeigt)",
     "⚠ История браузера пока не найдена.\n  Укажите браузер позже:  search set browser firefox\n  (пока будут показаны тренды дня)",
     "⚠ Nessuna cronologia del browser trovata per ora.\n  Indica il browser più tardi con:  search set browser firefox\n  (nel frattempo verranno mostrate le tendenze del giorno)",
     "⚠ Nenhum histórico de navegador encontrado por enquanto.\n  Defina o navegador depois com:  search set browser firefox\n  (enquanto isso, serão mostradas as tendências do dia)")
_add("w_geo", "Pays des tendances du jour [{g}] : ", "Country for daily trends [{g}]: ",
     "País de las tendencias del día [{g}]: ", "Land für die Tagestrends [{g}]: ",
     "Страна для трендов дня [{g}]: ", "Paese per le tendenze del giorno [{g}]: ",
     "País das tendências do dia [{g}]: ")
_add("w_saved", "✔ Réglages enregistrés dans {p}", "✔ Settings saved to {p}",
     "✔ Ajustes guardados en {p}", "✔ Einstellungen gespeichert in {p}",
     "✔ Настройки сохранены в {p}", "✔ Impostazioni salvate in {p}", "✔ Ajustes salvos em {p}")
_add("w_later",
     "Pour changer plus tard :\n  search mode base|perso|mix     change le type de tendances\n  search lang fr|en|es|de|ru…    change la langue\n  search setup                   relance cet assistant\n  Dans l'interface : tape / pour ouvrir les paramètres (chat) · Tab change de mode",
     "To change later:\n  search mode base|perso|mix     change the trend type\n  search lang fr|en|es|de|ru…    change the language\n  search setup                   run this wizard again\n  In the interface: type / to open settings (chat) · Tab switches mode",
     "Para cambiar más tarde:\n  search mode base|perso|mix     cambia el tipo de tendencias\n  search lang fr|en|es|de|ru…    cambia el idioma\n  search setup                   vuelve a ejecutar este asistente\n  En la interfaz: escribe / para abrir los ajustes (chat) · Tab cambia de modo",
     "Später ändern:\n  search mode base|perso|mix     Trend-Art ändern\n  search lang fr|en|es|de|ru…    Sprache ändern\n  search setup                   Assistenten erneut starten\n  In der Oberfläche: / öffnet die Einstellungen (Chat) · Tab wechselt den Modus",
     "Изменить позже:\n  search mode base|perso|mix     тип трендов\n  search lang fr|en|es|de|ru…    язык\n  search setup                   запустить мастер заново\n  В интерфейсе: / открывает настройки (чат) · Tab меняет режим",
     "Per cambiare in seguito:\n  search mode base|perso|mix     cambia il tipo di tendenze\n  search lang fr|en|es|de|ru…    cambia la lingua\n  search setup                   riavvia questa procedura\n  Nell'interfaccia: / apre le impostazioni (chat) · Tab cambia modalità",
     "Para mudar depois:\n  search mode base|perso|mix     muda o tipo de tendências\n  search lang fr|en|es|de|ru…    muda o idioma\n  search setup                   executa este assistente de novo\n  Na interface: / abre os ajustes (chat) · Tab muda o modo")

# ---- aide de la ligne de commande
_add("ap_desc", "Globe 3D dans le terminal : tendances (du jour ou perso) et recherche web.",
     "3D globe in your terminal: trends (daily or personal) and web search.",
     "Globo 3D en la terminal: tendencias (del día o personales) y búsqueda web.",
     "3D-Globus im Terminal: Trends (täglich oder persönlich) und Websuche.",
     "3D-глобус в терминале: тренды (дня или персональные) и веб-поиск.",
     "Globo 3D nel terminale: tendenze (del giorno o personali) e ricerca web.",
     "Globo 3D no terminal: tendências (do dia ou pessoais) e busca na web.")
_add("ap_o_geo", "pays des tendances, pour cette session (FR, US…)",
     "trends country, this session only (FR, US…)",
     "país de las tendencias, solo esta sesión (ES, MX…)",
     "Land der Trends, nur diese Sitzung (DE, AT…)",
     "страна трендов, только на этот сеанс (RU, US…)",
     "paese delle tendenze, solo questa sessione (IT, US…)",
     "país das tendências, só nesta sessão (BR, PT…)")
_add("ap_o_engine", "moteur de recherche, pour cette session", "search engine, this session only",
     "motor de búsqueda, solo esta sesión", "Suchmaschine, nur diese Sitzung",
     "поисковая система, только на этот сеанс", "motore di ricerca, solo questa sessione",
     "mecanismo de busca, só nesta sessão")
_add("ap_o_mode", "base | perso | mix, pour cette session", "base | perso | mix, this session only",
     "base | perso | mix, solo esta sesión", "base | perso | mix, nur diese Sitzung",
     "base | perso | mix, только на этот сеанс", "base | perso | mix, solo questa sessione",
     "base | perso | mix, só nesta sessão")
_add("ap_o_lang", "langue (fr, en, es, de, ru, it, pt), pour cette session",
     "language (fr, en, es, de, ru, it, pt), this session only",
     "idioma (fr, en, es, de, ru, it, pt), solo esta sesión",
     "Sprache (fr, en, es, de, ru, it, pt), nur diese Sitzung",
     "язык (fr, en, es, de, ru, it, pt), только на этот сеанс",
     "lingua (fr, en, es, de, ru, it, pt), solo questa sessione",
     "idioma (fr, en, es, de, ru, it, pt), só nesta sessão")
_add("ap_setup", "relance l'assistant de configuration", "run the setup wizard again",
     "vuelve a ejecutar el asistente", "Einrichtungsassistent erneut starten",
     "запустить мастер настройки заново", "riavvia la procedura guidata",
     "executa o assistente de novo")
_add("ap_config", "affiche les réglages", "show settings", "muestra los ajustes",
     "Einstellungen anzeigen", "показать настройки", "mostra le impostazioni", "mostra os ajustes")
_add("ap_history", "montre tes centres d'intérêt détectés", "show your detected interests",
     "muestra tus intereses detectados", "erkannte Interessen anzeigen",
     "показать найденные интересы", "mostra gli interessi rilevati",
     "mostra seus interesses detectados")
_add("ap_reset", "supprime les réglages", "delete the settings", "elimina los ajustes",
     "Einstellungen löschen", "удалить настройки", "elimina le impostazioni", "exclui os ajustes")
_add("ap_preview", "aperçu des tendances perso sans lancer l'interface",
     "preview personal trends without the interface",
     "vista previa de tendencias personales sin la interfaz",
     "persönliche Trends ohne Oberfläche testen",
     "предпросмотр персональных трендов без интерфейса",
     "anteprima delle tendenze personali senza interfaccia",
     "prévia das tendências pessoais sem a interface")
_add("ap_mousetest", "teste la souris (survol et clics)", "test the mouse (hover and clicks)",
     "prueba el ratón (hover y clics)", "Maus testen (Hover und Klicks)",
     "проверка мыши (наведение и клики)", "testa il mouse (hover e clic)",
     "testa o mouse (hover e cliques)")
_add("ap_mode", "change le type de tendances (base, perso, mix)",
     "change the trend type (base, perso, mix)", "cambia el tipo de tendencias (base, perso, mix)",
     "Trend-Art ändern (base, perso, mix)", "сменить тип трендов (base, perso, mix)",
     "cambia il tipo di tendenze (base, perso, mix)", "muda o tipo de tendências (base, perso, mix)")
_add("ap_set", "modifie un réglage : search set <clé> <valeur>",
     "change a setting: search set <key> <value>", "cambia un ajuste: search set <clave> <valor>",
     "Einstellung ändern: search set <Schlüssel> <Wert>",
     "изменить настройку: search set <ключ> <значение>",
     "modifica un'impostazione: search set <chiave> <valore>",
     "altera um ajuste: search set <chave> <valor>")
_add("ap_exclude", "masque des mots dans les tendances perso", "hide words in personal trends",
     "oculta palabras en las tendencias personales", "Wörter in persönlichen Trends ausblenden",
     "скрыть слова в персональных трендах", "nasconde parole nelle tendenze personali",
     "oculta palavras nas tendências pessoais")
_add("ap_lang", "change la langue (fr, en, es, de, ru, it, pt)",
     "change the language (fr, en, es, de, ru, it, pt)",
     "cambia el idioma (fr, en, es, de, ru, it, pt)", "Sprache ändern (fr, en, es, de, ru, it, pt)",
     "сменить язык (fr, en, es, de, ru, it, pt)", "cambia la lingua (fr, en, es, de, ru, it, pt)",
     "muda o idioma (fr, en, es, de, ru, it, pt)")

# ---- mode paramètres (chat)
_add("chat_title", "Paramètres", "Settings", "Ajustes", "Einstellungen", "Настройки",
     "Impostazioni", "Ajustes")
_add("chat_sub", "tape /help pour la liste des commandes", "type /help for the command list",
     "escribe /help para ver los comandos", "/help zeigt alle Befehle", "/help — список команд",
     "scrivi /help per i comandi", "digite /help para ver os comandos")
_add("chat_placeholder", "Écrire un message ou /help…", "Write a message or /help…",
     "Escribe un mensaje o /help…", "Nachricht schreiben oder /help…",
     "Напишите сообщение или /help…", "Scrivi un messaggio o /help…",
     "Escreva uma mensagem ou /help…")
_add("chat_welcome",
     "Bienvenue dans les paramètres ⚙\nTape /help pour la liste des commandes, ou clique sur une commande ci-dessous.",
     "Welcome to settings ⚙\nType /help for the command list, or click a command below.",
     "Bienvenido a los ajustes ⚙\nEscribe /help para ver los comandos o haz clic en uno de abajo.",
     "Willkommen in den Einstellungen ⚙\nTippe /help für alle Befehle oder klicke unten auf einen Befehl.",
     "Добро пожаловать в настройки ⚙\nНапишите /help, чтобы увидеть команды, или нажмите на команду ниже.",
     "Benvenuto nelle impostazioni ⚙\nScrivi /help per l'elenco dei comandi o clicca su un comando qui sotto.",
     "Bem-vindo aos ajustes ⚙\nDigite /help para ver os comandos ou clique em um comando abaixo.")
_add("chat_unknown", "Commande inconnue : {c}\nTape /help pour la liste.",
     "Unknown command: {c}\nType /help for the list.",
     "Comando desconocido: {c}\nEscribe /help para ver la lista.",
     "Unbekannter Befehl: {c}\n/help zeigt die Liste.",
     "Неизвестная команда: {c}\nНапишите /help для списка.",
     "Comando sconosciuto: {c}\nScrivi /help per l'elenco.",
     "Comando desconhecido: {c}\nDigite /help para ver a lista.")
_add("chat_plain", "Je ne comprends que les commandes qui commencent par /. Essaie /help.",
     "I only understand commands starting with /. Try /help.",
     "Solo entiendo comandos que empiezan por /. Prueba /help.",
     "Ich verstehe nur Befehle, die mit / beginnen. Probiere /help.",
     "Я понимаю только команды, начинающиеся с /. Попробуйте /help.",
     "Capisco solo i comandi che iniziano con /. Prova /help.",
     "Só entendo comandos que começam com /. Tente /help.")
_add("c_opts", "Options : {o}", "Options: {o}", "Opciones: {o}", "Optionen: {o}",
     "Варианты: {o}", "Opzioni: {o}", "Opções: {o}")
_add("c_langs", "Langues :", "Languages:", "Idiomas:", "Sprachen:", "Языки:", "Lingue:", "Idiomas:")
_add("c_refresh", "Rechargement des tendances…", "Reloading trends…", "Recargando tendencias…",
     "Trends werden neu geladen…", "Обновляю тренды…", "Ricarico le tendenze…",
     "Recarregando tendências…")
_add("c_cleared", "Conversation effacée.", "Conversation cleared.", "Conversación borrada.",
     "Unterhaltung gelöscht.", "Чат очищен.", "Conversazione cancellata.", "Conversa limpa.")
_add("c_reset_confirm", "Pour confirmer, tape /reset oui", "To confirm, type /reset yes",
     "Para confirmar, escribe /reset si", "Zum Bestätigen: /reset ja",
     "Для подтверждения: /reset да", "Per confermare, scrivi /reset si",
     "Para confirmar, digite /reset sim")
_add("c_reset_done", "✔ Réglages réinitialisés.", "✔ Settings reset.", "✔ Ajustes restablecidos.",
     "✔ Einstellungen zurückgesetzt.", "✔ Настройки сброшены.", "✔ Impostazioni ripristinate.",
     "✔ Ajustes redefinidos.")
_add("c_history_wait", "Lecture de l'historique…", "Reading history…", "Leyendo el historial…",
     "Verlauf wird gelesen…", "Читаю историю…", "Lettura della cronologia…", "Lendo o histórico…")
_add("c_no_trends", "Aucune tendance affichée pour l'instant.", "No trends shown yet.",
     "Aún no hay tendencias.", "Noch keine Trends angezeigt.", "Трендов пока нет.",
     "Nessuna tendenza per ora.", "Nenhuma tendência por enquanto.")
_add("h_title", "Commandes disponibles :", "Available commands:", "Comandos disponibles:",
     "Verfügbare Befehle:", "Доступные команды:", "Comandi disponibili:", "Comandos disponíveis:")
_add("h_help", "affiche cette aide", "show this help", "muestra esta ayuda", "zeigt diese Hilfe",
     "показать эту справку", "mostra questo aiuto", "mostra esta ajuda")
_add("h_mode", "type de tendances", "trend type", "tipo de tendencias", "Trend-Art",
     "тип трендов", "tipo di tendenze", "tipo de tendências")
_add("h_lang", "langue de l'interface et des actus", "language of the interface and news",
     "idioma de la interfaz y las noticias", "Sprache der Oberfläche und News",
     "язык интерфейса и новостей", "lingua dell'interfaccia e delle notizie",
     "idioma da interface e das notícias")
_add("h_geo", "pays des tendances", "trends country", "país de las tendencias", "Land der Trends",
     "страна трендов", "paese delle tendenze", "país das tendências")
_add("h_engine", "moteur de recherche", "search engine", "motor de búsqueda", "Suchmaschine",
     "поисковая система", "motore di ricerca", "mecanismo de busca")
_add("h_browser", "navigateur lu pour le mode perso", "browser read for perso mode",
     "navegador leído en modo perso", "Browser für den Perso-Modus",
     "браузер для режима perso", "browser letto in modalità perso",
     "navegador lido no modo perso")
_add("h_topics", "nombre de centres d'intérêt (1-5)", "number of interests (1-5)",
     "número de intereses (1-5)", "Anzahl Interessen (1–5)", "число интересов (1–5)",
     "numero di interessi (1-5)", "número de interesses (1-5)")
_add("h_days", "jours d'historique analysés", "days of history analyzed",
     "días de historial analizados", "analysierte Verlaufstage", "дней истории для анализа",
     "giorni di cronologia analizzati", "dias de histórico analisados")
_add("h_max", "nombre de tendances affichées (1-8)", "number of trends shown (1-8)",
     "número de tendencias mostradas (1-8)", "Anzahl angezeigter Trends (1–8)",
     "число показанных трендов (1–8)", "numero di tendenze mostrate (1-8)",
     "número de tendências exibidas (1-8)")
_add("h_exclude", "masquer un sujet", "hide a topic", "ocultar un tema", "Thema ausblenden",
     "скрыть тему", "nascondi un tema", "ocultar um tema")
_add("h_history", "mes centres d'intérêt détectés", "my detected interests",
     "mis intereses detectados", "meine erkannten Interessen", "мои найденные интересы",
     "i miei interessi rilevati", "meus interesses detectados")
_add("h_preview", "tendances affichées en ce moment", "trends currently shown",
     "tendencias mostradas ahora", "aktuell angezeigte Trends", "тренды на экране сейчас",
     "tendenze mostrate ora", "tendências exibidas agora")
_add("h_config", "affiche les réglages", "show settings", "muestra los ajustes",
     "zeigt die Einstellungen", "показать настройки", "mostra le impostazioni", "mostra os ajustes")
_add("h_refresh", "recharge les tendances", "reload trends", "recarga las tendencias",
     "Trends neu laden", "обновить тренды", "ricarica le tendenze", "recarrega as tendências")
_add("h_clear", "efface la conversation", "clear the conversation", "borra la conversación",
     "Unterhaltung löschen", "очистить чат", "cancella la conversazione", "limpa a conversa")
_add("h_reset", "réinitialise les réglages", "reset settings", "restablece los ajustes",
     "Einstellungen zurücksetzen", "сбросить настройки", "ripristina le impostazioni",
     "redefine os ajustes")
_add("h_exit", "retour au globe", "back to the globe", "volver al globo", "zurück zum Globus",
     "вернуться к глобусу", "torna al globo", "voltar ao globo")
_add("h_quit", "quitte l'application", "quit the app", "salir de la aplicación",
     "Anwendung beenden", "выйти из приложения", "esci dall'app", "sair do aplicativo")
_add("h_examples", "Exemples : /mode perso · /lang es · /exclude add banque",
     "Examples: /mode perso · /lang es · /exclude add bank",
     "Ejemplos: /mode perso · /lang en · /exclude add banco",
     "Beispiele: /mode perso · /lang es · /exclude add bank",
     "Примеры: /mode perso · /lang es · /exclude add банк",
     "Esempi: /mode perso · /lang es · /exclude add banca",
     "Exemplos: /mode perso · /lang es · /exclude add banco")


# ---- consentement, hors-ligne
_add("consent_title", "🔒 Consentement", "🔒 Consent", "🔒 Consentimiento", "🔒 Einwilligung",
     "🔒 Согласие", "🔒 Consenso", "🔒 Consentimento")
_add("consent_intro",
     "Pour trouver des actus liées à tes centres d'intérêt, search-globe enverrait UNIQUEMENT ces mots-clés à Google News et à Wikipédia :",
     "To find news related to your interests, search-globe would send ONLY these keywords to Google News and Wikipedia:",
     "Para buscar noticias relacionadas con tus intereses, search-globe enviaría ÚNICAMENTE estas palabras clave a Google News y Wikipedia:",
     "Um passende News zu finden, würde search-globe NUR diese Stichwörter an Google News und Wikipedia senden:",
     "Чтобы найти новости по вашим интересам, search-globe отправит ТОЛЬКО эти ключевые слова в Google News и Википедию:",
     "Per trovare notizie legate ai tuoi interessi, search-globe invierebbe SOLO queste parole chiave a Google News e Wikipedia:",
     "Para achar notícias ligadas aos seus interesses, o search-globe enviaria APENAS estas palavras-chave ao Google News e à Wikipédia:")
_add("consent_none_kw",
     "(aucun mot-clé détecté pour l'instant : ils seront déduits de ton historique)",
     "(no keyword detected yet: they will be derived from your history)",
     "(aún no hay palabras clave: se deducirán de tu historial)",
     "(noch keine Stichwörter erkannt: sie werden aus deinem Verlauf abgeleitet)",
     "(ключевых слов пока нет: они будут взяты из вашей истории)",
     "(nessuna parola chiave rilevata: verranno dedotte dalla tua cronologia)",
     "(nenhuma palavra-chave detectada: elas serão deduzidas do seu histórico)")
_add("consent_notsent",
     "Jamais envoyés : tes URL, ton historique complet, tes autres recherches. Comme pour tout site web, ces services voient ton adresse IP.",
     "Never sent: your URLs, your full history, your other searches. As with any website, these services can see your IP address.",
     "Nunca se envían: tus URL, tu historial completo, tus otras búsquedas. Como en cualquier sitio web, estos servicios ven tu dirección IP.",
     "Nie gesendet: deine URLs, dein kompletter Verlauf, deine anderen Suchen. Wie bei jeder Website sehen diese Dienste deine IP-Adresse.",
     "Никогда не отправляются: ваши URL, вся история, другие запросы. Как и любой сайт, эти сервисы видят ваш IP-адрес.",
     "Mai inviati: i tuoi URL, la cronologia completa, le altre ricerche. Come ogni sito web, questi servizi vedono il tuo indirizzo IP.",
     "Nunca enviados: suas URLs, seu histórico completo, suas outras buscas. Como em qualquer site, esses serviços veem seu endereço IP.")
_add("consent_audit",
     "Un journal local de chaque envoi est conservé : search consent log",
     "A local log of every request is kept: search consent log",
     "Se guarda un registro local de cada envío: search consent log",
     "Jede Übermittlung wird lokal protokolliert: search consent log",
     "Каждая отправка записывается в локальный журнал: search consent log",
     "Ogni invio viene registrato in locale: search consent log",
     "Cada envio fica registrado localmente: search consent log")
_add("consent_revoke",
     "Tu peux retirer ton accord à tout moment : search consent no  (ou /consent no dans le chat).",
     "You can withdraw your consent at any time: search consent no  (or /consent no in the chat).",
     "Puedes retirar tu consentimiento en cualquier momento: search consent no  (o /consent no en el chat).",
     "Du kannst deine Einwilligung jederzeit widerrufen: search consent no  (oder /consent no im Chat).",
     "Вы можете отозвать согласие в любой момент: search consent no  (или /consent no в чате).",
     "Puoi revocare il consenso in qualsiasi momento: search consent no  (o /consent no nella chat).",
     "Você pode retirar o consentimento a qualquer momento: search consent no  (ou /consent no no chat).")
_add("consent_cmds",
     "Pour autoriser : /consent yes · pour refuser : /consent no",
     "To allow: /consent yes · to refuse: /consent no",
     "Para permitir: /consent yes · para rechazar: /consent no",
     "Erlauben: /consent yes · ablehnen: /consent no",
     "Разрешить: /consent yes · отказать: /consent no",
     "Per consentire: /consent yes · per rifiutare: /consent no",
     "Para permitir: /consent yes · para recusar: /consent no")
_add("consent_ask", "Autoriser cet envoi ? [o/N] ", "Allow this? [y/N] ",
     "¿Permitir este envío? [s/N] ", "Diese Übermittlung erlauben? [j/N] ",
     "Разрешить отправку? [д/Н] ", "Consentire questo invio? [s/N] ", "Permitir este envio? [s/N] ")
_add("consent_granted", "✔ Envoi autorisé : les actus liées sont activées.",
     "✔ Sending allowed: related news is now enabled.",
     "✔ Envío permitido: las noticias relacionadas están activadas.",
     "✔ Übermittlung erlaubt: passende News sind aktiviert.",
     "✔ Отправка разрешена: связанные новости включены.",
     "✔ Invio consentito: le notizie correlate sono attive.",
     "✔ Envio permitido: as notícias relacionadas estão ativadas.")
_add("consent_denied", "✔ Aucun envoi : les sujets détectés restent affichés en local, sans actus.",
     "✔ Nothing is sent: detected topics stay local, without news.",
     "✔ No se envía nada: los temas detectados se muestran solo en local, sin noticias.",
     "✔ Nichts wird gesendet: erkannte Themen bleiben lokal, ohne News.",
     "✔ Ничего не отправляется: найденные темы остаются локально, без новостей.",
     "✔ Nessun invio: gli argomenti rilevati restano in locale, senza notizie.",
     "✔ Nada é enviado: os temas detectados ficam locais, sem notícias.")
_add("consent_state_yes", "Consentement : accordé le {d}", "Consent: granted on {d}",
     "Consentimiento: concedido el {d}", "Einwilligung: erteilt am {d}", "Согласие: дано {d}",
     "Consenso: concesso il {d}", "Consentimento: concedido em {d}")
_add("consent_state_no", "Consentement : non accordé", "Consent: not granted",
     "Consentimiento: no concedido", "Einwilligung: nicht erteilt", "Согласие: не дано",
     "Consenso: non concesso", "Consentimento: não concedido")
_add("offline_state", "Mode hors-ligne : {s}", "Offline mode: {s}", "Modo sin conexión: {s}",
     "Offline-Modus: {s}", "Офлайн-режим: {s}", "Modalità offline: {s}", "Modo offline: {s}")
_add("word_on", "activé", "on", "activado", "an", "включён", "attivo", "ativado")
_add("word_off", "désactivé", "off", "desactivado", "aus", "выключен", "disattivo", "desativado")
_add("consent_log_title", "Derniers envois (date · hôte · mot-clé) :",
     "Latest requests (date · host · keyword):", "Últimos envíos (fecha · host · palabra clave):",
     "Letzte Übermittlungen (Datum · Host · Stichwort):", "Последние отправки (дата · хост · слово):",
     "Ultimi invii (data · host · parola chiave):", "Últimos envios (data · host · palavra-chave):")
_add("consent_log_empty", "(aucun envoi enregistré)", "(no request logged)",
     "(ningún envío registrado)", "(keine Übermittlung protokolliert)", "(отправок не было)",
     "(nessun invio registrato)", "(nenhum envio registrado)")
_add("consent_hint", "🔒 actus désactivées : /consent", "🔒 news off: /consent",
     "🔒 noticias desactivadas: /consent", "🔒 News aus: /consent", "🔒 новости выкл.: /consent",
     "🔒 notizie disattivate: /consent", "🔒 notícias desativadas: /consent")
_add("ok_offline_on", "✔ Mode hors-ligne activé : plus aucune requête réseau.",
     "✔ Offline mode on: no more network requests.",
     "✔ Modo sin conexión activado: ninguna petición de red.",
     "✔ Offline-Modus an: keine Netzwerkanfragen mehr.",
     "✔ Офлайн-режим включён: сетевых запросов больше нет.",
     "✔ Modalità offline attiva: nessuna richiesta di rete.",
     "✔ Modo offline ativado: nenhuma requisição de rede.")
_add("ok_offline_off", "✔ Mode hors-ligne désactivé.", "✔ Offline mode off.",
     "✔ Modo sin conexión desactivado.", "✔ Offline-Modus aus.", "✔ Офлайн-режим выключен.",
     "✔ Modalità offline disattivata.", "✔ Modo offline desativado.")
_add("status_offline_mode", "mode hors-ligne : aucune requête réseau",
     "offline mode: no network requests", "modo sin conexión: ninguna petición de red",
     "Offline-Modus: keine Netzwerkanfragen", "офлайн-режим: сетевых запросов нет",
     "modalità offline: nessuna richiesta di rete", "modo offline: nenhuma requisição de rede")
_add("c_consent_prompt",
     "🔒 Les actus liées ont besoin de ton accord. Tape /consent pour voir exactement ce qui serait envoyé.",
     "🔒 Related news needs your consent. Type /consent to see exactly what would be sent.",
     "🔒 Las noticias relacionadas necesitan tu consentimiento. Escribe /consent para ver exactamente qué se enviaría.",
     "🔒 Für passende News brauchen wir deine Einwilligung. /consent zeigt genau, was gesendet würde.",
     "🔒 Для связанных новостей нужно ваше согласие. Напишите /consent, чтобы увидеть, что именно будет отправлено.",
     "🔒 Le notizie correlate richiedono il tuo consenso. Scrivi /consent per vedere esattamente cosa verrebbe inviato.",
     "🔒 As notícias relacionadas precisam do seu consentimento. Digite /consent para ver exatamente o que seria enviado.")

# ---- thèmes, économie
_add("err_theme", "thème inconnu. Choisis parmi : {l}", "unknown theme. Choose from: {l}",
     "tema desconocido. Elige entre: {l}", "unbekanntes Farbschema. Wähle aus: {l}",
     "неизвестная тема. Выберите: {l}", "tema sconosciuto. Scegli tra: {l}",
     "tema desconhecido. Escolha entre: {l}")
_add("ok_theme", "✔ Thème : {n}", "✔ Theme: {n}", "✔ Tema: {n}", "✔ Farbschema: {n}",
     "✔ Тема: {n}", "✔ Tema: {n}", "✔ Tema: {n}")
_add("c_themes", "Thèmes :", "Themes:", "Temas:", "Farbschemata:", "Темы:", "Temi:", "Temas:")
_add("err_perf", "choisis : on, off ou auto", "choose: on, off or auto", "elige: on, off o auto",
     "wähle: on, off oder auto", "выберите: on, off или auto", "scegli: on, off o auto",
     "escolha: on, off ou auto")
_add("perf_auto", "auto (s'active si le terminal est lent)", "auto (turns on if the terminal is slow)",
     "auto (se activa si el terminal es lento)", "auto (aktiviert sich bei langsamem Terminal)",
     "auto (включается, если терминал медленный)", "auto (si attiva se il terminale è lento)",
     "auto (ativa se o terminal for lento)")
_add("ok_perf", "✔ Mode économie : {p}", "✔ Eco mode: {p}", "✔ Modo ahorro: {p}",
     "✔ Sparmodus: {p}", "✔ Экономный режим: {p}", "✔ Modalità risparmio: {p}",
     "✔ Modo econômico: {p}")
_add("msg_eco_auto", "mode économie activé (terminal lent)", "eco mode enabled (slow terminal)",
     "modo ahorro activado (terminal lento)", "Sparmodus aktiviert (langsames Terminal)",
     "экономный режим включён (медленный терминал)", "modalità risparmio attivata (terminale lento)",
     "modo econômico ativado (terminal lento)")

# ---- widget, démarrage automatique
_add("wid_env", "Session : {s} · Bureau : {d} · Méthode : {m}",
     "Session: {s} · Desktop: {d} · Method: {m}", "Sesión: {s} · Escritorio: {d} · Método: {m}",
     "Sitzung: {s} · Desktop: {d} · Methode: {m}", "Сессия: {s} · Рабочий стол: {d} · Метод: {m}",
     "Sessione: {s} · Desktop: {d} · Metodo: {m}", "Sessão: {s} · Desktop: {d} · Método: {m}")
_add("wid_cmd", "Commande : {c}", "Command: {c}", "Comando: {c}", "Befehl: {c}", "Команда: {c}",
     "Comando: {c}", "Comando: {c}")
_add("wid_started", "✔ Widget lancé. Pour l'arrêter : search widget stop",
     "✔ Widget started. To stop it: search widget stop",
     "✔ Widget iniciado. Para detenerlo: search widget stop",
     "✔ Widget gestartet. Beenden mit: search widget stop",
     "✔ Виджет запущен. Остановить: search widget stop",
     "✔ Widget avviato. Per fermarlo: search widget stop",
     "✔ Widget iniciado. Para parar: search widget stop")
_add("wid_failed", "✘ Le widget s'est arrêté tout de suite (voir ci-dessus). Essaie : search widget --dry-run",
     "✘ The widget exited immediately (see above). Try: search widget --dry-run",
     "✘ El widget se cerró enseguida (ver arriba). Prueba: search widget --dry-run",
     "✘ Das Widget wurde sofort beendet (siehe oben). Versuche: search widget --dry-run",
     "✘ Виджет сразу завершился (см. выше). Попробуйте: search widget --dry-run",
     "✘ Il widget si è chiuso subito (vedi sopra). Prova: search widget --dry-run",
     "✘ O widget fechou logo (veja acima). Tente: search widget --dry-run")
_add("wid_none",
     "✘ Aucune méthode automatique pour ton environnement. Voir « Widget de bureau » dans le README (règles de fenêtre KDE, Hyprland, Sway, i3).",
     "✘ No automatic method for your environment. See “Desktop widget” in the README (window rules for KDE, Hyprland, Sway, i3).",
     "✘ No hay método automático para tu entorno. Consulta «Widget de escritorio» en el README (reglas de ventana para KDE, Hyprland, Sway, i3).",
     "✘ Keine automatische Methode für deine Umgebung. Siehe „Desktop-Widget“ im README (Fensterregeln für KDE, Hyprland, Sway, i3).",
     "✘ Для вашей среды нет автоматического способа. См. «Виджет рабочего стола» в README (правила окон для KDE, Hyprland, Sway, i3).",
     "✘ Nessun metodo automatico per il tuo ambiente. Vedi «Widget desktop» nel README (regole finestra per KDE, Hyprland, Sway, i3).",
     "✘ Nenhum método automático para o seu ambiente. Veja «Widget de desktop» no README (regras de janela para KDE, Hyprland, Sway, i3).")
_add("wid_tools", "Outils conseillés pour X11 : {l}  (sudo pacman -S {l})",
     "Recommended X11 tools: {l}  (sudo pacman -S {l})",
     "Herramientas recomendadas para X11: {l}  (sudo pacman -S {l})",
     "Empfohlene X11-Werkzeuge: {l}  (sudo pacman -S {l})",
     "Рекомендуемые инструменты для X11: {l}  (sudo pacman -S {l})",
     "Strumenti consigliati per X11: {l}  (sudo pacman -S {l})",
     "Ferramentas recomendadas para X11: {l}  (sudo pacman -S {l})")
_add("wid_stopped", "✔ {n} widget(s) arrêté(s).", "✔ {n} widget(s) stopped.",
     "✔ {n} widget(s) detenido(s).", "✔ {n} Widget(s) beendet.", "✔ Остановлено виджетов: {n}.",
     "✔ {n} widget fermato/i.", "✔ {n} widget(s) parado(s).")
_add("wid_nothing", "Aucun widget en cours d'exécution.", "No widget is running.",
     "Ningún widget en ejecución.", "Es läuft kein Widget.", "Виджет не запущен.",
     "Nessun widget in esecuzione.", "Nenhum widget em execução.")
_add("auto_on", "✔ Lancement automatique activé : {p}", "✔ Autostart enabled: {p}",
     "✔ Inicio automático activado: {p}", "✔ Autostart aktiviert: {p}",
     "✔ Автозапуск включён: {p}", "✔ Avvio automatico attivato: {p}",
     "✔ Início automático ativado: {p}")
_add("auto_off", "✔ Lancement automatique désactivé.", "✔ Autostart disabled.",
     "✔ Inicio automático desactivado.", "✔ Autostart deaktiviert.", "✔ Автозапуск выключен.",
     "✔ Avvio automatico disattivato.", "✔ Início automático desativado.")
_add("auto_state", "Lancement automatique : {s}", "Autostart: {s}", "Inicio automático: {s}",
     "Autostart: {s}", "Автозапуск: {s}", "Avvio automatico: {s}", "Início automático: {s}")
_add("auto_manual",
     "Ton bureau ({d}) ne lit pas les démarrages XDG. Ajoute cette ligne à sa configuration :\n  {l}",
     "Your desktop ({d}) does not read XDG autostart entries. Add this line to its config:\n  {l}",
     "Tu escritorio ({d}) no lee el inicio automático XDG. Añade esta línea a su configuración:\n  {l}",
     "Dein Desktop ({d}) liest keine XDG-Autostarts. Füge diese Zeile zur Konfiguration hinzu:\n  {l}",
     "Ваш рабочий стол ({d}) не читает автозапуск XDG. Добавьте эту строку в его конфигурацию:\n  {l}",
     "Il tuo desktop ({d}) non legge l'avvio automatico XDG. Aggiungi questa riga alla sua configurazione:\n  {l}",
     "Seu desktop ({d}) não lê o início automático XDG. Adicione esta linha à configuração dele:\n  {l}")

# ---- aide du chat et de la ligne de commande (nouveautés)
_add("h_theme", "couleurs : cyan, violet, matrix…", "colors: cyan, violet, matrix…",
     "colores: cyan, violet, matrix…", "Farben: cyan, violet, matrix…",
     "цвета: cyan, violet, matrix…", "colori: cyan, violet, matrix…", "cores: cyan, violet, matrix…")
_add("h_eco", "mode économie (moins d'images/s)", "eco mode (fewer frames/s)",
     "modo ahorro (menos fps)", "Sparmodus (weniger Bilder/s)", "экономный режим (меньше кадров)",
     "modalità risparmio (meno fps)", "modo econômico (menos fps)")
_add("h_consent", "envoi de mots-clés : yes, no, log", "keyword sending: yes, no, log",
     "envío de palabras clave: yes, no, log", "Stichwort-Übermittlung: yes, no, log",
     "отправка слов: yes, no, log", "invio parole chiave: yes, no, log",
     "envio de palavras-chave: yes, no, log")
_add("h_offline", "aucune requête réseau : on, off", "no network requests: on, off",
     "sin peticiones de red: on, off", "keine Netzwerkanfragen: on, off",
     "без сетевых запросов: on, off", "nessuna richiesta di rete: on, off",
     "sem requisições de rede: on, off")
_add("ap_theme", "change le thème de couleurs", "change the color theme", "cambia el tema de color",
     "Farbschema ändern", "сменить цветовую тему", "cambia il tema di colori", "muda o tema de cores")
_add("ap_eco", "mode économie : on, off ou auto", "eco mode: on, off or auto",
     "modo ahorro: on, off o auto", "Sparmodus: on, off oder auto",
     "экономный режим: on, off или auto", "modalità risparmio: on, off o auto",
     "modo econômico: on, off ou auto")
_add("ap_consent", "consentement d'envoi des mots-clés : status, yes, no, log",
     "keyword-sending consent: status, yes, no, log",
     "consentimiento de envío de palabras clave: status, yes, no, log",
     "Einwilligung zur Stichwort-Übermittlung: status, yes, no, log",
     "согласие на отправку слов: status, yes, no, log",
     "consenso all'invio delle parole chiave: status, yes, no, log",
     "consentimento de envio de palavras-chave: status, yes, no, log")
_add("ap_offline", "mode hors-ligne : on ou off", "offline mode: on or off",
     "modo sin conexión: on u off", "Offline-Modus: on oder off", "офлайн-режим: on или off",
     "modalità offline: on o off", "modo offline: on ou off")
_add("ap_widget", "globe en fond de bureau (start, stop)", "globe as a desktop widget (start, stop)",
     "globo como widget de escritorio (start, stop)", "Globus als Desktop-Widget (start, stop)",
     "глобус как виджет рабочего стола (start, stop)", "globo come widget del desktop (start, stop)",
     "globo como widget de desktop (start, stop)")
_add("ap_autostart", "lancement du widget à l'ouverture de session : on, off, status",
     "start the widget at login: on, off, status",
     "iniciar el widget al abrir sesión: on, off, status",
     "Widget beim Login starten: on, off, status",
     "запускать виджет при входе: on, off, status",
     "avvia il widget al login: on, off, status",
     "iniciar o widget no login: on, off, status")
_add("ap_shellhook", "affiche la ligne à ajouter pour lancer le globe à l'ouverture du terminal",
     "print the line to add to show the globe when a terminal opens",
     "muestra la línea para mostrar el globo al abrir la terminal",
     "zeigt die Zeile, um den Globus beim Terminalstart anzuzeigen",
     "показать строку для запуска глобуса при открытии терминала",
     "mostra la riga da aggiungere per avviare il globo all'apertura del terminale",
     "mostra a linha para exibir o globo ao abrir o terminal")
_add("ap_o_theme", "thème de couleurs, pour cette session", "color theme, this session only",
     "tema de color, solo esta sesión", "Farbschema, nur diese Sitzung",
     "цветовая тема, только на этот сеанс", "tema di colori, solo questa sessione",
     "tema de cores, só nesta sessão")
_add("ap_o_eco", "force le mode économie, pour cette session", "force eco mode, this session only",
     "fuerza el modo ahorro, solo esta sesión", "Sparmodus erzwingen, nur diese Sitzung",
     "принудительно экономный режим, только на этот сеанс",
     "forza la modalità risparmio, solo questa sessione", "força o modo econômico, só nesta sessão")
_add("ap_o_offline", "aucune requête réseau, pour cette session", "no network requests, this session only",
     "sin peticiones de red, solo esta sesión", "keine Netzwerkanfragen, nur diese Sitzung",
     "без сетевых запросов, только на этот сеанс", "nessuna richiesta di rete, solo questa sessione",
     "sem requisições de rede, só nesta sessão")
_add("ap_o_splash", "affiche le globe N secondes puis quitte (démarrage du terminal)",
     "show the globe for N seconds then exit (terminal startup)",
     "muestra el globo N segundos y sale (inicio de la terminal)",
     "Globus N Sekunden zeigen, dann beenden (Terminalstart)",
     "показать глобус N секунд и выйти (запуск терминала)",
     "mostra il globo per N secondi poi esce (avvio del terminale)",
     "mostra o globo por N segundos e sai (início do terminal)")
_add("ap_o_widget", "mode widget : globe seul, sans saisie (utilisé par « search widget »)",
     "widget mode: globe only, no input (used by “search widget”)",
     "modo widget: solo el globo, sin entrada (usado por «search widget»)",
     "Widget-Modus: nur Globus, keine Eingabe (von „search widget“ genutzt)",
     "режим виджета: только глобус, без ввода (используется «search widget»)",
     "modalità widget: solo globo, senza input (usata da «search widget»)",
     "modo widget: só o globo, sem entrada (usado por «search widget»)")


# --------------------------------------------------------------------------
#  Carte du monde
# --------------------------------------------------------------------------
def rasterize(gj, step=STEP):
    rows_n, cols_n = int(180 / step), int(360 / step)
    cells, polys = set(), []
    for f in gj["features"]:
        g = f["geometry"]
        if g["type"] == "Polygon":
            polys.append(g["coordinates"])
        elif g["type"] == "MultiPolygon":
            polys.extend(g["coordinates"])
    for poly in polys:
        hits = {}
        for ring in poly:
            for a, b in zip(ring, ring[1:]):
                x1, y1, x2, y2 = a[0], a[1], b[0], b[1]
                if y1 == y2:
                    continue
                if y1 > y2:
                    x1, y1, x2, y2 = x2, y2, x1, y1
                j0 = max(0, int((90 - y2) / step - 1))
                j1 = min(rows_n - 1, int((90 - y1) / step + 1))
                for j in range(j0, j1 + 1):
                    lat = 90 - step * (j + 0.5)
                    if y1 <= lat < y2:
                        hits.setdefault(j, []).append(
                            x1 + (lat - y1) * (x2 - x1) / (y2 - y1))
        for j, xs in hits.items():
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                i0 = max(0, math.ceil((xs[k] + 180) / step - 0.5))
                i1 = min(cols_n - 1, math.floor((xs[k + 1] + 180) / step - 0.5))
                for i in range(i0, i1 + 1):
                    cells.add((j, i))
    return sorted(cells)


def load_land():
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text())
        except Exception:
            pass
    print("Première exécution : téléchargement de la carte du monde (~130 Ko)…")
    req = urllib.request.Request(LAND_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        gj = json.load(r)
    cells = rasterize(gj)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cells))
    return cells


class World:
    pass


def unit(lat, lon):
    la, lo = np.radians(lat), np.radians(lon)
    return np.cos(la) * np.sin(lo), np.sin(la), np.cos(la) * np.cos(lo)


def build_world(cells):
    rows_n, cols_n = int(180 / STEP), int(360 / STEP)
    grid = np.zeros((rows_n, cols_n), bool)
    c = np.array(cells, dtype=np.int32).reshape(-1, 2)
    grid[c[:, 0], c[:, 1]] = True
    J, I = c[:, 0], c[:, 1]
    lat = 90 - STEP * (J + 0.5)
    lon = -180 + STEP * (I + 0.5)
    k = np.maximum(1, np.rint(1 / np.maximum(np.cos(np.radians(lat)), 0.06))).astype(np.int32)
    keep = (I % k) == 0
    lat_l, lon_l = lat[keep], lon[keep]

    olat, olon = [], []                       # océans : anneaux de points
    for n_row, la in enumerate(np.arange(-87, 88, 3.0)):
        n = max(8, int(120 * math.cos(math.radians(la))))
        lo = -180 + (np.arange(n) + 0.5 * (n_row % 2)) * 360.0 / n
        j = min(rows_n - 1, max(0, int((90 - la) / STEP)))
        i = ((lo + 180) / STEP).astype(int) % cols_n
        free = ~grid[j, i]
        olat.append(np.full(free.sum(), la))
        olon.append(lo[free])

    glat, glon = [], []                       # graticule (méridiens / parallèles)
    for lo0 in range(-180, 180, 30):
        la = np.arange(-90, 90.1, 1.5)
        glat.append(la)
        glon.append(np.full_like(la, lo0))
    for la0 in (-60, -30, 0, 30, 60):
        lo = np.arange(-180, 180, 1.5)
        glat.append(np.full_like(lo, la0))
        glon.append(lo)

    LAT = np.concatenate([lat_l] + olat + glat)
    LON = np.concatenate([lon_l] + olon + glon)
    w = World()
    w.LAND = np.concatenate([np.ones(len(lat_l), bool),
                             np.zeros(len(LAT) - len(lat_l), bool)])
    w.X, w.Y, w.Z = (v.astype(np.float32) for v in unit(LAT, LON))
    w.LON = LON.astype(np.float32)
    w.APP = np.random.random(len(LAT)).astype(np.float32)
    w.city = np.array([unit(a, b) for a, b in CITIES], dtype=np.float64)  # (8,3)
    n = 320
    w.HA = np.random.uniform(0, math.tau, n)
    w.HD = np.random.exponential(4.0, n) + 1.0
    w.HP = np.random.uniform(0, math.tau, n)
    e = World()                                  # version allégée (mode économie)
    for name in ("X", "Y", "Z", "LAND", "LON", "APP"):
        setattr(e, name, np.ascontiguousarray(getattr(w, name)[::2]))
    for name in ("city", "HA", "HD", "HP"):
        setattr(e, name, getattr(w, name))
    w.eco = e
    return w


# --------------------------------------------------------------------------
#  Configuration  (~/.config/search-globe/config.json)
# --------------------------------------------------------------------------
MODES = ("base", "perso", "mix")
BROWSER_NAMES = ("firefox", "librewolf", "zen", "floorp", "brave", "vivaldi",
                 "edge", "opera", "chromium", "chrome")
DEFAULTS = {"mode": "base", "geo": "FR", "engine": "google", "browser": "auto",
            "history_days": 60, "max_trends": 8, "topics": 3, "lang": "auto",
            "theme": "cyan", "perf": "auto", "consent": False, "consent_date": "",
            "offline": False, "exclude": []}
CONFIG_PATH = (Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
               / "search-globe" / "config.json")
def mode_text(m):
    return tx("mode_" + m)


def sanitize(cfg):
    if cfg.get("mode") not in MODES:
        cfg["mode"] = "base"
    if cfg.get("engine") not in ENGINES:
        cfg["engine"] = "google"
    geo = str(cfg.get("geo", "FR")).strip().upper()
    cfg["geo"] = geo if len(geo) == 2 and geo.isalpha() else "FR"
    b = str(cfg.get("browser", "auto")).strip().lower()
    cfg["browser"] = b if b == "auto" or b in BROWSER_NAMES else "auto"
    for key, lo, hi in (("history_days", 1, 3650), ("max_trends", 1, MAX_TRENDS),
                        ("topics", 1, 5)):
        try:
            cfg[key] = min(hi, max(lo, int(cfg[key])))
        except (TypeError, ValueError, KeyError):
            cfg[key] = DEFAULTS[key]
    lg = str(cfg.get("lang", "auto")).strip().lower()
    cfg["lang"] = lg if lg == "auto" or (len(lg) == 2 and lg.isalpha()) else "auto"
    th = str(cfg.get("theme", "cyan")).strip().lower()
    cfg["theme"] = th if th in THEMES else "cyan"
    pf = str(cfg.get("perf", "auto")).strip().lower()
    cfg["perf"] = pf if pf in ("on", "off", "auto") else "auto"
    cfg["consent"] = cfg.get("consent") is True      # jamais de consentement « par défaut »
    cfg["offline"] = cfg.get("offline") is True
    cfg["consent_date"] = str(cfg.get("consent_date", ""))[:10] if cfg["consent"] else ""
    ex = cfg.get("exclude", [])
    cfg["exclude"] = (sorted({str(x).strip().lower() for x in ex if str(x).strip()})
                      if isinstance(ex, list) else [])
    return cfg


def load_config():
    cfg = {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULTS.items()}
    existed = CONFIG_PATH.exists()
    if existed:
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update({k: data[k] for k in DEFAULTS if k in data})
        except Exception:
            pass
    return sanitize(cfg), existed


def save_config(cfg):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")


# --------------------------------------------------------------------------
#  Historique du navigateur -> recherches les plus fréquentes (100 % local)
# --------------------------------------------------------------------------
SEARCH_PATTERNS = ["%google.%/search?%", "%bing.com/search?%", "%duckduckgo.com/?%",
                   "%duckduckgo.com/html%", "%search.brave.com/search?%", "%qwant.com/?%",
                   "%ecosia.org/search?%", "%startpage.com/%", "%search.yahoo.com/search%",
                   "%youtube.com/results?%", "%kagi.com/search?%", "%yandex.%/search%"]
# (fragment du nom d'hôte, chemin requis, paramètre de la requête)
SEARCH_SITES = (("google.", "/search", "q"), ("bing.com", "/search", "q"),
                ("duckduckgo.com", None, "q"), ("search.brave.com", "/search", "q"),
                ("qwant.com", None, "q"), ("ecosia.org", "/search", "q"),
                ("startpage.com", None, "query"), ("search.yahoo.com", "/search", "p"),
                ("youtube.com", "/results", "search_query"), ("kagi.com", "/search", "q"),
                ("yandex.", "/search", "text"))

HIST_GLOBS = {
    "firefox": ["~/.mozilla/firefox/*/places.sqlite",
                "~/.config/mozilla/firefox/*/places.sqlite",
                "~/.var/app/org.mozilla.firefox/.mozilla/firefox/*/places.sqlite",
                "~/snap/firefox/common/.mozilla/firefox/*/places.sqlite"],
    "librewolf": ["~/.librewolf/*/places.sqlite",
                  "~/.var/app/io.gitlab.librewolf-community/.librewolf/*/places.sqlite"],
    "zen": ["~/.zen/*/places.sqlite", "~/.var/app/app.zen_browser.zen/.zen/*/places.sqlite"],
    "floorp": ["~/.floorp/*/places.sqlite",
               "~/.var/app/one.ablaze.floorp/.floorp/*/places.sqlite"],
    "brave": ["~/.config/BraveSoftware/Brave-Browser/*/History",
              "~/.var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser/*/History"],
    "vivaldi": ["~/.config/vivaldi/*/History"],
    "edge": ["~/.config/microsoft-edge/*/History"],
    "opera": ["~/.config/opera/History", "~/.config/opera/*/History"],
    "chromium": ["~/.config/chromium/*/History",
                 "~/.var/app/org.chromium.Chromium/config/chromium/*/History"],
    "chrome": ["~/.config/google-chrome/*/History",
               "~/.var/app/com.google.Chrome/config/google-chrome/*/History"],
}


def extract_query(url):
    """URL de moteur de recherche -> requête normalisée (ou None)."""
    try:
        u = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(u.query)
    except ValueError:
        return None
    host = (u.hostname or "").lower()
    for frag, path, param in SEARCH_SITES:
        if frag in host and (path is None or u.path.startswith(path)) and qs.get(param):
            q = " ".join(qs[param][0].lower().split())
            if not (2 <= len(q) <= 60) or "://" in q or q.startswith("www."):
                return None
            if " " not in q and re.fullmatch(r"[\w-]+(\.[\w-]+)+", q):
                return None                      # adresse tapée dans la barre, pas une recherche
            return q
    return None


def detect_default_browser():
    try:
        out = subprocess.run(["xdg-settings", "get", "default-web-browser"],
                             capture_output=True, text=True, timeout=3).stdout.lower()
    except Exception:
        return None
    for name in BROWSER_NAMES:
        if name in out:
            return name
    return None


def history_files(cfg):
    found = {}
    for name, pats in HIST_GLOBS.items():
        paths = sorted({p for pat in pats for p in glob.glob(os.path.expanduser(pat))})
        if paths:
            found[name] = paths
    want = cfg.get("browser", "auto")
    if want != "auto":
        names = [want] if want in found else []
    else:
        d = detect_default_browser()
        names = [d] if d in found else list(found)
    return [(n, p) for n in names for p in found[n]]


def read_queries(path, since):
    """Lit une COPIE temporaire de la base (le navigateur peut rester ouvert)."""
    firefox = os.path.basename(path) == "places.sqlite"
    tmp = tempfile.mkdtemp(prefix="search-globe-")
    try:
        db = os.path.join(tmp, "h.sqlite")
        shutil.copy2(path, db)
        for suf in ("-wal", "-shm"):
            if os.path.exists(path + suf):
                shutil.copy2(path + suf, db + suf)
        like = " OR ".join(["u.url LIKE ?"] * len(SEARCH_PATTERNS))
        if firefox:
            sql = ("SELECT u.url, COUNT(*), MAX(v.visit_date) FROM moz_historyvisits v "
                   "JOIN moz_places u ON u.id = v.place_id "
                   f"WHERE v.visit_date >= ? AND ({like}) GROUP BY u.url")
            off = 0
        else:
            sql = ("SELECT u.url, COUNT(*), MAX(v.visit_time) FROM visits v "
                   "JOIN urls u ON u.id = v.url "
                   f"WHERE v.visit_time >= ? AND ({like}) GROUP BY u.url")
            off = 11644473600                    # époque WebKit (1601) -> Unix
        con = sqlite3.connect(db)
        try:
            rows = con.execute(sql, [int((since + off) * 1e6)] + SEARCH_PATTERNS).fetchall()
        finally:
            con.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    agg = {}
    for url, n, t in rows:
        q = extract_query(url)
        if q:
            c, last = agg.get(q, (0, 0))
            agg[q] = (c + n, max(last, (t or 0) / 1e6 - off))
    return [(q, c, last) for q, (c, last) in agg.items()]


BLOCK_RE = re.compile(r"\b(porn\w*|xxx|sex\w*|hentai|nsfw|onlyfans|escort\w*|nude\w*|"
                      r"password|mot de passe|iban)\b")
STOP = set("""le la les un une des du de d l et ou à a au aux en dans sur pour par avec sans
 ce cet cette ces mon ma mes ton ta tes son sa ses vs comment pourquoi quel quelle quels quand
 où qui que quoi est sont the of and or to in on for with how what why is are my your best
 a an at by from vs near me way learn use using make get does do can should need free
 online new quick easy fast simple""".split())
NOISE = set("""trailer gameplay soluce wiki gratuit gratuitement prix avis test date sortie
 télécharger telecharger download streaming vf vostfr pdf review guide meilleur meilleurs
 meilleure top liste tuto tutoriel installer install config""".split())
GEO_LANG = {"FR": "fr", "BE": "fr", "CH": "fr", "LU": "fr", "CA": "en", "US": "en", "GB": "en",
            "AU": "en", "IE": "en", "DE": "de", "AT": "de", "ES": "es", "MX": "es", "AR": "es",
            "IT": "it", "PT": "pt", "BR": "pt", "NL": "nl", "PL": "pl", "JP": "ja"}
BAD_CAT = ("wikipédia", "wikipedia", "article", "page ", "portail", "homonymie", "bon ",
           "ébauche", "modèle", "catégorie", "categor", "lien", "pages", "commons",
           "wikidata", "stub", "liste")


STATE_PATH = (Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
              / "search-globe" / "sent.log")
NO_WORDS = {"n", "no", "non", "nein", "нет", "nao", "não", "off", "0"}


def log_send(host, keyword):
    """Journal LOCAL de chaque mot-clé envoyé (consultable : search consent log)."""
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with STATE_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{host}\t{keyword}\n")
        lines = STATE_PATH.read_text(encoding="utf-8").splitlines()
        if len(lines) > 300:
            STATE_PATH.write_text("\n".join(lines[-200:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def log_report(n=15):
    try:
        lines = STATE_PATH.read_text(encoding="utf-8").splitlines()[-n:]
    except OSError:
        lines = []
    if not lines:
        return tx("consent_log_empty")
    return tx("consent_log_title") + "\n" + "\n".join("  " + ln.replace("\t", " · ") for ln in lines)


def consent_screen(cfg):
    """Texte du consentement : montre les mots-clés RÉELS qui seraient envoyés."""
    try:
        qs, _ = history_queries(cfg)
        topics = pick_topics(qs, cfg["topics"])
    except Exception:
        topics = []
    kw = "\n".join(f"   • {tp}" for tp in topics) if topics else "   " + tx("consent_none_kw")
    state = (tx("consent_state_yes", d=cfg.get("consent_date") or "?") if cfg.get("consent")
             else tx("consent_state_no"))
    off = tx("offline_state", s=tx("word_on") if cfg.get("offline") else tx("word_off"))
    return "\n".join([tx("consent_title"), "", tx("consent_intro"), kw, "", tx("consent_notsent"),
                      tx("consent_audit"), tx("consent_revoke"), "", state, off])


def set_consent(cfg, value):
    cfg["consent"] = bool(value)
    cfg["consent_date"] = time.strftime("%Y-%m-%d") if value else ""


def is_blocked(q, exclude):
    return bool(BLOCK_RE.search(q)) or any(w in q for w in exclude)


def history_queries(cfg):
    """-> ([(requête, nombre, dernière_date)], [navigateurs lus]) ; 100 % local."""
    since = time.time() - cfg["history_days"] * 86400
    counts, last, srcs = {}, {}, []
    for name, path in history_files(cfg):
        try:
            rows = read_queries(path, since)
        except Exception:
            continue
        if name not in srcs:
            srcs.append(name)
        for q, n, ts in rows:
            if is_blocked(q, cfg["exclude"]):
                continue
            counts[q] = counts.get(q, 0) + n
            last[q] = max(last.get(q, 0), ts)
    return [(q, counts[q], last[q]) for q in counts], srcs


def topic_key(q):
    """« resident evil 4 remake » -> « resident evil »"""
    toks = [w for w in re.findall(r"[^\W_][\w'-]*", q.lower())
            if w not in STOP and w not in NOISE and not w.isdigit() and len(w) > 1]
    return " ".join(toks[:2]) or None


def pick_topics(queries, n, now=None):
    """Regroupe les recherches par sujet ; les sujets récents et répétés passent devant."""
    now = now or time.time()
    score = {}
    for q, c, last in queries:
        k = topic_key(q)
        if k:
            score[k] = score.get(k, 0.0) + c * 0.5 ** (max(0.0, now - last) / 86400 / 14)
    return sorted(score, key=lambda k: (-score[k], k))[:n]


def detect_lang():
    """Langue du système (LANG=fr_FR.UTF-8 -> fr) si elle est gérée."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANGUAGE", "LANG"):
        v = os.environ.get(var, "")
        code = v.split(":")[0].split("_")[0].split(".")[0].lower()[:2]
        if code in LANGS:
            return code
    return None


def lang_for(cfg):
    """Langue des actus et de Wikipédia (et de l'interface si elle est gérée)."""
    if cfg.get("lang", "auto") != "auto":
        return cfg["lang"]
    return detect_lang() or GEO_LANG.get(cfg["geo"], "en")


def ui_lang(cfg):
    code = lang_for(cfg)
    return code if code in LANGS else "en"


def http_get(url, timeout=8, ua=UA):
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_news(topic, geo, lang, n=2):
    """Dernières actus Google News sur le sujet -> [(titre, source, lien)]"""
    for window in ("7d", "30d"):
        q = urllib.parse.quote(f"{topic} when:{window}")
        url = (f"https://news.google.com/rss/search?q={q}&hl={lang}&gl={geo}"
               f"&ceid={geo}:{lang}")
        root = ET.fromstring(http_get(url))
        out, seen = [], set()
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            if not title or not link:
                continue
            head, _, src = title.rpartition(" - ")
            if not head:
                head, src = title, ""
            if head.lower() in seen:
                continue
            seen.add(head.lower())
            out.append((head, src, link))
            if len(out) >= n:
                break
        if out:
            return out
    return []


def pick_genre(cats, topic):
    toks = topic.lower().split()
    ok = []
    for c in cats:
        name = c.split(":", 1)[-1].strip()
        low = name.lower()
        if not (4 <= len(name) <= 40) or re.search(r"\d", name):
            continue
        if any(b in low for b in BAD_CAT) or all(t in low for t in toks):
            continue
        ok.append(name)
    return min(ok, key=lambda x: (len(x), x)) if ok else None


def fetch_wiki(topic, lang):
    """Wikipédia -> (sujets similaires, catégories de l'article)"""
    base = f"https://{lang}.wikipedia.org/w/api.php"

    def get(params):
        return json.loads(http_get(base + "?format=json&" + params, ua=WIKI_UA))

    r = get("action=opensearch&limit=1&namespace=0&search=" + urllib.parse.quote(topic))
    if len(r) < 2 or not r[1]:
        return [], []
    title = r[1][0]
    toks = topic.lower().split()
    j = get("action=query&list=search&srlimit=8&srnamespace=0&srsearch="
            + urllib.parse.quote("morelike:" + title))
    similar = []
    for x in j.get("query", {}).get("search", []):
        t = x.get("title", "")
        low = t.lower()
        if t and not all(w in low for w in toks) and not low.startswith(("liste", "list of")):
            similar.append(t)
    j = get("action=query&prop=categories&cllimit=50&clshow=!hidden&titles="
            + urllib.parse.quote(title))
    cats = [c.get("title", "") for pg in j.get("query", {}).get("pages", {}).values()
            for c in pg.get("categories", [])]
    return similar, cats


def build_topic_items(topic, cfg):
    """Un sujet -> file d'éléments : actu, titre similaire, genre, actu, similaires…"""
    geo, lang, disp = cfg["geo"], lang_for(cfg), topic.title()
    log_send("news.google.com", topic)
    try:
        news = fetch_news(topic, geo, lang)
    except Exception:
        news = []
    log_send(f"{lang}.wikipedia.org", topic)
    try:
        similar, cats = fetch_wiki(topic, lang)
    except Exception:
        similar, cats = [], []
    n_items = [(h, f"{tx('d_news')} · {disp}" + (f" · {src}" if src else ""), "news", link)
               for h, src, link in news]
    l_items = [(x, tx("d_like", t=disp), "like", None) for x in similar[:3]]
    g = pick_genre(cats, topic)
    g_items = [(g, f"{tx('d_genre')} · {disp}", "genre", None)] if g else []
    queue = n_items[:1] + l_items[:1] + g_items + n_items[1:2] + l_items[1:]
    return queue or [(disp, tx("d_hist"), "like", None)]


def merge_queues(queues):
    out, seen = [], set()
    for rank in range(max((len(q) for q in queues), default=0)):
        for q in queues:
            if rank < len(q) and q[rank][0].lower() not in seen:
                seen.add(q[rank][0].lower())
                out.append(q[rank])
    return out


# --------------------------------------------------------------------------
#  Tendances : Google Trends (base) et/ou actus liées à l'historique (perso)
# --------------------------------------------------------------------------
class Trends:
    def __init__(self, cfg):
        self.cfg = cfg
        self.mode = cfg["mode"]
        self.geo = cfg["geo"]
        self.base, self.perso, self.sources, self.topics = [], [], [], []
        self.perso_loaded = False
        self.status = "status_sync"
        self.updated = 0.0
        self.last_refresh = 0.0
        self.busy_b = self.busy_p = False

    @property
    def items(self):
        """[(titre, détail, genre, cible)] ; cible = lien à ouvrir, ou None (= recherche)"""
        b = [(t, tr, "base", None) for t, tr in self.base]
        p = list(self.perso)
        if self.mode == "base":
            out = b
        elif self.mode == "perso":
            out = p or b                         # historique vide -> tendances du jour
        else:
            out, seen = [], set()
            for it in itertools.chain.from_iterable(itertools.zip_longest(p, b)):
                if it and it[0].lower() not in seen:
                    seen.add(it[0].lower())
                    out.append(it)
        return out[: self.cfg["max_trends"]]

    @property
    def needs_consent(self):
        return (self.mode in ("perso", "mix") and bool(self.topics)
                and not self.cfg.get("consent") and not self.cfg.get("offline"))

    def header(self):
        h = self._header0()
        return h + " · " + tx("consent_hint") if self.needs_consent else h

    def _header0(self):
        if self.mode == "perso":
            if self.perso:
                return tx("header_perso", t=" · ".join(self.topics or self.sources))
            return tx("header_perso_empty", geo=self.geo)
        if self.mode == "mix":
            return tx("header_mix", geo=self.geo)
        return tx("header_base", geo=self.geo)

    def set_mode(self, mode):
        self.mode = mode
        self.refresh()

    def refresh(self, force=False):
        self.last_refresh = time.time()
        if self.mode in ("base", "mix"):
            self._start_base(force)
        if self.mode in ("perso", "mix") and not self.busy_p \
                and (force or not self.perso_loaded):
            self.busy_p = True
            if not self.perso:
                self.status = "status_analyze"
            threading.Thread(target=self._run_perso, daemon=True).start()

    def _start_base(self, force=False):
        if self.cfg.get("offline"):
            self.status = "status_offline_mode"
            return
        if not self.busy_b and (force or not self.base):
            self.busy_b = True
            threading.Thread(target=self._run_base, daemon=True).start()

    def _run_perso(self):
        try:
            qs, srcs = history_queries(self.cfg)
            topics = pick_topics(qs, self.cfg["topics"])
            self.sources = srcs
            if not topics:
                self.perso, self.topics = [], []
                self.status = "status_nohist"
                self._start_base()               # repli : tendances du jour
            elif self.cfg.get("offline") or not self.cfg.get("consent"):
                # rien n'est envoyé : on n'affiche que les sujets détectés, en local
                self.perso = [(tp.title(), tx("d_hist"), "like", None) for tp in topics]
                self.topics = topics
            else:
                with ThreadPoolExecutor(max_workers=min(6, len(topics))) as ex:
                    queues = list(ex.map(lambda tp: build_topic_items(tp, self.cfg), topics))
                self.perso, self.topics = merge_queues(queues), topics
            self.perso_loaded = True
            self.updated = time.time()
        except Exception:
            self.perso_loaded = True
            self.status = "status_histerr"
            self._start_base()
        finally:
            self.busy_p = False

    def _run_base(self):
        urls = (f"https://trends.google.com/trending/rss?geo={self.geo}",
                f"https://trends.google.com/trends/trendingsearches/daily/rss?geo={self.geo}")
        for url in urls:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=10) as r:
                    root = ET.fromstring(r.read())
                items = []
                for it in root.iter("item"):
                    title = (it.findtext("title") or "").strip()
                    traffic = ""
                    for ch in it:
                        if ch.tag.endswith("approx_traffic"):
                            traffic = (ch.text or "").strip()
                    if title:
                        items.append((title, traffic))
                if items:
                    self.base = items
                    self.status = "ok"
                    self.updated = time.time()
                    self.busy_b = False
                    return
            except Exception:
                continue
        if not self.base:
            self.status = "status_offline"
        self.busy_b = False


# --------------------------------------------------------------------------
#  Utilitaires
# --------------------------------------------------------------------------
def ease_out(x):
    return 1 - (1 - x) ** 3


def wcell(c):
    return 2 if unicodedata.east_asian_width(c) in "WF" else 1


def cwidth(s):
    return sum(wcell(c) for c in s)


def fit(s, w):
    if cwidth(s) <= w:
        return s
    out, n = [], 0
    for c in s:
        if n + wcell(c) > w - 1:
            break
        out.append(c)
        n += wcell(c)
    return "".join(out) + "…"


def put(win, y, x, s, attr=0):
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x >= w or not s:
        return
    if x < 0:
        s, x = s[-x:], 0
    s = s[: w - x]
    if not s:
        return
    try:
        win.addstr(y, x, s, attr)
    except curses.error:
        pass


THEMES = {
    "cyan":   {1: 24, 2: 27, 3: 33, 4: 39, 5: 51, 6: 195, 7: 244, 8: 123},
    "violet": {1: 54, 2: 55, 3: 93, 4: 135, 5: 177, 6: 225, 7: 244, 8: 183},
    "matrix": {1: 22, 2: 28, 3: 34, 4: 40, 5: 46, 6: 157, 7: 243, 8: 120},
    "amber":  {1: 94, 2: 130, 3: 172, 4: 214, 5: 220, 6: 230, 7: 244, 8: 222},
    "rose":   {1: 53, 2: 89, 3: 125, 4: 161, 5: 205, 6: 224, 7: 244, 8: 218},
    "mono":   {1: 236, 2: 240, 3: 245, 4: 250, 5: 255, 6: 231, 7: 244, 8: 252},
}
THEME_BASIC = {"cyan": "COLOR_CYAN", "violet": "COLOR_MAGENTA", "matrix": "COLOR_GREEN",
               "amber": "COLOR_YELLOW", "rose": "COLOR_RED", "mono": "COLOR_WHITE"}


def init_colors(theme="cyan"):
    curses.start_color()
    try:
        curses.use_default_colors()
    except curses.error:
        pass
    if curses.COLORS >= 256:
        spec = dict(THEMES.get(theme, THEMES["cyan"]))
    else:                                       # terminaux 8 couleurs : une teinte par thème
        main = getattr(curses, THEME_BASIC.get(theme, "COLOR_CYAN"))
        white = curses.COLOR_WHITE
        spec = {1: main, 2: main, 3: main, 4: main, 5: main, 6: white, 7: white, 8: main}
    for n, c in spec.items():
        curses.init_pair(n, c, -1)
    A = {0: 0}
    for n in spec:
        A[n] = curses.color_pair(n)
    A[5] |= curses.A_BOLD
    A[6] |= curses.A_BOLD
    return A


def mouse_motion(on):
    """Demande au terminal d'envoyer les mouvements de souris (survol) : sans cela,
    la plupart des terminaux ne transmettent que les clics."""
    try:
        sys.stdout.write("\x1b[?1003h" if on else "\x1b[?1003l")
        sys.stdout.flush()
    except Exception:
        pass


def mouse_test(scr):
    curses.curs_set(0)
    curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
    curses.mouseinterval(0)
    mouse_motion(True)
    scr.keypad(True)
    scr.timeout(100)
    moves, clicks, log = 0, 0, []
    try:
        while True:
            scr.erase()
            put(scr, 0, 1, tx("mt_title"))
            put(scr, 2, 1, tx("mt_counts", m=moves, c=clicks))
            put(scr, 3, 1, tx("mt_ok") if moves else tx("mt_ko"))
            for n, line in enumerate(log[-8:]):
                put(scr, 5 + n, 1, line)
            scr.refresh()
            try:
                key = scr.get_wch()
            except curses.error:
                continue
            if key == "\x1b":
                return
            if key == curses.KEY_MOUSE:
                try:
                    _, x, y, _, b = curses.getmouse()
                except curses.error:
                    continue
                if b & curses.REPORT_MOUSE_POSITION:
                    moves += 1
                if b & (curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED):
                    clicks += 1
                log.append(f"x={x:<4} y={y:<4} état={b}")
    finally:
        mouse_motion(False)


def open_url(url):
    """xdg-open : nouvel onglet si le navigateur tourne, sinon nouvelle fenêtre."""
    try:
        subprocess.Popen(["xdg-open", url], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except FileNotFoundError:
        webbrowser.open(url)


def plot(lev, xs, ys, level):
    H, W = lev.shape
    ok = (xs >= 0) & (xs < W) & (ys >= 0) & (ys < H)
    xs, ys = xs[ok], ys[ok]
    if xs.size:
        lev[ys, xs] = np.maximum(lev[ys, xs], level)


def block(lev, x, y, level, rad=1):
    r = np.arange(-rad, rad + 1)
    xs = int(round(x)) + np.repeat(r, len(r))
    ys = int(round(y)) + np.tile(r, len(r))
    plot(lev, xs, ys, level)


def line(x0, y0, x1, y1):
    n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
    return (np.rint(np.linspace(x0, x1, n)).astype(int),
            np.rint(np.linspace(y0, y1, n)).astype(int))


def circle(cx, cy, R, step=1.0):
    n = max(12, int(math.tau * R / step))
    a = np.linspace(0, math.tau, n, endpoint=False)
    return np.rint(cx + R * np.cos(a)).astype(int), np.rint(cy - R * np.sin(a)).astype(int)


# --------------------------------------------------------------------------
#  Application
# --------------------------------------------------------------------------
class App:
    def __init__(self, world, trends, cfg, widget=False, splash=0):
        self.w = world
        self.trends = trends
        self.cfg = cfg
        self.widget, self.splash = widget, float(splash or 0)
        self.minimal = bool(widget or splash)        # globe seul : pas de barre, ni HUD, ni chat
        self.ft, self.slow = None, 0
        self.eco = False
        self.geo = cfg["geo"]
        self.home_url, self.query_url = ENGINES[cfg["engine"]]
        self.zoom = 1.0
        self.chat = False                       # mode paramètres (chat)
        self.chat_p = 0.0                       # progression de l'animation d'ouverture
        self.chat_log, self.chat_pending, self.chat_hits = [], [], []
        self.cbuf, self.cpos = [], 0
        self.chat_scroll = 0
        self.chat_hist, self.hist_i = [], 0
        self.want_quit = False
        self.gear = None
        self.eco = self.want_eco()
        self.A = {i: 0 for i in range(10)}
        self.angle = 0.9
        self.spin = 0.30
        self.boost = 0.0
        self.pulse_t0 = -10.0
        self.ripples = []                 # [x, y, t0]
        self.vis = [0.0] * MAX_TRENDS
        self.flash = {}
        self.buf, self.pos = [], 0
        self.msg, self.msg_until = "", 0.0
        self.mouse = None
        self.last_click = 0.0
        self.geom = None
        self.t0 = self.last = time.monotonic()

    # ---------- actions ----------
    def search(self, q, now):
        q = q.strip()
        if not q:
            return
        open_url(self.query_url + urllib.parse.quote_plus(q))
        self.msg, self.msg_until = tx("msg_search", q=q), now + 3
        self.pulse_t0, self.boost = now, self.boost + 2.5
        if self.geom:
            self.ripples.append([self.geom["cx"], self.geom["cy"], now])

    # ================= mode paramètres (chat) =================
    CHAT_COMMANDS = ("/help", "/mode", "/lang", "/geo", "/engine", "/browser", "/topics",
                     "/days", "/max", "/exclude", "/history", "/preview", "/config",
                     "/refresh", "/clear", "/reset", "/theme", "/eco", "/consent", "/offline",
                     "/exit", "/quit")

    def chat_open(self, now, prefill=""):
        if self.minimal:
            return
        if not self.chat:
            self.chat = True
            if not self.chat_log and not self.chat_pending:
                self.chat_pending.append((now + 0.3, tx("chat_welcome")))
        self.cbuf, self.cpos = list(prefill), len(prefill)

    def chat_close(self, now):
        self.chat = False

    def chat_submit(self, text, now):
        text = text.strip()
        if not text:
            return
        self.chat_log.append({"who": "me", "text": text, "t0": now})
        self.chat_scroll = 0
        reply = self.chat_exec(text, now) if text.startswith("/") else tx("chat_plain")
        if reply:
            self.chat_pending.append((now + 0.45, reply))     # « écrit… » puis la réponse

    def after_setting(self, key, now, save=True):
        if save:
            try:
                save_config(self.cfg)
            except OSError:
                pass
        if key == "theme":
            self.A = init_colors(self.cfg["theme"])
        if key == "perf":
            self.eco = self.want_eco()
        tr = self.trends
        if key == "geo":
            tr.geo = self.geo = self.cfg["geo"]
        if key == "engine":
            self.home_url, self.query_url = ENGINES[self.cfg["engine"]]
        if key == "mode":
            tr.mode = self.cfg["mode"]
        if key in ("geo", "lang", "browser", "topics", "history_days", "exclude", "mode",
                   "consent", "offline"):
            tr.perso_loaded = False
            self.vis = [0.0] * MAX_TRENDS
            tr.refresh(force=True)

    def help_text(self):
        spec = (("/help", "h_help"), ("/mode base|perso|mix", "h_mode"),
                ("/lang fr|en|es|de|ru|it|pt", "h_lang"), ("/geo FR", "h_geo"),
                ("/engine google", "h_engine"), ("/browser auto", "h_browser"),
                ("/topics 3", "h_topics"), ("/days 60", "h_days"), ("/max 8", "h_max"),
                ("/exclude add|remove|list|clear", "h_exclude"), ("/history", "h_history"),
                ("/preview", "h_preview"), ("/config", "h_config"), ("/refresh", "h_refresh"),
                ("/clear", "h_clear"), ("/reset", "h_reset"), ("/theme cyan", "h_theme"),
                ("/eco on|off|auto", "h_eco"), ("/consent yes|no|log", "h_consent"),
                ("/offline on|off", "h_offline"), ("/exit", "h_exit"), ("/quit", "h_quit"))
        out = [tx("h_title"), ""] + [f"{u} — {tx(k)}" for u, k in spec]
        return "\n".join(out + ["", tx("h_examples")])

    def chat_exec(self, text, now):
        parts = text.split(None, 2)
        cmd = parts[0][1:].lower()
        a1 = parts[1] if len(parts) > 1 else ""
        a2 = parts[2] if len(parts) > 2 else ""
        cfg = self.cfg
        if cmd in ("help", "?", "h"):
            return self.help_text()
        if cmd == "mode":
            if not a1:
                return tx("cfg_mode", m=mode_text(cfg["mode"])) + "\n" + \
                    tx("c_opts", o="base · perso · mix")
            try:
                m = apply_setting(cfg, "mode", a1)
            except ValueError as e:
                return f"✘ {e}"
            self.set_mode(m, now)
            note = ("\n" + tx("c_consent_prompt")
                    if m != "base" and not cfg["consent"] and not cfg["offline"] else "")
            return tx("ok_mode", m=mode_text(m)) + note
        if cmd == "lang":
            if not a1:
                names = " · ".join(f"{c} {LANG_NAMES[c]}" for c in LANGS)
                return f"{tx('c_langs')}\n{names}\n→ {cfg['lang']}"
            try:
                v = apply_setting(cfg, "lang", a1)
            except ValueError as e:
                return f"✘ {e}"
            set_lang(ui_lang(cfg))
            self.after_setting("lang", now)
            return tx("ok_lang", n=LANG_NAMES.get(v) or f"{v} ({LANG_NAMES[ui_lang(cfg)]})")
        keymap = {"geo": "geo", "engine": "engine", "browser": "browser", "topics": "topics",
                  "days": "history_days", "max": "max_trends"}
        if cmd in keymap:
            key = keymap[cmd]
            if not a1:
                return f"{key} : {cfg[key]}"
            try:
                v = apply_setting(cfg, key, a1)
            except ValueError as e:
                return f"✘ {key} : {e}"
            self.after_setting(key, now)
            return f"✔ {key} = {v}"
        if cmd == "exclude":
            msg, changed = exclude_action(cfg, a1.lower() or "list", a2)
            if changed:
                self.after_setting("exclude", now)
            return msg
        if cmd == "history":
            def work():
                try:
                    txt = history_report(cfg, short=True)
                except Exception as e:
                    txt = f"✘ {e}"
                self.chat_pending.append((time.monotonic(), txt))
            threading.Thread(target=work, daemon=True).start()
            return tx("c_history_wait")
        if cmd == "preview":
            its = self.trends.items
            if not its:
                return tx("c_no_trends")
            return "\n".join(f"{GLYPH.get(k, '▸')} {t_}" + (f" — {d_}" if d_ else "")
                             for t_, d_, k, _ in its)
        if cmd == "config":
            return "\n".join(f"{k}: {cfg[k]}" for k in DEFAULTS) + "\n" + \
                tx("cfg_mode", m=mode_text(cfg["mode"]))
        if cmd == "refresh":
            self.trends.refresh(force=True)
            return tx("c_refresh")
        if cmd == "clear":
            self.chat_log, self.chat_pending = [], []
            return tx("c_cleared")
        if cmd == "reset":
            if a1.lower() not in YES_WORDS:
                return tx("c_reset_confirm")
            try:
                CONFIG_PATH.unlink()
            except OSError:
                pass
            fresh = sanitize({k: (list(v) if isinstance(v, list) else v)
                              for k, v in DEFAULTS.items()})
            cfg.clear()
            cfg.update(fresh)
            set_lang(ui_lang(cfg))
            for key in ("geo", "engine", "mode"):
                self.after_setting(key, now, save=False)
            return tx("c_reset_done")
        if cmd == "theme":
            if not a1:
                return tx("c_themes") + "\n" + " · ".join(THEMES) + f"\n→ {cfg['theme']}"
            try:
                v = apply_setting(cfg, "theme", a1)
            except ValueError as e:
                return f"✘ {e}"
            self.after_setting("theme", now)
            return tx("ok_theme", n=v)
        if cmd in ("eco", "perf"):
            if a1:
                try:
                    v = apply_setting(cfg, "perf", a1)
                except ValueError as e:
                    return f"✘ {e}"
                self.after_setting("perf", now)
            return tx("ok_perf", p=perf_text(cfg["perf"]))
        if cmd == "offline":
            arg = a1.lower()
            if arg == "on" or arg in YES_WORDS:
                cfg["offline"] = True
            elif arg in NO_WORDS:
                cfg["offline"] = False
            else:
                return tx("offline_state", s=tx("word_on") if cfg["offline"] else tx("word_off"))
            self.after_setting("offline", now)
            return tx("ok_offline_on") if cfg["offline"] else tx("ok_offline_off")
        if cmd == "consent":
            arg = a1.lower()
            if arg in YES_WORDS:
                set_consent(cfg, True)
                self.after_setting("consent", now)
                return tx("consent_granted")
            if arg in NO_WORDS:
                set_consent(cfg, False)
                self.after_setting("consent", now)
                return tx("consent_denied")
            if arg == "log":
                return log_report()

            def work():
                try:
                    txt = consent_screen(cfg) + "\n\n" + tx("consent_cmds")
                except Exception as e:
                    txt = f"✘ {e}"
                self.chat_pending.append((time.monotonic(), txt))
            threading.Thread(target=work, daemon=True).start()
            return tx("c_history_wait")
        if cmd in ("exit", "close", "back"):
            self.chat_close(now)
            return None
        if cmd in ("quit", "q"):
            self.want_quit = True
            return None
        return tx("chat_unknown", c="/" + cmd)

    def chat_key(self, key, now):
        """Édition de la zone de chat. Renvoie True pour quitter l'application."""
        if key == "\x1b":
            self.chat_close(now)
        elif key in ("\n", "\r", curses.KEY_ENTER):
            text = "".join(self.cbuf)
            if text.strip():
                self.chat_hist.append(text)
            self.hist_i = len(self.chat_hist)
            self.cbuf, self.cpos = [], 0
            self.chat_submit(text, now)
            return self.want_quit
        elif key in ("\x7f", "\b", curses.KEY_BACKSPACE):
            if self.cpos > 0:
                del self.cbuf[self.cpos - 1]
                self.cpos -= 1
        elif key == curses.KEY_DC:
            if self.cpos < len(self.cbuf):
                del self.cbuf[self.cpos]
        elif key == curses.KEY_LEFT:
            self.cpos = max(0, self.cpos - 1)
        elif key == curses.KEY_RIGHT:
            self.cpos = min(len(self.cbuf), self.cpos + 1)
        elif key == curses.KEY_HOME:
            self.cpos = 0
        elif key == curses.KEY_END:
            self.cpos = len(self.cbuf)
        elif key == "\x15":
            self.cbuf, self.cpos = [], 0
        elif key == curses.KEY_UP:
            if self.chat_hist and self.hist_i > 0:
                self.hist_i -= 1
                self.cbuf = list(self.chat_hist[self.hist_i])
                self.cpos = len(self.cbuf)
        elif key == curses.KEY_DOWN:
            if self.hist_i < len(self.chat_hist) - 1:
                self.hist_i += 1
                self.cbuf = list(self.chat_hist[self.hist_i])
            else:
                self.hist_i, self.cbuf = len(self.chat_hist), []
            self.cpos = len(self.cbuf)
        elif key == curses.KEY_PPAGE:
            self.chat_scroll += 5
        elif key == curses.KEY_NPAGE:
            self.chat_scroll = max(0, self.chat_scroll - 5)
        elif key == "\t":
            text = "".join(self.cbuf)
            if text.startswith("/") and " " not in text:
                ms = [c for c in self.CHAT_COMMANDS if c.startswith(text)]
                if ms:
                    nxt = ms[(ms.index(text) + 1) % len(ms)] if text in ms and len(ms) > 1 else ms[0]
                    self.cbuf, self.cpos = list(nxt), len(nxt)
        elif isinstance(key, str) and key.isprintable():
            self.cbuf.insert(self.cpos, key)
            self.cpos += 1
        return False

    def chat_rows(self, now, bmax, x0, w):
        """Conversation -> lignes d'écran [(x, texte, attr), …] (bulles arrondies)."""
        A, rows = self.A, []

        def bubble(text, who, shown=None):
            lines = []
            for para in text.split("\n"):
                ind = "   " if para.startswith("/") else ""
                lines.extend(textwrap.wrap(para, bmax - 4, subsequent_indent=ind,
                                           break_long_words=True) or [""])
            inner = max(len(ln) for ln in lines)
            wid = inner + 4
            x = x0 + 2 if who == "bot" else x0 + w - 2 - wid
            bd, tc = (A[4], A[8]) if who == "bot" else (A[5], A[6])
            rows.append([(x, "╭" + "─" * (wid - 2) + "╮", bd)])
            budget = shown
            for ln in lines:
                if budget is None:
                    part = ln
                else:
                    part = ln[:max(0, budget)]
                    budget -= len(ln)
                rows.append([(x, "│ ", bd), (x + 2, part.ljust(inner), tc),
                             (x + 2 + inner, " │", bd)])
            rows.append([(x, "╰" + "─" * (wid - 2) + "╯", bd)])
            rows.append([])

        last = len(self.chat_log) - 1
        for i, m in enumerate(self.chat_log):
            shown = None
            if m["who"] == "bot" and i == last and not self.eco:   # effet « machine à écrire »
                n = len(m["text"])
                c = int((now - m["t0"]) * max(260.0, n / 0.9))
                if c < n:
                    shown = c
            bubble(m["text"], m["who"], shown)
        if self.chat_pending:                                   # indicateur « écrit… »
            ph = int(now * 4) % 3
            bubble(" ".join("●" if j == ph else "○" for j in range(3)), "bot")
        return rows

    def draw_chat(self, scr, now, x0, cols, rows):
        A = self.A
        w = cols - x0
        if w < 16:
            return None
        bottom = rows - 2
        for p_ in [q for q in list(self.chat_pending) if q[0] <= now]:   # réponses prêtes
            try:
                self.chat_pending.remove(p_)
            except ValueError:
                continue
            self.chat_log.append({"who": "bot", "text": p_[1], "t0": now})
            self.chat_scroll = 0
        # --- cadre, titre, puces de commandes
        title = f" ⚙ {tx('chat_title')} "
        put(scr, 0, x0, "╭─" + title + "─" * max(0, w - 3 - len(title)) + "╮", A[5])
        for y in range(1, bottom):
            put(scr, y, x0, "│", A[4])
            put(scr, y, x0 + w - 1, "│", A[4])
        put(scr, bottom, x0, "╰" + "─" * (w - 2) + "╯", A[4])
        put(scr, 1, x0 + 2, fit(tx("chat_sub"), w - 4), A[7])
        self.chat_hits = []
        mcx, mcy = self.mouse if self.mouse else (-1, -1)
        cxp = x0 + 2
        for cmd in ("/help", "/mode", "/lang", "/config", "/exit"):
            label = f" {cmd} "
            if cxp + len(label) > x0 + w - 2:
                break
            hot = mcy == 2 and cxp <= mcx < cxp + len(label)
            put(scr, 2, cxp, label, (A[6] if hot else A[4]) | curses.A_REVERSE)
            self.chat_hits.append((cxp, cxp + len(label), 2, cmd))
            cxp += len(label) + 1
        put(scr, 3, x0 + 1, "─" * (w - 2), A[1])
        # --- messages (alignés en bas, défilables)
        ah = max(1, bottom - 7)
        lines = self.chat_rows(now, max(12, min(w - 6, 46)), x0, w)
        while lines and not lines[-1]:
            lines.pop()
        total = len(lines)
        self.chat_scroll = max(0, min(self.chat_scroll, max(0, total - ah)))
        end = total - self.chat_scroll
        start = max(0, end - ah)
        vis = lines[start:end]
        y = 4 + max(0, ah - len(vis))
        for row in vis:
            for x, txt, at in row:
                put(scr, y, x, txt, at)
            y += 1
        if start > 0:
            put(scr, 4, x0 + w - 2, "↑", A[7])
        if self.chat_scroll > 0:
            put(scr, 4 + ah - 1, x0 + w - 2, "↓", A[7])
        # --- zone de saisie « Écrire… »
        by = bottom - 3
        put(scr, by, x0 + 2, "╭" + "─" * (w - 6) + "╮", A[5])
        put(scr, by + 1, x0 + 2, "│", A[5])
        put(scr, by + 1, x0 + w - 3, "│", A[5])
        put(scr, by + 2, x0 + 2, "╰" + "─" * (w - 6) + "╯", A[5])
        put(scr, by + 1, x0 + 4, "❯", A[6])
        inner = w - 10
        text = "".join(self.cbuf)
        scroll = max(0, self.cpos - inner + 1)
        if text:
            put(scr, by + 1, x0 + 6, text[scroll:scroll + inner], A[8])
        else:
            put(scr, by + 1, x0 + 6, fit(tx("chat_placeholder"), inner), A[7])
        return (by + 1, x0 + 6 + self.cpos - scroll)

    def activate(self, target, now):
        """Lien (actu) -> ouvre la page ; sinon -> lance une recherche."""
        if target.startswith(("http://", "https://")):
            open_url(target)
            self.msg, self.msg_until = tx("msg_article"), now + 3
            self.pulse_t0, self.boost = now, self.boost + 1.5
        else:
            self.search(target, now)

    def want_eco(self):
        p = self.cfg.get("perf", "auto")
        if p == "on":
            return True
        if p == "off":
            return False
        return self.widget or bool(os.environ.get("SSH_CONNECTION"))

    def watch_perf(self, spent, now):
        """Mode auto : passe en économie si les images mettent trop longtemps à se dessiner."""
        self.ft = spent if self.ft is None else self.ft * 0.9 + spent * 0.1
        if self.cfg.get("perf", "auto") == "auto" and not self.eco:
            self.slow = self.slow + 1 if self.ft > 0.045 else 0
            if self.slow > 45:
                self.eco = True
                self.msg, self.msg_until = tx("msg_eco_auto"), now + 4

    def cycle_mode(self, now):
        m = MODES[(MODES.index(self.trends.mode) + 1) % len(MODES)]
        self.set_mode(m, now)
        self.msg, self.msg_until = tx("msg_mode", m=m), now + 3

    def set_mode(self, m, now):
        self.trends.set_mode(m)
        self.cfg["mode"] = m
        try:
            save_config(self.cfg)
        except OSError:
            pass
        self.vis = [0.0] * MAX_TRENDS
        self.pulse_t0 = now

    def on_click(self, mx, my, now):
        if self.splash:
            self.want_quit = True
            return
        if self.chat_p > 0.5:
            for x0, x1, y, cmd in self.chat_hits:
                if y == my and x0 <= mx < x1:
                    self.chat_submit(cmd, now)
                    return
        if self.gear and my == 0 and self.gear[0] <= mx <= self.gear[0] + 1:
            self.chat_close(now) if self.chat else self.chat_open(now)
            return
        g = self.geom
        if not g:
            return
        for c0, c1, row, q, ex, ey, k in g["labels"]:
            if c0 <= mx < c1 and row <= my <= row + 1:
                self.flash[k] = now + 0.5
                self.ripples.append([ex, ey, now])
                self.activate(q, now)
                return
        dx, dy = mx * 2 + 1 - g["cx"], my * 4 + 2 - g["cy"]
        if dx * dx + dy * dy <= g["r"] ** 2 and my < g["ch"]:
            open_url(self.home_url)
            self.msg, self.msg_until = tx("msg_browser"), now + 3
            self.pulse_t0, self.boost = now, self.boost + 1.5
            self.ripples.append([mx * 2 + 1, my * 4 + 2, now])

    def handle_input(self, scr, now, wait_ms):
        scr.timeout(wait_ms)
        while True:
            try:
                key = scr.get_wch()
            except curses.error:
                return False
            scr.timeout(0)
            if self.minimal and key not in (curses.KEY_MOUSE, curses.KEY_RESIZE):
                if self.splash:
                    return True                      # n'importe quelle touche ferme l'écran d'accueil
                continue
            if key == curses.KEY_RESIZE:
                curses.update_lines_cols()
            elif key == curses.KEY_MOUSE:
                try:
                    _, mx, my, _, bs = curses.getmouse()
                except curses.error:
                    continue
                self.mouse = (mx, my)
                if self.chat_p > 0.5:
                    if bs & getattr(curses, "BUTTON4_PRESSED", 0):
                        self.chat_scroll += 3
                    elif bs & getattr(curses, "BUTTON5_PRESSED", 0):
                        self.chat_scroll = max(0, self.chat_scroll - 3)
                if bs & (curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED) \
                        and now - self.last_click > 0.25:
                    self.last_click = now
                    self.on_click(mx, my, now)
            elif self.chat:
                if self.chat_key(key, now):
                    return True
            elif key in ("\n", "\r", curses.KEY_ENTER):
                self.search("".join(self.buf), now)
                self.buf, self.pos = [], 0
            elif key == "/" and not self.buf:
                self.chat_open(now, "/")
            elif key == curses.KEY_F2:
                self.chat_open(now)
            elif key == "\t":
                self.cycle_mode(now)
            elif key == "\x1b":
                return True
            elif key in ("\x7f", "\b", curses.KEY_BACKSPACE):
                if self.pos > 0:
                    del self.buf[self.pos - 1]
                    self.pos -= 1
            elif key == curses.KEY_DC:
                if self.pos < len(self.buf):
                    del self.buf[self.pos]
            elif key == curses.KEY_LEFT:
                self.pos = max(0, self.pos - 1)
            elif key == curses.KEY_RIGHT:
                self.pos = min(len(self.buf), self.pos + 1)
            elif key == curses.KEY_HOME:
                self.pos = 0
            elif key == curses.KEY_END:
                self.pos = len(self.buf)
            elif key == "\x15":
                self.buf, self.pos = [], 0
            elif isinstance(key, str) and key.isprintable():
                self.buf.insert(self.pos, key)
                self.pos += 1

    # ---------- orbite ----------
    @staticmethod
    def orbit(th, f, theta, phi):
        x = f * np.cos(th) * math.cos(theta)
        y = f * np.cos(th) * math.sin(theta)
        z = f * np.sin(th)
        xx = x * math.cos(phi) + z * math.sin(phi)
        zz = -x * math.sin(phi) + z * math.cos(phi)
        return xx, y * CT - zz * ST, y * ST + zz * CT

    # ---------- rendu ----------
    def frame(self, scr, now, t, dt):
        A = self.A
        rows, cols = scr.getmaxyx()
        eco = self.eco
        if eco:
            t += 10.0                                     # pas d'intro ni d'effets progressifs
        ch, cw = rows - (0 if self.minimal else 4), cols
        scr.erase()
        tgt_p = 1.0 if self.chat else 0.0                 # animation du panneau de chat
        self.chat_p += (tgt_p - self.chat_p) * (1.0 if eco else min(1.0, dt * 9))
        if abs(tgt_p - self.chat_p) < 0.004:
            self.chat_p = tgt_p
        pw = min(64, max(40, int(cols * 0.44))) if cols >= 100 else cols
        left_cols = cols - int(pw * self.chat_p)          # largeur de la zone du globe
        H, W = ch * 4, cw * 2
        cx, cy = float(left_cols), H / 2.0
        side = min(32, max(12, cols // 4))
        lab = 1.0 - self.chat_p
        r0 = min((H / 2 - 8) / 1.25, left_cols - side * 2 * lab - 8, 115)
        if ch < 12 or cols < 50 or (self.chat_p == 0 and (cols < 64 or r0 < 20)):
            put(scr, 0, 0, tx("too_small"), A[6])
            self.geom = None
            return
        r0 = max(r0, 2.0)
        w = self.w.eco if eco else self.w

        # --- lancement / impulsions ---
        s = ease_out(min(1.0, t / 1.8))
        age = now - self.pulse_t0
        osc = math.exp(-age * 5) * math.sin(age * 24) * 0.045 if age < 1.5 else 0.0
        r_base = max(2.0, r0 * s * (1 + osc))

        hover_globe, mxd, myd = False, None, None
        hov_prev = -1
        if self.mouse:
            mcx, mcy = self.mouse
            mxd, myd = mcx * 2 + 1, mcy * 4 + 2
            rh = r_base * max(1.0, self.zoom)
            hover_globe = mcy < ch and (mxd - cx) ** 2 + (myd - cy) ** 2 <= rh * rh
            if self.geom:
                for c0_, c1_, row_, _q, _x, _y, k_ in self.geom["labels"]:
                    if c0_ <= mcx < c1_ and row_ <= mcy <= row_ + 1:
                        hov_prev = k_
        ztarget = 1.10 if hover_globe else (1.06 if hov_prev >= 0 else 1.0)
        self.zoom += (ztarget - self.zoom) * (1.0 if eco else min(1.0, dt * 9))
        r = r_base * self.zoom                       # rayon affiché (avec zoom)

        base_spin = 0.18 if eco else 0.30
        self.spin += ((0.10 if hover_globe else base_spin) - self.spin) * min(1.0, dt * 4)
        self.boost *= math.exp(-dt * 1.6)
        self.angle += (self.spin + self.boost + 7 * (1 - s) ** 2) * dt
        a = self.angle
        ca, sa = math.cos(a), math.sin(a)

        lev = np.zeros((H, W), np.uint8)

        # --- globe : points terre / océan / graticule ---
        x1 = w.X * ca + w.Z * sa
        z1 = w.Z * ca - w.X * sa
        y2 = w.Y * CT - z1 * ST
        z2 = w.Y * ST + z1 * CT
        m = (z2 > 0) & (w.APP < s)
        zz = z2[m]
        px = (cx + x1[m] * r).astype(np.int32)
        py = (cy - y2[m] * r).astype(np.int32)
        land = w.LAND[m]
        lv = np.where(land, np.where(zz < 0.3, 5, np.where(zz < 0.7, 4, 3)),
                      np.where(zz < 0.35, 2, 1)).astype(np.uint8)
        if s > 0.98 and not eco:                       # balayage radar
            scan = (-t * 55.0) % 360 - 180
            d = (w.LON[m] - scan + 180) % 360 - 180
            lv[np.abs(d) < 1.6] = 6
        if hover_globe:                                # loupe lumineuse
            d2 = (px - mxd) ** 2 + (py - myd) ** 2
            outer = d2 < 196
            lv[outer] = np.maximum(lv[outer], 5)
            lv[d2 < 64] = 6
        ib = (px >= 0) & (px < W) & (py >= 0) & (py < H)
        px, py, lv = px[ib], py[ib], lv[ib]
        order = np.argsort(lv, kind="stable")
        lev[py[order], px[order]] = lv[order]

        # --- anneau lumineux + graduations ---
        ar = np.linspace(0, math.tau, max(60, int(math.tau * r * 0.9)), endpoint=False)
        plot(lev, np.rint(cx + r * np.cos(ar)).astype(int),
             np.rint(cy - r * np.sin(ar)).astype(int), 5)
        a2 = ar[::2]
        plot(lev, np.rint(cx + (r + 2.5) * np.cos(a2)).astype(int),
             np.rint(cy - (r + 2.5) * np.sin(a2)).astype(int), 2)
        ks = np.arange(72)
        angs = np.radians(ks * 5) + t * 0.14
        for sel, ln, lvl in ((ks % 6 != 0, 3, 3), (ks % 6 == 0, 7, 5)):
            rr = r * 1.07 + np.arange(ln + 1)
            xs = np.rint(cx + np.outer(np.cos(angs[sel]), rr)).astype(int).ravel()
            ys = np.rint(cy - np.outer(np.sin(angs[sel]), rr)).astype(int).ravel()
            plot(lev, xs, ys, lvl)

        # --- particules (halo) ---
        if not eco:
            rad = r + 3 + w.HD * (1 + 0.25 * np.sin(t * 1.3 + w.HP)) * (1 + 10 * (1 - s))
            kp = np.random.random(rad.size) < 0.55
            plot(lev, np.rint(cx + rad[kp] * np.cos(w.HA[kp])).astype(int),
                 np.rint(cy - rad[kp] * np.sin(w.HA[kp])).astype(int), 2)

        # --- anneaux orbitaux + satellites ---
        if s > 0.6 and not eco:
            th = np.linspace(0, math.tau, 260, endpoint=False)
            for idx, (f, theta, spd) in enumerate(((1.30, 0.35, 0.25), (1.48, -0.6, -0.18))):
                phi = t * spd
                xx, yy, zr = self.orbit(th, f, theta, phi)
                sx = np.rint(cx + xx * r).astype(int)
                sy = np.rint(cy - yy * r).astype(int)
                front = zr > 0
                back = (~front) & (xx * xx + yy * yy > 1.0)
                plot(lev, sx[front], sy[front], 3)
                plot(lev, sx[back], sy[back], 1)
                sgn = 1 if spd > 0 else -1
                ths = t * (1.1 + 0.3 * idx) * sgn + idx * math.pi - np.arange(12) * 0.06 * sgn
                xx, yy, zr = self.orbit(ths, f, theta, phi)
                for j in range(12):
                    if not (zr[j] > 0 or xx[j] ** 2 + yy[j] ** 2 > 1.0):
                        continue
                    lvl = 6 if j < 2 else 5 if j < 5 else 3 if j < 9 else 2
                    if j == 0:
                        block(lev, cx + xx[j] * r, cy - yy[j] * r, 6)
                    else:
                        plot(lev, np.array([int(round(cx + xx[j] * r))]),
                             np.array([int(round(cy - yy[j] * r))]), lvl)

        # --- tendances : marqueurs sur le globe + étiquettes en orbite ---
        items = self.trends.items[:MAX_TRENDS]
        n = len(items)
        labels, cand = [], []
        if n:
            cv = w.city[:n]
            mx1 = cv[:, 0] * ca + cv[:, 2] * sa
            mz1 = cv[:, 2] * ca - cv[:, 0] * sa
            my2 = cv[:, 1] * CT - mz1 * ST
            mz2 = cv[:, 1] * ST + mz1 * CT
            for k in range(n):
                pxm, pym = cx + mx1[k] * r, cy - my2[k] * r
                on_front = mz2[k] > 0.10 and s > 0.95 and t > 1.2 + 0.1 * k
                hot = self.flash.get(k, 0) > now
                if on_front:
                    big = k == hov_prev
                    pulse = 3 + 2 * (0.5 + 0.5 * math.sin(t * 3 + k)) + (3 if big else 0)
                    cxs, cys = circle(pxm, pym, pulse, 0.8)
                    plot(lev, cxs, cys, 6 if big else 5)
                    block(lev, pxm, pym, 6, 2 if big else 1)
                vx = pxm - cx
                want = (on_front and abs(vx) > 0.32 * r and t > 1.5 + 0.15 * k
                        and self.chat_p < 0.02)
                step = dt * (2.5 if want else 4.0)
                tgt = 1.0 if want else 0.0
                self.vis[k] += max(-step, min(step, tgt - self.vis[k]))
                if self.vis[k] <= 0.01:
                    continue
                vy = pym - cy
                dist = max(1.0, math.hypot(vx, vy))
                ux, uy = vx / dist, vy / dist
                sd = 1 if vx >= 0 else -1
                R1 = r_base * 1.12 + 8
                p1x = cx + ux * R1
                p1y = min(H - 6, max(10, cy + uy * R1))
                cand.append(dict(k=k, v=self.vis[k], sd=sd, p0=(pxm, pym),
                                 p1=(p1x, p1y), row=int(p1y // 4), hot=hot))
            for sd in (-1, 1):                         # anti-chevauchement
                grp = sorted([c for c in cand if c["sd"] == sd], key=lambda c: c["row"])
                last = -99
                for c in grp:
                    c["row"] = max(c["row"], last + 3)
                    last = c["row"]
                if grp and grp[-1]["row"] > ch - 3:
                    sh = grp[-1]["row"] - (ch - 3)
                    for c in grp:
                        c["row"] = max(2, c["row"] - sh)

            mcx_, mcy_ = self.mouse if self.mouse else (-1, -1)
            for c in cand:
                k, v, sd = c["k"], c["v"], c["sd"]
                name, traffic, kind, target = items[k]
                p2x = c["p1"][0] + sd * 14
                row = c["row"]
                col_end = int(p2x // 2)
                full = f"{k + 1:02d}{GLYPH.get(kind, '▸')} {name}"
                if sd > 0:
                    maxw = max(6, min(30, cols - (col_end + 2) - 1))
                else:
                    maxw = max(6, min(30, col_end - 2))
                txt = fit(full, maxw)
                wd = cwidth(txt)
                c0 = col_end + 2 if sd > 0 else max(0, col_end - 2 - wd)
                hover = c0 <= mcx_ < c0 + wd and row <= mcy_ <= row + 1
                c.update(txt=txt, wd=wd, c0=c0, traffic=traffic,
                         hover=hover, ex=p2x, ey=row * 4 + 2)
                lvl = 6 if (hover or c["hot"]) else 4
                p0, p1 = c["p0"], c["p1"]
                sx0, sy0 = line(p0[0], p0[1], p1[0], p1[1])
                sx1, sy1 = line(p1[0], p1[1], p2x, c["ey"])
                xs, ys = np.concatenate([sx0, sx1]), np.concatenate([sy0, sy1])
                cut = max(1, int(len(xs) * v))
                plot(lev, xs[:cut], ys[:cut], lvl)
                if hover:
                    plot(lev, xs[:cut], ys[:cut] + 1, lvl)
                if v > 0.9:
                    block(lev, p2x, c["ey"], 6 if lvl == 6 else 5)
                if v > 0.6:
                    labels.append((c0, c0 + wd, row, target or name, p2x, c["ey"], k))

        # --- ondes de choc (clics) ---
        alive = []
        for rp in ([] if eco else self.ripples):
            ag = now - rp[2]
            if ag > 1.1:
                continue
            alive.append(rp)
            R = ag * 170
            lvl = 6 if ag < 0.25 else 5 if ag < 0.5 else 4 if ag < 0.8 else 2
            xs, ys = circle(rp[0], rp[1], max(1.0, R))
            plot(lev, xs, ys, lvl)
            if R > 12:
                xs, ys = circle(rp[0], rp[1], R * 0.72, 1.6)
                plot(lev, xs, ys, 3)
        self.ripples = alive

        self.geom = dict(cx=cx, cy=cy, r=r_base * max(1.0, self.zoom), ch=ch, labels=labels)

        # --- canvas braille -> écran ---
        v4 = lev.reshape(ch, 4, cw, 2)
        mask = np.zeros((ch, cw), np.uint16)
        for rr in range(4):
            for cc in range(2):
                mask |= (v4[:, rr, :, cc] > 0).astype(np.uint16) * BIT[rr][cc]
        level = v4.max(axis=(1, 3))
        ml, ll = mask.tolist(), level.tolist()
        for j in range(ch):
            mrow, lrow = ml[j], ll[j]
            i = 0
            while i < left_cols:
                if not mrow[i]:
                    i += 1
                    continue
                L, k2, chars = lrow[i], i, []
                while k2 < left_cols and mrow[k2] and lrow[k2] == L:
                    chars.append(chr(0x2800 + mrow[k2]))
                    k2 += 1
                put(scr, j, i, "".join(chars), A[L])
                i = k2

        # --- textes des étiquettes ---
        for c in cand:
            if c["v"] <= 0.6:
                continue
            v, sd, txt = c["v"], c["sd"], c["txt"]
            nshow = min(len(txt), math.ceil(len(txt) * min(1.0, (v - 0.6) / 0.4)))
            attr = (A[6] | curses.A_UNDERLINE) if (c["hover"] or c["hot"]) else A[8]
            if sd > 0:
                put(scr, c["row"], c["c0"], txt[:nshow], attr)
            else:
                put(scr, c["row"], c["c0"] + len(txt) - nshow, txt[len(txt) - nshow:], attr)
            if v > 0.95 and c["traffic"]:
                put(scr, c["row"] + 1, c["c0"], fit(f"↗ {c['traffic']}", max(6, c["wd"])), A[7])

        # --- HUD ---
        self.gear = None
        if left_cols >= 30 and not self.minimal:
            title = "◢ SEARCH // GLOBE"
            put(scr, 0, 1, title[: int(t * 24)], A[5])
            if items:
                up = time.strftime("%H:%M", time.localtime(self.trends.updated or time.time()))
                put(scr, 1, 1, fit(f"{self.trends.header()} · {tx('updated')} {up}",
                                   left_cols - 22)[: int(t * 36)], A[7])
            else:
                sp = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[int(t * 10) % 10]
                put(scr, 1, 1, f"{sp} {tx(self.trends.status)}"[: left_cols - 2], A[7])
            clock = time.strftime("%H:%M:%S")
            cxk = left_cols - len(clock) - 2
            put(scr, 0, cxk, clock, A[5])
            gx = cxk - 3                                   # bouton ⚙ (paramètres)
            hot = bool(self.mouse) and self.mouse[1] == 0 and gx <= self.mouse[0] <= gx + 1
            put(scr, 0, gx, "⚙", A[6] if (hot or self.chat) else A[7])
            self.gear = (gx, 0)

        # --- barre de recherche ---
        bw = min(cols - 8, 70)
        bx, by = (cols - bw) // 2, rows - 4
        rev = ease_out(max(0.0, min(1.0, (t - 1.0) / 0.8)))
        wv = int(bw * rev)
        cursor = None
        if wv >= 6 and self.chat_p == 0 and not self.minimal:
            x0 = bx + (bw - wv) // 2
            top = list("╭" + "─" * (wv - 2) + "╮")
            p = int((t * 28) % wv)
            for q in range(max(1, p), min(wv - 1, p + 8)):
                top[q] = "━"
            put(scr, by, x0, "".join(top), A[5])
            put(scr, by + 2, x0, "╰" + "─" * (wv - 2) + "╯", A[4])
            if rev >= 1.0:
                put(scr, by + 1, bx, "│", A[5])
                put(scr, by + 1, bx + bw - 1, "│", A[5])
                put(scr, by + 1, bx + 2, "❯", A[6])
                inner = bw - 6
                text = "".join(self.buf)
                scroll = max(0, self.pos - inner + 1)
                if text:
                    put(scr, by + 1, bx + 4, text[scroll:scroll + inner], A[8])
                else:
                    put(scr, by + 1, bx + 4, tx("placeholder")[:inner], A[7])
                cursor = (by + 1, bx + 4 + self.pos - scroll)

        # --- ligne d'aide ---
        hint, hattr = tx("hint_main"), A[7]
        if t < 1.8:
            hint, hattr = tx("hint_boot"), A[5]
        if hover_globe:
            xs_, ys_ = (mxd - cx) / r, (cy - myd) / r
            zs = math.sqrt(max(0.0, 1 - xs_ * xs_ - ys_ * ys_))
            yy = ys_ * CT + zs * ST
            z1_ = -ys_ * ST + zs * CT
            xw, zw = xs_ * ca - z1_ * sa, xs_ * sa + z1_ * ca
            la = math.degrees(math.asin(max(-1.0, min(1.0, yy))))
            lo = math.degrees(math.atan2(xw, zw))
            hint = tx("hover_globe",
                      lat=f"{abs(la):05.2f}°{tx('dir_n' if la >= 0 else 'dir_s')}",
                      lon=f"{abs(lo):06.2f}°{tx('dir_e' if lo >= 0 else 'dir_w')}")
            hattr = A[5]
        for c in cand:
            if c.get("hover"):
                it_ = items[c['k']]
                hint = tx("hover_article") if it_[3] else tx("hover_search", q=it_[0])
                hattr = A[6]
        if self.chat_p > 0.5:
            hint, hattr = tx("hint_chat"), A[7]
        if now < self.msg_until:
            hint, hattr = self.msg, A[6]
        hw = cols if left_cols < 40 else left_cols
        if not self.minimal:
            put(scr, rows - 1, max(0, (hw - cwidth(hint)) // 2), fit(hint, hw - 1), hattr)

        if self.chat_p > 0.01:
            cursor = self.draw_chat(scr, now, left_cols, cols, rows)
        if cursor:
            try:
                scr.move(*cursor)
            except curses.error:
                pass

    def run(self, scr):
        curses.curs_set(0 if self.minimal else 1)
        curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
        curses.mouseinterval(0)
        mouse_motion(True)                            # active le survol
        scr.keypad(True)
        self.A = init_colors(self.cfg.get("theme", "cyan"))
        self.t0 = self.last = time.monotonic()
        self.trends.refresh()
        try:
            while True:
                fs = time.monotonic()
                t, dt = fs - self.t0, min(0.2 if self.eco else 0.1, fs - self.last)
                self.last = fs
                if time.time() - self.trends.last_refresh > 600:
                    self.trends.refresh(force=True)
                self.frame(scr, fs, t, dt)
                scr.refresh()
                spent = time.monotonic() - fs
                self.watch_perf(spent, fs)
                wait = max(1, int(((0.083 if self.eco else 0.033) - spent) * 1000))
                if self.handle_input(scr, time.monotonic(), wait) or self.want_quit:
                    return
                if self.splash and fs - self.t0 > self.splash:
                    return
        finally:
            mouse_motion(False)


# --------------------------------------------------------------------------
#  Réglages partagés (CLI + chat), assistant de premier lancement, commandes
# --------------------------------------------------------------------------
def ask(prompt, default=""):
    try:
        ans = input(prompt).strip()
    except EOFError:
        return default
    return ans or default


def norm_mode(v):
    v = str(v).strip().lower()
    v = {"mixte": "mix", "personnalise": "perso", "personnalisé": "perso",
         "personnalisées": "perso", "default": "base", "defaut": "base"}.get(v, v)
    if v not in MODES:
        raise argparse.ArgumentTypeError(tx("err_mode"))
    return v


def norm_perf(v):
    v = str(v).strip().lower()
    v = {"eco": "on", "1": "on", "true": "on", "oui": "on", "normal": "off", "0": "off",
         "false": "off", "non": "off"}.get(v, v)
    if v not in ("on", "off", "auto"):
        raise argparse.ArgumentTypeError(tx("err_perf"))
    return v


def perf_text(p):
    return {"on": tx("word_on"), "off": tx("word_off")}.get(p) or tx("perf_auto")


def norm_lang(v):
    v = str(v).strip().lower()
    return LANG_ALIASES.get(v, v)


def apply_setting(cfg, key, raw):
    """Valide et applique un réglage (utilisé par `search set` et par le chat)."""
    v = str(raw).strip()
    try:
        if key == "mode":
            v = norm_mode(v)
        elif key == "geo":
            if not (len(v) == 2 and v.isalpha()):
                raise ValueError(tx("err_geo"))
            v = v.upper()
        elif key == "engine":
            v = v.lower()
            if v not in ENGINES:
                raise ValueError(tx("err_engine", l=", ".join(sorted(ENGINES))))
        elif key == "browser":
            v = v.lower()
            if v != "auto" and v not in BROWSER_NAMES:
                raise ValueError("auto, " + ", ".join(BROWSER_NAMES))
        elif key == "theme":
            v = v.lower()
            if v not in THEMES:
                raise ValueError(tx("err_theme", l=", ".join(THEMES)))
        elif key == "perf":
            v = norm_perf(v)
        elif key == "lang":
            v = norm_lang(v)
            if v != "auto" and not (len(v) == 2 and v.isalpha()):
                raise ValueError(tx("err_lang"))
        else:
            lo, hi = {"history_days": (1, 3650), "topics": (1, 5)}.get(key, (1, MAX_TRENDS))
            if not v.isdigit():
                raise ValueError(tx("err_int"))
            v = int(v)
            if not lo <= v <= hi:
                raise ValueError(tx("err_range", lo=lo, hi=hi))
    except argparse.ArgumentTypeError as e:
        raise ValueError(str(e))
    cfg[key] = v
    return v


def exclude_action(cfg, action, word):
    """-> (message, modifié ?)"""
    w = (word or "").strip().lower()
    if action == "list":
        return ("\n".join(cfg["exclude"]) or tx("exc_empty")), False
    if action == "clear":
        cfg["exclude"] = []
        return tx("exc_cleared"), True
    if action in ("add", "remove"):
        if not w:
            return tx("exc_need"), False
        if action == "add":
            cfg["exclude"] = sorted(set(cfg["exclude"]) | {w})
            return tx("exc_added", w=w), True
        cfg["exclude"] = [x for x in cfg["exclude"] if x != w]
        return tx("exc_removed", w=w), True
    return "/exclude add|remove|list|clear", False


def history_report(cfg, short=False):
    files = history_files(cfg)
    if not files:
        return tx("hist_none")
    names = ", ".join(sorted({n for n, _ in files}))
    out = [tx("hist_src", s=names if short else ", ".join(
        f"{n} ({os.path.dirname(p).replace(str(Path.home()), '~')})" for n, p in files))]
    qs, _ = history_queries(cfg)
    if not qs:
        out.append(tx("hist_empty", d=cfg["history_days"]))
    else:
        out += ["", tx("hist_topics")] + [f"  • {tp}" for tp in pick_topics(qs, cfg["topics"])]
        if not short:
            out += ["", tx("hist_freq")]
            out += [f"  {n:>4}×  {q}" for q, n, _ in
                    sorted(qs, key=lambda x: (-x[1], x[0]))[:15]]
    if not short:
        out += ["", tx("hist_note")]
    return "\n".join(out)


def ask_language(cfg):
    print("\nLanguage / Langue / Idioma / Sprache / Язык / Lingua")
    for i, c in enumerate(LANGS, 1):
        print(f"  {i}) {LANG_NAMES[c]}")
    d = ui_lang(dict(cfg, lang="auto"))
    ans = ask(f"[1-{len(LANGS)}] (Enter = {LANG_NAMES[d]}) : ", "").strip().lower()
    code = None
    if ans.isdigit() and 1 <= int(ans) <= len(LANGS):
        code = LANGS[int(ans) - 1]
    elif norm_lang(ans) in LANGS:
        code = norm_lang(ans)
    cfg["lang"] = code or "auto"
    set_lang(ui_lang(cfg))


def wizard(cfg):
    ask_language(cfg)
    print(f"\n🌐  {tx('w_welcome')}\n")
    print(tx("w_q") + "\n")
    for k in ("w_opt1", "w_opt2", "w_opt3"):
        print("  " + tx(k))
    print("\n" + tx("w_priv") + "\n")
    choice = ask(tx("w_choice"), "1")
    cfg["mode"] = {"1": "base", "2": "perso", "3": "mix"}.get(choice, "base")
    if cfg["mode"] != "base":
        files = history_files(cfg)
        if files:
            print(tx("w_hist_ok", n=", ".join(sorted({n for n, _ in files}))))
        else:
            print(tx("w_hist_no"))
        print("\n" + consent_screen(cfg) + "\n")          # consentement explicite (refus par défaut)
        ok = ask(tx("consent_ask"), "n").lower() in YES_WORDS
        set_consent(cfg, ok)
        print(tx("consent_granted") if ok else tx("consent_denied"))
    geo = ask("\n" + tx("w_geo", g=cfg["geo"]), cfg["geo"]).upper()
    if len(geo) == 2 and geo.isalpha():
        cfg["geo"] = geo
    save_config(cfg)
    print("\n" + tx("w_saved", p=CONFIG_PATH))
    print("  " + tx("w_later").replace("\n", "\n  ") + "\n")
    return cfg


# --------------------------------------------------------------------------
#  Widget de bureau (façon glava), démarrage automatique, écran d'accueil du terminal
# --------------------------------------------------------------------------
WIDGET_CLASS = "search-globe-widget"
WIDGET_LOG = STATE_PATH.parent / "widget.log"
AUTOSTART = (Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
             / "autostart" / "search-globe-widget.desktop")


def self_cmd():
    return [sys.executable, os.path.realpath(__file__)]


def session_info():
    sess = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if not sess:
        sess = ("wayland" if os.environ.get("WAYLAND_DISPLAY")
                else "x11" if os.environ.get("DISPLAY") else "")
    desk = os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION") or "?"
    return sess, desk


def widget_plan(term="auto", size="100x46"):
    """-> (méthode, commande) ; globe transparent sans bordure, collé au fond du bureau."""
    sess, _ = session_info()
    try:
        cols, rows = (int(x) for x in size.lower().split("x"))
    except ValueError:
        cols, rows = 100, 46
    inner = self_cmd() + ["--widget"]
    kitty = shutil.which("kitty")
    if sess == "wayland" and term in ("auto", "kitty") and kitty:
        kitten = shutil.which("kitten")                 # Wayland : couche « fond d'écran »
        base = [kitten] if kitten else [kitty, "+kitten"]
        return "kitty-panel", base + ["panel", "--edge=background", f"--class={WIDGET_CLASS}",
                                      "-o", "background_opacity=0"] + inner
    if sess == "x11" or (sess != "wayland" and os.environ.get("DISPLAY")):
        if term in ("auto", "kitty") and kitty:
            return "x11-kitty", [kitty, "--class", WIDGET_CLASS, "-o", "background_opacity=0",
                                 "-o", "hide_window_decorations=yes",
                                 "-o", f"initial_window_width={cols}c",
                                 "-o", f"initial_window_height={rows}c",
                                 "-o", "remember_window_size=no"] + inner
        if term in ("auto", "alacritty") and shutil.which("alacritty"):
            return "x11-alacritty", ["alacritty", "--class", WIDGET_CLASS, "-o", "window.opacity=0",
                                     "-o", 'window.decorations="None"',
                                     "-o", f"window.dimensions.columns={cols}",
                                     "-o", f"window.dimensions.lines={rows}", "-e"] + inner
    return None, []


def x11_tweak(timeout=6):
    """X11 : fenêtre sous les autres, sur tous les bureaux, hors barre des tâches."""
    if not (shutil.which("xdotool") and shutil.which("wmctrl")):
        return False
    try:
        out = subprocess.run(["xdotool", "search", "--sync", "--class", WIDGET_CLASS],
                             capture_output=True, text=True, timeout=timeout).stdout.split()
    except Exception:
        return False
    ok = False
    for wid in out:
        r = subprocess.run(["wmctrl", "-i", "-r", hex(int(wid)), "-b",
                            "add,below,sticky,skip_taskbar,skip_pager"], capture_output=True)
        ok = ok or r.returncode == 0
    return ok


def stop_widgets():
    n, me = 0, os.getpid()
    for d in os.listdir("/proc"):
        if not d.isdigit() or int(d) == me:
            continue
        try:
            with open(f"/proc/{d}/cmdline", "rb") as f:
                argv = [a.decode(errors="ignore") for a in f.read().split(b"\0") if a]
        except OSError:
            continue
        if "--widget" in argv and any(os.path.basename(a) in ("search", "search-globe", "search.py")
                                      for a in argv):
            try:
                os.kill(int(d), signal.SIGTERM)
                n += 1
            except OSError:
                pass
    return n


def cmd_widget(args):
    if args.action == "stop":
        n = stop_widgets()
        print(tx("wid_stopped", n=n) if n else tx("wid_nothing"))
        return
    method, cmd = widget_plan(args.terminal, args.size)
    sess, desk = session_info()
    print(tx("wid_env", s=sess or "?", d=desk, m=method or "-"))
    if not method:
        sys.exit(tx("wid_none"))
    print(tx("wid_cmd", c=" ".join(shlex.quote(c) for c in cmd)))
    if args.dry_run:
        return
    WIDGET_LOG.parent.mkdir(parents=True, exist_ok=True)
    with WIDGET_LOG.open("w") as log:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                start_new_session=True)
    time.sleep(1.5)
    if proc.poll() is not None:                          # s'est arrêté tout de suite
        try:
            print(WIDGET_LOG.read_text(errors="replace")[-600:])
        except OSError:
            pass
        sys.exit(tx("wid_failed"))
    if method.startswith("x11") and not x11_tweak():
        print(tx("wid_tools", l="xdotool wmctrl"))
    print(tx("wid_started"))


def dq(c):
    return f'"{c}"' if " " in c else c


def cmd_autostart(action):
    _, desk = session_info()
    line = " ".join(dq(c) for c in self_cmd() + ["widget"])
    if action == "on":
        AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
        AUTOSTART.write_text("[Desktop Entry]\nType=Application\nName=search-globe widget\n"
                             f"Exec={line}\nTerminal=false\nNoDisplay=true\n"
                             "X-GNOME-Autostart-enabled=true\nX-GNOME-Autostart-Delay=5\n",
                             encoding="utf-8")
        print(tx("auto_on", p=AUTOSTART))
        low = desk.lower()
        if any(w in low for w in ("hypr", "sway", "i3", "bspwm", "river", "dwm", "niri", "qtile")):
            print(tx("auto_manual", d=desk, l=("exec-once = " if "hypr" in low else "exec ") + line))
    elif action == "off":
        try:
            AUTOSTART.unlink()
        except OSError:
            pass
        print(tx("auto_off"))
    else:
        print(tx("auto_state", s=tx("word_on") if AUTOSTART.exists() else tx("word_off")))


def shellhook(shell):
    sh = (shell or os.path.basename(os.environ.get("SHELL", "bash"))).lower()
    if sh == "fish":
        where = "~/.config/fish/config.fish"
        code = ("if status is-interactive; and not set -q SEARCH_GLOBE_SHOWN\n"
                "    set -gx SEARCH_GLOBE_SHOWN 1\n"
                "    search --splash 3\n"
                "end")
    else:
        where = "~/.zshrc" if sh == "zsh" else "~/.bashrc"
        code = ('if [[ $- == *i* && -z "$SEARCH_GLOBE_SHOWN" ]]; then\n'
                "    export SEARCH_GLOBE_SHOWN=1\n"
                "    search --splash 3\n"
                "fi")
    print(f"# {where}\n{code}")


def run_command(args, cfg):
    cmd = args.cmd
    if cmd == "setup":
        wizard(cfg)
    elif cmd == "config":
        print(tx("cfg_file", p=CONFIG_PATH) + ("" if CONFIG_PATH.exists() else "  " + tx("cfg_new")))
        for k in DEFAULTS:
            print(f"  {k:<13} {cfg[k]}")
        print("\n" + tx("cfg_mode", m=mode_text(cfg["mode"])))
    elif cmd == "history":
        print(history_report(cfg))
    elif cmd == "preview":
        tr = Trends(dict(cfg, mode="perso"))
        print(tx("prev_wait"))
        tr.busy_p = True
        tr._run_perso()
        if not tr.perso:
            print(tx("prev_none", s=tx(tr.status)))
        else:
            print(tx("prev_topics", s=", ".join(tr.topics)) + "\n")
            for t_, d_, k_, link in tr.perso:
                print(f"  {GLYPH.get(k_, '▸')} {t_}\n      {d_}" + (f"\n      {link}" if link else ""))
    elif cmd == "mousetest":
        curses.wrapper(mouse_test)
    elif cmd == "reset":
        if CONFIG_PATH.exists() and ask(tx("reset_ask", p=CONFIG_PATH), "n").lower() in YES_WORDS:
            CONFIG_PATH.unlink()
            print(tx("reset_done"))
        else:
            print(tx("reset_no"))
    elif cmd == "mode":
        cfg["mode"] = args.value
        save_config(cfg)
        print(tx("ok_mode", m=mode_text(args.value)))
    elif cmd in ("lang", "set"):
        key, raw = ("lang", args.value) if cmd == "lang" else (args.key, args.value)
        try:
            v = apply_setting(cfg, key, raw)
        except ValueError as e:
            sys.exit(f"✘ {key} : {e}")
        save_config(cfg)
        if key == "lang":
            set_lang(ui_lang(cfg))
            print(tx("ok_lang", n=LANG_NAMES.get(v) or f"{v} ({LANG_NAMES[ui_lang(cfg)]})"))
        else:
            print(f"✔ {key} = {v}")
    elif cmd == "exclude":
        msg, changed = exclude_action(cfg, args.action, args.word)
        if changed:
            save_config(cfg)
        print(msg)
    elif cmd == "theme":
        if not args.value:
            print(tx("c_themes") + " " + ", ".join(THEMES) + f"   → {cfg['theme']}")
        else:
            try:
                v = apply_setting(cfg, "theme", args.value)
            except ValueError as e:
                sys.exit(f"✘ {e}")
            save_config(cfg)
            print(tx("ok_theme", n=v))
    elif cmd == "eco":
        if args.value:
            try:
                apply_setting(cfg, "perf", args.value)
            except ValueError as e:
                sys.exit(f"✘ {e}")
            save_config(cfg)
        print(tx("ok_perf", p=perf_text(cfg["perf"])))
    elif cmd == "offline":
        v = (args.value or "").lower()
        if v == "on" or v in YES_WORDS:
            cfg["offline"] = True
        elif v in NO_WORDS:
            cfg["offline"] = False
        else:
            print(tx("offline_state", s=tx("word_on") if cfg["offline"] else tx("word_off")))
            return
        save_config(cfg)
        print(tx("ok_offline_on") if cfg["offline"] else tx("ok_offline_off"))
    elif cmd == "consent":
        act = (args.action or "status").lower()
        if act == "log":
            print(log_report(30))
        elif act in YES_WORDS:
            print(consent_screen(cfg) + "\n")
            ok = (ask(tx("consent_ask"), "n").lower() in YES_WORDS) if sys.stdin.isatty() else True
            set_consent(cfg, ok)
            save_config(cfg)
            print(tx("consent_granted") if ok else tx("consent_denied"))
        elif act in NO_WORDS:
            set_consent(cfg, False)
            save_config(cfg)
            print(tx("consent_denied"))
        else:
            print(consent_screen(cfg))
    elif cmd == "widget":
        cmd_widget(args)
    elif cmd == "autostart":
        cmd_autostart(args.action)
    elif cmd == "shellhook":
        shellhook(args.shell)


def main():
    cfg, existed = load_config()
    set_lang(ui_lang(cfg))
    ap = argparse.ArgumentParser(prog="search", description=tx("ap_desc"))
    ap.add_argument("--geo", help=tx("ap_o_geo"))
    ap.add_argument("--engine", choices=sorted(ENGINES), help=tx("ap_o_engine"))
    ap.add_argument("--mode", type=norm_mode, help=tx("ap_o_mode"))
    ap.add_argument("--lang", type=norm_lang, help=tx("ap_o_lang"))
    ap.add_argument("--theme", help=tx("ap_o_theme"))
    ap.add_argument("--eco", action="store_true", help=tx("ap_o_eco"))
    ap.add_argument("--offline", action="store_true", help=tx("ap_o_offline"))
    ap.add_argument("--splash", nargs="?", const=3.0, type=float, metavar="N",
                    help=tx("ap_o_splash"))
    ap.add_argument("--widget", action="store_true", help=tx("ap_o_widget"))
    ap.add_argument("--version", action="version", version=f"search-globe {VERSION}")
    sub = ap.add_subparsers(dest="cmd", metavar="<cmd>")
    sub.add_parser("setup", help=tx("ap_setup"))
    sub.add_parser("config", help=tx("ap_config"))
    sub.add_parser("history", help=tx("ap_history"))
    sub.add_parser("reset", help=tx("ap_reset"))
    sub.add_parser("preview", help=tx("ap_preview"))
    sub.add_parser("mousetest", help=tx("ap_mousetest"))
    p = sub.add_parser("mode", help=tx("ap_mode"))
    p.add_argument("value", type=norm_mode)
    p = sub.add_parser("lang", help=tx("ap_lang"))
    p.add_argument("value", type=norm_lang)
    p = sub.add_parser("set", help=tx("ap_set"))
    p.add_argument("key", choices=("mode", "geo", "engine", "browser", "history_days",
                                   "max_trends", "topics", "lang", "theme", "perf"))
    p.add_argument("value")
    p = sub.add_parser("exclude", help=tx("ap_exclude"))
    p.add_argument("action", choices=("add", "remove", "list", "clear"))
    p.add_argument("word", nargs="?")
    for name in ("theme", "eco", "offline"):
        p = sub.add_parser(name, help=tx("ap_" + name))
        p.add_argument("value", nargs="?")
    p = sub.add_parser("consent", help=tx("ap_consent"))
    p.add_argument("action", nargs="?", default="status")
    p = sub.add_parser("widget", help=tx("ap_widget"))
    p.add_argument("action", nargs="?", choices=("start", "stop"), default="start")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--terminal", choices=("auto", "kitty", "alacritty"), default="auto")
    p.add_argument("--size", default="100x46", metavar="COLSxROWS")
    p = sub.add_parser("autostart", help=tx("ap_autostart"))
    p.add_argument("action", nargs="?", choices=("on", "off", "status"), default="status")
    p = sub.add_parser("shellhook", help=tx("ap_shellhook"))
    p.add_argument("shell", nargs="?", choices=("fish", "bash", "zsh"))
    args = ap.parse_args()

    if args.cmd:
        run_command(args, cfg)
        return
    if (not existed and sys.stdin.isatty() and sys.stdout.isatty()
            and not (args.widget or args.splash)):
        cfg = wizard(cfg)
    for key, env in (("geo", "SEARCH_GEO"), ("engine", "SEARCH_ENGINE"),
                     ("mode", "SEARCH_MODE"), ("lang", "SEARCH_LANG")):
        if os.environ.get(env):
            cfg[key] = os.environ[env] if key == "geo" else os.environ[env].lower()
    for key in ("geo", "engine", "mode", "lang"):         # options de session (non enregistrées)
        if getattr(args, key):
            cfg[key] = getattr(args, key)
    if args.theme:
        cfg["theme"] = args.theme.lower()
    if args.eco:
        cfg["perf"] = "on"
    if args.offline:
        cfg["offline"] = True
    cfg = sanitize(cfg)
    set_lang(ui_lang(cfg))

    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")
    try:
        cells = load_land()
    except Exception as e:
        sys.exit(f"Impossible de charger la carte du monde ({e}).\n"
                 "Check your connection: it is downloaded only once.")
    world = build_world(cells)
    app = App(world, Trends(cfg), cfg, widget=args.widget, splash=args.splash or 0)
    try:
        curses.wrapper(app.run)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
