#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
search v2 : globe holographique 3D + tendances en orbite + barre de recherche.

  - Clic sur le globe        -> ouvre le navigateur par défaut
  - Clic sur une tendance    -> lance la recherche correspondante
  - Texte + Entrée           -> recherche (nouvel onglet, ou nouvelle fenêtre si fermé)
  - Survol du globe          -> ralentit, loupe lumineuse + coordonnées GPS
  - Échap / Ctrl+C           -> quitter

Dépendance : python-numpy  (sudo pacman -S python-numpy)
Usage : search [--geo FR] [--engine google|duckduckgo|brave|bing|qwant]
"""
import argparse
import curses
import json
import locale
import math
import os
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
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
    return w


# --------------------------------------------------------------------------
#  Tendances Google (RSS) en arrière-plan
# --------------------------------------------------------------------------
class Trends:
    def __init__(self, geo):
        self.geo = geo
        self.items = []
        self.status = "synchronisation des tendances…"
        self.updated = 0.0
        self.busy = False

    def refresh(self):
        if self.busy:
            return
        self.busy = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
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
                    self.items, self.status = items, "ok"
                    self.updated = time.time()
                    self.busy = False
                    return
            except Exception:
                continue
        if not self.items:
            self.status = "tendances indisponibles (hors-ligne ?)"
        self.busy = False


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


def init_colors():
    curses.start_color()
    try:
        curses.use_default_colors()
    except curses.error:
        pass
    if curses.COLORS >= 256:
        spec = {1: 24, 2: 27, 3: 33, 4: 39, 5: 51, 6: 195, 7: 244, 8: 123}
    else:
        B, C, W = curses.COLOR_BLUE, curses.COLOR_CYAN, curses.COLOR_WHITE
        spec = {1: B, 2: B, 3: B, 4: C, 5: C, 6: W, 7: W, 8: C}
    for n, c in spec.items():
        curses.init_pair(n, c, -1)
    A = {0: 0}
    for n in spec:
        A[n] = curses.color_pair(n)
    A[5] |= curses.A_BOLD
    A[6] |= curses.A_BOLD
    return A


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
    def __init__(self, world, trends, engine, geo):
        self.w = world
        self.trends = trends
        self.geo = geo
        self.home_url, self.query_url = ENGINES[engine]
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
        self.msg, self.msg_until = f"↗ recherche : {q}", now + 3
        self.pulse_t0, self.boost = now, self.boost + 2.5
        if self.geom:
            self.ripples.append([self.geom["cx"], self.geom["cy"], now])

    def on_click(self, mx, my, now):
        g = self.geom
        if not g:
            return
        for c0, c1, row, q, ex, ey, k in g["labels"]:
            if c0 <= mx < c1 and row <= my <= row + 1:
                self.flash[k] = now + 0.5
                self.ripples.append([ex, ey, now])
                self.search(q, now)
                return
        dx, dy = mx * 2 + 1 - g["cx"], my * 4 + 2 - g["cy"]
        if dx * dx + dy * dy <= g["r"] ** 2 and my < g["ch"]:
            open_url(self.home_url)
            self.msg, self.msg_until = "↗ ouverture du navigateur", now + 3
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
            if key == curses.KEY_RESIZE:
                curses.update_lines_cols()
            elif key == curses.KEY_MOUSE:
                try:
                    _, mx, my, _, bs = curses.getmouse()
                except curses.error:
                    continue
                self.mouse = (mx, my)
                if bs & (curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED) \
                        and now - self.last_click > 0.25:
                    self.last_click = now
                    self.on_click(mx, my, now)
            elif key in ("\n", "\r", curses.KEY_ENTER):
                self.search("".join(self.buf), now)
                self.buf, self.pos = [], 0
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
        ch, cw = rows - 4, cols
        scr.erase()
        H, W = ch * 4, cw * 2
        cx, cy = W / 2.0, H / 2.0
        side = min(32, max(12, cols // 4))
        r0 = min(H / 2 - 8, W / 2 - side * 2 - 6, 120)
        if ch < 12 or cw < 64 or r0 < 20:
            put(scr, 0, 0, "Terminal trop petit — agrandis la fenêtre.", A[6])
            self.geom = None
            return
        w = self.w

        # --- lancement / impulsions ---
        s = ease_out(min(1.0, t / 1.8))
        age = now - self.pulse_t0
        osc = math.exp(-age * 5) * math.sin(age * 24) * 0.045 if age < 1.5 else 0.0
        r = max(2.0, r0 * s * (1 + osc))

        hover_globe, mxd, myd = False, None, None
        if self.mouse:
            mcx, mcy = self.mouse
            mxd, myd = mcx * 2 + 1, mcy * 4 + 2
            hover_globe = mcy < ch and (mxd - cx) ** 2 + (myd - cy) ** 2 <= r * r

        self.spin += ((0.10 if hover_globe else 0.30) - self.spin) * min(1.0, dt * 4)
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
        if s > 0.98:                                   # balayage radar
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
        rad = r + 3 + w.HD * (1 + 0.25 * np.sin(t * 1.3 + w.HP)) * (1 + 10 * (1 - s))
        kp = np.random.random(rad.size) < 0.55
        plot(lev, np.rint(cx + rad[kp] * np.cos(w.HA[kp])).astype(int),
             np.rint(cy - rad[kp] * np.sin(w.HA[kp])).astype(int), 2)

        # --- anneaux orbitaux + satellites ---
        if s > 0.6:
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
                    pulse = 3 + 2 * (0.5 + 0.5 * math.sin(t * 3 + k))
                    cxs, cys = circle(pxm, pym, pulse, 0.8)
                    plot(lev, cxs, cys, 5)
                    block(lev, pxm, pym, 6)
                vx = pxm - cx
                want = on_front and abs(vx) > 0.32 * r and t > 1.5 + 0.15 * k
                step = dt * (2.5 if want else 4.0)
                tgt = 1.0 if want else 0.0
                self.vis[k] += max(-step, min(step, tgt - self.vis[k]))
                if self.vis[k] <= 0.01:
                    continue
                vy = pym - cy
                dist = max(1.0, math.hypot(vx, vy))
                ux, uy = vx / dist, vy / dist
                sd = 1 if vx >= 0 else -1
                R1 = r * 1.12 + 8
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
                name, traffic = items[k]
                p2x = c["p1"][0] + sd * 14
                row = c["row"]
                col_end = int(p2x // 2)
                full = f"{k + 1:02d}▸ {name}"
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
                if v > 0.9:
                    block(lev, p2x, c["ey"], 6 if lvl == 6 else 5)
                if v > 0.6:
                    labels.append((c0, c0 + wd, row, name, p2x, c["ey"], k))

        # --- ondes de choc (clics) ---
        alive = []
        for rp in self.ripples:
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

        self.geom = dict(cx=cx, cy=cy, r=r, ch=ch, labels=labels)

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
            while i < cw:
                if not mrow[i]:
                    i += 1
                    continue
                L, k2, chars = lrow[i], i, []
                while k2 < cw and mrow[k2] and lrow[k2] == L:
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
        title = "◢ SEARCH // GLOBE"
        put(scr, 0, 1, title[: int(t * 24)], A[5])
        if self.trends.items:
            up = time.strftime("%H:%M", time.localtime(self.trends.updated))
            put(scr, 1, 1, f"TENDANCES · {self.geo} · maj {up}"[: int(t * 30)], A[7])
        else:
            sp = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[int(t * 10) % 10]
            put(scr, 1, 1, f"{sp} {self.trends.status}", A[7])
        clock = time.strftime("%H:%M:%S")
        put(scr, 0, cols - len(clock) - 2, clock, A[5])

        # --- barre de recherche ---
        bw = min(cols - 8, 70)
        bx, by = (cols - bw) // 2, rows - 4
        rev = ease_out(max(0.0, min(1.0, (t - 1.0) / 0.8)))
        wv = int(bw * rev)
        cursor = None
        if wv >= 6:
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
                    put(scr, by + 1, bx + 4, "Rechercher sur le web…"[:inner], A[7])
                cursor = (by + 1, bx + 4 + self.pos - scroll)

        # --- ligne d'aide ---
        hint, hattr = ("clic globe : navigateur · clic tendance : chercher · "
                       "Entrée : rechercher · Échap : quitter"), A[7]
        if t < 1.8:
            hint, hattr = "initialisation…", A[5]
        if hover_globe:
            xs_, ys_ = (mxd - cx) / r, (cy - myd) / r
            zs = math.sqrt(max(0.0, 1 - xs_ * xs_ - ys_ * ys_))
            yy = ys_ * CT + zs * ST
            z1_ = -ys_ * ST + zs * CT
            xw, zw = xs_ * ca - z1_ * sa, xs_ * sa + z1_ * ca
            la = math.degrees(math.asin(max(-1.0, min(1.0, yy))))
            lo = math.degrees(math.atan2(xw, zw))
            hint = (f"◉ LAT {abs(la):05.2f}°{'N' if la >= 0 else 'S'}  "
                    f"LON {abs(lo):06.2f}°{'E' if lo >= 0 else 'O'}  ·  clic : ouvrir le navigateur")
            hattr = A[5]
        for c in cand:
            if c.get("hover"):
                hint, hattr = f"↗ clic : rechercher « {items[c['k']][0]} »", A[6]
        if now < self.msg_until:
            hint, hattr = self.msg, A[6]
        put(scr, rows - 1, max(0, (cols - cwidth(hint)) // 2), hint[: cols - 1], hattr)

        if cursor:
            try:
                scr.move(*cursor)
            except curses.error:
                pass

    def run(self, scr):
        curses.curs_set(1)
        curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
        curses.mouseinterval(0)
        scr.keypad(True)
        self.A = init_colors()
        self.t0 = self.last = time.monotonic()
        self.trends.refresh()
        while True:
            fs = time.monotonic()
            t, dt = fs - self.t0, min(0.1, fs - self.last)
            self.last = fs
            if self.trends.items and time.time() - self.trends.updated > 600:
                self.trends.refresh()
            self.frame(scr, fs, t, dt)
            scr.refresh()
            wait = max(1, int((0.033 - (time.monotonic() - fs)) * 1000))
            if self.handle_input(scr, time.monotonic(), wait):
                return


def main():
    ap = argparse.ArgumentParser(prog="search")
    ap.add_argument("--geo", default=os.environ.get("SEARCH_GEO", "FR"),
                    help="pays des tendances (FR, US, BE, CH, CA…)")
    ap.add_argument("--engine", default=os.environ.get("SEARCH_ENGINE", "google"),
                    choices=sorted(ENGINES))
    args = ap.parse_args()
    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")
    try:
        cells = load_land()
    except Exception as e:
        sys.exit(f"Impossible de charger la carte du monde ({e}).\n"
                 "Vérifie ta connexion : elle n'est téléchargée qu'une seule fois.")
    world = build_world(cells)
    app = App(world, Trends(args.geo.upper()), args.engine, args.geo.upper())
    try:
        curses.wrapper(app.run)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
