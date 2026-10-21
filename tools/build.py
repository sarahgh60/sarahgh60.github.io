#!/usr/bin/env python3
"""Folio build (Python 3 standard library only).

Validates content/site.json and content/projects/*.json, renders the case pages
from templates/case.html, renders the data artifacts, fills the markers in
index.html, writes the SEO files, and checks the pages and the size budgets.

Usage:
  python3 tools/build.py                  full build
  python3 tools/build.py --check          validate only, write nothing
  python3 tools/build.py --ci --out _site the build GitHub runs on every push (see below)
  python3 tools/build.py --refresh-masters  record the current pictures in assets/img/masters.json
  python3 tools/build.py --grain          write assets/img/grain.png only
  python3 tools/build.py --offline        no network (skip the font URL check)
  python3 tools/build.py --allow-missing-images   development only
  python3 tools/build.py --content DIR    alternate content folder (site.json + projects/)
  python3 tools/build.py --root DIR       build another copy of the site

--ci (also on inside GitHub Actions) keeps the site publishable after an edit made in the GitHub
web editor: the house-style rules (lengths, word counts, the number canon, image sizes) only
warn. A problem that would break a page (a JSON syntax error, a missing field or picture, a
broken tag in index.html) still fails the build, with the file and line, and nothing is
published. --out DIR copies the publishable files into DIR.

Pictures: each picture is its master file (.jpg, .jpeg, .png or .webp, found by name), and the
page reads its pixel size from the file. The AVIF and the smaller sizes made from a master are
used only while assets/img/masters.json holds that master's sha256; a replaced picture is served
as uploaded. A full build on a Mac (sips) makes its AVIF and sizes again and records it.
The link-preview cards in assets/img/og/ are used only while masters.json holds the texts and
cover they show; otherwise a page's link preview uses its hero picture (home: the About photo).
"""
from __future__ import annotations

import argparse
import datetime
import gzip
import hashlib
import html
import json
import math
import os
import random
import re
import shutil
import struct
import subprocess
import sys
import urllib.parse
import urllib.request
import zlib
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# ----------------------------------------------------------------- constants
STAGES = {  # --stage / --stage-dark / --stage-shadow / --stage-pigment
    "bone": ("#e7dcd0", "#342c23", "#584a3b", "#af9b84"),
    "sage": ("#c1e1c6", "#1a3520", "#295935", "#6fb07d"),
    "aqua": ("#b2e2e7", "#02353a", "#005962", "#41b0bc"),
    "iris": ("#cdd6f9", "#262c47", "#414978", "#8c99dd"),
    "sand": ("#ebd3b4", "#3c2a0e", "#664610", "#c39553"),
    "clay": ("#f6cdbf", "#43251a", "#713d2a", "#d4896e"),
}
SHEETS = {  # sheet number -> (case slug, stage)
    "A-101": ("design-team", "bone"), "A-102": ("shopify-suite", "sage"),
    "A-103": ("virtual-care", "aqua"), "A-104": ("design-system", "iris"),
    "A-105": ("mobile-commerce", "sand"), "A-106": ("buildings-to-products", "clay"),
}
FILTERS = ("leadership", "commerce", "health", "saas", "mobile", "architecture")
ALTITUDE = {"manager": "Manager", "player-coach": "Player-coach", "hands-on": "Hands-on"}
ROSTER = {"DL": "Design lead", "PD": "Product designer", "UXR": "Researcher",
          "PM": "Product manager", "ENG": "Engineer", "CA": "Clinical advisor"}
DECISION_STATUS = ("shipped", "killed", "descoped")
KINDS = ("bars", "ring", "lanes", "heatgrid", "table", "brief", "cadence", "ladder")
HOME_ARTIFACTS = ("hiring-funnel", "budget-ring", "capacity-lanes", "heart-scorecard",
                  "monthly-brief", "week", "roadmap-2026", "ladder", "cadence")
CANON_KEYS = (
    "career.years", "career.digital", "team.attrition",
    "hiring.funnel", "hiring.tth", "budget.variance", "report.briefs", "ops.handoff",
    "shopify.apps", "shopify.setup", "shopify.activation", "shopify.installs", "ai.rubric",
    "health.noshows", "health.intake", "health.sus", "health.caregivers",
    "ds.colours", "ds.coverage", "ds.defects", "mc.checkout", "mc.payout", "mc.tickets",
    "arch.projects", "arch.disciplines", "arch.rfis")
FONT_URL = ("https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght,SOFT,WONK@"
            "0,9..144,300..600,100,0..1;1,9..144,300..600,100,0..1"
            "&family=Geist+Mono:wght@400;500&family=Mona+Sans:wdth,wght@75..125,400..700&display=swap")
CHROME_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36")
BUDGETS_KB = {"boot": 0.8, "main.js": 10, "hero-gl.js": 8, "home.js": 4, "hinge-gl.js": 3, "case.js": 6,
              "js-page": 25, "main.css": 30, "case.css": 12}
# JS each page type downloads (home.js and hinge-gl.js are imported by main.js / hero-gl.js on home only)
JS_PAGES = {"JS home": ("boot", "main.js", "hero-gl.js", "home.js", "hinge-gl.js"),
            "JS case": ("boot", "main.js", "case.js")}
# Responsive image variants (generated by the build with macOS sips into SIZES_DIR/<slug>/).
SIZES_DIR = "assets/img/sizes"
VARIANT_W = (1200, 1600)        # AVIF widths below the full file
JPEG_VARIANT_W = 1200           # one smaller JPEG for the <img> fallback
VARIANT_Q = {"avif": 62, "jpeg": 78}
WPM = 230                       # reading speed for the computed reading time
SIZES = {  # `sizes` per use (layout widths from case.css / main.css)
    "hero": "(min-width:1280px) 76vw, 100vw",
    "band": "(min-width:1280px) 60vw, (min-width:900px) 76vw, 100vw",
    "compare": "(min-width:1280px) 62vw, (min-width:600px) 92vw, 100vw",
    "plate": "(min-width:1024px) 34vw, 86vw",
}
STATUS_WORDS = {  # word (lower) -> class
    "ready": "ok", "on track": "ok", "done": "ok", "shipped": "ok", "pass": "ok", "live": "ok",
    "in review": "watch", "watch": "watch", "active": "watch", "in progress": "watch",
    "planned": "plan", "next": "plan",
    "gap": "risk", "at risk": "risk", "blocked": "risk", "fail": "risk", "killed": "risk",
    "descoped": "risk",
}
# Pictures: a master is found by name with any of these endings (two files for one picture: the
# most recently changed one wins).
MASTER_EXT = (".jpg", ".jpeg", ".webp", ".png")
# A second ending typed onto a hidden one (hero.jpg.jpeg) still names the picture hero.
SECOND_EXT = MASTER_EXT + (".heic", ".heif", ".gif", ".tif", ".tiff", ".bmp", ".avif")
# Picture files a browser cannot show (or that need converting first): reported, never published.
UNSUPPORTED_EXT = (".heic", ".heif", ".gif", ".tif", ".tiff", ".bmp")
SAVE_AS_JPG = "open it in Preview, choose File → Export…, set Format to JPEG, and upload that file"
BIG_UPLOAD = (1.5 * 1024 * 1024, 3000)      # bytes, px wide: a picture served as uploaded above this
OG_DIR = "assets/img/og"                    # link-preview cards, 1200×630
MANIFEST_REL = "assets/img/masters.json"   # master path -> sha256 the AVIF and sizes were made from
STUDIO_DIR = "assets/img/studio"            # paintings: AVIF sizes next to the master
AVIF_Q = 62                                 # full-size AVIF quality (the smaller sizes use VARIANT_Q)
# `sizes` for the hand-authored home pictures with width descriptors, by <picture> class
HOME_SIZES = {"hinge__painting": "(min-width:1200px) 1100px, 92vw", "canvas": "(min-width:1024px) 62vw, 92vw"}
# The files GitHub Pages serves (--out); everything else in the repository is source.
PUBLISH_FILES = ("index.html", "404.html", "robots.txt", "sitemap.xml", "llms.txt", "CNAME", ".nojekyll")
PUBLISH_DIRS = ("assets", "work")
CI = False   # --ci: house-style rules warn instead of failing (set in main)
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "source", "track", "wbr"}
MINUS = "−"


def e(s) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-") or "x"


# ------------------------------------------------------------- typography
SMART_SKIP = {"slug", "image", "before", "after", "artifact", "hex", "href", "stage", "canon", "id"}


def smart(s: str) -> str:
    """Typographer's quotes, apostrophes and spaced en dashes for rendered text."""
    if not isinstance(s, str) or not any(c in s for c in "'\"-"):
        return s
    s = re.sub(r"(?<=\w)'(?=\w)", "’", s)                       # don't, it's
    s = re.sub(r"(^|[\s(\[{“—–/-])'(?=\S)", r"\1‘", s)          # opening single
    s = s.replace("'", "’")                                     # closing, s' possessive
    s = re.sub(r'(^|[\s(\[{‘—–/-])"(?=\S)', r"\1“", s)
    s = s.replace('"', "”")
    return s.replace(" - ", " – ").replace(" -- ", " — ")


def smarten(obj, key=None):
    """Applies smart() to every string value of a parsed JSON tree (dict keys untouched)."""
    if isinstance(obj, dict):
        return {k: (v if k in SMART_SKIP else smarten(v, k)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [smarten(v, key) for v in obj]
    return smart(obj) if isinstance(obj, str) else obj


def objs(v) -> list:
    """The objects of a list (anything else in it, or a non-list, is left to the validator)."""
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def texts(v) -> list:
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


def prose_words(p: dict) -> int:
    """Words a reader actually reads on a case page (prose fields, not labels)."""
    parts = texts(p.get("tldr"))
    ch = p.get("challenge") if isinstance(p.get("challenge"), dict) else {}
    parts += [ch.get("inherited", ""), ch.get("body", "")]
    parts += texts(p.get("role_led")) + texts(p.get("role_team"))
    for pr in objs(p.get("principles")):
        parts += [pr.get("title", ""), pr.get("body", "")]
    for dc in objs(p.get("decisions")):
        parts += [dc.get(k, "") for k in ("decision", "why", "tradeoff", "risk")]
    for pr in objs(p.get("process")):
        parts += [pr.get("heading", "")] + texts(pr.get("body"))
        fig = pr.get("figure")
        parts.append(fig.get("caption", "") if isinstance(fig, dict) else "")
    for al in objs(p.get("after_launch")):
        parts += [al.get("what", ""), al.get("metric", "")]
    parts += texts(p.get("not_taken")) + texts(p.get("reflections"))
    for dp in objs(p.get("deeper")):
        parts += [dp.get("title", "")] + texts(dp.get("body"))
    return sum(nwords(x) for x in parts if isinstance(x, str))


def reading_minutes(p: dict) -> int:
    return max(1, math.ceil(prose_words(p) / WPM))


# -------------------------------------------------------------------- report
class Report:
    def __init__(self):
        self.errors, self.warnings, self.info, self.shown = [], [], [], []

    def err(self, where, field, msg, polish=False):
        """polish=True: a house-style rule, which only warns in --ci mode."""
        if polish and CI:
            self.warn(where, field, msg)
        else:
            self.errors.append((str(where), str(field), str(msg)))

    def warn(self, where, field, msg, show=False):
        """show=True: also a yellow note on the GitHub run page (an upload that did nothing, or
        one that needs a smaller copy), not only a line in the log."""
        self.warnings.append((str(where), str(field), str(msg)))
        if show:
            self.shown.append((str(where), str(field), str(msg)))

    def note(self, label, text):
        self.info.append((label, text))


R = Report()


# ------------------------------------------------------------- type helpers
def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def is_str(v):
    return isinstance(v, str)


def nwords(s: str) -> int:
    return len(str(s).split())


TAG_RE = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")


class V:
    """Small validator bound to one file. A missing field or a wrong type breaks the page and is
    always an error; lengths, counts and ranges are house style (polish), which --ci only warns."""

    def __init__(self, where):
        self.where = where

    def err(self, field, msg, polish=False):
        R.err(self.where, field, msg, polish)

    def warn(self, field, msg):
        R.warn(self.where, field, msg)

    def text(self, obj, key, path, *, required=True, max_chars=None, max_words=None,
             allow_empty=False, soft=False):
        """soft=True: a missing value does not break the page (only house style)."""
        if key not in obj or obj[key] is None:
            if required:
                self.err(path, "missing (string required)", soft)
            return None
        v = obj[key]
        if not is_str(v):
            self.err(path, f"must be text in double quotes (a string), got {type(v).__name__}")
            return None
        if not allow_empty and not v.strip():
            self.err(path, "must not be empty", True)
        if max_chars is not None and len(v) > max_chars:
            self.err(path, f"{len(v)} characters, limit {max_chars}", True)
        if max_words is not None and nwords(v) > max_words:
            self.err(path, f"{nwords(v)} words, limit {max_words}", True)
        if TAG_RE.search(v):
            self.err(path, "contains markup; only title_html may hold one <em>", True)
        return v

    def integer(self, obj, key, path, *, required=True, lo=None, hi=None, soft=False):
        if key not in obj:
            if required:
                self.err(path, "missing (integer required)", soft)
            return None
        v = obj[key]
        if not is_int(v):
            self.err(path, f"must be an integer, got {v!r}", soft)
            return None
        if lo is not None and v < lo or hi is not None and v > hi:
            self.err(path, f"{v} is outside {lo}–{hi}", True)
        return v

    def lst(self, obj, key, path, *, required=True, lo=None, hi=None):
        if key not in obj or obj[key] is None:
            if required:
                self.err(path, "missing (list required)")
            return []
        v = obj[key]
        if not isinstance(v, list):
            self.err(path, f"must be a list, got {type(v).__name__}")
            return []
        if lo is not None and len(v) < lo or hi is not None and len(v) > hi:
            want = f"{lo}" if lo == hi else f"{lo if lo is not None else 0}–{hi if hi is not None else '∞'}"
            self.err(path, f"has {len(v)} items, needs {want}", True)
        return v

    def obj(self, obj, key, path, *, required=True):
        if key not in obj or obj[key] is None:
            if required:
                self.err(path, "missing (object required)")
            return {}
        v = obj[key]
        if not isinstance(v, dict):
            self.err(path, f"must be an object, got {type(v).__name__}")
            return {}
        return v

    def enum(self, obj, key, path, values, *, required=True, strict=False, default=None):
        """strict=True: the renderer cannot draw any other value (otherwise house style). default:
        what --ci draws in place of a value that is not one of `values`."""
        if key not in obj:
            if required:
                self.err(path, f"missing (one of {', '.join(values)})")
            return None
        v = obj[key]
        if not is_str(v) or v not in values:
            self.err(path, f"{v!r} is not one of {', '.join(values)}", not strict)
            if CI and default is not None:
                obj[key] = default
            return None
        return v

    def strings(self, obj, key, path, *, lo=None, hi=None, max_words=None, required=True):
        items = self.lst(obj, key, path, lo=lo, hi=hi, required=required)
        out = []
        for i, s in enumerate(items):
            if not is_str(s) or not s.strip():
                self.err(f"{path}[{i}]", "must be a non-empty string", is_str(s))
                continue
            if TAG_RE.search(s):
                self.err(f"{path}[{i}]", "contains markup", True)
            if max_words and nwords(s) > max_words:
                self.err(f"{path}[{i}]", f"{nwords(s)} words, limit {max_words}", True)
            out.append(s)
        return out


# ------------------------------------------------------------ image reading
def jpeg_size(data: bytes):
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        m = data[i + 1]
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7 or m == 0xFF:
            i += 1 if m == 0xFF else 2
            continue
        ln = struct.unpack(">H", data[i + 2:i + 4])[0]
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return w, h
        i += 2 + ln
    return None


def iter_boxes(data: bytes, start: int, end: int):
    i = start
    while i + 8 <= end:
        size, typ = struct.unpack(">I4s", data[i:i + 8])
        hdr = 8
        if size == 1:
            size = struct.unpack(">Q", data[i + 8:i + 16])[0]
            hdr = 16
        elif size == 0:
            size = end - i
        if size < hdr or i + size > end:
            return
        yield typ.decode("latin-1"), i + hdr, i + size
        i += size


def avif_parse(data: bytes):
    """Returns (width, height, metadata bytes) for an AVIF file."""
    meta = None
    for typ, s, en in iter_boxes(data, 0, len(data)):
        if typ == "meta":
            meta = (s + 4, en)  # FullBox
            break
    if not meta:
        return None, b""
    primary, ispes, assoc, items, locs = None, [], {}, {}, {}
    metabytes = [data[meta[0]:meta[1]]]
    for typ, s, en in iter_boxes(data, *meta):
        if typ == "pitm":
            ver = data[s]
            primary = struct.unpack(">H" if ver == 0 else ">I", data[s + 4:s + (6 if ver == 0 else 8)])[0]
        elif typ == "iprp":
            for t2, s2, e2 in iter_boxes(data, s, en):
                if t2 == "ipco":
                    for t3, s3, e3 in iter_boxes(data, s2, e2):
                        ispes.append(struct.unpack(">II", data[s3 + 4:s3 + 12]) if t3 == "ispe" else None)
                elif t2 == "ipma":
                    ver, flags = data[s2], int.from_bytes(data[s2 + 1:s2 + 4], "big")
                    p = s2 + 4
                    n = struct.unpack(">I", data[p:p + 4])[0]
                    p += 4
                    for _ in range(n):
                        if ver < 1:
                            iid = struct.unpack(">H", data[p:p + 2])[0]
                            p += 2
                        else:
                            iid = struct.unpack(">I", data[p:p + 4])[0]
                            p += 4
                        cnt = data[p]
                        p += 1
                        lst = []
                        for _ in range(cnt):
                            if flags & 1:
                                v = struct.unpack(">H", data[p:p + 2])[0] & 0x7FFF
                                p += 2
                            else:
                                v = data[p] & 0x7F
                                p += 1
                            lst.append(v)
                        assoc[iid] = lst
        elif typ == "iinf":
            ver = data[s]
            p = s + 4 + (2 if ver == 0 else 4)
            for t2, s2, e2 in iter_boxes(data, p, en):
                if t2 != "infe":
                    continue
                v2 = data[s2]
                q = s2 + 4
                if v2 >= 2:
                    if v2 == 2:
                        iid = struct.unpack(">H", data[q:q + 2])[0]
                        q += 2
                    else:
                        iid = struct.unpack(">I", data[q:q + 4])[0]
                        q += 4
                    q += 2
                    itype = data[q:q + 4].decode("latin-1")
                    items[iid] = itype
        elif typ == "iloc":
            try:
                ver = data[s]
                p = s + 4
                osz, lsz = data[p] >> 4, data[p] & 15
                bsz, isz = data[p + 1] >> 4, (data[p + 1] & 15 if ver in (1, 2) else 0)
                p += 2
                if ver < 2:
                    n = struct.unpack(">H", data[p:p + 2])[0]
                    p += 2
                else:
                    n = struct.unpack(">I", data[p:p + 4])[0]
                    p += 4

                def rd(sz):
                    nonlocal p
                    v = int.from_bytes(data[p:p + sz], "big") if sz else 0
                    p += sz
                    return v
                for _ in range(n):
                    iid = rd(2 if ver < 2 else 4)
                    method = rd(2) & 15 if ver in (1, 2) else 0
                    rd(2)
                    base = rd(bsz)
                    ext = []
                    for _ in range(rd(2)):
                        if ver in (1, 2) and isz:
                            rd(isz)
                        off, ln = rd(osz), rd(lsz)
                        ext.append((base + off, ln))
                    locs[iid] = (method, ext)
            except (IndexError, struct.error):
                pass
    for iid, itype in items.items():
        if itype in ("Exif", "mime") and iid in locs and locs[iid][0] == 0:
            for off, ln in locs[iid][1]:
                metabytes.append(data[off:off + ln] if ln else data[off:])
    size = None
    if primary is not None and primary in assoc:
        for idx in assoc[primary]:
            if 0 < idx <= len(ispes) and ispes[idx - 1]:
                size = ispes[idx - 1]
                break
    if size is None:
        cand = [x for x in ispes if x]
        size = max(cand, key=lambda t: t[0] * t[1]) if cand else None
    return size, b"\n".join(metabytes)


IMG_CACHE: dict = {}


def image_info(path: Path):
    """(width, height) or None; caches metadata text."""
    key = str(path)
    if key in IMG_CACHE:
        return IMG_CACHE[key]
    try:
        data = path.read_bytes()
    except OSError:
        IMG_CACHE[key] = None
        return None
    if path.suffix.lower() in (".jpg", ".jpeg"):
        size = jpeg_size(data)
    elif path.suffix.lower() == ".avif":
        size, _ = avif_parse(data)
    elif path.suffix.lower() == ".png" and data[:8] == b"\x89PNG\r\n\x1a\n":
        size = struct.unpack(">II", data[16:24])
    else:
        size = None
    IMG_CACHE[key] = size
    return size


def jpeg_orientation(data: bytes) -> int:
    """EXIF orientation (1–8) of a JPEG; 1 when there is none."""
    i = 2
    while i + 4 <= len(data) and data[i] == 0xFF:
        m = data[i + 1]
        if m == 0xDA:
            break
        if 0xD0 <= m <= 0xD9 or m == 0x01:
            i += 2
            continue
        ln = struct.unpack(">H", data[i + 2:i + 4])[0]
        if m == 0xE1 and data[i + 4:i + 10] == b"Exif\0\0":
            t = data[i + 10:i + 2 + ln]
            try:
                end = "<" if t[:2] == b"II" else ">"
                off = struct.unpack(end + "I", t[4:8])[0]
                for k in range(struct.unpack(end + "H", t[off:off + 2])[0]):
                    at = off + 2 + 12 * k
                    if struct.unpack(end + "H", t[at:at + 2])[0] == 0x0112:
                        return struct.unpack(end + "H", t[at + 8:at + 10])[0]
            except struct.error:
                return 1
        i += 2 + ln
    return 1


def webp_size(data: bytes):
    chunk = data[12:16]
    if chunk == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
        w, h = struct.unpack("<HH", data[26:30])
        return w & 0x3FFF, h & 0x3FFF
    if chunk == b"VP8L" and data[20:21] == b"\x2f":
        b = int.from_bytes(data[21:25], "little")
        return (b & 0x3FFF) + 1, ((b >> 14) & 0x3FFF) + 1
    if chunk == b"VP8X":
        return int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1
    return None


def master_size(path: Path):
    """(width, height) as a browser shows a JPEG, PNG or WebP (EXIF rotation applied), whatever the
    file is called; None when the file is not one of those."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    size = None
    if data[:2] == b"\xff\xd8":
        size = jpeg_size(data)
        if size and jpeg_orientation(data) in (5, 6, 7, 8):
            size = (size[1], size[0])
    elif data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        size = struct.unpack(">II", data[16:24])
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) >= 30:
        size = webp_size(data)
    return tuple(size) if size and size[0] and size[1] else None


# ----------------------------------------------------------- master pictures
class Img:
    """One picture: its master file (whatever was uploaded under the picture's name) and the AVIF
    that is made from it (`fresh` while masters.json holds the master's sha256 and the AVIF exists)."""

    def __init__(self, folder: str, name: str, path: Path):
        self.folder, self.name, self.path = folder, name, path
        self.rel = f"{folder}/{path.name}"
        self.avif = f"{folder}/{name}.avif"
        self.size = master_size(path)
        self.w, self.h = self.size or (None, None)
        self.sha = hashlib.sha256(path.read_bytes()).hexdigest()
        self.fresh = False


def master_stem(fn: str):
    """The picture a file stands for, by name: hero.jpg → hero, Hero.PNG → Hero, and hero.jpg.jpeg
    (an ending typed while the computer hid the real one) → hero. None for any other file."""
    p = Path(fn)
    if p.suffix.lower() not in MASTER_EXT:
        return None
    stem = p.stem
    second = Path(stem).suffix.lower()
    return stem[:-len(second)] if second in SECOND_EXT and len(stem) > len(second) else stem


def commit_time(root: Path, path: Path) -> int:
    """When a file was last committed (0 when git cannot say): a fresh checkout gives every file
    the same file time, so --ci tells the newer of two uploads apart by their commits."""
    try:
        r = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%ct", "--", str(path)],
                           capture_output=True, text=True)
        return int(r.stdout.strip() or 0)
    except (OSError, ValueError):
        return 0


class Masters:
    """Finds each picture's master by name and knows which masters the AVIFs and sizes were made from."""

    def __init__(self):
        self.root, self.known, self.found, self.recs, self.dirs, self.dirty = REPO, {}, False, {}, {}, False

    def load(self, root: Path):
        self.root = root
        fp = root / MANIFEST_REL
        self.found = fp.exists()
        if self.found:
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                self.known = {k: v for k, v in data.items() if is_str(v)} if isinstance(data, dict) else {}
            except ValueError:
                R.warn(MANIFEST_REL, "-", "cannot be read; every picture is served as uploaded")

    def files(self, folder: str):
        if folder not in self.dirs:
            d = self.root / folder
            self.dirs[folder] = sorted(os.listdir(d)) if d.is_dir() else []
        return self.dirs[folder]

    def changed_at(self, rec: Img):
        if CI and (self.root / ".git").exists():
            return commit_time(self.root, rec.path)
        return rec.path.stat().st_mtime

    def get(self, folder: str, name: str, where: str, *, strict: bool):
        """The picture `name` in `folder` (None when no file has that name). Two files for one name:
        the one masters.json does not know (the new upload) wins, and of two new ones the one
        changed last; a local strict build refuses."""
        key = (folder, name)
        if key in self.recs:
            return self.recs[key]
        low = name.lower()
        cands = [self.root / folder / f for f in self.files(folder)
                 if (master_stem(f) or "").lower() == low and (self.root / folder / f).is_file()]
        rec = None
        if cands:
            recs = [Img(folder, name, c) for c in cands]
            rec = recs[0]
            if len(recs) > 1:
                new = [r for r in recs if self.known.get(r.rel) != r.sha] or recs
                rec = max(new, key=lambda r: (self.changed_at(r), MASTER_EXT.index(r.path.suffix.lower())))
                names = ", ".join(r.path.name for r in recs)
                if strict:
                    R.err(where, name, f"{len(recs)} files for one picture ({names}); keep only one")
                else:
                    R.warn(f"{folder}/{rec.path.name}", name,
                           f"{len(recs)} files for one picture ({names}); the site shows {rec.path.name}, the one "
                           f"changed last. Delete the other file so the choice is yours", show=True)
            rec.fresh = self.known.get(rec.rel) == rec.sha and (self.root / rec.avif).is_file()
        self.recs[key] = rec
        return rec

    def rec(self, folder: str, name: str):
        return self.recs.get((folder, name))

    def upload_notes(self):
        """Uploads that change nothing on the site: [(rel, message)]. A picture file whose name
        matches no picture, a kind of file a browser cannot show, and a picture put in a folder
        that holds no pictures."""
        out = []
        for folder in sorted({f for f, _ in self.recs}):
            names = {n.lower(): n for f, n in self.recs if f == folder}
            for fn in self.files(folder):
                suf = Path(fn).suffix.lower()
                if suf in UNSUPPORTED_EXT:
                    stem = Path(fn).stem
                    target = names.get(stem.lower())
                    out.append((f"{folder}/{fn}", "a website cannot show this kind of picture file; "
                                + SAVE_AS_JPG + f" as {target or stem}.jpg"
                                + ("" if target else " under the name of the picture it replaces")))
                    continue
                stem = master_stem(fn)
                if stem is None or stem.lower() in names or re.search(r"-\d{3,4}$", stem):
                    continue
                example = names.get("hero") or (sorted(names.values())[0] if names else "hero")
                out.append((f"{folder}/{fn}", f"no picture here is called {stem}, so the site does not show "
                                              f"this file. To replace a picture, upload the new file under the "
                                              f"old one's name (for example {example}.jpg)"))
        loose = ["", "assets", "assets/img", "assets/img/work", "content", "content/projects"]
        for folder in loose:
            for fn in self.files(folder) if folder else sorted(os.listdir(self.root)):
                if Path(fn).suffix.lower() in MASTER_EXT + UNSUPPORTED_EXT and not (
                        folder == "assets/img" and fn in ("apple-touch-icon.png", "grain.png")):
                    rel = f"{folder}/{fn}" if folder else fn
                    out.append((rel, "the site does not show pictures from this folder: upload the picture to "
                                     "the folder of the picture it replaces (see EDITING.md)"))
        return out

    def record(self, rec: Img):
        """The AVIF and sizes now match this master."""
        for k in [k for k in self.known if k.rsplit("/", 1)[0] == rec.folder
                  and (master_stem(k.rsplit("/", 1)[1]) or "").lower() == rec.name.lower()]:
            del self.known[k]
        self.known[rec.rel] = rec.sha
        self.dirty = True

    def manifest(self) -> str:
        return json.dumps(dict(sorted(self.known.items())), indent=1) + "\n"


MASTERS = Masters()


def unreadable(rec: Img) -> str:
    return (f"this file is not a JPG, PNG or WebP picture inside (often an iPhone HEIC photo whose name was "
            f"changed): {SAVE_AS_JPG} as {rec.name}.jpg")


def case_dir(slug: str) -> str:
    return f"assets/img/work/{slug}"


# ------------------------------------------------------- link-preview cards
OG_FRESH: dict = {}   # slug or "home" -> the card in assets/img/og/ still shows the page as it is
OG_CASE_KEYS = ("sheet", "order", "title_html", "register_line", "sector", "years", "role", "stage")


def og_key(name: str) -> str:
    return f"{OG_DIR}/{name}.jpg"


def digest(data) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def og_case_print(p: dict) -> str:
    """What a case's card shows: its sheet, title, results line, sector, years, role, stage and cover."""
    cover = MASTERS.rec(case_dir(p.get("slug")), "cover")
    return digest({**{k: p.get(k) for k in OG_CASE_KEYS}, "cover": cover.sha if cover else ""})


def og_home_print(index_text: str, site: dict) -> str:
    """What the home card shows: the words of the cover sheet's first screen (name, role, thesis,
    the four figures, the drawing's labels)."""
    m = re.search(r'<section\b[^>]*\bclass="hero\b.*?</section>', index_text or "", re.S)
    words = squash(html.unescape(re.sub(r"<[^>]+>", " ", m.group(0)))) if m else ""
    return digest({"hero": words, "name": site.get("name")})


def og_prints(projects, index_text: str, site: dict) -> dict:
    out = {og_key(p["slug"]): og_case_print(p) for p in projects if is_str(p.get("slug"))}
    if index_text is not None:
        out[og_key("home")] = og_home_print(index_text, site)
    return out


# ------------------------------------------------------- responsive variants
VARIANTS: dict = {}       # (slug, name) -> {"avif": [(w, rel)], "jpg": (w, rel) | None}
HOME_VARIANTS: dict = {}  # master rel -> [(w, "avif", rel)] for the hand-authored home pictures


def variant_rel(slug, name, w, ext):
    return f"{SIZES_DIR}/{slug}/{name}-{w}.{ext}"


def variant_plan(root: Path, slug: str, name: str, full_w: int):
    """The variant files an image should have: [(width, ext, rel_path)]."""
    out = []
    for w in VARIANT_W:
        if full_w >= w * 1.15:
            out.append((w, "avif", variant_rel(slug, name, w, "avif")))
    if full_w >= JPEG_VARIANT_W * 1.15:
        out.append((JPEG_VARIANT_W, "jpg", variant_rel(slug, name, JPEG_VARIANT_W, "jpg")))
    return out


def studio_plan(rec: Img):
    """A painting's smaller AVIF widths, next to its master: <name>-1200.avif, <name>-1600.avif."""
    return [(w, "avif", f"{rec.folder}/{rec.name}-{w}.avif") for w in VARIANT_W if rec.w >= w * 1.15]


def sips_make(root: Path, src: Path, rel: str, ext: str, width=None) -> bool:
    dst = root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    fmt = "avif" if ext == "avif" else "jpeg"
    q = VARIANT_Q[fmt] if width else AVIF_Q
    cmd = ["sips", "-s", "format", fmt, "-s", "formatOptions", str(q)]
    if width:
        cmd += ["--resampleWidth", str(width)]
    r = subprocess.run(cmd + [str(src), "--out", str(dst)], capture_output=True)
    IMG_CACHE.pop(str(dst), None)
    if r.returncode == 0 and dst.exists():
        return True
    R.warn(rel, "variant", f"sips failed: {r.stderr.decode('utf-8', 'replace').strip()[:120]}")
    return False


def bring_up_to_date(root: Path, rec: Img, plan, can_make: bool, written: list, tally: dict):
    """The usable smaller sizes of one picture [(w, ext, rel)]. Locally (can_make) a changed master
    gets its AVIF and sizes made again and is recorded in masters.json; otherwise it is served as
    uploaded, with no AVIF and no sizes made from the picture it replaced."""
    if rec is None or rec.w is None:
        return []
    if not rec.fresh:
        if not can_make:
            tally["stale"].append(rec)
            return []
        jobs = [(None, "avif", rec.avif)] + list(plan)
        if not all(sips_make(root, rec.path, rel, ext, w) for w, ext, rel in jobs):
            tally["stale"].append(rec)
            return []
        written += [str(root / rel) for _, _, rel in jobs]
        tally["made"] += len(jobs)
        MASTERS.record(rec)
        rec.fresh = True
    out = []
    for w, ext, rel in plan:
        if not (root / rel).exists() and can_make and sips_make(root, rec.path, rel, ext, w):
            written.append(str(root / rel))
            tally["made"] += 1
        if (root / rel).exists():
            out.append((w, ext, rel))
        else:
            tally["missing"] += 1
    return out


def ensure_variants(root: Path, projects, home, *, can_make: bool, written: list):
    """Brings every picture's AVIF and smaller sizes up to date with its master (case images:
    assets/img/sizes/<slug>/<name>-<w>.<ext>; paintings: next to the master)."""
    tally = {"made": 0, "missing": 0, "stale": []}
    done = set()
    for p in projects:
        slug = p.get("slug")
        for name in (p.get("_dims") or {}):
            rec = MASTERS.rec(case_dir(slug), name)
            if rec is None or rec.w is None:
                continue
            got = bring_up_to_date(root, rec, variant_plan(root, slug, name, rec.w), can_make, written, tally)
            done.add(id(rec))
            VARIANTS[(slug, name)] = {"avif": [(w, rel) for w, ext, rel in got if ext == "avif"],
                                      "jpg": next(((w, rel) for w, ext, rel in got if ext == "jpg"), None)}
    for rec in home:
        if rec is None or rec.w is None or id(rec) in done:
            continue
        done.add(id(rec))
        plan = studio_plan(rec) if rec.folder == STUDIO_DIR else []
        HOME_VARIANTS[rec.rel] = bring_up_to_date(root, rec, plan, can_make, written, tally)
    # variants whose source image is gone (renamed or dropped from the JSON)
    want = {variant_rel(sl, nm, vw, ext) for (sl, nm) in VARIANTS for vw, ext in
            [(w, "avif") for w in VARIANT_W] + [(JPEG_VARIANT_W, "jpg")]}
    sizes = root / SIZES_DIR
    if sizes.exists() and not CI:
        orphans = sorted(str(f.relative_to(root)) for f in sizes.rglob("*")
                         if f.is_file() and f.name != ".DS_Store" and str(f.relative_to(root)) not in want)
        if orphans:
            R.warn(SIZES_DIR, "orphans", f"{len(orphans)} size variant(s) with no source image (move them to the Trash): "
                   + ", ".join(orphans[:4]) + (" …" if len(orphans) > 4 else ""))
    return tally


# --------------------------------------------------------------------- grain
def write_grain() -> bytes:
    n = 128
    rng = random.Random(1913)
    fine = [rng.random() for _ in range(n * n)]
    coarse = [rng.random() for _ in range(16 * 16)]

    def cval(x, y):  # tileable bilinear value noise, 16x16 lattice
        fx, fy = x / 8.0, y / 8.0
        x0, y0 = int(fx) % 16, int(fy) % 16
        x1, y1 = (x0 + 1) % 16, (y0 + 1) % 16
        tx, ty = fx - int(fx), fy - int(fy)
        tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
        a = coarse[y0 * 16 + x0] * (1 - tx) + coarse[y0 * 16 + x1] * tx
        b = coarse[y1 * 16 + x0] * (1 - tx) + coarse[y1 * 16 + x1] * tx
        return a * (1 - ty) + b * ty

    rows = []
    for y in range(n):
        row = bytearray([0])
        for x in range(n):
            v = 0.72 * fine[y * n + x] + 0.28 * cval(x, y)
            g = int(round(255 * (0.30 + 0.70 * v))) & 0xF8
            a = int(round(255 * (0.40 + 0.60 * (1 - v)))) & 0xF0
            row += bytes((max(0, min(255, g)), max(0, min(255, a))))
        rows.append(bytes(row))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 4, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))
    return png


# ------------------------------------------------------------- html helpers
def find_ids(fragment: str) -> set:
    return set(re.findall(r'\bid=["\']([^"\']+)["\']', fragment))


ATTR_RE = re.compile(r'(?<![\w-])(href|src|data-href|poster|action|xlink:href|srcset|data-avif)=(["\'])(.*?)\2', re.S)


def rewrite_links(fragment: str, prefix: str, keep_ids: set) -> str:
    def one(val):
        if not val or re.match(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//|/)", val):
            return val
        if val.startswith("#"):
            return val if val[1:] in keep_ids else prefix + val
        if val.startswith("./"):
            val = val[2:]
        return prefix + val

    def fix(m):
        attr, q, val = m.groups()
        if attr == "srcset":
            parts = []
            for c in val.split(","):
                c = c.strip()
                if c:
                    bits = c.split(None, 1)
                    parts.append(" ".join([one(bits[0])] + bits[1:]))
            new = ", ".join(parts)
        else:
            new = one(val)
        return f"{attr}={q}{new}{q}"
    return ATTR_RE.sub(fix, fragment)


def marker_block(text: str, name: str):
    """Returns (start_index_after_START, end_index_of_END, indent) or None."""
    s = text.find(f"<!-- {name}:START -->")
    en = text.find(f"<!-- {name}:END -->")
    if s < 0 or en < 0 or en < s:
        return None
    line_start = text.rfind("\n", 0, s) + 1
    indent = re.match(r"[ \t]*", text[line_start:s]).group(0)
    return s + len(f"<!-- {name}:START -->"), en, indent


def inject(text: str, name: str, content: str):
    blk = marker_block(text, name)
    if not blk:
        return text, False
    a, b, indent = blk
    body = "\n".join((indent + "  " + ln) if ln.strip() else "" for ln in content.strip("\n").split("\n"))
    return text[:a] + "\n" + body + "\n" + indent + text[b:], True


def marker_inner(text: str, name: str):
    blk = marker_block(text, name)
    return text[blk[0]:blk[1]] if blk else None


class CanonParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.caps, self.found = [], [], []

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            return
        a = dict(attrs)
        self.stack.append((tag, a.get("aria-hidden") == "true"))
        if "data-canon" in a:
            self.caps.append({"key": a["data-canon"], "all": [], "acc": [], "depth": len(self.stack),
                              "line": self.getpos()[0]})

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        while self.stack:
            t, _ = self.stack.pop()
            for c in [c for c in self.caps if c["depth"] > len(self.stack)]:
                self.caps.remove(c)
                self.found.append(c)
            if t == tag:
                break

    def handle_data(self, d):
        hidden = any(h for _, h in self.stack)
        for c in self.caps:
            c["all"].append(d)
            if not hidden:
                c["acc"].append(d)


HTML_TAGS = set("""
a abbr address area article aside audio b base bdi bdo blockquote body br button canvas caption cite code col
colgroup data datalist dd del details dfn dialog div dl dt em embed fieldset figcaption figure footer form h1 h2
h3 h4 h5 h6 head header hgroup hr html i iframe img input ins kbd label legend li link main map mark menu meta
meter nav noscript object ol optgroup option output p picture pre progress q rp rt ruby s samp script search
section select slot small source span strong style sub summary sup table tbody td template textarea tfoot th
thead time title tr track u ul var video wbr
svg g path rect circle ellipse line polyline polygon text tspan textpath defs use symbol clippath mask pattern
lineargradient radialgradient stop marker desc filter foreignobject image fegaussianblur feturbulence
fedisplacementmap fecolormatrix feblend feoffset femerge femergenode feflood fecomposite femorphology
""".split())
OPTIONAL_END = {"p", "li", "dt", "dd", "option", "optgroup", "tr", "td", "th", "thead", "tbody", "tfoot",
                "colgroup", "rt", "rp", "html", "head", "body"}
ATTR_NAME_RE = re.compile(r"[a-z_:][a-z0-9_.:-]*")


class TagCheck(HTMLParser):
    """The slips a hand edit of a page can make: a letter typed into a tag (<pI …), a deleted
    '<' or tag (an end tag that closes nothing), a straight double quote inside alt="…"."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.problems = [], []

    def _check(self, tag, attrs) -> bool:
        ln = self.getpos()[0]
        raw = squash(self.get_starttag_text() or "")
        if tag not in HTML_TAGS:
            raw = raw if len(raw) <= 40 else raw[:39] + "…"
            self.problems.append((ln, f"“{raw}” is not a tag a page knows: a '>' or a space is probably "
                                      "missing (for example <p> followed straight by a word)"))
            return False
        for name, _ in attrs:
            if not ATTR_NAME_RE.fullmatch(name):
                self.problems.append((ln, f"<{tag}> has a stray “{name[:30]}”: a straight double quote (\") "
                                          "inside a description such as alt=\"…\" ends it early; use curly "
                                          "quotes “ ” or ’ there, or a '>' is missing"))
                break
        return True

    def handle_starttag(self, tag, attrs):
        if self._check(tag, attrs) and tag not in VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag, attrs):
        self._check(tag, attrs)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                for t, ln in self.stack[i + 1:]:
                    if t not in OPTIONAL_END:
                        self.problems.append((ln, f"<{t}> opened here is never closed: its </{t}> was "
                                                  "probably deleted"))
                del self.stack[i:]
                return
        self.problems.append((self.getpos()[0], f"</{tag}> closes nothing: a '<' or a whole tag was probably "
                                                "deleted just before it"))

    def close(self):
        super().close()
        for t, ln in self.stack:
            if t not in OPTIONAL_END:
                self.problems.append((ln, f"<{t}> opened here is never closed: its </{t}> was probably deleted"))
        self.stack = []


GENERATED_MARKERS = ("WORK", "INDEX", "PLATES", "ARTIFACT", "THUMB")   # filled by the build (NAV, FOOTER: by hand)


def tag_problems(text: str):
    """[(line, message)] for a hand-edited page, first problems first. Lines inside the markers the
    build fills are left out: the build writes them again."""
    tc = TagCheck()
    tc.feed(text)
    tc.close()
    spans = []
    for m in re.finditer(r"<!-- ([A-Z]+)(:[a-z0-9-]+)?:START -->.*?<!-- \1\2:END -->", text, re.S):
        if m.group(1) in GENERATED_MARKERS:
            spans.append((text.count("\n", 0, m.start()) + 1, text.count("\n", 0, m.end()) + 1))
    return sorted({(ln, msg) for ln, msg in tc.problems if not any(a < ln < b for a, b in spans)})


def squash(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


# ----------------------------------------------------------- number parsing
NUM_RE = re.compile(r"^(.*?)(\d[\d,]*(?:\.\d+)?)(.*)$", re.S)


def split_number(s: str):
    m = NUM_RE.match(s.strip())
    if not m:
        return None
    pre, num, post = m.groups()
    try:
        val = float(num.replace(",", ""))
    except ValueError:
        return None
    return pre, num, post, val


def countup(s: str, sr: str) -> str:
    """Display string with its first number wrapped in a count-up <data>."""
    parts = split_number(s)
    if not parts:
        return f'<span class="cs-fig__word">{e(s)}</span>'
    pre, num, post, val = parts
    v = int(val) if val == int(val) else val
    out = []
    if pre.strip():
        cls = "cs-fig__sign" if len(pre.strip()) <= 3 and not re.search(r"[a-z]{2}", pre, re.I) else "cs-fig__pre"
        out.append(f'<span class="{cls}" aria-hidden="true">{e(pre.strip())}</span>')
    srs = f'<span class="sr-only">{e(sr)}</span>' if sr else ""
    out.append(f'<data value="{v}" data-countup><span aria-hidden="true">{e(num)}</span>{srs}</data>')
    if post.strip():
        cls = "cs-fig__unit" if len(post.strip()) <= 2 else "cs-fig__suffix"
        out.append(f'<span class="{cls}" aria-hidden="true">{e(post.strip())}</span>')
    return "".join(out)


# ------------------------------------------------------- canon helpers
def canon_norm(s: str) -> str:
    return squash(str(s).lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"'))


def figure_core(seg: str) -> str:
    m = re.search(r"[0-9+−]", seg)
    return seg[m.start():] if m else seg


def segment_in_canon(seg: str, canon: dict) -> bool:
    s = canon_norm(seg)
    core = canon_norm(figure_core(seg))
    label = set(re.findall(r"[a-z][a-z'-]+", canon_norm(seg[:len(seg) - len(figure_core(seg))])))
    for k, v in canon.items():
        nv = canon_norm(v)
        if s in nv:
            return True
        if core and core in nv:
            words = set(re.findall(r"[a-z][a-z'-]+", nv)) | set(re.split(r"[._]", k.lower()))
            if not label or label & words:
                return True
    return False


# ========================================================= artifact renders
def arc_path(cx, cy, r, a0, a1):
    def pt(a):
        rad = math.radians(a - 90)
        return cx + r * math.cos(rad), cy + r * math.sin(rad)
    x0, y0 = pt(a0)
    x1, y1 = pt(a1)
    large = 1 if (a1 - a0) > 180 else 0
    return f"M{x0:.2f} {y0:.2f}A{r} {r} 0 {large} 1 {x1:.2f} {y1:.2f}"


def fmt_num(v) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if is_int(v):
        return f"{v:,}"
    return str(v)


def table_html(head, rows, cls="", label_cols=1, labelledby="") -> str:
    th = "".join(f'<th scope="col">{e(h)}</th>' for h in head)
    body = []
    for r in rows:
        cells = []
        for i, c in enumerate(r):
            lab = f' data-label="{e(head[i])}"' if i < len(head) else ""
            if i < label_cols:
                cells.append(f'<th scope="row"{lab}>{e(c)}</th>')
            else:
                cells.append(f"<td{lab}>{e(c)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    lab = f' aria-labelledby="{e(labelledby)}"' if labelledby else ""
    return (f'<table class="{cls}"{lab}><thead><tr>{th}</tr></thead><tbody>'
            + "".join(body) + "</tbody></table>")


def status_class(text: str):
    t = text.strip().lower()
    for w in sorted(STATUS_WORDS, key=len, reverse=True):
        if t == w or t.startswith(w + " ") or t.startswith(w + ":") or t.startswith(w + " (") \
                or t.startswith(w + " ·") or t.startswith(w + " —") or t.startswith(w + ","):
            return STATUS_WORDS[w], text.strip()[:len(w)], text.strip()[len(w):].lstrip(" :·—,")
    return None


def a11y(aid):
    return f"artifact-{aid}-t", f"artifact-{aid}-d"


def art_bars(a, aid):
    d = a["data"]
    bars = d.get("bars", [])
    unit = "" if d.get("unit") is None else str(d.get("unit"))
    horiz = d.get("orientation", "horizontal") == "horizontal"
    vals = [b.get("value", 0) for b in bars] + [b.get("from", 0) or 0 for b in bars]
    mx = d.get("max") or max([v for v in vals if isinstance(v, (int, float))] or [1]) or 1
    has_from = any("from" in b for b in bars)
    tid, did = a11y(aid)
    desc = "; ".join(
        f"{b.get('label')}: {('from ' + fmt_num(b['from']) + ' to ') if 'from' in b else ''}"
        f"{fmt_num(b.get('value'))}{(' ' + unit) if unit else ''}" for b in bars)
    rows = []
    for i, b in enumerate(bars):
        v = b.get("value", 0)
        hl = " is-hl" if b.get("highlight") else ""
        ghost = (f'<span class="a-bars__ghost" style="--g:{(b["from"] or 0) / mx:.4f}"></span>'
                 if "from" in b else "")
        frm = (f'<span class="a-bars__from">{e(fmt_num(b["from"]))}<i aria-hidden="true"> → </i></span>'
               if "from" in b else "")
        note = f'<span class="a-bars__note">{e(b["note"])}</span>' if b.get("note") else ""
        if horiz:
            rows.append(
                f'<div class="a-bars__row{hl}" style="--v:{v / mx:.4f};--i:{i}">'
                f'<span class="a-bars__label">{e(b.get("label"))}</span>'
                f'<span class="a-bars__track">{ghost}<span class="a-bars__bar"></span></span>'
                f'<span class="a-bars__val">{frm}{e(fmt_num(v))}{note}</span></div>')
        else:
            rows.append(
                f'<div class="a-bars__col{hl}" style="--v:{v / mx:.4f};--i:{i}">'
                f'<span class="a-bars__val">{e(fmt_num(v))}</span>{ghost}<span class="a-bars__bar"></span>'
                f'<span class="a-bars__label">{e(b.get("label"))}</span></div>')
    unit_html = f'<span class="a-bars__unit">{e(unit)}</span>' if unit else ""
    legend = ('<span class="a-bars__legend"><i class="a-lg a-lg--ghost"></i>Before <i class="a-lg a-lg--bar"></i>After</span>'
              if has_from else "")
    # Solid strokes only: pathLength dashes break under non-scaling-stroke in a stretched viewBox,
    # so the axis is revealed with a clip-path wipe (artifacts.css), never stroke-dashoffset.
    axis = ('<svg class="a-bars__axis" viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true">'
            '<path vector-effect="non-scaling-stroke" d="M0 .5H100"/>'
            + "".join(f'<path vector-effect="non-scaling-stroke" d="M{x} 0V{6 if x % 50 else 10}"/>'
                      for x in (0, 25, 50, 75, 100)) + "</svg>")
    scale = "".join(f"<span>{e(fmt_num(round(mx * t / 4, 1) if mx < 8 else round(mx * t / 4)))}</span>"
                    for t in range(5))
    if horiz:
        body = (f'<div class="a-bars a-bars--h" role="img" aria-labelledby="{tid} {did}">'
                f'<span class="sr-only" id="{did}">{e(desc)}</span>'
                f'<div class="a-bars__meta" aria-hidden="true">{unit_html}{legend}</div>'
                + "".join(rows)
                + f'<div class="a-bars__scale" aria-hidden="true"><span></span><span class="a-bars__ticks">{axis}<span class="a-bars__nums">{scale}</span></span><span></span></div>'
                + "</div>")
    else:
        body = (f'<div class="a-bars a-bars--v" style="--n:{len(bars)}" role="img" aria-labelledby="{tid} {did}">'
                f'<span class="sr-only" id="{did}">{e(desc)}</span>'
                f'<div class="a-bars__meta" aria-hidden="true">{unit_html}{legend}</div>'
                f'<div class="a-bars__plot">' + "".join(rows) + "</div>"
                + (f'<p class="a-bars__xlabel" aria-hidden="true">{e(d["x_label"])}</p>' if d.get("x_label") else "")
                + "</div>")
    head = ["Label"] + (["Before"] if has_from else []) + [("Value (" + unit + ")") if unit else "Value"] \
        + (["Note"] if any(b.get("note") for b in bars) else [])
    trows = []
    for b in bars:
        r = [b.get("label", "")]
        if has_from:
            r.append(fmt_num(b.get("from", "")) if "from" in b else "")
        r.append(fmt_num(b.get("value")))
        if any(x.get("note") for x in bars):
            r.append(b.get("note", ""))
        trows.append(r)
    return body, table_html(head, trows), desc


RING_STYLES = ("line", "ink", "hatch", "graphite", "accent")


def art_ring(a, aid):
    d = a["data"]
    segs = d.get("segments", [])
    tid, did = a11y(aid)
    desc = "; ".join(f"{s.get('label')} {fmt_num(s.get('pct'))}%" for s in segs)
    if d.get("center"):
        desc += f". Centre: {d.get('center')} {d.get('center_label', '')}".rstrip()
    cx = cy = 120
    paths, legend = [], []
    a0 = 0.0
    gap = 1.6
    for i, s in enumerate(segs):
        sweep = 360.0 * float(s.get("pct", 0)) / 100.0
        st = "accent" if s.get("accent") else RING_STYLES[i % len(RING_STYLES)]
        if sweep > gap:
            hatch = f' stroke="url(#hatch-{aid})"' if st == "hatch" else ""
            paths.append(f'<path class="a-ring__seg a-ring__seg--{st} draw"{hatch} pathLength="1" style="--i:{i}" '
                         f'd="{arc_path(cx, cy, 86, a0 + gap / 2, a0 + sweep - gap / 2)}"/>')
        legend.append(f'<li class="a-ring__li"><i class="a-ring__sw a-ring__sw--{st}" aria-hidden="true"></i>'
                      f'<span class="a-ring__lab">{e(s.get("label"))}</span>'
                      f'<span class="a-ring__pct">{e(fmt_num(s.get("pct")))}%</span></li>')
        a0 += sweep
    ticks = []
    for t in range(40):
        ang = t * 9
        r0 = 103 if t % 10 else 100
        rad = math.radians(ang - 90)
        ticks.append(f"M{cx + r0 * math.cos(rad):.2f} {cy + r0 * math.sin(rad):.2f}"
                     f"L{cx + 108 * math.cos(rad):.2f} {cy + 108 * math.sin(rad):.2f}")
    center = ""
    if d.get("center"):
        center = (f'<text class="a-ring__c" x="120" y="122" text-anchor="middle">{e(d["center"])}</text>'
                  f'<text class="a-ring__cl" x="120" y="146" text-anchor="middle">{e(d.get("center_label", ""))}</text>')
    svg = (f'<svg class="a-ring__svg" viewBox="0 0 240 240" role="img" aria-labelledby="{tid} {did}">'
           f'<title>{e(a.get("title"))}</title><desc id="{did}">{e(desc)}</desc>'
           f'<defs><pattern id="hatch-{aid}" class="a-ring__hatch" patternUnits="userSpaceOnUse" width="5" height="5" '
           f'patternTransform="rotate(45)"><rect width="1.4" height="5"/></pattern></defs>'
           f'<circle class="a-ring__guide" cx="120" cy="120" r="108"/>'
           f'<path class="a-ring__ticks draw" pathLength="1" d="{"".join(ticks)}"/>'
           f'<circle class="a-ring__guide" cx="120" cy="120" r="64"/>'
           + "".join(paths)
           + center + "</svg>")
    body = f'<div class="a-ring">{svg}<ul class="a-ring__legend" aria-hidden="true">{"".join(legend)}</ul></div>'
    rows = [[s.get("label", ""), f"{fmt_num(s.get('pct'))}%"] for s in segs]
    if d.get("center"):
        rows.append([d.get("center_label", "Centre") or "Centre", d["center"]])
    return body, table_html(["Segment", "Share"], rows), desc


def art_lanes(a, aid):
    d = a["data"]
    cols = d.get("columns", [])
    n = max(1, len(cols))
    tid, did = a11y(aid)
    lanes = d.get("lanes", [])
    desc = "; ".join(
        f"{ln.get('label')}: " + ", ".join(f"{it.get('text')} ({it.get('status')})" for it in ln.get("items", []))
        for ln in lanes)
    head = '<span class="a-lanes__corner"></span>' + "".join(f'<span class="a-lanes__col">{e(c)}</span>' for c in cols)
    out = []
    trows = []
    k = 0
    for ln in lanes:
        items = []
        for it in ln.get("items", []):
            st = it.get("status", "planned")
            s = int(it.get("start", 1))
            sp = max(1, int(it.get("span", 1)))
            when = cols[s - 1] if 0 < s <= len(cols) else ""
            if sp > 1 and 0 < s + sp - 1 <= len(cols):
                when += " → " + cols[s + sp - 2]
            val = f'<span class="a-lanes__v">{e(it["value"])}</span>' if it.get("value") not in (None, "") else ""
            items.append(
                f'<span class="a-lanes__item is-{e(st)}" style="--s:{s};--sp:{sp};--i:{k}">'
                f'<span class="a-lanes__text">{e(it.get("text"))}</span>{val}'
                f'<span class="a-lanes__meta"><span class="a-lanes__st">{e(st.capitalize())}</span>'
                f'<span class="a-lanes__when">{e(when)}</span></span></span>')
            trows.append([ln.get("label", ""), it.get("text", ""), when, st.capitalize()])
            k += 1
        lab_val = f'<span class="a-lanes__lv">{e(ln["value"])}</span>' if ln.get("value") not in (None, "") else ""
        out.append(f'<div class="a-lanes__lane"><span class="a-lanes__label">{e(ln.get("label"))}{lab_val}</span>'
                   f'<span class="a-lanes__track">{"".join(items)}</span></div>')
    total = f'<p class="a-lanes__total">{e(d["total"])}</p>' if d.get("total") else ""
    legend = ('<p class="a-lanes__legend" aria-hidden="true"><span><i class="a-lk is-done"></i>Done</span>'
              '<span><i class="a-lk is-active"></i>Active</span><span><i class="a-lk is-planned"></i>Planned</span></p>')
    present = {it.get("status") for ln in lanes for it in ln.get("items", [])}
    if present <= {"done"} or len(present) <= 1:
        legend = ""
    body = (f'<div class="a-lanes" style="--n:{n}" role="img" aria-labelledby="{tid} {did}">'
            f'<span class="sr-only" id="{did}">{e(desc)}</span>'
            f'<div class="a-lanes__head" aria-hidden="true">{head}</div>' + "".join(out) + total + legend + "</div>")
    return body, table_html(["Lane", "Item", "When", "Status"], trows), desc


TREND = {"up": ("▲", "up"), "flat": ("▬", "flat"), "down": ("▼", "down")}
HEAT = {"on-track": "On track", "watch": "Watch", "at-risk": "At risk"}


def art_heatgrid(a, aid):
    d = a["data"]
    cols = d.get("cols", [])
    rows = d.get("rows", [])
    tid, did = a11y(aid)
    descs, out, trows = [], [], []

    def colhead(c):
        m = re.match(r"^(.*?)\s*\((.+)\)\s*$", c)
        return (f'{e(m.group(1))}<small>{e(m.group(2))}</small>') if m else e(c)
    head = '<span class="a-heat__corner"></span>' + "".join(f'<span class="a-heat__col">{colhead(c)}</span>' for c in cols)
    for r in rows:
        cells, tr = [], [r.get("label", "")]
        for j, c in enumerate(r.get("cells", [])):
            st = c.get("status", "on-track")
            arrow, tw = TREND.get(c.get("trend", "flat"), ("▬", "flat"))
            word = HEAT.get(st, st)
            colname = re.sub(r"\s*\(.*\)$", "", cols[j]) if j < len(cols) else ""
            val = str(c.get("value", ""))
            sp_ = split_number(val)
            if sp_ and not sp_[0].strip():
                big = sp_[1] + (sp_[2][:1] if sp_[2][:1] == "%" else "")
                small = sp_[2][1:] if sp_[2][:1] == "%" else sp_[2]
                sm = small.strip()
                inl = ' class="is-inline"' if len(sm) <= 4 else ""
                val_html = f'{e(big)}<small{inl}>{e(sm)}</small>' if sm else e(big)
            else:
                val_html = e(val)
            cells.append(f'<span class="a-heat__cell is-{e(st)}" data-col="{e(colname)}">'
                         f'<span class="a-heat__val">{val_html}</span>'
                         f'<span class="a-heat__trend is-{tw}" title="Trend {tw}">{arrow}</span>'
                         f'<span class="a-heat__st">{e(word)}</span></span>')
            tr.append(f"{c.get('value')} {arrow} {word}")
            descs.append(f"{r.get('label')} {colname}: {c.get('value')}, trend {tw}, {word}")
        out.append(f'<div class="a-heat__row"><span class="a-heat__label">{e(r.get("label"))}</span>{"".join(cells)}</div>')
        trows.append(tr)
    desc = "; ".join(descs)
    legend = ('<p class="a-heat__legend" aria-hidden="true"><span><i class="a-hk is-on-track"></i>On track</span>'
              '<span><i class="a-hk is-watch"></i>Watch</span><span><i class="a-hk is-at-risk"></i>At risk</span>'
              '<span>▲ ▬ ▼ trend vs last month</span></p>')
    body = (f'<div class="a-heat" style="--n:{max(1, len(cols))}" role="img" aria-labelledby="{tid} {did}">'
            f'<span class="sr-only" id="{did}">{e(desc)}</span>'
            f'<div class="a-heat__row a-heat__row--head" aria-hidden="true">{head}</div>' + "".join(out) + legend + "</div>")
    return body, table_html([d.get("row_head", "")] + cols, trows), desc


def art_table(a, aid):
    d = a["data"]
    head = d.get("head", [])
    rows = d.get("rows", [])
    sc = d.get("status_col")
    if sc is None:
        status_cols = set()
        for j in range(1, len(head)):
            colvals = [r[j] for r in rows if j < len(r) and str(r[j]).strip()]
            if colvals and all(status_class(str(v)) for v in colvals):
                status_cols.add(j)
    else:
        status_cols = set(sc) if isinstance(sc, list) else {sc}
    th = "".join(f'<th scope="col">{e(h)}</th>' for h in head)
    body = []
    for r in rows:
        cells = []
        for j, c in enumerate(r):
            lab = f' data-label="{e(head[j])}"' if j < len(head) else ""
            inner = e(c)
            if j in status_cols:
                stc = status_class(str(c))
                if stc:
                    kls, word, rest = stc
                    inner = (f'<span class="a-st a-st--{kls}">{e(word)}</span>'
                             + (f' <span class="a-st__note">{e(rest)}</span>' if rest else ""))
            code = re.fullmatch(r"[a-z][a-z0-9-]*(?:\s+#[0-9a-fA-F]{3,8})?", str(c).strip())
            if code and j not in status_cols and "-" in str(c):
                parts = str(c).split()
                sw = (f'<i class="a-tok__sw" style="background:{e(parts[1])}" aria-hidden="true"></i>'
                      if len(parts) > 1 else "")
                inner = f'<code class="a-tok">{sw}{e(parts[0])}</code>' + (f' <span class="a-tok__hex">{e(parts[1])}</span>' if len(parts) > 1 else "")
            if j == 0:
                cells.append(f'<th scope="row"{lab}>{inner}</th>')
            else:
                cells.append(f"<td{lab}>{inner}</td>")
        total = r is rows[-1] and len(rows) > 2 and bool(r) and str(r[0]).strip().lower() in ("total", "totals")
        body.append(("<tr class=\"is-total\">" if total else "<tr>") + "".join(cells) + "</tr>")
    tid, _ = a11y(aid)
    html_t = (f'<div class="sched-wrap"><table class="a-sched" aria-labelledby="{tid}"><thead><tr>{th}</tr></thead><tbody>'
              + "".join(body) + "</tbody></table></div>")
    if d.get("note"):
        html_t += f'<p class="a-sched__note">{e(d["note"])}</p>'
    return html_t, "", ""


def brief_page(d, full: bool, aid: str) -> str:
    h_title = "h2" if full else "p"
    h_sec = "h3" if full else "p"
    meta = []
    for k, lab in (("from", "From"), ("to", "To"), ("period", "Period")):
        if d.get(k):
            meta.append(f"<div><dt>{lab}</dt><dd>{e(d[k])}</dd></div>")
    secs = []
    for i, s in enumerate(d.get("sections", [])):
        hd = s.get("heading", "")
        kls = slugify(hd)
        items = "".join(f"<li>{e(x)}</li>" for x in s.get("items", []))
        secs.append(f'<section class="a-brief__sec a-brief__sec--{kls}"><{h_sec} class="a-brief__h">'
                    f'<span class="a-brief__n">{i + 1:02d}</span>{e(hd)}</{h_sec}><ul>{items}</ul></section>')
    hid = f' id="brief-{aid}-h"' if full else ""
    return (f'<article class="a-brief">'
            f'<header class="a-brief__head"><p class="a-brief__kicker">{e(d.get("title", ""))}</p>'
            f'<{h_title} class="a-brief__title"{hid}>{e(d.get("period", ""))}</{h_title}>'
            f'<dl class="a-brief__meta">{"".join(meta)}</dl></header>'
            f'<div class="a-brief__body">{"".join(secs)}</div>'
            + (f'<footer class="a-brief__foot">{e(d["footer"])}</footer>' if d.get("footer") else "")
            + "</article>")


def art_brief(a, aid):
    d = a["data"]
    did = f"brief-{aid}"
    desc = f"{d.get('title', '')}, {d.get('period', '')}. " + " ".join(
        f"{s.get('heading')}: " + "; ".join(s.get("items", [])) + "." for s in d.get("sections", []))
    body = (f'<div class="a-brief-thumb" aria-hidden="true"><div class="a-brief-thumb__page">{brief_page(d, False, aid)}</div></div>'
            f'<button type="button" class="a-btn-open" data-dialog-open="{did}" commandfor="{did}" command="show-modal">'
            f'Open full size<span class="sr-only">: {e(d.get("title", ""))}, {e(d.get("period", ""))}</span>'
            f'<span aria-hidden="true"> ↗</span></button>'
            f'<dialog class="a-brief-dialog" id="{did}" aria-labelledby="brief-{aid}-h">'
            f'<form method="dialog" class="a-brief-dialog__bar"><span class="a-brief-dialog__label">'
            f'{e(a.get("title", ""))}</span><button class="a-brief-dialog__close" value="close">Close<span aria-hidden="true"> ✕</span></button></form>'
            f'<div class="a-brief-dialog__page">{brief_page(d, True, aid)}</div></dialog>')
    return body, "", desc


DAY_RE = re.compile(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\.?\s*(\d{1,2}[:.]\d{2})?", re.I)
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")


def art_cadence(a, aid):
    d = a["data"]
    rows = d.get("rows", [])
    tid, did = a11y(aid)
    items_all = [it for r in rows for it in r.get("items", [])]
    layout = d.get("layout")
    if not layout:
        dayish = [it for it in items_all if DAY_RE.match(str(it.get("when", "")))]
        layout = "week" if items_all and len(dayish) >= 0.6 * len(items_all) and len(rows) == 1 else "chain"
    trows, descs = [], []
    for r in rows:
        for it in r.get("items", []):
            mins = it.get("minutes")
            trows.append([r.get("rhythm", ""), it.get("when", ""), it.get("name", ""),
                          f"{mins} min" if mins else ""])
            descs.append(f"{r.get('rhythm') or ''}: {it.get('when') or ''} {it.get('name') or ''}"
                         + (f" ({mins} min)" if mins else ""))
    desc = "; ".join(descs)
    if layout == "week":
        cols = {k: [] for k in DAYS}
        for it in items_all:
            m = DAY_RE.match(str(it.get("when", "")))
            day = m.group(1).capitalize() if m else None
            if day not in cols:
                continue
            t = m.group(2) or ""
            rest = str(it.get("when", ""))[m.end():].strip(" ·,()")
            cols[day].append((t.replace(".", ":") if t else "~", t, it, rest))
        dcols = []
        for di, day in enumerate(DAYS):
            evs = sorted(cols[day], key=lambda x: (x[0] == "~", x[0].zfill(5)))
            lis = []
            for k, (_, t, it, rest) in enumerate(evs):
                mins = it.get("minutes")
                tm = e(t) if t else e(rest)
                dur = f'<span class="a-week__d">{e(mins)} min</span>' if mins else (
                    f'<span class="a-week__d">{e(rest)}</span>' if rest and t else "")
                bar = f'<i class="a-week__bar" style="--m:{min(1.0, (mins or 30) / 60):.3f}" aria-hidden="true"></i>' if mins else ""
                tspan = f'<span class="a-week__t">{tm}</span>' if tm else ""
                lis.append(f'<li class="a-week__ev{" is-flex" if not t else ""}" style="--i:{di + k}">'
                           f'{tspan}<span class="a-week__n">{e(it.get("name"))}</span>{dur}{bar}</li>')
            empty = '<li class="a-week__empty" aria-hidden="true"></li>' if not lis else ""
            dcols.append(f'<div class="a-week__day"><span class="a-week__dn">{day}</span><ol class="a-week__list">{"".join(lis)}{empty}</ol></div>')
        body = (f'<div class="a-week" role="img" aria-labelledby="{tid} {did}">'
                f'<span class="sr-only" id="{did}">{e(desc)}</span>{"".join(dcols)}</div>')
        return body, table_html(["Rhythm", "When", "What", "Length"], trows), desc
    segs = []
    for i, r in enumerate(rows):
        lis = []
        for it in r.get("items", []):
            name = str(it.get("name", ""))
            flow = it.get("flow")
            if not flow:
                m = re.search(r"\b(in|out)\b\s*$", name, re.I) or re.search(r"\b(in|out)\b(?=\s*\()", name, re.I)
                flow = m.group(1).lower() if m else None
            fl = (f'<span class="a-chain__flow a-chain__flow--{flow}" aria-hidden="true">'
                  f'{"↘ in" if flow == "in" else "↗ out"}</span>') if flow in ("in", "out") else ""
            when = f'<span class="a-chain__when">{e(it["when"])}</span>' if it.get("when") else ""
            lis.append(f'<li class="a-chain__it{" has-flow" if fl else ""}">{fl}<span class="a-chain__name">{e(name)}</span>{when}</li>')
        segs.append(f'<li class="a-chain__seg" style="--i:{i}"><span class="a-chain__rhythm">{e(r.get("rhythm"))}</span>'
                    f'<span class="a-chain__tick" aria-hidden="true"></span><ul class="a-chain__items">{"".join(lis)}</ul></li>')
    body = (f'<div class="a-chain" style="--n:{len(rows)}" role="img" aria-labelledby="{tid} {did}">'
            f'<span class="sr-only" id="{did}">{e(desc)}</span>'
            f'<span class="a-chain__line" aria-hidden="true"></span><ol class="a-chain__segs">{"".join(segs)}</ol></div>')
    return body, table_html(["Rhythm", "When", "What", "Length"], trows), desc


def strip_id(p):
    """A move text without its leading person id ('D3 ↑ Senior' -> '↑ Senior')."""
    return re.sub("^" + re.escape(str(p.get("id"))) + r"\s*", "", str(p.get("move", "")))


def art_ladder(a, aid):
    d = a["data"]
    levels = d.get("levels", [])
    tracks = d.get("tracks", [])
    cells = d.get("cells", [])
    people = d.get("people", [])
    tid, did = a11y(aid)

    def lvl_index(v):
        if is_int(v):
            return v if v < len(levels) else None
        if is_str(v):
            for i, name in enumerate(levels):
                if name.lower() == v.lower():
                    return i
            m = re.match(r"^L?(\d+)$", v.strip(), re.I)
            if m:
                return int(m.group(1)) - 1
        return None
    by_level = {i: [] for i in range(len(levels))}
    for p in people:
        li = lvl_index(p.get("level"))
        if li is not None and li in by_level:
            by_level[li].append(p)
    rows = []
    for li in reversed(range(len(levels))):
        pins = "".join(
            f'<span class="a-pin{" has-move" if p.get("move") else ""}">{e(p.get("id"))}</span>' for p in by_level[li])
        cs = cells[li] if li < len(cells) and isinstance(cells[li], list) else []
        cell_html = "".join(f'<span class="a-ladder__cell" data-track="{e(tracks[j]) if j < len(tracks) else ""}">{e(c)}</span>'
                            for j, c in enumerate(cs))
        rows.append(f'<div class="a-ladder__lvl" style="--l:{li}"><span class="a-ladder__name">'
                    f'<span class="a-ladder__el">▽ L{li + 1}</span>{e(levels[li])}'
                    f'<span class="a-ladder__pins">{pins}</span></span>{cell_html}</div>')
    head = ('<div class="a-ladder__head" aria-hidden="true"><span>Level</span>'
            + "".join(f"<span>{e(t)}</span>" for t in tracks) + "</div>") if cells else ""
    moves = [p for p in people if p.get("move")]
    mv = ""
    if moves:
        mv = ('<ul class="a-ladder__moves">' + "".join(
            f'<li><span class="a-pin has-move">{e(p.get("id"))}</span><span class="a-ladder__mv">'
            f'{e(strip_id(p))}</span></li>'
            for p in moves) + "</ul>")
    desc = "Levels: " + ", ".join(levels) + ". Tracks: " + ", ".join(tracks) + ". " + "; ".join(
        f"{p.get('id')} at {levels[lvl_index(p.get('level'))] if lvl_index(p.get('level')) is not None else p.get('level')}"
        + (f", {p.get('move')}" if p.get("move") else "") for p in people)
    body = (f'<div class="a-ladder{" has-cells" if cells else ""}" style="--t:{max(1, len(tracks))}" role="img" aria-labelledby="{tid} {did}">'
            f'<span class="sr-only" id="{did}">{e(desc)}</span>{head}{"".join(rows)}{mv}</div>')
    trows = []
    for li, name in enumerate(levels):
        cs = cells[li] if li < len(cells) and isinstance(cells[li], list) else []
        ppl = ", ".join(str(p.get("id")) + (f" ({p['move']})" if p.get("move") else "") for p in by_level.get(li, []))
        trows.append([name] + [cs[j] if j < len(cs) else "" for j in range(len(tracks))] + [ppl])
    return body, table_html(["Level"] + list(tracks) + ["People"], trows), desc


RENDERERS = {"bars": art_bars, "ring": art_ring, "lanes": art_lanes, "heatgrid": art_heatgrid,
             "table": art_table, "brief": art_brief, "cadence": art_cadence, "ladder": art_ladder}


def render_artifact(a) -> str:
    aid = a["id"]
    kind = a["kind"]
    body, table, _ = RENDERERS[kind](a, aid)
    tid, _ = a11y(aid)
    if table and "aria-labelledby" not in table.split(">", 1)[0]:
        table = table.replace("<table", f'<table aria-labelledby="{tid}"', 1)
    details = (f'<details class="artifact__table"><summary>View as table</summary>{table}</details>'
               if table else "")
    cap = f'<p class="artifact__caption">{e(a.get("caption"))}</p>' if a.get("caption") else ""
    return (f'<figure class="artifact artifact--{kind}" id="artifact-{aid}" data-draw>'
            f'<figcaption class="artifact__title" id="{tid}">{e(a.get("title"))}</figcaption>'
            f'<div class="artifact__body">{body}</div>{details}{cap}</figure>')


# ---------------------------------------------------- artifact validation
def validate_artifact(v: V, a: dict, path: str):
    kind = v.enum(a, "kind", f"{path}.kind", KINDS, strict=True)
    v.text(a, "id", f"{path}.id")
    if is_str(a.get("id")) and not re.fullmatch(r"[a-z0-9-]+", a["id"]):
        v.err(f"{path}.id", "must match ^[a-z0-9-]+$", True)
    v.text(a, "title", f"{path}.title")
    v.text(a, "caption", f"{path}.caption", required=False)
    d = v.obj(a, "data", f"{path}.data")
    if not kind or not isinstance(a.get("data"), dict):
        return
    p = f"{path}.data"
    if kind == "bars":
        v.enum(d, "orientation", f"{p}.orientation", ("horizontal", "vertical"), required=False,
               default="horizontal")
        bars = v.lst(d, "bars", f"{p}.bars", lo=1)
        for i, b in enumerate(bars):
            if not isinstance(b, dict):
                v.err(f"{p}.bars[{i}]", "must be an object")
                continue
            v.text(b, "label", f"{p}.bars[{i}].label")
            if not isinstance(b.get("value"), (int, float)) or isinstance(b.get("value"), bool):
                v.err(f"{p}.bars[{i}].value", "must be a number")
            if "from" in b and (not isinstance(b["from"], (int, float)) or isinstance(b["from"], bool)):
                v.err(f"{p}.bars[{i}].from", "must be a number")
    elif kind == "ring":
        segs = v.lst(d, "segments", f"{p}.segments", lo=2)
        tot = 0
        for i, s in enumerate(segs):
            if not isinstance(s, dict) or not isinstance(s.get("pct"), (int, float)):
                v.err(f"{p}.segments[{i}]", "needs {label, pct:number}")
                continue
            v.text(s, "label", f"{p}.segments[{i}].label")
            tot += s["pct"]
        if segs and abs(tot - 100) > 0.01:
            v.err(f"{p}.segments", f"pct values sum to {tot}, must be 100", True)
    elif kind == "lanes":
        cols = v.strings(d, "columns", f"{p}.columns", lo=1)
        for i, ln in enumerate(v.lst(d, "lanes", f"{p}.lanes", lo=1)):
            if not isinstance(ln, dict):
                v.err(f"{p}.lanes[{i}]", "must be an object")
                continue
            v.text(ln, "label", f"{p}.lanes[{i}].label")
            for j, it in enumerate(v.lst(ln, "items", f"{p}.lanes[{i}].items", lo=1)):
                q = f"{p}.lanes[{i}].items[{j}]"
                if not isinstance(it, dict):
                    v.err(q, "must be an object")
                    continue
                v.text(it, "text", f"{q}.text")
                s = v.integer(it, "start", f"{q}.start", lo=1, hi=max(1, len(cols)))
                sp = v.integer(it, "span", f"{q}.span", lo=1, hi=max(1, len(cols)))
                if s and sp and s + sp - 1 > len(cols):
                    v.err(q, f"start {s} + span {sp} runs past the {len(cols)} columns", True)
                v.enum(it, "status", f"{q}.status", ("done", "active", "planned"), default="planned")
    elif kind == "heatgrid":
        cols = v.strings(d, "cols", f"{p}.cols", lo=1)
        for i, r in enumerate(v.lst(d, "rows", f"{p}.rows", lo=1)):
            if not isinstance(r, dict):
                v.err(f"{p}.rows[{i}]", "must be an object")
                continue
            v.text(r, "label", f"{p}.rows[{i}].label")
            cells = v.lst(r, "cells", f"{p}.rows[{i}].cells", lo=len(cols), hi=len(cols))
            for j, c in enumerate(cells):
                q = f"{p}.rows[{i}].cells[{j}]"
                if not isinstance(c, dict):
                    v.err(q, "must be an object")
                    continue
                if not is_str(c.get("value")) and not isinstance(c.get("value"), (int, float)):
                    v.err(f"{q}.value", "missing")
                v.enum(c, "trend", f"{q}.trend", ("up", "flat", "down"), default="flat")
                v.enum(c, "status", f"{q}.status", ("on-track", "watch", "at-risk"), default="on-track")
    elif kind == "table":
        head = v.strings(d, "head", f"{p}.head", lo=1)
        for i, r in enumerate(v.lst(d, "rows", f"{p}.rows", lo=1)):
            if not isinstance(r, list) or len(r) != len(head) or not all(is_str(x) for x in r):
                v.err(f"{p}.rows[{i}]", f"must be a list of {len(head)} strings", isinstance(r, list))
        sc = d.get("status_col")
        if sc is not None:
            scs = sc if isinstance(sc, list) else [sc]
            if not all(is_int(x) and 0 <= x < len(head) for x in scs):
                v.err(f"{p}.status_col", "must be a column index (or a list of indexes)", True)
    elif kind == "brief":
        for k in ("title", "period", "from", "to"):
            v.text(d, k, f"{p}.{k}")
        v.text(d, "footer", f"{p}.footer", required=False)
        for i, s in enumerate(v.lst(d, "sections", f"{p}.sections", lo=1)):
            if not isinstance(s, dict):
                v.err(f"{p}.sections[{i}]", "must be an object")
                continue
            v.text(s, "heading", f"{p}.sections[{i}].heading")
            v.strings(s, "items", f"{p}.sections[{i}].items", lo=1)
    elif kind == "cadence":
        v.enum(d, "layout", f"{p}.layout", ("week", "chain"), required=False, default="chain")
        for i, r in enumerate(v.lst(d, "rows", f"{p}.rows", lo=1)):
            if not isinstance(r, dict):
                v.err(f"{p}.rows[{i}]", "must be an object")
                continue
            v.text(r, "rhythm", f"{p}.rows[{i}].rhythm")
            for j, it in enumerate(v.lst(r, "items", f"{p}.rows[{i}].items", lo=1)):
                q = f"{p}.rows[{i}].items[{j}]"
                if not isinstance(it, dict):
                    v.err(q, "must be an object")
                    continue
                v.text(it, "name", f"{q}.name")
                v.text(it, "when", f"{q}.when", required=False)
                if "minutes" in it and it["minutes"] is not None:
                    v.integer(it, "minutes", f"{q}.minutes", lo=1)
    elif kind == "ladder":
        levels = v.strings(d, "levels", f"{p}.levels", lo=2)
        tracks = v.strings(d, "tracks", f"{p}.tracks", lo=1)
        cells = v.lst(d, "cells", f"{p}.cells", required=False)
        if cells and (len(cells) != len(levels) or not all(isinstance(r, list) and len(r) == len(tracks) for r in cells)):
            v.err(f"{p}.cells", f"must be {len(levels)} rows (levels) × {len(tracks)} strings (tracks)", True)
        for i, pp in enumerate(v.lst(d, "people", f"{p}.people", required=False)):
            if not isinstance(pp, dict) or "id" not in pp or "level" not in pp:
                v.err(f"{p}.people[{i}]", "needs {id, level, move?}")
                continue
            lv = pp["level"]
            ok = (is_int(lv) and 0 <= lv < len(levels)) or (is_str(lv) and (
                lv.lower() in [x.lower() for x in levels] or re.fullmatch(r"L?\d+", lv.strip(), re.I)))
            if not ok:
                v.err(f"{p}.people[{i}].level", f"{lv!r} is not a level index (0–{len(levels) - 1}) or level name", True)


# ========================================================== project checks
def validate_site(site: dict, where: str):
    v = V(where)
    if site.get("schema") != 1:
        v.err("schema", "must be 1")
    origin = v.text(site, "origin", "origin")
    if origin and (not re.match(r"^https?://[^/]+$", origin)):
        v.err("origin", "must be scheme + host with no trailing slash, e.g. https://name.github.io")
    bp = site.get("base_path", "/")
    if not is_str(bp) or not bp.startswith("/") or not bp.endswith("/"):
        v.err("base_path", "must start and end with '/'")
    for k in ("name", "title", "email", "rev"):
        v.text(site, k, k)
    if is_str(site.get("email")) and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", site["email"]):
        v.err("email", "is not an email address", True)
    if not is_str(site.get("linkedin", "")):
        v.err("linkedin", "must be a string (empty when there is none)", True)
        if CI:
            site["linkedin"] = ""
    if not isinstance(site.get("index"), bool):
        v.err("index", "must be true or false (no quotes)", True)
        if CI:   # "true" with quotes, or anything else: read it the way it was meant
            site["index"] = str(site.get("index")).strip().lower() in ("true", "yes", "1")
    for i, c in enumerate(v.lst(site, "cv", "cv", required=False)):
        if not isinstance(c, dict) or not is_str(c.get("label")) or not is_str(c.get("file")):
            v.err(f"cv[{i}]", "needs {label, file}")
    if not isinstance(site.get("testimonials", []), list):
        v.err("testimonials", "must be a list", True)
    if not isinstance(site.get("canon"), dict):
        v.err("canon", "missing (object required)", True)
        site["canon"] = {}
    canon = site["canon"]
    for k in CANON_KEYS:
        if k not in canon:
            v.err(f"canon.{k}", "missing canon key", True)
        elif not is_str(canon[k]) or not canon[k].strip():
            v.err(f"canon.{k}", "must be a non-empty string", True)
    for k in canon:
        if k not in CANON_KEYS:
            v.warn(f"canon.{k}", "not one of the known canon keys")
    if CI:   # a number or true/false where a text belongs: read it as that text
        site["canon"] = {k: x if is_str(x) else ("" if x is None else str(x)) for k, x in canon.items()}


EM_RE = re.compile(r"^([^<>]*)<em>([^<>\s]+)</em>([^<>]*)$")


def title_html_for(title: str, th) -> str:
    """--ci: the title as the pages show it, following `title`. The italic word of title_html stays
    while it is still in the title; without it the title is set without an italic word."""
    if is_str(th):
        m = EM_RE.match(th)
        if m and m.group(1) + m.group(2) + m.group(3) == title:
            return th
        word = re.search(r"<em>\s*([^<>\s]+)\s*</em>", th)
        if word:
            at = re.search(r"(?<![\w-])" + re.escape(word.group(1)) + r"(?![\w-])", title)
            if at and not TAG_RE.search(title):
                return title[:at.start()] + f"<em>{at.group(0)}</em>" + title[at.end():]
    return title


def validate_project(p: dict, fname: str, site: dict, root: Path, allow_missing: bool):
    where = f"content/projects/{fname}"
    v = V(where)
    canon = site.get("canon", {}) if isinstance(site.get("canon"), dict) else {}
    if p.get("schema") != 1:
        v.err("schema", "must be 1")
    slug = v.text(p, "slug", "slug")
    if slug and (not re.fullmatch(r"[a-z0-9-]+", slug) or slug + ".json" != fname):
        v.err("slug", f"{slug!r} must match ^[a-z0-9-]+$ and the file name")
    sheet = v.text(p, "sheet", "sheet")
    if sheet and not re.fullmatch(r"A-10[1-6]", sheet):
        v.err("sheet", f"{sheet!r} must match ^A-10[1-6]$", True)
    v.integer(p, "order", "order", lo=1, hi=6)
    title = v.text(p, "title", "title", max_chars=70)
    th = p.get("title_html")
    if not is_str(th):
        v.err("title_html", "missing (string with exactly one <em>word</em>)", True)
    else:
        m = EM_RE.match(th)
        if not m:
            v.err("title_html", "needs exactly one <em>word</em> (a single word, no other markup)", True)
        elif title and (m.group(1) + m.group(2) + m.group(3)) != title:
            v.err("title_html", "with the tags stripped it must equal title", True)
    if CI and is_str(title) and title.strip():
        p["title_html"] = title_html_for(title, th)
    v.text(p, "hook", "hook", max_chars=140)
    v.text(p, "dek", "dek", max_words=30)
    v.text(p, "sector", "sector")
    filters = v.strings(p, "filters", "filters", lo=1)
    for f in filters:
        if f not in FILTERS:
            v.err("filters", f"{f!r} is not one of {', '.join(FILTERS)}", True)
    v.text(p, "industry", "industry")
    v.text(p, "era", "era")
    yrs = v.text(p, "years", "years")
    if yrs and "-" in yrs:
        v.err("years", "use an en dash (–), not a hyphen", True)
    ys = v.integer(p, "year_start", "year_start", lo=1990, hi=2100)
    ye = v.integer(p, "year_end", "year_end", lo=1990, hi=2100)
    if ys and ye and ye < ys:
        v.err("year_end", "must be ≥ year_start", True)
    v.text(p, "role", "role")
    alt = v.enum(p, "altitude", "altitude", tuple(ALTITUDE), default="hands-on")
    v.text(p, "team", "team")
    v.text(p, "duration", "duration")
    v.strings(p, "platforms", "platforms", lo=1, hi=5)
    # reading time is computed from the prose (reading_minutes()); a hand-entered value is ignored
    if "reading_minutes" in p and not is_int(p["reading_minutes"]):
        v.err("reading_minutes", "is computed by the build; remove the field", True)
    rmin = reading_minutes(p)
    if rmin > 8:
        v.warn("reading time", f"{prose_words(p)} words ≈ {rmin} min at {WPM} wpm; aim for 8 min or less")
    stage = v.enum(p, "stage", "stage", tuple(STAGES), default=SHEETS.get(sheet, ("", "bone"))[1])
    if sheet in SHEETS:
        want_slug, want_stage = SHEETS[sheet]
        if stage and stage != want_stage:
            v.err("stage", f"{sheet} uses stage {want_stage!r}, not {stage!r}", True)
        if slug and slug != want_slug:
            v.warn("slug", f"{sheet} belongs to {want_slug!r}")
    v.strings(p, "keywords", "keywords", required=False)
    rl = v.text(p, "register_line", "register_line")
    if rl and re.search(r"(^|[\s(])-\d", rl):
        v.err("register_line", "use the minus sign (−), not a hyphen, before a number", True)
    if rl and canon:
        for seg in [s.strip() for s in rl.split("·") if s.strip()]:
            if not segment_in_canon(seg, canon):
                v.err("register_line", f"segment {seg!r} does not match any canon value", True)
    for i, mt in enumerate(v.lst(p, "metrics", "metrics", lo=3, hi=3)):
        q = f"metrics[{i}]"
        if not isinstance(mt, dict):
            v.err(q, "must be an object")
            continue
        v.text(mt, "label", f"{q}.label")
        v.text(mt, "period", f"{q}.period")
        has_ft = "to" in mt
        has_d = "delta" in mt
        if has_ft == has_d:
            v.err(q, "needs either from + to, or delta")
        if has_ft:
            v.text(mt, "to", f"{q}.to")
            v.text(mt, "from", f"{q}.from")
        if has_d:
            v.text(mt, "delta", f"{q}.delta")
        for k in ("from", "to", "delta"):
            if is_str(mt.get(k)) and re.match(r"^\s*-\d", mt[k]):
                v.err(f"{q}.{k}", "use the minus sign (−), not a hyphen", True)
        v.text(mt, "dim", f"{q}.dim", required=False, max_chars=14)
        if "method" in mt and not (is_int(mt["method"]) and 1 <= mt["method"] <= len(p.get("deeper") or [])):
            v.err(f"{q}.method", "must be the 1-based number of a deeper[] note", True)
        key = mt.get("canon")
        if not is_str(key) or key not in canon:
            v.err(f"{q}.canon", f"{key!r} is not a key in site.json canon", True)
        else:
            cv = canon_norm(canon[key])
            for k in ("to", "delta", "from"):
                if is_str(mt.get(k)) and canon_norm(mt[k]) not in cv:
                    v.err(f"{q}.{k}", f"{mt[k]!r} does not appear in canon {key} = {canon[key]!r}", True)
    tl = v.strings(p, "tldr", "tldr", lo=3, hi=4)
    if sum(nwords(x) for x in tl) > 60:
        v.err("tldr", f"{sum(nwords(x) for x in tl)} words in total, limit 60", True)
    ch = v.obj(p, "challenge", "challenge")
    if isinstance(p.get("challenge"), dict):
        inh = v.text(ch, "inherited", "challenge.inherited")
        if inh and len(re.findall(r"[.!?](?=\s+[A-Z])", inh)) > 0:
            v.err("challenge.inherited", "must be one sentence", True)
        v.text(ch, "body", "challenge.body", max_words=60)
    led = v.strings(p, "role_led", "role_led", lo=3, hi=5)
    for i, s in enumerate(led):
        first = s.split()[0] if s.split() else ""
        if first.lower() in ("i", "the", "a", "an", "my", "we", "our"):
            v.err(f"role_led[{i}]", f"should start with a verb, starts with {first!r}", True)
    v.strings(p, "role_team", "role_team", lo=2, hi=4)
    for i, r in enumerate(v.lst(p, "roster", "roster", lo=1)):
        if not isinstance(r, dict):
            v.err(f"roster[{i}]", "must be an object")
            continue
        v.enum(r, "abbr", f"roster[{i}].abbr", tuple(ROSTER), default="PD")
        v.text(r, "label", f"roster[{i}].label")
    v.strings(p, "constraints", "constraints", lo=4, hi=6)
    v.text(p, "constraints_title", "constraints_title", required=False, max_chars=40)
    v.text(p, "baseline", "baseline", required=False, max_chars=60)
    for i, pr in enumerate(v.lst(p, "principles", "principles", lo=3, hi=3)):
        if not isinstance(pr, dict):
            v.err(f"principles[{i}]", "must be an object")
            continue
        if pr.get("id") != f"P{i + 1}":
            v.err(f"principles[{i}].id", f"must be 'P{i + 1}'", is_str(pr.get("id")))
        v.text(pr, "title", f"principles[{i}].title")
        v.text(pr, "body", f"principles[{i}].body", max_words=25)
    decs = v.lst(p, "decisions", "decisions", lo=3, hi=6)
    dids = set()
    for i, dc in enumerate(decs):
        q = f"decisions[{i}]"
        if not isinstance(dc, dict):
            v.err(q, "must be an object")
            continue
        if dc.get("id") != f"D{i + 1}":
            v.err(f"{q}.id", f"must be 'D{i + 1}'", is_str(dc.get("id")))
        if is_str(dc.get("id")):
            dids.add(dc["id"])
        for k in ("decision", "why", "tradeoff", "risk", "owner"):
            v.text(dc, k, f"{q}.{k}")
        v.enum(dc, "status", f"{q}.status", DECISION_STATUS, default="shipped")
    if decs and not any(isinstance(dc, dict) and dc.get("status") in ("killed", "descoped") for dc in decs):
        v.err("decisions", "needs at least one decision with status killed or descoped", True)
    images = v.obj(p, "images", "images")

    def decision_ok(obj, path):
        """A caption's decision: the id of one of the decisions, or none (--ci drops another one)."""
        d_ = obj.get("decision")
        if d_ is not None and (not is_str(d_) or d_ not in dids):
            v.err(path, f"{d_!r} is not a decision id", True)
            if CI:
                obj["decision"] = None
    arts = v.lst(p, "artifacts", "artifacts", required=False)
    art_ids = []
    for i, a in enumerate(arts):
        if not isinstance(a, dict):
            v.err(f"artifacts[{i}]", "must be an object")
            continue
        validate_artifact(v, a, f"artifacts[{i}]")
        if a.get("id") in art_ids:
            v.err(f"artifacts[{i}].id", f"duplicate id {a.get('id')!r}", True)
        art_ids.append(a.get("id"))
    used = set()

    def need_img(name, path):
        if not is_str(name):
            v.err(path, "must be an image name (a key in images)")
            return
        used.add(name)
        if name not in images:
            v.err(path, f"image {name!r} is not listed in images")
    proc_arts = []
    for i, pr in enumerate(v.lst(p, "process", "process", lo=3, hi=8)):
        q = f"process[{i}]"
        if not isinstance(pr, dict):
            v.err(q, "must be an object")
            continue
        v.text(pr, "id", f"{q}.id")
        v.text(pr, "eyebrow", f"{q}.eyebrow")
        v.text(pr, "heading", f"{q}.heading")
        v.strings(pr, "body", f"{q}.body", lo=1, hi=2)
        v.enum(pr, "align", f"{q}.align", ("left", "right"), default="left")
        fig = v.obj(pr, "figure", f"{q}.figure")
        if isinstance(pr.get("figure"), dict):
            has_i, has_a = "image" in fig, "artifact" in fig
            if has_i == has_a:
                v.err(f"{q}.figure", "needs exactly one of image / artifact")
            if has_i:
                need_img(fig["image"], f"{q}.figure.image")
            if has_a:
                if fig["artifact"] not in art_ids:
                    v.err(f"{q}.figure.artifact", f"{fig['artifact']!r} is not an artifact id")
                if fig["artifact"] in proc_arts:
                    v.err(f"{q}.figure.artifact", "the same artifact is used twice on the page", True)
                proc_arts.append(fig["artifact"])
            v.text(fig, "caption", f"{q}.figure.caption")
            decision_ok(fig, f"{q}.figure.decision")
    cmp_ = v.obj(p, "compare", "compare")
    if isinstance(p.get("compare"), dict):
        for k in ("before", "after"):
            need_img(cmp_.get(k), f"compare.{k}")
        for k in ("label_before", "label_after", "caption"):
            v.text(cmp_, k, f"compare.{k}")
        decision_ok(cmp_, "compare.decision")
        b, a_ = (images.get(cmp_.get(k)) if is_str(cmp_.get(k)) else None for k in ("before", "after"))
        if isinstance(b, dict) and isinstance(a_, dict) and (b.get("w"), b.get("h")) != (a_.get("w"), a_.get("h")):
            v.err("compare", "before and after must have identical pixel dimensions", True)
        modes = cmp_.get("modes")
        if modes is not None and (not isinstance(modes, list) or not modes or modes[0] != "wipe"
                                  or not set(modes) <= {"wipe", "overlay"} or len(set(modes)) != len(modes)):
            v.err("compare.modes", "must be ['wipe'] or ['wipe', 'overlay']", True)
            if CI:
                cmp_["modes"] = ["wipe"]
    on_page = {x for x in ["hero", cmp_.get("before"), cmp_.get("after")]
               + [(pr.get("figure") or {}).get("image") for pr in (p.get("process") or [])
                  if isinstance(pr, dict) and isinstance(pr.get("figure") or {}, dict)] if is_str(x)}
    dup_g = []
    for i, g in enumerate(v.lst(p, "gallery", "gallery", lo=2, hi=6)):
        if not isinstance(g, dict):
            v.err(f"gallery[{i}]", "must be an object")
            continue
        need_img(g.get("image"), f"gallery[{i}].image")
        if is_str(g.get("image")) and g.get("image") in on_page:
            dup_g.append(g.get("image"))
        v.text(g, "caption", f"gallery[{i}].caption")
        decision_ok(g, f"gallery[{i}].decision")
    if dup_g:
        v.warn("gallery", f"{len(dup_g)} of the reel's screens already appear on the page ({', '.join(dup_g)}); "
                          "the reel and lightbox should add new screens")
    sysm = v.obj(p, "system", "system", required=False)
    if sysm:
        v.text(sysm, "heading", "system.heading")
        v.text(sysm, "body", "system.body")
        for i, c in enumerate(v.lst(sysm, "colors", "system.colors", lo=1)):
            if not isinstance(c, dict) or not re.fullmatch(r"#[0-9a-fA-F]{6}", str(c.get("hex", ""))):
                v.err(f"system.colors[{i}]", "needs {token, hex:#rrggbb, use}")
            else:
                v.text(c, "token", f"system.colors[{i}].token")
                v.text(c, "use", f"system.colors[{i}].use")
        for i, t in enumerate(v.lst(sysm, "type", "system.type", lo=1)):
            if not isinstance(t, dict):
                v.err(f"system.type[{i}]", "needs {role, spec, text}")
                continue
            for k in ("role", "spec", "text"):
                v.text(t, k, f"system.type[{i}].{k}")
        v.strings(sysm, "components", "system.components", lo=1)
    for i, al in enumerate(v.lst(p, "after_launch", "after_launch", lo=2, hi=3)):
        if not isinstance(al, dict):
            v.err(f"after_launch[{i}]", "must be an object")
            continue
        v.text(al, "when", f"after_launch[{i}].when")
        v.text(al, "what", f"after_launch[{i}].what")
        v.text(al, "metric", f"after_launch[{i}].metric", required=False)
    v.strings(p, "not_taken", "not_taken", lo=2, hi=3)
    v.strings(p, "reflections", "reflections", lo=2, hi=2)
    for i, dp in enumerate(v.lst(p, "deeper", "deeper", lo=0, hi=3)):
        if not isinstance(dp, dict):
            v.err(f"deeper[{i}]", "must be an object")
            continue
        v.text(dp, "title", f"deeper[{i}].title")
        v.strings(dp, "body", f"deeper[{i}].body", lo=1)
    if p.get("privacy_note") is not None:
        v.text(p, "privacy_note", "privacy_note")
    for k in ("education",):
        if p.get(k) is not None:
            v.text(p, k, k)
    seo = v.obj(p, "seo", "seo")
    if isinstance(p.get("seo"), dict):
        v.text(seo, "description", "seo.description", max_chars=155)
        v.text(seo, "title", "seo.title", required=False, max_chars=60)
        if not seo.get("title") and is_str(title) and is_str(site.get("name")) and len(title) + 3 + len(site["name"]) > 60:
            v.warn("seo.title", f"the default <title> is {len(title) + 3 + len(site['name'])} characters; search results cut at about 60, "
                                "so add a seo.title of 60 or fewer")
    revs = v.lst(p, "revisions", "revisions", required=False, lo=1, hi=4)
    for i, rv in enumerate(revs):
        q = f"revisions[{i}]"
        if not isinstance(rv, dict):
            v.err(q, "must be an object {rev, label, date?, href?}")
            continue
        r_ = v.text(rv, "rev", f"{q}.rev", max_chars=2)
        v.text(rv, "label", f"{q}.label", max_chars=24)
        v.text(rv, "date", f"{q}.date", required=False, max_chars=12)
        hr = v.text(rv, "href", f"{q}.href", required=False)
        if hr and not re.fullmatch(r"#[a-z0-9-]+", hr):
            v.err(f"{q}.href", "must be an in-page anchor such as #after", True)
        if r_ and not re.fullmatch(r"[A-Z][0-9]?", r_):
            v.err(f"{q}.rev", "must be a capital letter (A, B, C …)", True)
    nx = p.get("next")
    if nx is not None and (not isinstance(nx, list) or len(nx) != 2 or not all(is_str(x) for x in nx)):
        v.err("next", "must be a list of 2 slugs", True)
        if CI:
            p["next"] = None
    # images: each picture's size comes from its master file; the JSON w/h say what it should be
    dims = {}
    if isinstance(p.get("images"), dict):
        for req, (w, h) in (("cover", (1200, 900)), ("hero", (2400, 1500))):
            if req not in images:
                v.err(f"images.{req}", "missing")
            elif isinstance(images[req], dict) and (images[req].get("w"), images[req].get("h")) != (w, h):
                v.err(f"images.{req}", f"must be {w}×{h}", True)
        extra = [k for k in images if k not in ("cover", "hero")]
        if not 4 <= len(extra) <= 10:
            v.err("images", f"must list cover, hero and 4–10 more; has {len(extra)} more ({', '.join(extra)})", True)
        for name, meta in images.items():
            q = f"images.{name}"
            if not re.fullmatch(r"[a-z0-9-]+", name):
                v.err(q, "image names must match ^[a-z0-9-]+$", True)
            if re.search(r"-\d{3,4}$", name):
                v.err(q, "must not end in -<digits> (reserved for the build's size variants)", True)
            if not isinstance(meta, dict):
                v.err(q, "must be {w, h, alt}")
                continue
            w = v.integer(meta, "w", f"{q}.w", lo=1, soft=True)
            h = v.integer(meta, "h", f"{q}.h", lo=1, soft=True)
            v.text(meta, "alt", f"{q}.alt", max_chars=140, soft=True)
            if "mobile" in meta:
                if not is_str(meta["mobile"]) or meta["mobile"] not in images or meta["mobile"] == name:
                    v.err(f"{q}.mobile", f"{meta['mobile']!r} must name another image (a tight crop for phones)", True)
                else:
                    used.add(meta["mobile"])
            dims[name] = (w, h)
            if not slug:
                continue
            rec = MASTERS.get(case_dir(slug), name, where, strict=not CI)
            if rec is None:
                (v.warn if allow_missing else v.err)(q, f"file missing: {case_dir(slug)}/{name}.jpg (or .png)")
                continue
            if rec.size is None:
                R.err(rec.rel, q, unreadable(rec))
                continue
            if w and h and rec.size != (w, h):
                v.err(q, f"{rec.rel} is {rec.w}×{rec.h}, JSON says {w}×{h}", True)
            dims[name] = rec.size
            ratio = rec.w / rec.h
            if CI and name == "hero" and ratio < 1.25:
                R.warn(rec.rel, q, f"{rec.w}×{rec.h} is upright or square: the top of a case study is made for a "
                                   "wide picture (about 2400×1500) and shows this one very tall", show=True)
            elif CI and name == "cover" and abs(ratio / (4 / 3) - 1) > .1:
                R.warn(rec.rel, q, f"{rec.w}×{rec.h}: the work list and the Next sheets cards show covers at 4:3 "
                                   "(1200×900), so this one is cropped", show=True)
            if rec.fresh:   # the AVIF serves only while it was made from this master
                real = image_info(root / rec.avif)
                if real is None:
                    v.err(q, f"cannot read the dimensions of {rec.avif}")
                elif tuple(real) != rec.size:
                    v.err(q, f"{rec.avif} is {real[0]}×{real[1]}, its master {rec.w}×{rec.h}", True)
        plates = p.get("plates")
        if plates is not None:
            if not isinstance(plates, list) or not 1 <= len(plates) <= 2:
                v.err("plates", "must be a list of 1–2 {image, caption}", True)
                plates = plates if isinstance(plates, list) else []
            for i, pl in enumerate(plates):
                q = f"plates[{i}]"
                if not isinstance(pl, dict):
                    v.err(q, "must be an object {image, caption}", True)
                    continue
                if not is_str(pl.get("image")) or pl.get("image") not in images:
                    v.err(f"{q}.image", f"{pl.get('image')!r} is not listed in images")
                else:
                    used.add(pl["image"])
                v.text(pl, "caption", f"{q}.caption", max_chars=60)
            if len(plates) == 1:
                v.warn("plates", "1 plate; the home gallery takes 2 per project (the build adds one)")
            names = [pl.get("image") for pl in plates if isinstance(pl, dict) and is_str(pl.get("image"))]
            if len(names) != len(set(names)):
                v.err("plates", "the two plates must use different images", True)
        for name in images:
            if name not in ("cover", "hero") and name not in used:
                v.warn(f"images.{name}", "listed but not used by process, compare, gallery or plates")
    p["_dims"] = dims
    return v


# ============================================================ case renderer
STRIP_KEYS = ("Sector", "Era", "Years", "Role", "Team", "Duration", "Platforms", "Reading time")


class Ctx:
    def __init__(self, root, site, projects, args):
        self.root, self.site, self.projects, self.args = root, site, projects, args
        self.by_slug = {p["slug"]: p for p in projects}
        self.ordered = sorted(projects, key=lambda p: p.get("order", 99))
        origin = site.get("origin", "").rstrip("/")
        self.base = origin + site.get("base_path", "/")
        self.today = datetime.date.today().isoformat()
        # dateModified = when the content last changed (file mtime), so a rebuild on another day changes nothing
        self.modified = max([p.get("_mdate", "") for p in projects] + [site.get("_mdate", "")]) or self.today

    def abs(self, path=""):
        return self.base + path

    def next_two(self, p):
        if isinstance(p.get("next"), list) and all(s in self.by_slug for s in p["next"]):
            return [self.by_slug[s] for s in p["next"]]
        order = self.ordered
        i = order.index(p)
        out = []
        for k in range(1, len(order)):
            q = order[(i + k) % len(order)]
            if q is not p:
                out.append(q)
            if len(out) == 2:
                break
        return out


def stage_style(stage):
    s = STAGES.get(stage, STAGES["bone"])
    return f"--stage:{s[0]};--stage-dark:{s[1]};--stage-shadow:{s[2]};--stage-pigment:{s[3]}"


def img_base(prefix, slug, name):
    return f"{prefix}assets/img/work/{slug}/{name}"


def img_files(p, name, prefix):
    """(master URL, AVIF URL or None) of a case picture. The AVIF is left out when the master
    changed after it was made: the page then shows the master itself."""
    rec = MASTERS.rec(case_dir(p["slug"]), name)
    if rec is None:   # --allow-missing-images
        b = img_base(prefix, p["slug"], name)
        return f"{b}.jpg", f"{b}.avif"
    return prefix + rec.rel, (prefix + rec.avif if rec.fresh else None)


def srcsets(p, name, prefix):
    """(avif srcset or None, img src, img srcset, has width descriptors) from the build's size variants."""
    slug = p["slug"]
    w, _ = p["_dims"].get(name, (None, None))
    src, full = img_files(p, name, prefix)
    if full is None:
        return None, src, "", False
    rec = VARIANTS.get((slug, name)) or {}
    av = [f"{prefix}{rel} {vw}w" for vw, rel in rec.get("avif", [])]
    avif = ", ".join(av + [f"{full} {w}w"]) if av and w else full
    jv = rec.get("jpg")
    if jv and w:
        return avif, f"{prefix}{jv[1]}", f"{prefix}{jv[1]} {jv[0]}w, {src} {w}w", True
    return avif, src, "", bool(av and w)


def reel_sizes(w, h):
    """The reel shows each picture at clamp(240px, 40vw, 560px) tall (case.css)."""
    r = (w or 16) / (h or 10)
    return f"(min-width:1400px) {round(560 * r)}px, (max-width:600px) {round(240 * r)}px, {round(40 * r, 1)}vw"


def picture_html(p, name, prefix, *, lazy=True, cls="", media_cover=False, alt=None, sizes=None,
                 fetch=None):
    slug = p["slug"]
    w, h = p["_dims"].get(name, (None, None))
    meta = p["images"].get(name, {})
    alt = meta.get("alt", "") if alt is None else alt
    srcs = ""
    if media_cover:
        cw, ch = p["_dims"].get("cover", (1200, 900))
        csrc, cavif = img_files(p, "cover", prefix)
        srcs = ((f'<source media="(max-width:600px)" type="image/avif" srcset="{cavif}" width="{cw}" height="{ch}">'
                 if cavif else "")
                + f'<source media="(max-width:600px)" srcset="{csrc}" width="{cw}" height="{ch}">')
    mob = meta.get("mobile")
    if mob and not media_cover and mob in p["_dims"]:
        mw, mh = p["_dims"][mob]
        mavif, mjsrc, mjset, mdesc = srcsets(p, mob, prefix)
        msz = ' sizes="100vw"' if mdesc else ""
        srcs += ((f'<source media="(max-width:600px)" type="image/avif" srcset="{mavif}"{msz} width="{mw}" height="{mh}">'
                  if mavif else "")
                 + f'<source media="(max-width:600px)" srcset="{mjset or mjsrc}"{msz} width="{mw}" height="{mh}">')
    avif, jsrc, jset, described = srcsets(p, name, prefix)
    sz = f' sizes="{e(sizes)}"' if (sizes and described) else ""
    attrs = 'loading="lazy" decoding="async"' if lazy else 'fetchpriority="high"'
    if fetch:
        attrs += f' fetchpriority="{fetch}"'
    c = f' class="{cls}"' if cls else ""
    jss = f' srcset="{jset}"' if jset else ""
    source = f'<source type="image/avif" srcset="{avif}"{sz}>' if avif else ""
    return (f'<picture{c}>{srcs}{source}'
            f'<img src="{jsrc}"{jss}{sz} width="{w}" height="{h}" alt="{e(alt)}" {attrs}></picture>')


def plate(p, name, prefix, caption_html="", *, cls="", lazy=True, scan=True, media_cover=False,
          sizes=SIZES["band"]):
    w, h = p["_dims"].get(name, (1, 1))
    src, avif = img_files(p, name, prefix)
    pic = picture_html(p, name, prefix, lazy=lazy, media_cover=media_cover, sizes=sizes)
    cap = f'<figcaption class="cs-cap">{caption_html}</figcaption>' if caption_html else ""
    # the lightbox finds its figures by a[data-avif]; an empty value opens the master itself
    return (f'<figure class="cs-plate {cls}" data-lightbox>'
            f'<a class="cs-plate__zoom{" scan" if scan else ""}" href="{src}" data-avif="{avif or ""}" '
            f'data-w="{w}" data-h="{h}" style="--ar:{w}/{h}">{pic}'
            f'<span class="cs-plate__hint" aria-hidden="true">Enlarge</span><span class="sr-only"> (open full size)</span></a>'
            f'{cap}</figure>')


def decision_ref(p, did, text):
    """Caption that opens with its decision: 'D2 · text'."""
    t = str(text).strip()
    if did:
        t = re.sub(r"^" + re.escape(did) + r"\s*[·:—-]\s*", "", t)
        return f'<a class="cs-cap__d" href="#{e(did.lower())}">{e(did)}</a><span aria-hidden="true"> · </span>{e(t)}'
    return e(t)


def title_words(th: str) -> str:
    out = []
    for i, tok in enumerate(th.split()):
        m = re.match(r"^(.*?)<em>(.*?)</em>(.*)$", tok)
        inner = (e(m.group(1)) + f"<em>{e(m.group(2))}</em>" + e(m.group(3))) if m else e(tok)
        out.append(f'<span class="cs-mask"><span class="cs-w" style="--i:{i}">{inner}</span></span>')
    return " ".join(out)


def nobr(s: str) -> str:
    """Keep hyphenated compounds ("Built-for-Shopify") on one line in titles."""
    return re.sub(r"(\w+(?:-\w+)+)", r'<span class="nobr">\1</span>', s)


def title_em(th: str) -> str:
    m = EM_RE.match(th)
    if not m:
        return nobr(e(th))
    return f"{nobr(e(m.group(1)))}<em>{e(m.group(2))}</em>{nobr(e(m.group(3)))}"


def sec_head(eyebrow, h2, hid, extra=""):
    return (f'<header class="cs-sec-head"><p class="eyebrow cs-eyebrow">{e(eyebrow)}</p>'
            f'<h2 class="cs-sec-head__h" id="{hid}">{nobr(h2)}</h2>{extra}</header>')


# ------------------------------------------------------ type specimen fonts
SPEC_FAMILY_RE = re.compile(r"^\s*([A-Za-z][A-Za-z ]*?[A-Za-z])\s+(?=\d)")
SPECIMEN_FONTS: dict = {}   # slug -> (stylesheet url | None, {family: loaded?})


def specimen_fonts(p: dict, offline: bool):
    """A per-page Google Fonts link limited (&text=) to the type-ladder specimens, so the
    'Rendered' column is set in the family its spec names. Returns (url | None, {family: ok})."""
    sysm = p.get("system") or {}
    fams, texts = {}, []
    for ty in sysm.get("type") or []:
        m = SPEC_FAMILY_RE.match(str(ty.get("spec", "")))
        if not m:
            continue
        fam = m.group(1).strip()
        wt = re.search(r"\b([1-9]00)\b", ty["spec"])
        fams.setdefault(fam, set()).add(int(wt.group(1)) if wt else 400)
        texts.append(str(ty.get("text", "")))
    if not fams:
        return None, {}
    chars = "".join(sorted(set("".join(texts) + " ")))

    def url_for(with_weights):
        parts = []
        for fam, wts in sorted(fams.items()):
            q = "family=" + urllib.parse.quote(fam).replace("%20", "+")
            if with_weights:
                q += ":wght@" + ";".join(str(x) for x in sorted(wts))
            parts.append(q)
        return ("https://fonts.googleapis.com/css2?" + "&".join(parts) + "&text="
                + urllib.parse.quote(chars, safe="") + "&display=swap")
    if offline:
        return url_for(True), {f: True for f in fams}
    for ww in (True, False):
        url = url_for(ww)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": CHROME_UA})
            with urllib.request.urlopen(req, timeout=8) as r:
                if r.status == 200:
                    return url, {f: True for f in fams}
        except Exception:  # noqa: BLE001  (400 for an unknown family or weight, or no network)
            continue
    return None, {f: False for f in fams}


GLYPHS = (
    # north arrow
    '<circle class="draw" pathLength="1" cx="20" cy="20" r="15"/><path class="draw" pathLength="1" d="M20 4 L26 26 L20 21 L14 26 Z"/>',
    # door swing
    '<path class="draw" pathLength="1" d="M6 34 H34"/><path class="draw" pathLength="1" d="M8 34 V8"/><path class="draw" pathLength="1" d="M8 8 A26 26 0 0 1 34 34"/>',
    # column grid
    '<path class="draw" pathLength="1" d="M4 10H36M4 20H36M4 30H36M10 4V36M20 4V36M30 4V36"/><path class="draw" pathLength="1" d="M17 17h6v6h-6z"/>',
    # section mark / level
    '<path class="draw" pathLength="1" d="M4 30H36"/><path class="draw" pathLength="1" d="M14 18 L20 28 L26 18 Z"/><path class="draw" pathLength="1" d="M20 6V16"/>',
)


def dim_line(dim, measure=False):
    """An architectural dimension line, with its dimension string when there is one."""
    cls = "cs-dim cs-dim--measure" if measure else "cs-dim"
    t = f'<span class="cs-dim__t">{e(dim)}</span>' if dim else ""
    return f'<span class="{cls}{" has-t" if dim else ""}" aria-hidden="true">{t}</span>'


def render_case(ctx: Ctx, p: dict, tpl: str, nav: str, footer: str, boot: str, fonts: str, skip: str,
                main_id: str) -> str:
    slug = p["slug"]
    prefix = "../../"
    site = ctx.site
    sheet = p["sheet"]
    nxt = ctx.next_two(p)
    order = ctx.ordered
    k_at = order.index(p)
    nx1 = order[(k_at + 1) % len(order)] if len(order) > 1 else None
    pv1 = order[(k_at - 1) % len(order)] if len(order) > 1 else None
    mins = reading_minutes(p)
    seo = p.get("seo") or {}
    fig_no = [0]

    def fig():
        fig_no[0] += 1
        return f'<span class="cs-cap__fig">Fig. {fig_no[0]:02d}</span>'

    t = {}
    t["boot"] = boot
    t["fonts"] = fonts
    t["skip"] = skip
    t["main_id"] = main_id
    t["robots"] = ('<meta name="robots" content="noindex, follow">' if not site.get("index")
                   else '<meta name="robots" content="index, follow">')
    t["title"] = e(seo.get("title") or f"{p['title']} — {site['name']}")
    t["meta_description"] = e(seo["description"])
    canonical = ctx.abs(f"work/{slug}/")
    t["canonical"] = e(canonical)
    og_img, og_w, og_h = ctx.abs(f"{OG_DIR}/{slug}.jpg"), 1200, 630
    hero_rec = MASTERS.rec(case_dir(slug), "hero")
    if not OG_FRESH.get(slug, True) and hero_rec is not None and hero_rec.w:
        og_img, og_w, og_h = ctx.abs(hero_rec.rel), hero_rec.w, hero_rec.h   # the card shows older texts
    t["og"] = "\n".join([
        '<meta property="og:type" content="article">',
        f'<meta property="og:site_name" content="{e(site["name"])}">',
        f'<meta property="og:title" content="{e(p["title"])} · {e(sheet)}">',
        f'<meta property="og:description" content="{e(seo["description"])}">',
        f'<meta property="og:url" content="{e(canonical)}">',
        f'<meta property="og:image" content="{e(og_img)}">',
        f'<meta property="og:image:width" content="{og_w}">',
        f'<meta property="og:image:height" content="{og_h}">',
        f'<meta property="og:image:alt" content="{e(p["images"]["hero"].get("alt", ""))}">',
        '<meta property="og:locale" content="en_CA">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:image" content="{e(og_img)}">',
    ])
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "CreativeWork", "@id": canonical + "#case", "name": p["title"], "headline": p["title"],
         "description": seo["description"], "about": {"@type": "Thing", "name": p["industry"]},
         "genre": p["industry"], "temporalCoverage": f"{p['year_start']}/{p['year_end']}", "inLanguage": "en-CA",
         "image": og_img, "dateModified": p.get("_mdate") or ctx.today,
         "isPartOf": {"@type": "WebSite", "name": site["name"], "url": ctx.abs()},
         "creator": {"@type": "Person", "name": site["name"], "url": ctx.abs()}, "url": canonical},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Cover sheet", "item": ctx.abs()},
            {"@type": "ListItem", "position": 2, "name": f"{sheet} · {p['title']}", "item": canonical}]}]}
    t["jsonld"] = ('<script type="application/ld+json">'
                   + json.dumps(ld, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + "</script>")
    t["specimen_fonts"] = ""
    sf_url, sf_ok = SPECIMEN_FONTS.get(slug, (None, {}))
    if sf_url:
        t["specimen_fonts"] = f'<link rel="stylesheet" href="{e(sf_url)}">'
    t["stage_style"] = stage_style(p["stage"])
    t["nav"] = nav
    t["footer"] = footer
    t["rev"] = e(site.get("rev", ""))
    t["index_items"] = ""
    t["breadcrumb"] = (f'<nav class="cs-crumb" aria-label="Breadcrumb"><ol>'
                       f'<li><a href="{prefix}#work">A-100 Drawing register</a></li>'
                       f'<li><span aria-current="page">{e(sheet)}</span></li></ol></nav>')
    # ---- H1: one copy of the words (the masks are presentational spans)
    t["title_html"] = f'<span class="case-title__words">{title_words(p["title_html"])}</span>'
    t["dek"] = e(p["dek"])
    t["sheet"] = e(sheet)
    # ---- title strip
    alt = p["altitude"]
    meter = ('<span class="cs-alt" data-alt="' + e(alt) + '" aria-hidden="true"><i></i><i></i><i></i></span>')
    rows = [
        ("Sector", e(p["sector"])),
        ("Era", e(p["era"])),
        ("Years", e(p["years"])),
        ("Role", f'{e(p["role"])}<span class="cs-strip__alt">{meter}{e(ALTITUDE.get(alt, alt))}</span>'),
        ("Team", e(p["team"])),
        ("Duration", e(p["duration"])),
        ("Platforms", e(" · ".join(p["platforms"]))),
        ("Reading time", f'{mins} min'),
    ]
    if p.get("education"):
        rows.insert(3, ("Education", e(p["education"])))
    meta = "".join(f'<div class="cs-strip__row"><dt>{k}</dt><dd>{v}</dd></div>' for k, v in rows)
    al_last = (p.get("after_launch") or [{}])[-1].get("when", "")
    revisions = p.get("revisions") or [
        {"rev": "A", "label": "Discovery", "date": str(p["year_start"]), "href": "#challenge"},
        {"rev": "B", "label": "Launch", "date": str(p["year_end"]), "href": "#decisions"},
        {"rev": "C", "label": "After launch", "date": al_last, "href": "#after"},
    ]
    rev_rows = []
    for rv in revisions:
        lab = e(rv["label"])
        if rv.get("href"):
            lab = f'<a href="{e(rv["href"])}">{lab}</a>'
        rev_rows.append(f'<tr><th scope="row"><span class="cs-rev">{e(rv["rev"])}</span></th><td>{lab}</td>'
                        f'<td class="cs-strip__rd">{e(rv.get("date", ""))}</td></tr>')
    revs = ('<div class="cs-strip__revwrap"><table class="cs-strip__revs"><caption>Revisions</caption><thead><tr>'
            '<th scope="col">Rev</th><th scope="col">Description</th><th scope="col">When</th></tr></thead><tbody>'
            + "".join(rev_rows) + "</tbody></table></div>")
    keys = "".join(
        f'<li><a href="#p-{e(slugify(pr["id"]))}"><span class="cs-kn" aria-hidden="true">{i + 1}</span>'
        f'<span class="sr-only">Keynote {i + 1}: </span>{e(pr["eyebrow"])}</a></li>'
        for i, pr in enumerate(p["process"]))
    nxt_link = ""
    if nx1 is not None:
        nxt_link = (f'<a class="cs-strip__next" href="../{e(nx1["slug"])}/" aria-keyshortcuts="]">'
                    f'<span class="cs-strip__nk">Next sheet</span><span class="cs-strip__nn">{e(nx1["sheet"])}</span>'
                    f'<span aria-hidden="true" class="cs-strip__arrow">→</span>'
                    f'<span class="cs-strip__nt">{nobr(e(nx1["title"]))}</span></a>')
    pager = (f' data-prev="../{e(pv1["slug"])}/" data-prev-sheet="{e(pv1["sheet"])}"'
             f' data-next="../{e(nx1["slug"])}/" data-next-sheet="{e(nx1["sheet"])}"') if nx1 and pv1 else ""
    summary = " · ".join([e(p["sector"]), e(p["years"]), e(p["role"]), f"{mins} min read"])
    t["title_strip"] = (
        f'<aside class="cs-strip" aria-label="Sheet {e(sheet)} details"{pager}><div class="cs-strip__inner">'
        f'<p class="cs-strip__no"><span class="cs-strip__k">Sheet</span><span class="cs-strip__sheet">{e(sheet)}</span>'
        f'<span class="cs-strip__of">{k_at + 1:02d} of {len(order):02d} · Rev. {e(site.get("rev", ""))}</span></p>'
        f'<p class="cs-strip__sum">{summary}</p>'
        f'<details class="cs-strip__data" open><summary class="cs-strip__more"><span>Sheet data</span>'
        f'<span class="cs-strip__mi" aria-hidden="true"></span></summary>'
        f'<dl class="cs-strip__meta">{meta}</dl>{revs}</details>'
        f'<div class="cs-strip__dock"><div class="cs-strip__progress" aria-hidden="true"><span></span></div>'
        f'<p class="cs-strip__mini" aria-hidden="true">{e(sheet)} · {e(p["sector"])}</p>'
        f'<nav class="cs-strip__keys" aria-label="Keynotes"><p class="cs-strip__k">Keynotes</p><ol>{keys}</ol></nav>'
        f'{nxt_link}</div></div></aside>')
    # ---- hero
    t["hero"] = plate(p, "hero", prefix, "", cls="cs-plate--hero", lazy=False, scan=False, media_cover=True,
                      sizes=SIZES["hero"])
    # ---- metrics
    deeper = p.get("deeper") or []
    method_auto = next((i + 1 for i, dp in enumerate(deeper)
                        if str(dp.get("title", "")).lower().startswith("how we measured")), None)
    mets = []
    for i, mt in enumerate(p["metrics"]):
        lab = mt["label"]
        dim = mt.get("dim")
        if "to" in mt:
            sr = f"{lab}: from {mt['from']} to {mt['to']}" + (f", {dim}" if dim else "")
            run = f'<span class="cs-metric__from" aria-hidden="true">{e(mt["from"])}</span>' + dim_line(dim)
            fig_html = countup(mt["to"], "")
        else:
            sr = f"{lab}: {mt['delta']}" + (f", {dim}" if dim else "")
            run = dim_line(dim, measure=True) if dim else ""
            fig_html = countup(mt["delta"], "")
        method = mt.get("method") or method_auto
        mlink = (f'<a class="cs-metric__m" href="#detail-{method}">Method<span class="sr-only">: how '
                 f'“{e(lab)}” was measured</span><span aria-hidden="true"> ↘</span></a>') if method else ""
        run_html = f'<span class="cs-metric__run">{run}</span>' if run else ""
        mets.append(
            f'<li class="cs-metric{"" if run else " cs-metric--solo"}" data-draw style="--i:{i}">'
            f'<p class="cs-metric__label">{e(lab)}</p>'
            f'<p class="cs-metric__fig"><span class="sr-only">{e(sr)}</span>'
            f'{run_html}<span class="cs-metric__to" aria-hidden="true">{fig_html}</span></p>'
            f'<p class="cs-metric__period">{e(mt["period"])}</p>{mlink}</li>')
    t["metrics"] = (f'<section class="cs-metrics" aria-labelledby="metrics-h"><h2 class="sr-only" id="metrics-h">Impact</h2>'
                    f'<ol class="cs-metrics__list">{"".join(mets)}</ol></section>')
    # ---- tldr
    t["tldr"] = (f'<section class="cs-notes" aria-labelledby="tldr-h"><div class="cs-notes__box">'
                 f'<p class="cs-notes__label"><span>General notes</span><span>{mins}-minute sheet</span></p>'
                 f'<h2 class="cs-notes__h" id="tldr-h">The 60-second version</h2><ol class="cs-notes__list">'
                 + "".join(f"<li>{e(x)}</li>" for x in p["tldr"]) + "</ol></div></section>")
    # ---- challenge
    ch = p["challenge"]
    t["challenge"] = (f'<section class="cs-challenge" id="challenge" aria-labelledby="challenge-h">'
                      + sec_head("Challenge", "Existing conditions", "challenge-h")
                      + f'<div class="cs-challenge__body"><p class="cs-challenge__inherited">{e(ch["inherited"])}</p>'
                        f'<p>{e(ch["body"])}</p></div></section>')
    # ---- role
    roster = "".join(
        f'<li class="cs-roster__it"><span class="cs-roundel" aria-hidden="true">{e(r["abbr"])}</span>'
        f'<span class="cs-roster__lab">{e(r["label"])}</span></li>'
        for r in p["roster"])
    t["role"] = (f'<section class="cs-role" id="role" aria-labelledby="role-h">'
                 + sec_head("Scope of work", "My role", "role-h")
                 + '<div class="cs-role__cols"><div class="cs-role__col"><h3 class="cs-role__h">I led…</h3><ul class="cs-ticks">'
                 + "".join(f"<li>{e(x)}</li>" for x in p["role_led"])
                 + '</ul></div><div class="cs-role__col"><h3 class="cs-role__h">The team…</h3><ul class="cs-ticks">'
                 + "".join(f"<li>{e(x)}</li>" for x in p["role_team"])
                 + f'</ul></div></div><ul class="cs-roster" aria-label="Team roster">{roster}</ul></section>')
    # ---- constraints
    t["constraints"] = (f'<section class="cs-constraints" id="constraints" aria-labelledby="code-h">'
                        + sec_head("Constraints", e(p.get("constraints_title") or "What we had to work within"), "code-h")
                        + '<ul class="cs-reqs">' + "".join(
                            f'<li class="cs-req"><span class="cs-req__no" aria-hidden="true">§{i + 1}</span>{e(c)}</li>'
                            for i, c in enumerate(p["constraints"])) + "</ul></section>")
    # ---- principles
    cards = []
    for i, pr in enumerate(p["principles"]):
        cards.append(
            f'<li class="cs-principle" data-draw><svg class="cs-principle__glyph" viewBox="0 0 40 40" aria-hidden="true">'
            f'{GLYPHS[i % len(GLYPHS)]}</svg><p class="cs-principle__id">{e(pr["id"])}</p>'
            f'<h3 class="cs-principle__t">{nobr(e(pr["title"]))}</h3><p class="cs-principle__b">{e(pr["body"])}</p></li>')
    t["principles"] = (f'<section class="cs-principles" id="principles" aria-labelledby="principles-h">'
                       + sec_head("Principles", "What we held to", "principles-h")
                       + f'<ol class="cs-principles__list">{"".join(cards)}</ol></section>')
    # ---- decisions (a stamp replaces the badge; the status stays in the text for screen readers)
    dcards = []
    for dc in p["decisions"]:
        st = dc["status"]
        did = dc["id"].lower()
        stamped = st in ("killed", "descoped")
        stamp = f'<span class="cs-stamp" aria-hidden="true">{st.upper()}</span>' if stamped else ""
        badge = (f'<span class="sr-only">Status: {e(st.capitalize())}</span>' if stamped else
                 f'<span class="cs-decision__st a-st a-st--ok">{e(st.capitalize())}</span>')
        dcards.append(
            f'<article class="cs-decision is-{st}" id="{did}" aria-labelledby="{did}-h"{" data-draw" if stamp else ""}>'
            f'<header class="cs-decision__head"><span class="cs-decision__id">{e(dc["id"])}</span>{badge}</header>'
            f'<dl class="cs-decision__dl"><div class="cs-decision__main"><dt>Decision</dt><dd><h3 class="cs-decision__t" id="{did}-h">'
            f'{nobr(e(dc["decision"]))}</h3></dd></div>'
            f'<div><dt>Why</dt><dd>{e(dc["why"])}</dd></div><div><dt>Trade-off</dt><dd>{e(dc["tradeoff"])}</dd></div>'
            f'<div><dt>Risk watched</dt><dd>{e(dc["risk"])}</dd></div><div><dt>Owner</dt><dd>{e(dc["owner"])}</dd></div>'
            f'</dl>{stamp}</article>')
    t["decisions"] = (f'<section class="cs-decisions" id="decisions" aria-labelledby="decisions-h">'
                      + sec_head("Decision log", "Decisions", "decisions-h")
                      + f'<div class="cs-decisions__grid">{"".join(dcards)}</div></section>')
    # ---- process
    arts = {a["id"]: a for a in p.get("artifacts", []) or []}
    bands = []
    for i, pr in enumerate(p["process"]):
        pid = "p-" + slugify(pr["id"])
        fg = pr["figure"]
        dref = fg.get("decision")
        cap = decision_ref(p, dref, fg["caption"])
        if "image" in fg:
            figure = plate(p, fg["image"], prefix, fig() + " " + cap, cls="cs-band__fig", sizes=SIZES["band"])
        else:
            a = arts.get(fg["artifact"])
            art = render_artifact(a) if a else ""
            figure = (f'<div class="cs-band__fig cs-band__fig--art">{art}'
                      f'<p class="cs-cap">{fig()} {cap}</p></div>')
        rail = (f'<div class="cs-band__rail" aria-hidden="true"><span class="cs-kn cs-kn--lg">{i + 1}</span>'
                f'<span class="cs-band__rk">Keynote {i + 1:02d}</span>'
                + (f'<a class="cs-band__rd" href="#{e(dref.lower())}" tabindex="-1">See {e(dref)}<span> →</span></a>' if dref else "")
                + "</div>")
        paras = "".join(f"<p>{e(x)}</p>" for x in pr["body"])
        bands.append(
            f'<section class="cs-band cs-band--{e(pr["align"])}" id="{pid}" aria-labelledby="{pid}-h">'
            f'<div class="cs-band__text"><p class="eyebrow cs-eyebrow cs-band__eyebrow"><span class="cs-kn" aria-hidden="true">'
            f'{i + 1}</span>{e(pr["eyebrow"])}</p>'
            f'<h2 class="cs-band__h" id="{pid}-h">{nobr(e(pr["heading"]))}</h2>{paras}</div>{rail}{figure}</section>')
    t["process"] = f'<div class="cs-process">{"".join(bands)}</div>'
    # ---- compare (wipe, and an overlay mode where the geometry matches)
    c = p["compare"]
    bw, bh = p["_dims"].get(c["before"], (1, 1))
    dmap = {dc["id"]: dc for dc in p["decisions"]}
    ch2 = e(dmap[c["decision"]]["decision"]) if c.get("decision") in dmap else "Before and after"
    cap = decision_ref(p, c.get("decision"), c["caption"])
    modes = c.get("modes") or ["wipe"]
    mode_ui = ""
    if len(modes) > 1:
        mode_ui = ('<fieldset class="compare__modes"><legend class="sr-only">Compare by</legend>'
                   + "".join(f'<label class="compare__mode"><input type="radio" name="cmp-mode-{e(slug)}" value="{m}"'
                             f'{" checked" if j == 0 else ""}><span>{"Wipe" if m == "wipe" else "Overlay"}</span></label>'
                             for j, m in enumerate(modes))
                   + "</fieldset>")
    t["compare"] = (
        f'<section class="cs-compare-sec" id="compare" aria-labelledby="compare-h">'
        + sec_head("Before / after", ch2, "compare-h", mode_ui)
        + f'<figure class="compare" data-mode="wipe" style="--pos:50;--ar:{bw}/{bh}">'
          f'<div class="compare__stage">'
          f'<div class="compare__img compare__img--before">{picture_html(p, c["before"], prefix, sizes=SIZES["compare"])}'
          f'<span class="compare__tag compare__tag--before">{e(c["label_before"])}</span></div>'
          f'<div class="compare__img compare__img--after">{picture_html(p, c["after"], prefix, sizes=SIZES["compare"])}'
          f'<span class="compare__tag compare__tag--after">{e(c["label_after"])}</span></div>'
          f'<input class="compare__range" type="range" min="0" max="100" step="5" value="50" '
          f'aria-label="Compare before and after" aria-valuetext="50% before, 50% after">'
          f'<span class="compare__handle" aria-hidden="true"><span class="compare__knob"></span></span></div>'
          f'<figcaption class="cs-cap">{fig()} {cap}</figcaption></figure></section>')
    # ---- gallery
    slides = []
    gal = p["gallery"]
    for i, g in enumerate(gal):
        cap = decision_ref(p, g.get("decision"), g["caption"])
        gw, gh = p["_dims"].get(g["image"], (16, 10))
        slides.append(f'<li class="reel__item" aria-roledescription="slide" aria-label="{i + 1} of {len(gal)}">'
                      + plate(p, g["image"], prefix, fig() + " " + cap, cls="reel__fig", sizes=reel_sizes(gw, gh))
                      + "</li>")
    ctrl = ('<div class="reel__ctrl"><span class="reel__count" aria-live="polite"><span class="reel__cur">01</span>'
            f' / {len(gal):02d}</span><button type="button" class="reel__btn reel__prev" aria-label="Previous screen">'
            '<span aria-hidden="true">←</span></button><button type="button" class="reel__btn reel__next" '
            'aria-label="Next screen"><span aria-hidden="true">→</span></button></div>')
    t["gallery"] = (f'<section class="cs-gallery" id="gallery" aria-labelledby="gallery-h">'
                    + sec_head("Key screens", "Key screens", "gallery-h", ctrl)
                    + f'<div class="reel" role="region" aria-roledescription="carousel" aria-labelledby="gallery-h" tabindex="0">'
                      f'<ul class="reel__track">{"".join(slides)}</ul></div></section>')
    # ---- system
    sysm = p.get("system")
    if sysm:
        sw = []
        for c2 in sysm["colors"]:
            hx = c2["hex"]
            r_, g_, b_ = (int(hx[k:k + 2], 16) / 255 for k in (1, 3, 5))
            lum = 0.2126 * r_ ** 2.2 + 0.7152 * g_ ** 2.2 + 0.0722 * b_ ** 2.2
            ink = "#1a1511" if lum > 0.28 else "#ffffff"
            sw.append(f'<li class="cs-swatch"><span class="cs-swatch__chip" style="background:{e(hx)};color:{ink}">'
                      f'<span>{e(hx.upper())}</span></span><code class="cs-swatch__tok">{e(c2["token"])}</code>'
                      f'<span class="cs-swatch__use">{e(c2["use"])}</span></li>')
        ladder = []
        for ty in sysm["type"]:
            spec = ty["spec"]
            m = re.search(r"\b([1-9]00)\b\D+?(\d{2})\b(?:\s*/\s*(\d{2}))?", spec)
            css = []
            if m:
                css += [f"font-weight:{m.group(1)}", f"font-size:{int(m.group(2))}px"]
                if m.group(3):
                    css.append(f"line-height:{int(m.group(3))}px")
                if re.search(r"\bcaps\b", spec, re.I):
                    css += ["text-transform:uppercase", "letter-spacing:.04em"]
            else:
                m2 = re.search(r"\b(\d{3})\b", spec)
                if m2:
                    css.append(f"font-weight:{m2.group(1)}")
            fm = SPEC_FAMILY_RE.match(spec)
            fam = fm.group(1).strip() if fm else None
            note = ""
            if fam and sf_ok.get(fam):
                css.insert(0, f"font-family:'{fam}',var(--font-text)")
            elif fam:
                note = '<span class="cs-tl__note">shown in Mona Sans</span>'
            style = f' style="{e(";".join(css))}"' if css else ""
            ladder.append(f'<tr><th scope="row">{e(ty["role"])}</th><td class="cs-tl__spec">{e(spec)}{note}</td>'
                          f'<td class="cs-tl__txt"><span{style}>{e(ty["text"])}</span></td></tr>')
        comps = "".join(f'<li class="cs-req cs-req--comp">{e(x)}</li>' for x in sysm["components"])
        t["system"] = (f'<section class="cs-system" id="system" aria-labelledby="system-h">'
                       + sec_head("Design system", e(sysm["heading"]), "system-h", f'<p class="cs-sec-head__dek">{e(sysm["body"])}</p>')
                       + f'<ul class="cs-swatches">{"".join(sw)}</ul>'
                         f'<table class="cs-typeladder"><caption class="sr-only">Type ladder</caption><thead><tr>'
                         f'<th scope="col">Role</th><th scope="col">Spec</th><th scope="col">Rendered</th></tr></thead>'
                         f'<tbody>{"".join(ladder)}</tbody></table>'
                         f'<h3 class="cs-system__h">Components</h3><ul class="cs-reqs">{comps}</ul></section>')
    else:
        t["system"] = ""
    # ---- after launch
    base = f'<p class="cs-chain2__what">{e(p["baseline"])}</p>' if p.get("baseline") else ""
    pts = [f'<li class="cs-chain2__pt cs-chain2__pt--origin"><span class="cs-chain2__when">Launch</span>'
           f'<p class="cs-chain2__metric">{e(p["year_end"])}</p>{base}</li>']
    for al in p["after_launch"]:
        met = f'<p class="cs-chain2__metric">{e(al["metric"])}</p>' if al.get("metric") else ""
        pts.append(f'<li class="cs-chain2__pt"><span class="cs-chain2__when">{e(al["when"])}</span>{met}'
                   f'<p class="cs-chain2__what">{e(al["what"])}</p></li>')
    t["after_launch"] = (f'<section class="cs-after" id="after" aria-labelledby="after-h">'
                         + sec_head("Outcomes", "After launch", "after-h")
                         + f'<ol class="cs-chain2{" has-base" if base else ""}" data-draw style="--n:{len(pts)}">{"".join(pts)}</ol></section>')
    # ---- learnings
    t["learnings"] = (f'<section class="cs-learn" id="learnings" aria-labelledby="learn-h">'
                      + sec_head("Learnings", "Revisions", "learn-h")
                      + '<div class="cs-learn__cols"><div class="cs-learn__col"><h3 class="cs-learn__h">Paths not taken</h3><ol class="cs-revlist">'
                      + "".join(f'<li><span class="cs-revtri" aria-hidden="true">{i + 1}</span>{e(x)}</li>'
                                for i, x in enumerate(p["not_taken"]))
                      + '</ol></div><div class="cs-learn__col"><h3 class="cs-learn__h">Two reflections</h3><ol class="cs-revlist cs-revlist--r">'
                      + "".join(f'<li><span class="cs-revtri" aria-hidden="true">{chr(65 + i)}</span>{e(x)}</li>'
                                for i, x in enumerate(p["reflections"]))
                      + "</ol></div></div></section>")
    # ---- deeper
    if deeper:
        drs = []
        for i, dp in enumerate(deeper):
            drs.append(
                f'<details class="cs-drawer" id="detail-{i + 1}"><summary class="cs-drawer__sum"><span class="cs-callout" aria-hidden="true">'
                f'<span class="cs-callout__n">{i + 1}</span><span class="cs-callout__s">{e(sheet)}</span></span>'
                f'<span class="cs-drawer__k">Detail {i + 1}</span><span class="cs-drawer__t">{e(dp["title"])}</span>'
                f'<span class="cs-drawer__i" aria-hidden="true"></span></summary><div class="cs-drawer__body">'
                + "".join(f"<p>{e(x)}</p>" for x in dp["body"]) + "</div></details>")
        t["deeper"] = (f'<section class="cs-deeper" id="deeper" aria-labelledby="deeper-h">'
                       + sec_head("Go deeper", "Details", "deeper-h") + "".join(drs) + "</section>")
    else:
        t["deeper"] = ""
    t["privacy_note"] = (f'<p class="cs-privacy"><span class="cs-privacy__k">Note</span>{e(p["privacy_note"])}</p>'
                         if p.get("privacy_note") else "")
    # ---- next
    cards = []
    for q in nxt:
        cw, chh = q["_dims"].get("cover", (1200, 900))
        csrc, cavif = img_files(q, "cover", prefix)
        csource = f'<source type="image/avif" srcset="{cavif}">' if cavif else ""
        cards.append(
            f'<li class="cs-nextcard" style="{stage_style(q["stage"])}"><a class="cs-nextcard__a" href="../{e(q["slug"])}/">'
            f'<span class="cs-nextcard__cover"><picture>{csource}'
            f'<img src="{csrc}" width="{cw}" height="{chh}" alt="{e(q["images"].get("cover", {}).get("alt", ""))}" '
            f'loading="lazy" decoding="async"></picture></span>'
            f'<span class="cs-nextcard__no"><i class="cs-nextcard__sw" aria-hidden="true"></i><span class="sr-only">Sheet </span>{e(q["sheet"])}</span>'
            f'<h3 class="cs-nextcard__t">{title_em(q["title_html"])}</h3>'
            f'<span class="cs-nextcard__line">{e(q["register_line"])}</span></a></li>')
    t["next"] = (f'<section class="cs-next" id="next" aria-labelledby="next-h">'
                 + sec_head("Continue the set", "Next sheets", "next-h")
                 + f'<ul class="cs-next__list">{"".join(cards)}</ul>'
                   f'<p class="cs-cta"><a class="cs-cta__a" href="{prefix}#contact">Let’s talk about your product <span aria-hidden="true">→</span></a></p></section>')
    t["fig_count"] = str(fig_no[0])

    def sub(m):
        k = m.group(1)
        if k not in t:
            R.err("templates/case.html", "{{" + k + "}}", "unknown token")
            return ""
        return t[k]
    out = re.sub(r"\{\{\s*([a-z_]+)\s*\}\}", sub, tpl)
    return stamp_assets(out, site.get("rev", ""))


# ======================================================= home generators
def register_row(p, prefix=""):
    slug = p["slug"]
    cw, ch = p["_dims"].get("cover", (1200, 900))
    csrc, cavif = img_files(p, "cover", prefix)
    csource = f'<source type="image/avif" srcset="{cavif}">' if cavif else ""
    sectors = " ".join(p["filters"])
    return (f'<li class="register__row" data-sector="{e(sectors)}" data-slug="{e(slug)}"\n'
            f'    style="{stage_style(p["stage"])}">\n'
            f'  <a class="register__link" href="{prefix}work/{slug}/" data-href="{prefix}work/{slug}/">\n'
            f'    <span class="register__no"><i class="register__swatch" aria-hidden="true"></i><span class="sr-only">Sheet </span>{e(p["sheet"])}</span>\n'
            f'    <h3 class="register__title"><span class="sr-only">Project: </span>{title_em(p["title_html"])}</h3>\n'
            f'    <span class="register__sector"><span class="sr-only">Sector: </span>{e(p["sector"])}</span>\n'
            f'    <span class="register__role"><span class="sr-only">Role: </span>{e(p["role"])}</span>\n'
            f'    <span class="register__year"><span class="sr-only">Year: </span>{e(p["years"])}</span>\n'
            f'    <span class="register__outcome">{e(p["register_line"])}</span>\n'
            f'    <picture class="register__cover">{csource}<img src="{csrc}" '
            f'width="{cw}" height="{ch}" alt="{e(p["images"]["cover"].get("alt", ""))}" loading="lazy" decoding="async"></picture>\n'
            f'  </a>\n</li>')


def plate_list(p):
    """The project's two home plates: its own `plates`, else the hero plus the first process image."""
    out = [dict(x) for x in (p.get("plates") or []) if isinstance(x, dict)]
    if not out:
        out = [{"image": "hero", "caption": p["title"], "_auto": True}]
    if len(out) < 2:
        have = {x["image"] for x in out}
        for pr in p.get("process") or []:
            name = (pr.get("figure") or {}).get("image")
            if name and name not in have:
                out.append({"image": name, "caption": pr.get("heading", "")[:60], "_auto": True})
                break
    return out[:2]


def plate_item(p, pl, n, prefix=""):
    """One <li class="plate"> for the home PLATES gallery."""
    slug, name = p["slug"], pl["image"]
    w, h = p["_dims"].get(name, (None, None))
    meta = p["images"].get(name, {})
    avif, jsrc, jset, described = srcsets(p, name, prefix)
    sz = f' sizes="{SIZES["plate"]}"' if described else ""
    jss = f' srcset="{jset}"' if jset else ""
    source = f'<source type="image/avif" srcset="{avif}"{sz}>' if avif else ""
    fit = ' data-fit="contain"' if w and h and abs(w / h - 1.6) > 0.04 else ""
    return (f'<li class="plate" data-slug="{e(slug)}" data-sheet="{e(p["sheet"])}" data-title="{e(p["title"])}"{fit} '
            f'style="{stage_style(p["stage"])}"><a class="plate__link" href="{prefix}work/{e(slug)}/">'
            f'<figure class="plate__fig"><picture>{source}'
            f'<img src="{jsrc}"{jss}{sz} width="{w}" height="{h}" alt="{e(meta.get("alt", ""))}" '
            f'loading="lazy" decoding="async" fetchpriority="low"></picture>'
            f'<figcaption class="plate__cap"><span class="plate__no">{e(p["sheet"])}.{n}</span>'
            f'<span class="plate__title">{e(pl["caption"])}</span>'
            f'<span class="plate__sector">{e(p["sector"])}</span>'
            f'<span class="sr-only">. Case study: {e(p["title"])}</span></figcaption></figure></a></li>')


def thumb_html(p, prefix=""):
    """A small framed cover linked to its case (for <!-- THUMB:<slug>:START --> markers on home)."""
    cw, ch = p["_dims"].get("cover", (1200, 900))
    csrc, cavif = img_files(p, "cover", prefix)
    csource = f'<source type="image/avif" srcset="{cavif}">' if cavif else ""
    return (f'<a class="thumb" href="{prefix}work/{e(p["slug"])}/" style="{stage_style(p["stage"])}">'
            f'<picture class="thumb__pic">{csource}'
            f'<img src="{csrc}" width="{cw}" height="{ch}" alt="" loading="lazy" decoding="async"></picture>'
            f'<span class="thumb__no">{e(p["sheet"])}</span><span class="sr-only">: {e(p["title"])}</span></a>')


def plates_html(ordered, prefix=""):
    """Round-robin by project order, so consecutive plates never come from the same case."""
    lists = [(p, guarded(f"content/projects/{p['_file']}", plate_list, p, default=[])) for p in ordered]
    out = []
    for k in range(max((len(pl) for _, pl in lists), default=0)):
        for p, pl in lists:
            if k < len(pl):
                out.append(guarded(f"content/projects/{p['_file']}", plate_item, p, pl[k], k + 1, prefix))
    return out


def index_item(p, prefix=""):
    words = []
    for w in (p.get("keywords") or []) + re.split(r"[\s·&,/]+", p["sector"]) + re.split(r"[\s·&,/]+", p["industry"]) \
            + list(p["filters"]):
        w = w.strip().lower()
        if w and w not in words:
            words.append(w)
    return (f'<li class="ix__item" role="option" id="ix-{e(p["slug"])}" data-href="{prefix}work/{e(p["slug"])}/" '
            f'data-keywords="{e(" ".join(words))}"><span class="ix__no">{e(p["sheet"])}</span>'
            f'<span class="ix__title">{e(p["title"])}</span></li>')


def home_jsonld(ctx: Ctx) -> str:
    site = ctx.site
    person = {"@type": "Person", "name": site["name"], "jobTitle": "Design Lead",
              "description": "Design Lead and player-coach. Architect turned product designer.",
              "address": {"@type": "PostalAddress", "addressLocality": "Vancouver", "addressRegion": "BC",
                          "addressCountry": "CA"},
              "knowsAbout": ["Product design", "Design leadership", "Design systems", "Healthcare UX",
                             "Commerce UX", "Architecture"]}
    if site.get("linkedin"):
        person["sameAs"] = [site["linkedin"]]
    person["url"] = ctx.abs()
    person["image"] = ctx.abs(portrait_rel())
    if site.get("email"):
        person["email"] = "mailto:" + site["email"]
    ld = {"@context": "https://schema.org", "@type": "ProfilePage", "dateModified": ctx.modified,
          "mainEntity": person}
    return json.dumps(ld, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def set_attr_in_tag(text, tag_re, attr, value):
    """Sets attr=value inside every tag matched by tag_re. Returns (text, count)."""
    n = [0]

    def fix(m):
        tag = m.group(0)
        n[0] += 1
        if re.search(r'\b' + attr + r'=(["\']).*?\1', tag):
            return re.sub(r'\b' + attr + r'=(["\']).*?\1', f'{attr}="{e(value)}"', tag, count=1)
        return tag[:-1].rstrip("/").rstrip() + f' {attr}="{e(value)}">'
    return re.sub(tag_re, fix, text), n[0]


def set_email(text: str, email: str) -> str:
    """The address in content/site.json, everywhere index.html shows or copies it: the copy-email
    buttons (data-email), the mailto: links and the text of the element marked data-email-text."""
    ev = e(email)
    text = re.sub(r'(?<![\w-])data-email="[^"]*"', lambda m: f'data-email="{ev}"', text)
    text = re.sub(r'(?<![\w-])href="mailto:[^"]*"', lambda m: f'href="mailto:{ev}"', text)
    return re.sub(r'(<[a-z][^<>]*(?<![\w-])data-email-text(?![\w-])[^<>]*>)[^<]*(<)',
                  lambda m: m.group(1) + ev + m.group(2), text)


ASSET_URL_RE = re.compile(r'((?:href|src)=")((?:\.\./)*assets/(?:css|js)/[\w.-]+\.(?:css|js))(?:\?v=[^"]*)?(")')
TAG_WITH_ASSET_RE = re.compile(r'<(?:link|script)\b[^>]*>')


def stamp_assets(text: str, rev: str) -> str:
    """?v=<rev> on the site's stylesheets and entry scripts, so a host cache (GitHub Pages: max-age 600)
    never pairs new HTML with old CSS or JS. A modulepreload is stamped only when the same file is an
    entry <script src> on the page: modules imported from inside a script are requested without the
    query, and their preload must match that URL. Idempotent."""
    if not rev:
        return text
    v = urllib.parse.quote(str(rev), safe=".-_")
    entries = {m.group(2) for t in re.findall(r'<script\b[^>]*>', text) for m in ASSET_URL_RE.finditer(t)}

    def fix_tag(tm):
        tag = tm.group(0)
        pre = "modulepreload" in tag and tag.startswith("<link")

        def fix(m):
            if pre and m.group(2) not in entries:
                return f"{m.group(1)}{m.group(2)}{m.group(3)}"
            return f"{m.group(1)}{m.group(2)}?v={v}{m.group(3)}"
        return ASSET_URL_RE.sub(fix, tag)
    return TAG_WITH_ASSET_RE.sub(fix_tag, text)


def meta_re(attr: str, value: str) -> str:
    return r'<meta\b[^>]*\b' + attr + r'=["\']' + re.escape(value) + r'["\'][^>]*>'


def update_head(text: str, ctx: Ctx, *, page: str, robots: str) -> str:
    """Robots meta and absolute URLs in a hand-authored page head."""
    text = stamp_assets(text, ctx.site.get("rev", ""))
    text, n = set_attr_in_tag(text, r'<meta\b[^>]*\bname=["\']robots["\'][^>]*>', "content", robots)
    if n == 0:
        text = text.replace("</head>", f'<meta name="robots" content="{robots}">\n</head>', 1)
    if page == "home":
        url = ctx.abs()
        img = ctx.abs(f"{OG_DIR}/home.jpg")
        portrait = MASTERS.rec("assets/img/about", "portrait")
        if not OG_FRESH.get("home", True) and portrait is not None and portrait.w:
            # the card shows older words: link previews use the About photo instead
            img = ctx.abs(portrait.rel)
            text, _ = set_attr_in_tag(text, meta_re("property", "og:image:width"), "content", str(portrait.w))
            text, _ = set_attr_in_tag(text, meta_re("property", "og:image:height"), "content", str(portrait.h))
            alt = next((html.unescape(tag_attr(IMG_TAG_RE.search(m.group(2)).group(0), "alt") or "")
                        for m, folder, name in home_pictures(text)
                        if (folder, name) == ("assets/img/about", "portrait")), "")
            text, _ = set_attr_in_tag(text, meta_re("property", "og:image:alt"), "content",
                                      alt or ctx.site.get("name", ""))
        text, _ = set_attr_in_tag(text, r'<link\b[^>]*\brel=["\']canonical["\'][^>]*>', "href", url)
        text, _ = set_attr_in_tag(text, meta_re("property", "og:url"), "content", url)
        text, _ = set_attr_in_tag(text, meta_re("property", "og:image"), "content", img)
        text, _ = set_attr_in_tag(text, meta_re("name", "twitter:image"), "content", img)
        text = re.sub(r'(<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>)(.*?)(</script>)',
                      lambda m: m.group(1) + home_jsonld(ctx) + m.group(3), text, count=1, flags=re.S)
    return text


def extract_head_parts(index_text: str):
    head = index_text.split("</head>", 1)[0] if "</head>" in index_text else ""
    boot = ""
    for m in re.finditer(r"<script\b([^>]*)>(.*?)</script>", head, re.S):
        attrs = m.group(1)
        if "src=" in attrs or re.search(r'type=["\'](application/ld\+json|speculationrules|module)', attrs):
            continue
        boot = m.group(0)
        break
    fonts = []
    for m in re.finditer(r"<link\b[^>]*>", head):
        tag = m.group(0)
        if "fonts.googleapis.com" in tag or "fonts.gstatic.com" in tag:
            fonts.append(tag)
    return boot, fonts


# ---------------------------------------------- hand-authored home pictures
MARKER_SPAN_RE = re.compile(r"<!-- ([A-Z]+(?::[a-z0-9-]+)?):START -->.*?<!-- \1:END -->", re.S)
PICTURE_RE = re.compile(r"<picture\b([^>]*)>(.*?)</picture>", re.S)
IMG_TAG_RE = re.compile(r"<img\b[^>]*>")
AVIF_SOURCE_RE = re.compile(r'<source\b(?![^>]*\bmedia=)[^>]*\btype="image/avif"[^>]*>')


def tag_attr(tag: str, name: str):
    m = re.search(r'(?<![\w-])' + name + r'="([^"]*)"', tag)
    return m.group(1) if m else None


def home_pictures(text: str):
    """The <picture> elements written by hand in index.html (outside the build's markers) that show
    a picture from assets/img: [(match, folder, name)]."""
    spans = [(m.start(), m.end()) for m in MARKER_SPAN_RE.finditer(text)]
    out = []
    for m in PICTURE_RE.finditer(text):
        if any(a <= m.start() < b for a, b in spans):
            continue
        im = IMG_TAG_RE.search(m.group(2))
        src = tag_attr(im.group(0), "src") if im else None
        if not src or not src.startswith("assets/img/") or src.startswith("assets/img/og/") or "/" not in src:
            continue
        folder, fname = src.rsplit("/", 1)
        out.append((m, folder, Path(fname).stem))
    return out


def portrait_rel() -> str:
    rec = MASTERS.rec("assets/img/about", "portrait")
    return rec.rel if rec else "assets/img/about/portrait.jpg"


def fix_home_pictures(text: str) -> str:
    """Points each hand-authored home picture at its current master: the file, its real width and
    height (and a painting's --ar), and AVIF sources only while they were made from that master.
    Only the <picture> markup changes; the words around it stay as they are."""
    out, last = [], 0
    for m, folder, name in home_pictures(text):
        rec = MASTERS.rec(folder, name)
        if rec is None or rec.w is None:
            continue
        pattrs, inner = m.group(1), m.group(2)
        im = IMG_TAG_RE.search(inner)
        img = im.group(0)
        for attr, val in (("src", rec.rel), ("width", rec.w), ("height", rec.h)):
            img = re.sub(r'(?<![\w-])' + attr + r'="[^"]*"', f'{attr}="{val}"', img, count=1)
        old = AVIF_SOURCE_RE.search(inner)
        source = ""
        if rec.fresh:
            got = [(w, rel) for w, ext, rel in HOME_VARIANTS.get(rec.rel, []) if ext == "avif"]
            if got:
                classes = (tag_attr(f"<picture{pattrs}>", "class") or "").split()
                sizes = ((tag_attr(old.group(0), "sizes") if old else None)
                         or next((HOME_SIZES[c] for c in classes if c in HOME_SIZES), "100vw"))
                srcset = ", ".join(f"{rel} {w}w" for w, rel in got) + f", {rec.avif} {rec.w}w"
                source = f'<source type="image/avif" srcset="{srcset}" sizes="{sizes}">'
            else:
                source = f'<source type="image/avif" srcset="{rec.avif}">'
        new = inner.replace(im.group(0), img, 1)
        new = new.replace(old.group(0), source, 1) if old else new.replace(img, source + img, 1)
        if "--ar:" in pattrs:
            pattrs = re.sub(r"--ar:[0-9.]+", f"--ar:{format(round(rec.w / rec.h, 4), 'g')}", pattrs)
        out.append(text[last:m.start()] + f"<picture{pattrs}>{new}</picture>")
        last = m.end()
    out.append(text[last:])
    return "".join(out)


SCHEMA_DOC = """Optional project fields (content/projects/<slug>.json), on top of the required schema:

  plates          [{"image": <images key>, "caption": "≤60 chars"}] × 2 — the two home PLATES for this case.
                  Absent: the hero (caption = title) plus the first process image (caption = its heading).
                  Plates are numbered <sheet>.1 / <sheet>.2 and interleaved round-robin by project order.
  metrics[].dim   "≤14 chars" — dimension string printed on the metric's dimension line
                  ("2011–17", "per project", "6 mo vs 6 mo"). Without it a delta metric shows its figure alone.
  metrics[].method  1-based number of a deeper[] note that explains how the figure was measured.
                  Default: the deeper note whose title starts with "How we measured", if any.
  revisions       [{"rev": "A", "label": "≤24", "date": "≤12", "href": "#anchor"}] × 1–4 — the title-block
                  revisions. Default: A Discovery (year_start, #challenge), B Launch (year_end, #decisions),
                  C After launch (last after_launch.when, #after). Anchors: #challenge #role #constraints
                  #principles #decisions #compare #gallery #system #after #learnings #deeper #next #p-<process id>.
  constraints_title  "≤40 chars" — heading of the constraints section. Default "What we had to work within";
                  use "Code requirements" only for compliance or code constraints.
  baseline        "≤60 chars" — the state at launch, shown under "Launch" in the after-launch chain.
  compare.modes   ["wipe"] (default) or ["wipe", "overlay"] — overlay fades one sheet into the other; use it only
                  where both images share geometry.
  seo.title       "≤60 chars" — the <title>. Default "<title> — <site name>".
  images.<name>.mobile  name of another image: a tight crop of the annotated area, served below 600px
                  (the lightbox still opens the full plate).
  images          cover + hero + 4–10 more. Names must not end in -<digits> (the build's size variants).
  reading_minutes is computed from the prose at 230 wpm; do not enter it.

Build outputs from the images: <name>.avif next to each master, assets/img/sizes/<slug>/<name>-1200|1600.avif
and <name>-1200.jpg (macOS sips; made again when a master's sha256 differs from assets/img/masters.json;
--no-variants skips them, and a changed master is then served as it is).
Home markers filled by the build: NAV FOOTER WORK INDEX ARTIFACT:<id> PLATES THUMB:<slug>."""


DEFAULT_BOOT = (
    "<script>(function(d,p){try{p=JSON.parse(localStorage.getItem('folio.prefs'))||{}}catch(x){p={}}"
    "var m=function(q){return matchMedia(q).matches};d.dataset.theme=p.theme||(m('(prefers-color-scheme: dark)')"
    "?'blueprint':'paper');if(p.contrast==='more'||m('(prefers-contrast: more)'))d.dataset.contrast='more';"
    "if(p.motion!=='off'&&!m('(prefers-reduced-motion: reduce)'))d.dataset.motion='full';d.dataset.plot='done';"
    "if(p.keys==='off')d.dataset.keys='off'})(document.documentElement)</script>")


def gz(data: bytes) -> float:
    return len(gzip.compress(data, 9)) / 1024.0


def run_budgets(root: Path, boot: str):
    rows = []

    def size_of(rel):
        fp = root / rel
        return gz(fp.read_bytes()) if fp.exists() else None
    bt = gz(re.sub(r"</?script[^>]*>", "", boot).encode()) if boot else None
    sizes = {
        "boot": bt,
        "main.js": size_of("assets/js/main.js"),
        "hero-gl.js": size_of("assets/js/hero-gl.js"),
        "home.js": size_of("assets/js/home.js"),
        "hinge-gl.js": size_of("assets/js/hinge-gl.js"),
        "case.js": size_of("assets/js/case.js"),
        "main.css": size_of("assets/css/main.css"),
        "case.css": size_of("assets/css/case.css"),
        "artifacts.css": size_of("assets/css/artifacts.css"),
    }
    for k in ("boot", "main.js", "hero-gl.js", "home.js", "hinge-gl.js", "case.js", "main.css", "case.css",
              "artifacts.css"):
        v = sizes[k]
        lim = BUDGETS_KB.get(k)
        if v is None:
            rows.append((k, None, lim, "missing"))
            R.warn("budgets", k, "file not found, not measured")
            continue
        ok = lim is None or v <= lim
        rows.append((k, v, lim, "ok" if ok else "OVER"))
        if not ok:
            R.err("budgets", k, f"{v:.2f} KB gzip exceeds {lim} KB", True)
    for page, parts in JS_PAGES.items():
        tot = sum(sizes[x] or 0 for x in parts)
        ok = tot <= BUDGETS_KB["js-page"]
        rows.append((page, tot, BUDGETS_KB["js-page"], "ok" if ok else "OVER"))
        if not ok:
            R.err("budgets", page, f"{tot:.2f} KB gzip exceeds {BUDGETS_KB['js-page']} KB", True)
    return rows


# =================================================================== main
def write_if_changed(path: Path, data, written: list, check: bool):
    if isinstance(data, str):
        data = data.encode("utf-8")
    if path.exists() and path.read_bytes() == data:
        return False
    if check:
        written.append(str(path) + " (stale)")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    written.append(str(path))
    return True


JSON_HINTS = (
    ("Expecting ',' delimiter", "a comma is missing at the end of this line, or the text on it has a straight "
                                "double quote (\") inside; use curly quotes “ ” inside a text"),
    ("Expecting property name", "there is a comma too many before a closing } or ], or a name has lost "
                                "its double quotes"),
    ("Expecting ':' delimiter", "a colon (:) is missing after a name in double quotes"),
    ("Expecting value", "a value is missing: a comma too many before a closing ] or }, or a text without "
                        "its opening double quote"),
    ("Unterminated string", "a text has no closing double quote"),
    ("Invalid control character", "a text has lost its closing double quote, or runs onto a new line; keep "
                                  "each text on one line, between its two double quotes"),
    ("Invalid \\", "a backslash (\\) in a text; remove it"),
    ("Extra data", "there is more after the last closing }; remove it"),
)


def json_problem(x: json.JSONDecodeError, text: str, rel: str):
    """(where, plain-English message) for a JSON syntax error."""
    hint = next((h for k, h in JSON_HINTS if x.msg.startswith(k)), x.msg)
    line = x.lineno
    lines = text.splitlines()
    curly = "“”‘’„"
    straight = 'the quotes around each name and each text must be straight double quotes ("), not curly ones'
    if text[x.pos:x.pos + 1] in curly and x.msg.startswith(("Expecting property name", "Expecting value")):
        hint = f"a name or a text starts with a curly quote: {straight}"   # pasted from Notes or Word
    elif x.msg.startswith("Expecting value") and re.match(r"(true|false|yes|no|null|none)\b", text[x.pos:], re.I):
        hint = "write true or false in small letters and without quotes; any other text goes between double quotes"
    elif x.msg.startswith(("Expecting ',' delimiter", "Expecting property name", "Expecting value")):
        # reported at the next entry; the cause is where the text before it ends
        before = text[:x.pos].rstrip()
        line = before.count("\n") + 1 if before else 1
    if x.msg.startswith(("Invalid control character", "Unterminated string")) and 0 < line <= len(lines) \
            and re.search(r'[“”]\s*,?\s*$', lines[line - 1]):
        hint = f"this text ends with a curly quote: {straight}"
    near = lines[line - 1].strip() if 0 < line <= len(lines) else ""
    if len(near) > 80:
        near = near[:77] + "…"
    return f"{rel} line {line}", hint + (f". Near: {near}" if near else "")


def read_json(fp: Path, rel: str):
    try:
        text = fp.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        R.err(rel, "-", "is not UTF-8 text")
        return None
    except OSError as x:
        R.err(rel, "-", f"cannot read: {x}")
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as x:
        where, msg = json_problem(x, text, rel)
        R.err(where, "JSON", msg)
        return None


def content_date(fp: Path, root: Path) -> str:
    """When a content file last changed: its last commit in --ci (a fresh checkout has no useful
    file times), else the file time."""
    if CI and (root / ".git").exists():
        try:
            r = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%cs", "--", str(fp)],
                               capture_output=True, text=True)
            if r.returncode == 0 and re.fullmatch(r"\d{4}-\d\d-\d\d", r.stdout.strip()):
                return r.stdout.strip()
        except OSError:
            pass
    return datetime.date.fromtimestamp(fp.stat().st_mtime).isoformat()


def refresh_masters(root: Path, content: Path) -> int:
    """--refresh-masters: records every picture's current master as the one its AVIF and sizes
    were made from (run after making them outside the build), and what each link-preview card in
    assets/img/og/ shows (run after making the cards)."""
    MASTERS.load(root)
    MASTERS.known = {}
    recs, projects = [], []
    site = read_json(content / "site.json", "content/site.json")
    site = site if isinstance(site, dict) else {}
    for fp in sorted((content / "projects").glob("*.json")):
        rel = f"content/projects/{fp.name}"
        p = read_json(fp, rel)
        if not isinstance(p, dict) or not is_str(p.get("slug")) or not isinstance(p.get("images"), dict):
            continue
        projects.append(p)
        for name in p["images"]:
            rec = MASTERS.get(case_dir(p["slug"]), name, rel, strict=True)
            if rec is None:
                R.err(rel, name, f"no file for {case_dir(p['slug'])}/{name}")
            recs.append(rec)
    if (root / "index.html").exists():
        text = (root / "index.html").read_text(encoding="utf-8")
        for m, folder, name in home_pictures(text):
            rec = MASTERS.get(folder, name, "index.html", strict=True)
            if rec is None:
                R.err("index.html", name, f"no file for {folder}/{name}")
            recs.append(rec)
    for rec in recs:
        if rec is not None:
            MASTERS.record(rec)
            if not (root / rec.avif).is_file():
                R.warn(rec.rel, "avif", f"{rec.avif} does not exist yet; the next full build on a Mac makes it")
    index_text = (root / "index.html").read_text(encoding="utf-8") if (root / "index.html").exists() else None
    for key, fp in og_prints([smarten(p) for p in projects], index_text, site).items():
        if (root / key).is_file():
            MASTERS.known[key] = fp
        else:
            R.warn(key, "link preview", "no card file; the page's link preview uses its hero picture")
    for where, field, msg in R.warnings:
        print(f" WARN  {where} · {field} · {msg}")
    for where, field, msg in R.errors:
        print(f" ERROR {where} · {field} · {msg}")
    if R.errors:
        print(f" {MANIFEST_REL} not written")
        return 1
    written = []
    write_if_changed(root / MANIFEST_REL, MASTERS.manifest(), written, False)
    cards = sum(1 for k in MASTERS.known if k.startswith(OG_DIR + "/"))
    print(f" {MANIFEST_REL}: {len(MASTERS.known) - cards} pictures, {cards} link-preview cards · "
          f"{'written' if written else 'unchanged'}")
    return 0


def publish(root: Path, out: Path) -> int:
    """--out: copies the files the site serves (and nothing else) into a fresh folder."""
    out = out.resolve()
    if out == root or out in root.parents or any(out == root / d or (root / d) in out.parents
                                                 for d in PUBLISH_DIRS + ("content", "tools", "templates")):
        R.err(str(out), "--out", "must be a separate folder such as _site")
        return 0
    if out.exists():
        if not out.is_dir() or (out / ".git").exists() or (out / "content").exists():
            R.err(str(out), "--out", "exists and is not an earlier build output; choose another folder")
            return 0
        shutil.rmtree(out)
    out.mkdir(parents=True)
    n = 0
    for f in PUBLISH_FILES:
        if (root / f).is_file():
            shutil.copy2(root / f, out / f)
            n += 1
    manifest = (root / MANIFEST_REL).resolve()

    def skip(folder, names):   # and picture files a browser cannot show (an iPhone HEIC upload)
        return [x for x in names if x == ".DS_Store" or (Path(folder) / x).resolve() == manifest
                or Path(x).suffix.lower() in UNSUPPORTED_EXT]
    for d in PUBLISH_DIRS:
        if (root / d).is_dir():
            shutil.copytree(root / d, out / d, ignore=skip)
            n += sum(1 for f in (out / d).rglob("*") if f.is_file())
    return n


def annotate():
    """GitHub Actions: each error, and each upload that changed nothing or needs a smaller copy,
    also shows on the run page (red and yellow notes) with its file and line."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return

    def esc(t, prop=False):
        t = str(t).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        return t.replace(":", "%3A").replace(",", "%2C") if prop else t
    for level, rows in (("error", R.errors), ("warning", R.shown)):
        for where, field, msg in rows:
            m = re.match(r"^(.+?)(?: line |:)(\d+)$", where)
            f, ln = (m.group(1), m.group(2)) if m else (where, "")
            props = f"file={esc(f, True)}" + (f",line={ln}" if ln else "")
            print(f"::{level} {props}::{esc(where + ('' if field in ('-', 'picture') else ' · ' + field) + ' · ' + msg)}")


def shape_error(where: str, x: Exception):
    R.err(where, "-", f"a value here has a shape the page cannot use ({type(x).__name__}: {x}), such as a list "
                      "where one text belongs, or the reverse. Undo the last edit to this file, or compare the "
                      "lines with the same part of another case's file")


def guarded(where: str, fn, *args, default=""):
    """fn(*args); in --ci an unexpected shape in a content file becomes an error naming the file."""
    try:
        return fn(*args)
    except Exception as x:  # noqa: BLE001
        if not CI:
            raise
        shape_error(where, x)
        return default


def stop_early() -> int:
    """Reports the errors so far and stops: a file every page needs could not be used."""
    line = "─" * 72
    print(line)
    for where, field, msg in R.warnings:
        print(f" WARN  {where} · {field} · {msg}")
    for where, field, msg in R.errors:
        print(f" ERROR {where} · {field} · {msg}")
    print(f" Result: FAILED · {len(R.errors)} error(s) · {len(R.warnings)} warning(s)")
    print(" Nothing was " + ("published: the site keeps its previous version" if CI else "written")
          + ". Fix the line named above and save again.")
    print(line)
    annotate()
    return 1


def main(argv=None):
    global CI
    ap = argparse.ArgumentParser(description="Build the folio site.")
    ap.add_argument("--check", action="store_true", help="validate only; write nothing")
    ap.add_argument("--ci", action="store_true", help="publishable build: house-style rules only warn")
    ap.add_argument("--out", help="copy the publishable files into this folder (e.g. _site)")
    ap.add_argument("--refresh-masters", action="store_true",
                    help=f"record the current pictures in {MANIFEST_REL} and exit")
    ap.add_argument("--grain", action="store_true", help="write assets/img/grain.png only")
    ap.add_argument("--fonts", action="store_true", help="no-op: fonts load from one Google Fonts stylesheet")
    ap.add_argument("--offline", action="store_true", help="no network access")
    ap.add_argument("--allow-missing-images", action="store_true", help="development only")
    ap.add_argument("--content", help="alternate content folder (site.json + projects/)")
    ap.add_argument("--root", help="build another copy of the site")
    ap.add_argument("--no-variants", action="store_true", help="do not generate the responsive image sizes")
    ap.add_argument("--schema", action="store_true", help="print the optional project fields and exit")
    args = ap.parse_args(argv)
    if args.schema:
        print(SCHEMA_DOC)
        return 0
    root = Path(args.root).resolve() if args.root else REPO
    content = Path(args.content).resolve() if args.content else root / "content"
    written = []
    today = datetime.date.today().isoformat()
    CI = args.ci or os.environ.get("GITHUB_ACTIONS") == "true"

    if args.grain:
        png = write_grain()
        write_if_changed(root / "assets" / "img" / "grain.png", png, written, False)
        print(f"grain.png  128×128 · seed 1913 · {len(png)} bytes · {'written' if written else 'unchanged'}")
        return 0
    if args.refresh_masters:
        return refresh_masters(root, content)
    if args.fonts:
        R.note("Fonts", "--fonts is a no-op: fonts load from one Google Fonts stylesheet")
    if CI:
        R.note("Mode", "--ci: house-style rules warn")

    # ---------------------------------------------------------- load
    MASTERS.load(root)
    site = read_json(content / "site.json", "content/site.json")
    if site is not None and not isinstance(site, dict):
        R.err("content/site.json", "-", "must be a JSON object: { … }")
    if isinstance(site, dict):
        validate_site(site, "content/site.json")
        site["_mdate"] = content_date(content / "site.json", root)
    else:
        site = {}
    if R.errors:   # every page needs site.json: nothing can be built until it reads again
        return stop_early()
    projects = []
    pdir = content / "projects"
    files = sorted(pdir.glob("*.json")) if pdir.exists() else []
    if not files:
        R.warn("content/projects", "-", "no project files found")
    for fp in files:
        p = read_json(fp, f"content/projects/{fp.name}")
        if p is None:
            continue
        if not isinstance(p, dict):
            R.err(f"content/projects/{fp.name}", "-", "must be a JSON object")
            continue
        n_before = len(R.errors)
        guarded(f"content/projects/{fp.name}", validate_project, p, fp.name, site, root, args.allow_missing_images)
        p["_file"] = fp.name
        p["_mdate"] = content_date(fp, root)
        p["_ok"] = len(R.errors) == n_before
        projects.append(p)
    for k in ("sheet", "order"):
        seen = {}
        for p in projects:
            key = p.get(k) if isinstance(p.get(k), (str, int)) else repr(p.get(k))
            if key in seen:
                R.err(f"content/projects/{p['_file']}", k, f"{p.get(k)!r} also used by {seen[key]}", True)
            seen[key] = p["_file"]
    slugs = {p.get("slug") for p in projects if is_str(p.get("slug"))}
    for p in projects:
        for s in p.get("next") if isinstance(p.get("next"), list) else []:
            if not is_str(s) or s not in slugs:
                R.err(f"content/projects/{p['_file']}", "next", f"{s!r} is not a project slug", True)
    if len(projects) != 6:
        R.warn("content/projects", "-", f"expected 6 projects, found {len(projects)}")
    # Typographer's quotes for everything rendered from the project files (after validation).
    projects = [smarten(p) for p in projects]
    good = [p for p in projects if p.get("_ok")]
    ctx = Ctx(root, site, good, args)

    # ---------------------------------------------------------- pictures
    index_path = root / "index.html"
    index_text = index_path.read_text(encoding="utf-8") if index_path.exists() else None
    home_recs = []
    if index_text is not None:
        for m, folder, name in home_pictures(index_text):
            where = f"index.html:{index_text.count(chr(10), 0, m.start()) + 1}"
            rec = MASTERS.get(folder, name, where, strict=not CI)
            if rec is None:
                R.err(where, "picture", f"no file for {folder}/{name} (.jpg or .png): upload the picture as "
                                        f"{folder}/{name}.jpg")
            elif rec.size is None:
                R.err(rec.rel, "picture", unreadable(rec))
            home_recs.append(rec)
    for rel, msg in MASTERS.upload_notes():
        R.warn(rel, "picture", msg, show=True)
    # link-preview cards: each is used only while it shows what its page shows
    for key, fp in og_prints(good, index_text, site).items():
        name = Path(key).stem
        OG_FRESH[name] = MASTERS.known.get(key) == fp and (root / key).is_file()
        if OG_FRESH[name] or not MASTERS.found:
            continue
        what = ("the cover sheet's earlier words" if name == "home" else
                "this case's earlier title, results line, sector, years, role or cover")
        if CI:
            R.warn(key, "link preview", f"this card shows {what}, so link previews of the page use "
                                        + ("the About photo" if name == "home" else "the hero picture") + " instead")
        else:
            R.err(key, "link preview", f"this card shows {what}: make it again, then record it with "
                                       "python3 tools/build.py --refresh-masters", True)
    can_make = (not CI and not args.check and not args.no_variants and not R.errors and MASTERS.found
                and shutil.which("sips") is not None)
    tally = ensure_variants(root, good, home_recs, can_make=can_make, written=written)
    if not MASTERS.found:
        R.err(MANIFEST_REL, "-", "missing: run python3 tools/build.py --refresh-masters once", True)
    else:
        for rec in tally["stale"]:
            if CI:
                R.warn(rec.rel, "picture", "new picture: shown as uploaded")
                size = rec.path.stat().st_size
                if size > BIG_UPLOAD[0] or (rec.w or 0) > BIG_UPLOAD[1]:
                    want = 2400 if rec.name == "hero" else 1200 if rec.name in ("cover", "portrait") else 2000
                    R.warn(rec.rel, "picture", f"{size / 1048576:.1f} MB, {rec.w}×{rec.h} px: pages with this picture "
                                               f"load slowly, on phones most of all. Make a smaller copy (Preview → "
                                               f"Tools → Adjust Size…, width {want}) and upload it under the same "
                                               f"name, {rec.path.name}", show=True)
            elif args.check:
                written.append(str(root / rec.avif) + " (stale)")
            else:
                (R.warn if args.allow_missing_images else R.err)(
                    rec.rel, "picture", "changed since its AVIF and sizes were made; build on a Mac (sips) "
                                        "without --no-variants to make them again")
    if MASTERS.dirty and not args.check:
        write_if_changed(root / MANIFEST_REL, MASTERS.manifest(), written, False)
    n_var = sum(len(v["avif"]) + (1 if v["jpg"] else 0) for v in VARIANTS.values())
    R.note("Sizes", f"{n_var} responsive variants in {SIZES_DIR}/ ({tally['made']} made, {tally['missing']} missing)"
           + (f" · {len(tally['stale'])} picture(s) served as uploaded" if tally["stale"] else ""))
    for p in good:
        if (p.get("system") or {}).get("type"):
            SPECIMEN_FONTS[p["slug"]] = specimen_fonts(p, args.offline or CI)
            url, ok = SPECIMEN_FONTS[p["slug"]]
            for fam, yes in ok.items():
                if not yes:
                    R.warn(f"content/projects/{p['_file']}", "system.type",
                           f"{fam!r} is not on Google Fonts (or the weight is not); the specimen says 'shown in Mona Sans'")
    mins = {p["slug"]: reading_minutes(p) for p in good}
    if mins:
        R.note("Reading", " · ".join(f"{s} {m}" for s, m in mins.items())
               + f" min ({WPM} wpm; median {sorted(mins.values())[len(mins) // 2]})")

    # ---------------------------------------------------------- home page
    canon_total = canon_ok = 0
    home_stats = {}
    nav = footer = ""
    boot, font_links = DEFAULT_BOOT, []
    skip, main_id = "", "main"
    if index_text is None:
        R.err("index.html", "-", "missing; NAV/FOOTER cannot be copied")
    else:
        b, fl = extract_head_parts(index_text)
        if b:
            boot = b
        else:
            R.warn("index.html", "<head>", "no inline boot script found; case pages use the built-in one")
        font_links = fl
        if site.get("canon"):
            cp = CanonParser()
            cp.feed(index_text)
            for c in cp.found:
                canon_total += 1
                key = c["key"]
                if key not in site["canon"]:
                    R.err(f"index.html:{c['line']}", "data-canon", f"unknown canon key {key!r}", True)
                    continue
                want = squash(site["canon"][key])
                got_all, got_acc = squash("".join(c["all"])), squash("".join(c["acc"]))
                if want in (got_all, got_acc):
                    canon_ok += 1
                else:
                    R.err(f"index.html:{c['line']}", f"data-canon={key}", f"text {got_acc or got_all!r} ≠ canon {want!r}",
                          True)
    # skip link
    if index_text:
        nav_inner = marker_inner(index_text, "NAV")
        foot_inner = marker_inner(index_text, "FOOTER")
        if nav_inner is None:
            R.err("index.html", "NAV markers", "<!-- NAV:START --> / <!-- NAV:END --> not found")
        if foot_inner is None:
            R.err("index.html", "FOOTER markers", "<!-- FOOTER:START --> / <!-- FOOTER:END --> not found")
        body = index_text.split("<body", 1)[1] if "<body" in index_text else index_text
        sk = re.search(r'<a\b[^>]*href=["\']#([\w-]+)["\'][^>]*>\s*Skip[^<]*</a>', body, re.I)
        if sk:
            main_id = sk.group(1)
            if not nav_inner or sk.group(0) not in nav_inner:
                skip = sk.group(0)
        else:
            skip = '<a class="skip-link" href="#main">Skip to content</a>'

    # a slip in the hand-edited pages (a tag with a letter typed into it, a deleted '<') would cut
    # content from the live page without any other sign
    tag_bad = 0
    p404 = root / "404.html"
    for rel, text in (("index.html", index_text), ("404.html", p404.read_text(encoding="utf-8")
                                                    if p404.exists() else None)):
        if text is None:
            continue
        probs = tag_problems(text)
        tag_bad += len(probs)
        for ln, msg in probs[:3]:
            R.err(f"{rel}:{ln}", "tags", msg)
    html_note = "index.html and 404.html ok" if not tag_bad else f"{tag_bad} problem(s) in index.html / 404.html"

    # Validation errors block every write, so a bad content file never ships a half-built site.
    blocked = bool(R.errors) and not args.check
    if blocked:
        args.check = True
        R.note("Blocked", "validation failed: no outputs written (fix the errors above, then rebuild)")

    # ---------------------------------------------------------- CV files
    for i, c in enumerate(site.get("cv") or []):
        if not isinstance(c, dict) or not is_str(c.get("file")):
            continue
        fp = root / c["file"].lstrip("/")
        if c["file"].startswith("/"):
            R.warn("content/site.json", f"cv[{i}].file", "use a relative path (assets/cv/…), not one that starts with /")
        if not fp.exists():
            R.err("content/site.json", f"cv[{i}].file", f"{c['file']} not found")
            continue
        data = fp.read_bytes()
        pages = len(re.findall(rb"/Type\s*/Page(?![s\w])", data))
        R.note("CV", f"{c.get('label')}: {pages} pp, {len(data) / 1024:.0f} KB ({fp.name})")

    # ---------------------------------------------------------- inject home
    if index_text is not None and good:
        new = index_text
        rows = "\n".join(guarded(f"content/projects/{p['_file']}", register_row, p) for p in ctx.ordered)
        new, ok = inject(new, "WORK", rows)
        home_stats["WORK"] = f"{len(ctx.ordered)} rows" if ok else "markers missing"
        if not ok:
            R.err("index.html", "WORK markers", "<!-- WORK:START --> / <!-- WORK:END --> not found")
        if marker_block(new, "PLATES"):
            pl = plates_html(ctx.ordered)
            new, _ = inject(new, "PLATES", "\n".join(pl))
            per = {p["slug"]: len(guarded(f"content/projects/{p['_file']}", plate_list, p, default=[]))
                   for p in ctx.ordered}
            home_stats["PLATES"] = f"{len(pl)} plates"
            # the heading names the count in words: <span data-plates-word>Twelve</span>
            words = ("Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen Fourteen Fifteen "
                     "Sixteen Seventeen Eighteen Nineteen Twenty").split()
            word = words[len(pl)] if len(pl) < len(words) else str(len(pl))
            new = re.sub(r'(<span data-plates-word>)[^<]*(</span>)', lambda m: m.group(1) + word + m.group(2), new)
            for p in ctx.ordered:
                if per[p["slug"]] != 2:
                    R.warn(f"content/projects/{p['_file']}", "plates", f"{per[p['slug']]} plate(s); the gallery takes 2")
                elif not p.get("plates"):
                    R.note("Plates", f"{p['slug']}: no plates[] in the JSON; using the hero and the first process image")
        else:
            home_stats["PLATES"] = "markers missing"
        nthumb = 0
        for m in list(re.finditer(r"<!-- THUMB:([a-z0-9-]+):START -->", new)):
            q = ctx.by_slug.get(m.group(1))
            if not q:
                R.err("index.html", f"THUMB:{m.group(1)}", "no project with this slug")
                continue
            new, _ = inject(new, f"THUMB:{q['slug']}", guarded(f"content/projects/{q['_file']}", thumb_html, q))
            nthumb += 1
        if nthumb:
            home_stats["THUMB"] = f"{nthumb} thumbs"
        items = "\n".join(guarded(f"content/projects/{p['_file']}", index_item, p) for p in ctx.ordered)
        new, ok = inject(new, "INDEX", items)
        home_stats["INDEX"] = f"{len(ctx.ordered)} items" if ok else "markers missing"
        if not ok:
            R.err("index.html", "INDEX markers", "<!-- INDEX:START --> / <!-- INDEX:END --> not found")
        dt = ctx.by_slug.get("design-team")
        arts = {a["id"]: a for a in (dt.get("artifacts") or [])} if dt else {}
        filled = 0
        for aid in HOME_ARTIFACTS:
            if marker_block(new, f"ARTIFACT:{aid}") is None:
                R.warn("index.html", f"ARTIFACT:{aid}", "marker not found")
                continue
            if aid not in arts:
                R.err("content/projects/design-team.json", "artifacts", f"no artifact {aid!r} for the home marker")
                continue
            new, _ = inject(new, f"ARTIFACT:{aid}", guarded("content/projects/design-team.json", render_artifact,
                                                           arts[aid]))
            filled += 1
        for m in re.finditer(r"<!-- ARTIFACT:([a-z0-9-]+):START -->", new):
            if m.group(1) not in HOME_ARTIFACTS:
                if m.group(1) in arts:
                    new, _ = inject(new, f"ARTIFACT:{m.group(1)}", guarded("content/projects/design-team.json",
                                                                          render_artifact, arts[m.group(1)]))
                    filled += 1
                else:
                    R.err("index.html", f"ARTIFACT:{m.group(1)}", "no artifact with this id in design-team.json")
        home_stats["ARTIFACT"] = f"{filled}/{len(HOME_ARTIFACTS)}"
        counts = {"all": len(ctx.ordered)}
        for f in FILTERS:
            counts[f] = sum(1 for p in ctx.ordered if f in p["filters"])
        nchips = 0
        for f, n in counts.items():
            rx = re.compile(r'(<label\b[^>]*\bfor="f-' + f + r'"[^>]*>.*?<span class="chip__n">)(\d*)(</span>)', re.S)
            new, k = rx.subn(lambda m, n=n: m.group(1) + str(n) + m.group(3), new, count=1)
            nchips += k
        home_stats["chips"] = f"{nchips} chip counts"
        if is_str(site.get("email")) and site["email"].strip():
            new = set_email(new, site["email"].strip())
        new = fix_home_pictures(new)
        new = update_head(new, ctx, page="home",
                          robots="noindex, follow" if not site.get("index") else "index, follow")
        if new != index_text:
            write_if_changed(index_path, new, written, args.check)
        index_text = new
    if index_text:
        nav_inner = marker_inner(index_text, "NAV") or ""
        foot_inner = marker_inner(index_text, "FOOTER") or ""
        keep = find_ids(nav_inner) | {main_id}
        nav = rewrite_links(nav_inner.strip("\n"), "../../", keep)
        # case pages have no hero title block: the nav is final-width in the HTML (no shift on load)
        nav = re.sub(r'(<header\b(?=[^>]*\bclass="nav\b)(?![^>]*\bdata-wide)[^>]*?)(\s*/?>)', r"\1 data-wide\2", nav, count=1)
        footer = rewrite_links(foot_inner.strip("\n"), "../../", find_ids(foot_inner) | {main_id})
        if foot_inner and not re.search(r"\bdata-sheet\b", foot_inner):
            R.warn("index.html", "FOOTER", "no [data-sheet] element; case sheet numbers not written")

    # ---------------------------------------------------------- fonts head
    if font_links:
        fonts = "\n".join(font_links)
    else:
        fonts = ('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
                 '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
                 f'<link rel="stylesheet" href="{e(FONT_URL)}">')
    if not args.offline and not CI:
        m = re.search(r'href="(https://fonts\.googleapis\.com/css2[^"]+)"', fonts)
        url = html.unescape(m.group(1)) if m else FONT_URL
        try:
            req = urllib.request.Request(url, headers={"User-Agent": CHROME_UA})
            with urllib.request.urlopen(req, timeout=8) as r:
                R.note("Fonts", f"Google Fonts stylesheet HTTP {r.status}")
        except Exception as x:  # noqa: BLE001
            R.warn("fonts", "stylesheet", f"could not fetch the Google Fonts URL: {x}")

    # ---------------------------------------------------------- cases
    tpl_path = root / "templates" / "case.html"
    tpl = tpl_path.read_text(encoding="utf-8") if tpl_path.exists() else None
    if tpl is None:
        R.err("templates/case.html", "-", "missing")
    case_pages = []
    if tpl and good:
        for p in ctx.ordered:
            ft = footer
            if ft:
                ft = re.sub(r"(<[^>]*\bdata-sheet\b[^>]*>)(.*?)(</[a-zA-Z]+>)",
                            lambda m: m.group(1) + e(p["sheet"]) + m.group(3), ft, count=1, flags=re.S)
            out = guarded(f"content/projects/{p['_file']}", render_case, ctx, p, tpl, nav, ft, boot, fonts, skip,
                          main_id, default=None)
            if out is None:
                continue
            path = root / "work" / p["slug"] / "index.html"
            write_if_changed(path, out, written, args.check)
            case_pages.append((path, out))
        # stale case folders
        wdir = root / "work"
        if wdir.exists():
            for d in wdir.iterdir():
                if d.is_dir() and d.name not in ctx.by_slug:
                    R.warn(f"work/{d.name}/", "-", "no project JSON for this generated folder (stale output?)")
    # redirect page
    if site:
        redirect = (
            '<!doctype html>\n<html lang="en-CA">\n<head>\n<meta charset="utf-8">\n'
            f'<title>Drawing register · {e(site.get("name", ""))}</title>\n'
            '<meta name="robots" content="noindex, follow">\n'
            f'<link rel="canonical" href="{e(ctx.abs())}">\n'
            '<meta http-equiv="refresh" content="0;url=../#work">\n</head>\n<body>\n'
            '<p><a href="../#work">The drawing register is on the cover sheet.</a></p>\n</body>\n</html>\n')
        write_if_changed(root / "work" / "index.html", redirect, written, args.check)
    # 404
    p404 = root / "404.html"
    base_note = "missing"
    if p404.exists() and site:
        t404 = p404.read_text(encoding="utf-8")
        new404, n = set_attr_in_tag(t404, r"<base\b[^>]*>", "href", site.get("base_path", "/"))
        if n == 0:
            new404 = re.sub(r"(<head[^>]*>)", r'\1\n<base href="' + e(site.get("base_path", "/")) + '">', new404, count=1)
        new404 = update_head(new404, ctx, page="404", robots="noindex, follow")
        if re.search(r'(?:href|src)=["\']/(?!/)', re.sub(r"<base\b[^>]*>", "", new404)):
            R.warn("404.html", "urls", "root-absolute URL found; use base-relative URLs")
        write_if_changed(p404, new404, written, args.check)
        base_note = f'<base href="{site.get("base_path", "/")}">'
    else:
        R.warn("404.html", "-", "not found")
    # SEO files
    if site and good:
        urls = [ctx.abs()] + [ctx.abs(f"work/{p['slug']}/") for p in ctx.ordered]
        sm = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
              + "".join(f"  <url><loc>{e(u)}</loc><lastmod>{today}</lastmod></url>\n" for u in urls)
              + "</urlset>\n")
        write_if_changed(root / "sitemap.xml", sm, written, args.check)
        write_if_changed(root / "robots.txt",
                         f"User-agent: *\nAllow: /\nSitemap: {ctx.abs('sitemap.xml')}\n", written, args.check)
        write_if_changed(root / ".nojekyll", b"", written, args.check)
        cn = site.get("canon", {})
        llms = [f"# {site['name']} — Design Lead, Vancouver", "",
                f"> {site.get('description', '')}", "",
                f"- Role: {site.get('title', '')}",
                f"- Based in: {site.get('location', 'Vancouver, BC')}",
                f"- Scope: {cn.get('career.years', '')} · {cn.get('career.digital', '')} · "
                f"{cn.get('shopify.apps', '')}",
                f"- Contact: {site.get('email', '')}"]
        if site.get("linkedin"):
            llms.append(f"- LinkedIn: {site['linkedin']}")
        llms += ["", "## Sheets", ""]
        for p in ctx.ordered:
            llms.append(f"- [{p['sheet']} · {p['title']}]({ctx.abs('work/' + p['slug'] + '/')}): {p['hook']} "
                        f"{p['sector']}, {p['years']}. Outcomes: {p['register_line']}.")
        llms += ["", "## Pages", "", f"- [Cover sheet and drawing register]({ctx.abs()})",
                 f"- [Leadership ledger]({ctx.abs()}#leadership)", f"- [Studio: paintings]({ctx.abs()}#studio)",
                 f"- [Contact]({ctx.abs()}#contact)", ""]
        write_if_changed(root / "llms.txt", "\n".join(llms), written, args.check)
    # launch checks
    if site:
        if site.get("base_path", "/") != "/":
            R.warn("content/site.json", "base_path", "project site: crawlers read only /robots.txt at the host root, "
                   "so submit sitemap.xml in Search Console yourself")
        if site.get("index"):
            for path, out in [(root / "index.html", index_text or "")] + case_pages:
                if re.search(r'<meta\b[^>]*name="robots"[^>]*content="noindex', out):
                    R.err(os.path.relpath(path, root), "robots", "site.json index=true but this page still says noindex")
    # grain (plain run writes it too; deterministic)
    if not args.check:
        write_if_changed(root / "assets" / "img" / "grain.png", write_grain(), written, False)

    # ---------------------------------------------------------- page checks
    stray = 0
    outputs = [(path, out) for path, out in case_pages]
    for rel in ("index.html", "404.html", "work/index.html"):
        fp = root / rel
        if fp.exists():
            outputs.append((fp, fp.read_text(encoding="utf-8")))
    for path, out in outputs:
        for m in re.finditer(r"\{\{", out):
            ln = out.count("\n", 0, m.start()) + 1
            R.err(f"{os.path.relpath(path, root)}:{ln}", "stray token", out[m.start():m.start() + 40].split("\n")[0],
                  True)
            stray += 1
    budget_rows = run_budgets(root, boot)

    # ---------------------------------------------------------- summary
    W = 72
    line = "─" * W
    print(line)
    print(f" Folio build · {today} · {root}")
    print(line)
    ok_n = len(good)
    print(f" {'Content':<12}{len(projects)} project file(s), {ok_n} valid · site.json "
          f"{'ok' if site else 'missing'} · canon {len(site.get('canon', {}) or {})} keys")
    n_img = sum(len(p.get('images', {}) or {}) for p in projects)
    print(f" {'Images':<12}{n_img} listed × 2 formats · "
          f"{'missing allowed' if args.allow_missing_images else 'files required'}")
    print(f" {'Cases':<12}{len(case_pages)} page(s): " + ", ".join(p["slug"] for p in ctx.ordered))
    if index_text is not None:
        print(f" {'Home':<12}WORK {home_stats.get('WORK', '-')} · INDEX {home_stats.get('INDEX', '-')} · "
              f"ARTIFACT {home_stats.get('ARTIFACT', '-')} · {home_stats.get('chips', 'chips -')} · data-canon {canon_ok}/{canon_total}")
    if index_text is not None:
        print(f" {'Plates':<12}{home_stats.get('PLATES', '-')}" + (f" · {home_stats['THUMB']}" if home_stats.get("THUMB") else "")
              + " · optional fields: python3 tools/build.py --schema")
    print(f" {'404':<12}{base_note}")
    print(f" {'SEO':<12}sitemap.xml ({1 + len(good)} URLs) · robots.txt · llms.txt · .nojekyll · "
          f"robots meta: {'index' if site.get('index') else 'noindex'}")
    print(f" {'Checks':<12}tags: {html_note} · stray tokens {stray}")
    for lab, txt in R.info:
        print(f" {lab:<12}{txt}")
    print(f" {'Budgets':<12}gzip KB")
    for name, v, lim, st in budget_rows:
        vs = "   —  " if v is None else f"{v:6.2f}"
        ls = "  —" if lim is None else f"{lim:>4}"
        print(f"   {name:<16}{vs} / {ls}  {st}")
    if args.check:
        stale = [w for w in written if w.endswith("(stale)")]
        print(f" {'Check':<12}{len(stale)} output(s) would change")
        for w in stale:
            print(f"   {os.path.relpath(w.replace(' (stale)', ''), root)}")
    else:
        print(f" {'Written':<12}{len(written)} file(s)")
        for w in written:
            print(f"   {os.path.relpath(w, root)}")
    if args.out:
        if R.errors or args.check:
            print(f" {'Published':<12}nothing (--out {args.out}): the build " + ("failed" if R.errors else "ran with --check"))
        else:
            n = publish(root, Path(args.out))
            print(f" {'Published':<12}{n} file(s) to {args.out}" if n else f" {'Published':<12}nothing")
    print(line)
    for where, field, msg in R.warnings:
        print(f" WARN  {where} · {field} · {msg}")
    for where, field, msg in R.errors:
        print(f" ERROR {where} · {field} · {msg}")
    status = "FAILED" if R.errors else "OK"
    print(f" Result: {status} · {len(R.errors)} error(s) · {len(R.warnings)} warning(s)")
    if R.errors and CI:
        print(" Nothing was published: the site keeps its previous version. Fix the first error above "
              "(the file and line are named) and save again.")
    print(line)
    annotate()
    return 1 if R.errors else 0


def run(argv=None) -> int:
    """main() with a plain last word when something unexpected stops a --ci build."""
    try:
        return main(argv)
    except Exception as x:  # noqa: BLE001
        if not CI:
            raise
        import traceback
        traceback.print_exc()
        for where, field, msg in R.errors:
            print(f" ERROR {where} · {field} · {msg}")
        print(f" Result: FAILED · the build stopped ({type(x).__name__}: {x}). Nothing was published: the "
              "site keeps its previous version. Undo the last edit, or fix it, and save again.")
        annotate()
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::error::The build stopped ({type(x).__name__}: {x}); the site keeps its previous version. "
                  "Undo the last edit, or fix it, and save again.")
        return 1


if __name__ == "__main__":
    sys.exit(run())
