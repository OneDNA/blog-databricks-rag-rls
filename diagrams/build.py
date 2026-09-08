"""Generate both .drawio diagrams from the Databricks brand system.

The diagrams are generated rather than hand-written for one reason: the brand rule
("lava marks Databricks, oat marks everything else") plus the enforcement rule
("who enforces this?") have to hold on every single shape. Doing that by hand across
~100 cells is how inconsistencies creep in.

Icons are official Databricks SVGs, embedded as base64 data URIs so the output is
self-contained. Run from this directory:

    python build.py
"""

from __future__ import annotations

import json
import math
import pathlib
import re

ICONS: dict[str, str] = json.loads(pathlib.Path(".icons.json").read_text())

# ── Databricks brand tokens ──────────────────────────────────────────────────────
LAVA = "#FF5F46"       # marks Databricks
LAVA_DEEP = "#FF3621"  # the break, the danger
LAVA_TINT = "#FABFBA"
NAVY = "#143D4A"
NAVY_DEEP = "#1B3139"  # body text
NAVY_SOFT = "#618794"  # secondary text
SLATE = "#A9B8BD"
OAT_LINE = "#D9D7CE"   # marks not-Databricks
OAT = "#EEEDE9"
OAT_LIGHT = "#F9F7F4"
WHITE = "#FFFFFF"
GREEN = "#00A972"      # semantic green — "the platform enforces". Matches chat-response.html.

# DM Sans is the Databricks brand font. `fontSource` fetches it in the web editor, but the
# desktop app and any local render use INSTALLED fonts only -- so without a fallback chain a
# machine that lacks DM Sans silently drops to a default serif. Segoe UI ships with Windows and
# Helvetica with macOS, so the chain covers every viewer while keeping the brand font first.
# "DM Sans 14pt" is what the variable font registers itself as on Windows; plain "DM Sans" is
# the web/Google Fonts name. Listing both means one of them resolves wherever the file is opened.
FONT = (
    "fontFamily=DM Sans, DM Sans 14pt, Segoe UI, Helvetica Neue, Helvetica, Arial, sans-serif;"
    "fontSource=https%3A%2F%2Ffonts.googleapis.com%2Fcss%3F"
    "family%3DDM%2BSans%3A400%2C500%2C700;"
)


# ── Wide type scale ──────────────────────────────────────────────────────────────
# The wide diagrams are shaped for a slide, but the articles embed them in a column
# roughly a third of the canvas width, so the type has to be sized against the canvas
# rather than against the screen. At 2464px wide (the architecture render) a 10px
# detail line lands near 4px in an 820px column -- present in the file, unreadable on
# the page. These sizes put the smallest text near 7-9px there instead.
W_LANE = 22             # lane headers
W_TITLE = 20            # box titles
W_DETAIL = 17           # detail lines
W_NOTE = 19             # note shapes -- beige panels carry real content, not captions
W_STORE = 18            # cylinder labels
W_FOOT = 20             # the beige takeaway strip -- it carries the summary, so it
                        # should not be the smallest type on the page
W_PAGE_TITLE = 34       # the diagram title
W_PAGE_SUB = 20         # its subtitle


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def html(title: str, *lines: str, tcol: str = NAVY_DEEP, tsize: int = W_TITLE,
         dsize: int = W_DETAIL) -> str:
    """Build an XML-escaped inline-HTML label: bold title over small grey detail lines.

    Consolidating into one value (rather than stacking text cells) is what keeps labels
    from overlapping — the problem the drawio skill calls out.

    ``dsize`` sizes the detail lines. The narrow variants raise it, because a diagram
    scaled down to an article column turns 10px into about 5px on screen.
    """
    out = f'<b style="font-size:{tsize}px;color:{tcol};">{title}</b>'
    for ln in lines:
        out += f'<br><span style="font-size:{dsize}px;color:{NAVY_SOFT};">{ln}</span>'
    return esc(out)


# ── Narrow variants ──────────────────────────────────────────────────────────────
# The wide diagrams are built for a slide or a full-width screen. Dropped into an
# article column they scale to roughly 40% and their 10px detail text lands near 4px.
# These rebuild the same content in a portrait frame: lanes stacked rather than side
# by side, larger base fonts, and fewer words per box.

# Sized so the smallest text stays legible in an article column while the diagram keeps
# a shape you can take in at once. 560px was legible but ran to 1:3 -- a ribbon you have
# to scroll. 820px holds 15px detail at about 12px in a 680px column and lets two boxes
# sit side by side, which is what keeps the height down.
NARROW_W = 820
N_TITLE = 17            # box titles
N_DETAIL = 15           # detail lines
N_NOTE = 17             # note shapes -- beige panels carry real content, not captions
N_FOOT = 17             # the beige takeaway strip, a step up from the notes


def n_node(stroke: str, fill: str = WHITE, width: int = 2, dashed: bool = False) -> str:
    d = "dashed=1;dashPattern=6 4;fixDash=1;" if dashed else ""
    return (
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={fill};strokeColor={stroke};"
        f"strokeWidth={width};{d}align=left;spacingLeft=48;verticalAlign=middle;spacing=8;"
        f"fontSize={N_TITLE};fontStyle=0;fontColor={NAVY_DEEP};{FONT}"
    )


def n_plain(stroke: str, fill: str = WHITE, width: int = 2) -> str:
    return (
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={fill};strokeColor={stroke};"
        f"strokeWidth={width};align=center;verticalAlign=middle;spacing=8;"
        f"fontSize={N_TITLE};fontStyle=0;fontColor={NAVY_DEEP};{FONT}"
    )


def n_note(stroke: str = OAT_LINE, fill: str = OAT_LIGHT) -> str:
    return (
        f"shape=note;size=16;html=1;whiteSpace=wrap;fillColor={fill};strokeColor={stroke};"
        f"strokeWidth=1;align=left;verticalAlign=top;spacing=10;fontSize={N_NOTE};"
        f"fontStyle=0;fontColor={NAVY_DEEP};{FONT}"
    )


def n_decision() -> str:
    return (
        f"rhombus;html=1;whiteSpace=wrap;fillColor={WHITE};strokeColor={NAVY};strokeWidth=2;"
        f"align=center;verticalAlign=middle;fontSize={N_TITLE};fontStyle=0;"
        f"fontColor={NAVY_DEEP};{FONT}"
    )


def n_title(txt: str, sub: str = "") -> str:
    """Title only; see title()."""
    return esc(f'<b style="font-size:22px;color:{NAVY_DEEP};">{txt}</b>')


def n_html(title: str, *lines: str, tcol: str = NAVY_DEEP) -> str:
    return html(title, *lines, tcol=tcol, tsize=N_TITLE, dsize=N_DETAIL)


# ── Text fitting ─────────────────────────────────────────────────────────────────
# draw.io does not grow a box to fit its label, so an under-sized box silently
# overlaps its own text. These estimate the rendered height of an inline-HTML label
# and assert the box is big enough, which turns a layout bug into a build failure.

_CH_W = {10: 5.35, 11: 5.85, 12: 6.4, 13: 6.9, 15: 8.0, 16: 8.5, 17: 9.05,
         18: 9.6, 20: 10.6, 22: 11.7, 34: 18.0}


def text_height(parts: list[tuple[str, int]], usable_w: float) -> float:
    """Estimate rendered height, in px, of (text, font-size) runs wrapped to usable_w."""
    total = 0.0
    for txt, size in parts:
        clean = re.sub(r"<[^>]+>", "", txt).replace("&nbsp;", " ")
        for para in clean.split(chr(10)):
            chars = max(len(para), 1)
            lines = max(1, math.ceil(chars * _CH_W.get(size, size * 0.53) / usable_w))
            total += lines * size * 1.42
    return total


def fits(label_parts, w, h, pad_x=0, pad_y=None, name=""):
    """Raise if the label cannot fit the box. Called on every text-bearing shape."""
    if pad_y is None:
        pad_y = 6 if h <= 28 else 16          # a one-line row has little chrome
    need = text_height(label_parts, max(w - pad_x - 16, 24))
    if need > h - pad_y:
        raise SystemExit(
            f"LAYOUT: '{name}' needs ~{need:.0f}px of text height but the box is {h}px "
            f"(usable {h - pad_y}px). Widen or heighten it."
        )
    return True


# ── Style builders, all derived from the brand system ────────────────────────────
def zone(fill: str, fc: str, size: int = 44) -> str:
    return (
        f"swimlane;html=1;whiteSpace=wrap;startSize={size};horizontal=1;fillColor={fill};"
        f"swimlaneFillColor={WHITE};strokeColor={fill};strokeWidth=2;fontColor={fc};"
        f"fontSize={W_LANE};fontStyle=1;align=left;spacingLeft=14;verticalAlign=middle;"
        f"container=1;collapsible=0;{FONT}"
    )


def node(stroke: str, fill: str = WHITE, width: int = 2, dashed: bool = False) -> str:
    d = "dashed=1;dashPattern=6 4;fixDash=1;" if dashed else ""
    return (
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={fill};strokeColor={stroke};"
        f"strokeWidth={width};{d}align=left;spacingLeft=60;verticalAlign=middle;spacing=6;"
        f"fontSize={W_TITLE};fontStyle=0;fontColor={NAVY_DEEP};{FONT}"
    )


def plain(stroke: str, fill: str = WHITE, width: int = 2) -> str:
    return (
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={fill};strokeColor={stroke};"
        f"strokeWidth={width};align=center;verticalAlign=middle;spacing=6;"
        f"fontSize={W_TITLE};fontStyle=0;fontColor={NAVY_DEEP};{FONT}"
    )


def decision() -> str:
    return (
        f"rhombus;html=1;whiteSpace=wrap;fillColor={WHITE};strokeColor={NAVY};strokeWidth=2;"
        f"align=center;verticalAlign=middle;fontSize={W_TITLE};fontStyle=0;fontColor={NAVY_DEEP};{FONT}"
    )


def store(stroke: str) -> str:
    return (
        f"shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=12;html=1;whiteSpace=wrap;"
        f"fillColor={WHITE};strokeColor={stroke};strokeWidth=2;align=center;verticalAlign=middle;"
        f"fontSize={W_STORE};fontStyle=0;fontColor={NAVY_DEEP};{FONT}"
    )


def note(stroke: str = OAT_LINE, fill: str = OAT_LIGHT) -> str:
    return (
        f"shape=note;size=14;html=1;whiteSpace=wrap;fillColor={fill};strokeColor={stroke};"
        f"strokeWidth=1;align=left;verticalAlign=top;spacing=8;fontSize={W_NOTE};fontStyle=0;"
        f"fontColor={NAVY_DEEP};{FONT}"
    )


def icon(slug: str) -> str:
    return (
        f"shape=image;html=1;imageAspect=1;verticalAlign=middle;labelBackgroundColor=none;"
        f"image={ICONS[slug]};"
    )


def edge(color: str = NAVY, width: int = 2, dashed: bool = False, arrow: str = "block",
         fsize: int | None = None) -> str:
    """An orthogonal connector. `fsize` sizes its label.

    Both diagram families share this, so the default follows the wide scale and the
    narrow builders pass N_DETAIL. Left at 10px the edge labels stayed slide-sized
    while every box around them grew, which is exactly the unreadability being fixed.
    """
    d = "dashed=1;dashPattern=6 4;fixDash=1;" if dashed else ""
    return (
        f"edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;jettySize=auto;orthogonalLoop=1;"
        f"endArrow={arrow};endFill=1;strokeColor={color};strokeWidth={width};{d}"
        f"labelBackgroundColor={WHITE};labelBorderColor=none;"
        f"fontSize={fsize or W_DETAIL};fontStyle=1;"
        f"fontColor={NAVY_DEEP};{FONT}"
    )


def title(txt: str, sub: str = "") -> str:
    """Just the title. The subtitle used to sit under it, but the articles
    introduce each diagram in the sentence above it, so it only repeated them."""
    return esc(f'<b style="font-size:{W_PAGE_TITLE}px;color:{NAVY_DEEP};">{txt}</b>')


def check_layout(cells_xml: str, badges: dict | None = None) -> None:
    """Fail the build if an edge waypoint lands inside a shape it does not connect.

    draw.io resolves waypoints against the edge's PARENT, not the page. Mixing the two
    coordinate systems is invisible in the XML and obvious on the canvas: lines run
    straight through boxes. This catches it before the file is written.
    """
    import xml.etree.ElementTree as ET

    root = ET.fromstring(f"<root>{cells_xml}</root>")
    cells = {c.get("id"): c for c in root.findall("mxCell")}

    def absolute(cid):
        c = cells.get(cid)
        g = c.find("mxGeometry") if c is not None else None
        if g is None or not g.get("x"):
            return None
        x, y = float(g.get("x")), float(g.get("y"))
        w, h = float(g.get("width", 0)), float(g.get("height", 0))
        par = c.get("parent")
        while par and par not in ("0", "1"):
            pg = cells[par].find("mxGeometry")
            x += float(pg.get("x", 0))
            y += float(pg.get("y", 0))
            par = cells[par].get("parent")
        return x, y, w, h

    boxes = {
        cid: absolute(cid)
        for cid, c in cells.items()
        if c.get("vertex") == "1"
        and absolute(cid)
        and "shape=image" not in (c.get("style") or "")
        and "container=1" not in (c.get("style") or "")
    }

    problems = []
    for cid, c in cells.items():
        if c.get("edge") != "1":
            continue
        g = c.find("mxGeometry")
        arr = g.find("Array") if g is not None else None
        if arr is None:
            continue
        ox = oy = 0.0
        par = c.get("parent")
        while par and par not in ("0", "1"):
            pg = cells[par].find("mxGeometry")
            ox += float(pg.get("x", 0))
            oy += float(pg.get("y", 0))
            par = cells[par].get("parent")
        for pt in arr.findall("mxPoint"):
            px, py = float(pt.get("x")) + ox, float(pt.get("y")) + oy
            for bid, (bx, by, bw, bh) in boxes.items():
                # An edge may TOUCH its own endpoints -- that is what a port is -- but a
                # waypoint inside either of them still routes the line back through the
                # shape and over its label. Endpoints were exempt here, which is why the
                # c6/d3 crossing rendered clean XML and a line through the diamond.
                if bx < px < bx + bw and by < py < by + bh:
                    own = " (its own endpoint)" if bid in (c.get("source"), c.get("target")) else ""
                    problems.append(
                        f"edge {cid} waypoint ({px:.0f},{py:.0f}) sits inside {bid}{own}")


    # ---- children must clear the swimlane header and stay inside the lane ----
    for lid, c in cells.items():
        st = c.get("style") or ""
        if "swimlane" not in st:
            continue
        lg = c.find("mxGeometry")
        lw, lh = float(lg.get("width")), float(lg.get("height"))
        hdr = int(st.split("startSize=")[1].split(";")[0]) if "startSize=" in st else 0
        for kid, kc in cells.items():
            if kc.get("parent") != lid or kc.get("vertex") != "1":
                continue
            kg = kc.find("mxGeometry")
            if kg is None or not kg.get("x"):
                continue
            kx, ky = float(kg.get("x")), float(kg.get("y"))
            kw, kh = float(kg.get("width", 0)), float(kg.get("height", 0))
            if ky < hdr + 6:
                problems.append(f"{kid} sits under the {lid} header (y={ky:.0f}, header={hdr})")
            if kx + kw > lw:
                problems.append(f"{kid} overflows {lid} to the right by {kx + kw - lw:.0f}px")
            if ky + kh > lh:
                problems.append(f"{kid} overflows {lid} at the bottom by {ky + kh - lh:.0f}px")

    # ---- edge SEGMENTS must not cross a shape they do not connect ----
    # Checking waypoints alone is not enough: a straight run between two waypoints can pass
    # clean through a box without any waypoint landing inside it. That is how a cross-lane
    # connector ended up drawn over three other shapes.
    def seg_hits_box(x1, y1, x2, y2, bx, by, bw, bh):
        """Does the segment (x1,y1)-(x2,y2) pass through the rectangle?

        Handles diagonals too. An orthogonal edge whose endpoints are not aligned is drawn
        by draw.io as a dog-leg, so treating it as a straight line is the conservative read:
        it flags a route that needs explicit waypoints, which is exactly what we want.
        """
        if abs(y1 - y2) < 1:                                   # horizontal
            return by < y1 < by + bh and min(x1, x2) < bx + bw and max(x1, x2) > bx
        if abs(x1 - x2) < 1:                                   # vertical
            return bx < x1 < bx + bw and min(y1, y2) < by + bh and max(y1, y2) > by
        # diagonal: Liang-Barsky clip against the rectangle
        dx, dy = x2 - x1, y2 - y1
        t0, t1 = 0.0, 1.0
        for num, den in ((bx - x1, dx), (x1 - (bx + bw), -dx),
                         (by - y1, dy), (y1 - (by + bh), -dy)):
            if abs(den) < 1e-9:
                if num > 0:
                    return False
                continue
            t = num / den
            if den > 0:
                if t > t1:
                    return False
                t0 = max(t0, t)
            else:
                if t < t0:
                    return False
                t1 = min(t1, t)
        return t0 < t1

    for cid, c in cells.items():
        if c.get("edge") != "1":
            continue
        src, tgt = c.get("source"), c.get("target")
        if not (src in boxes and tgt in boxes):
            continue
        ox = oy = 0.0
        par = c.get("parent")
        while par and par not in ("0", "1"):
            pg = cells[par].find("mxGeometry")
            ox += float(pg.get("x", 0))
            oy += float(pg.get("y", 0))
            par = cells[par].get("parent")

        st = c.get("style") or ""

        def port(box, ax, ay):
            bx, by, bw, bh = boxes[box]
            fx = float(re.search(rf"{ax}=([\d.]+)", st).group(1)) if f"{ax}=" in st else 0.5
            fy = float(re.search(rf"{ay}=([\d.]+)", st).group(1)) if f"{ay}=" in st else 0.5
            return bx + bw * fx, by + bh * fy

        pts = [port(src, "exitX", "exitY")]
        g = c.find("mxGeometry")
        arr = g.find("Array") if g is not None else None
        if arr is not None:
            pts += [(float(q.get("x")) + ox, float(q.get("y")) + oy) for q in arr.findall("mxPoint")]
        pts.append(port(tgt, "entryX", "entryY"))

        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            for bid, (bx, by, bw, bh) in boxes.items():
                if bid in (src, tgt):
                    continue
                if seg_hits_box(x1, y1, x2, y2, bx, by, bw, bh):
                    problems.append(f"edge {cid} is drawn across {bid}")

    # ---- siblings inside a lane must not overlap each other ----
    by_parent = {}
    for cid, c in cells.items():
        if c.get("vertex") != "1" or "shape=image" in (c.get("style") or ""):
            continue
        g = c.find("mxGeometry")
        if g is None or not g.get("x"):
            continue
        by_parent.setdefault(c.get("parent"), []).append(
            (cid, float(g.get("x")), float(g.get("y")),
             float(g.get("width", 0)), float(g.get("height", 0))))
    for par, sibs in by_parent.items():
        if par in ("1", None):
            continue                      # top level is checked separately below
        for i, (aid, ax, ay, aw, ah) in enumerate(sibs):
            for bid, bx, by, bw, bh in sibs[i + 1:]:
                if ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by:
                    ox = min(ax + aw, bx + bw) - max(ax, bx)
                    oy = min(ay + ah, by + bh) - max(ay, by)
                    problems.append(
                        f"{aid} overlaps {bid} inside {par} by {ox:.0f}x{oy:.0f}px")

    # ---- top-level blocks must not overlap each other ----
    tops = [
        (cid, absolute(cid))
        for cid, c in cells.items()
        if c.get("parent") == "1" and c.get("vertex") == "1" and absolute(cid)
        and "shape=image" not in (c.get("style") or "")
    ]
    for i, (aid, (ax, ay, aw, ah)) in enumerate(tops):
        for bid, (bx, by, bw, bh) in tops[i + 1:]:
            if ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by:
                problems.append(f"{aid} overlaps {bid}")


    # ---- an icon badge must sit fully inside the box it labels ----
    for bid, box in (badges or {}).items():
        if bid not in cells or box not in cells:
            continue
        ig, bg = cells[bid].find("mxGeometry"), cells[box].find("mxGeometry")
        ix, iy = float(ig.get("x")), float(ig.get("y"))
        iw, ih = float(ig.get("width")), float(ig.get("height"))
        bx, by = float(bg.get("x")), float(bg.get("y"))
        bw, bh = float(bg.get("width")), float(bg.get("height"))
        if not (bx <= ix and ix + iw <= bx + bw and by <= iy and iy + ih <= by + bh):
            problems.append(f"badge {bid} has drifted outside {box}")

        bst = cells[box].get("style") or ""
        if "align=left" in bst and "spacingLeft=" in bst:
            inset = int(re.search(r"spacingLeft=(\d+)", bst).group(1))
            if inset - (ix + iw - bx) < 4:
                problems.append(f"label of {box} starts on top of badge {bid}")

    if problems:
        raise SystemExit("LAYOUT:" + "".join(
            chr(10) + "  " + p for p in problems))


class Doc:
    def __init__(self, did: str, name: str, w: int, h: int):
        self.did, self.name, self.w, self.h = did, name, w, h
        self.cells: list[str] = []
        self.boxes: dict[str, tuple] = {}
        self.badges: dict[str, str] = {}

    def add(self, cid, value, style, x, y, w, h, parent="1"):
        if value:
            raw = (value.replace("&lt;", "<").replace("&gt;", ">")
                        .replace("&quot;", '"').replace("&amp;", "&"))
            # size of each run: honour explicit font-size, else the shape's own
            runs, m = [], re.findall(r'font-size:(\d+)px;[^>]*>([^<]*)', raw)
            base = int((re.search(r"fontSize=(\d+)", style) or [0, 12])[1]) if "fontSize=" in style else 12
            if m:
                runs = [(t, int(sz)) for sz, t in m]
                leftover = re.sub(r"<[^>]+>", " ", raw)
                _ = leftover  # tags already accounted for above
            else:
                runs = [(re.sub(r"<[^>]+>", "", raw), base)]
            pad = 16 if "spacingLeft=4" in style else 24
            if "shape=image" not in style:
                fits(runs, w, h, pad_x=pad, name=cid)
        self.boxes[cid] = (x, y, w, h, parent)
        self.cells.append(
            f'        <mxCell id="{cid}" value="{value}" style="{style}" vertex="1" '
            f'parent="{parent}">\n'
            f'          <mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/>\n'
            f"        </mxCell>"
        )

    def badge(self, cid, slug, box_id, size=30, gap=10, side="left", pad=8):
        """Place an icon badge relative to a box, and push the box's label clear of it.

        Two things drift when done by hand: the badge (when the box moves) and the label
        (when the icon changes size). Both are derived here. `check_layout` then verifies
        the badge is inside its box and the text starts past it.
        """
        bx, by, bw, bh, parent = self.boxes[box_id]
        y = by + (bh - size) / 2
        x = bx + gap if side == "left" else bx + bw - size - gap
        self.add(cid, "", icon(slug), int(x), int(y), size, size, parent)
        self.badges[cid] = box_id

        if side == "left":
            need = gap + size + pad
            for i, cell in enumerate(self.cells):
                if f'<mxCell id="{box_id}"' in cell and "spacingLeft=" in cell:
                    self.cells[i] = re.sub(r"spacingLeft=\d+", f"spacingLeft={need}", cell)
                    break

    def link(self, cid, src, tgt, style, value="", pts=None, ports="", parent="1"):
        """Draw an edge. NOTE: `pts` are relative to `parent`, not to the page.

        Getting this wrong displaces every waypoint by the lane offset, which is how
        routed lines end up crossing other shapes. `check_layout` catches it.
        """
        geo = '<mxGeometry relative="1" as="geometry">'
        if pts:
            geo += "<Array as=\"points\">" + "".join(
                f'<mxPoint x="{px}" y="{py}"/>' for px, py in pts
            ) + "</Array>"
        geo += "</mxGeometry>"
        self.cells.append(
            f'        <mxCell id="{cid}" value="{esc(value)}" style="{style}{ports}" edge="1" '
            f'parent="{parent}" source="{src}" target="{tgt}">\n          {geo}\n        </mxCell>'
        )

    def write(self, path):
        body = "\n".join(self.cells)
        check_layout(body, self.badges)
        xml = (
            f'<mxfile host="app.diagrams.net" agent="OneDNA" version="24.7.17">\n'
            f'  <diagram id="{self.did}" name="{self.name}">\n'
            f'    <mxGraphModel dx="1800" dy="1100" grid="1" gridSize="10" guides="1" '
            f'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
            f'pageWidth="{self.w}" pageHeight="{self.h}" math="0" shadow="0" '
            f'background="{WHITE}">\n'
            f"      <root>\n"
            f'        <mxCell id="0"/>\n        <mxCell id="1" parent="0"/>\n'
            f"{body}\n"
            f"      </root>\n    </mxGraphModel>\n  </diagram>\n</mxfile>\n"
        )
        pathlib.Path(path).write_text(xml, encoding="utf-8")
        print(f"  {path}  ({len(self.cells)} cells, {len(xml)/1024:.0f} KB)")


# ═════════════════════════════════════════════════════════════════════════════════
# Diagram 1 — reference architecture
# ═════════════════════════════════════════════════════════════════════════════════
def architecture():
    d = Doc("rls-architecture", "RLS reference architecture", 1900, 1770)

    d.add("title", title(
        "Row-level security in a Databricks RAG pipeline",
        "Border colour indicates which layer enforces access control."),
        f"text;html=1;whiteSpace=wrap;strokeColor=none;fillColor=none;align=left;"
        f"verticalAlign=middle;{FONT}", 40, 16, 1180, 72)

    # Legend
    d.add("lg", esc(f'<b style="color:{NAVY_DEEP};">Who enforces</b>'),
          f"rounded=0;html=1;fillColor={WHITE};strokeColor={OAT_LINE};strokeWidth=2;"
          f"verticalAlign=top;align=left;spacingLeft=10;spacingTop=8;fontSize={W_NOTE};"
          f"container=1;collapsible=0;{FONT}", 40, 96, 1000, 268)
    for i, (lbl, col) in enumerate([
        ("Unity Catalog enforces, and gives notice when it goes wrong", GREEN),
        ("Your code enforces, however you wrote it", LAVA),
        ("Nothing enforces here at all", NAVY_DEEP),
        ("Outside Databricks", OAT_LINE),
    ]):
        d.add(f"lgr{i}", esc(f'<span style="color:{NAVY_DEEP};">{lbl}</span>'),
              f"rounded=0;html=1;fillColor={WHITE};strokeColor={col};strokeWidth=3;"
              f"align=left;spacingLeft=10;fontSize={W_NOTE};{FONT}", 12, 44 + i * 54, 976, 50, "lg")

    # ── Lane 1: identity ─────────────────────────────────────────────────────────
    d.add("idlane", esc("IDENTITY  ·  which caller reaches Unity Catalog"), zone(LAVA, WHITE, 56), 40, 400, 1820, 290)

    d.add("usr", html("User", "asks a question"), node(OAT_LINE), 20, 92, 200, 128, "idlane")
    d.badge("usrico", "ms-person", "usr", size=30)
    d.add("teams", html("Front end", "a web UI, Teams, …",
                        f'<b style="color:{LAVA_DEEP};">returns an <b>Entra</b> token</b>'),
          node(OAT_LINE), 240, 88, 285, 136, "idlane")
    d.badge("teamsico", "ms-teams", "teams", size=34)
    d.add("exch", html("RFC 8693 exchange", "POST /oidc/v1/token",
                       f'<b style="color:{LAVA_DEEP};">needs an account-level policy</b>'),
          node(OAT_LINE), 545, 88, 300, 136, "idlane")
    d.badge("exchico", "az-appreg", "exch", size=32)

    d.add("apps", html("Databricks Apps", "x-forwarded-access-token",
                       f'<b style="color:#2E7D32;">widest scope, reaches Volumes</b>'),
          node(LAVA), 900, 62, 390, 100, "idlane")
    d.badge("appsico", "databricks-apps", "apps", size=30)
    d.add("msrv", html("Model Serving", "ModelServingUserCredentials()",
                       f'<b style="color:{LAVA_DEEP};">no Volumes, no file operations</b>'),
          node(LAVA), 900, 178, 390, 100, "idlane")
    d.badge("msrvico", "model-serving", "msrv", size=30)

    for cid, s, t in [("e1", "usr", "teams"), ("e2", "teams", "exch")]:
        d.link(cid, s, t, edge(), ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    d.link("e3", "exch", "apps", edge(), "user token",
           [(872, 156), (872, 112)], "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="idlane")
    d.link("e4", "exch", "msrv", edge(), "user token",
           [(872, 156), (872, 228)], "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="idlane")

    # ── Lane 2: indexing ─────────────────────────────────────────────────────────
    d.add("pipe", esc("BUILD  ·  the pipeline, and where platform enforcement stops"),
          zone(LAVA, WHITE, 56), 40, 720, 1820, 330)

    # Widths grew with the type: these hold two short lines each, so the extra room
    # goes sideways rather than into height, which keeps the lane shallow.
    stages = [
        ("s12", "1–2 Gather · Load", "Volume &#8594; bronze", 20, 235),
        ("s34", "3–4 Parse · Chunk", "silver text &#8594; chunks", 275, 245),
        ("s7", "7 Combine", "gold one-big-table", 830, 215),
        ("s8", "8 Embed", "index source", 1065, 190),
    ]
    for cid, t, sub, x, w in stages:
        d.add(cid, html(t, sub), plain(LAVA), x, 66, w, 96, "pipe")

    d.add("s56", html("5–6 Enrich · Join",
                      f'<b style="color:{LAVA_DEEP};">where ACL columns</b>',
                      f'<b style="color:{LAVA_DEEP};">are written</b>'),
          plain(LAVA, WHITE, 3), 540, 66, 270, 96, "pipe")

    d.add("s9", html("9 Serve", "AI Search index"), plain(LAVA_DEEP, WHITE, 3) +
          "align=left;spacingLeft=58;", 1440, 66, 250, 96, "pipe")
    d.badge("s9ico", "ai-search", "s9", size=28)

    d.add("break", esc(
        f'<b style="color:{LAVA_DEEP};font-size:{W_TITLE}px;">enforcement<br>stops here</b>'
        f'<br><span style="font-size:{W_DETAIL}px;color:{NAVY_SOFT};">a vector is a<br>list of floats</span>'),
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={WHITE};strokeColor={LAVA_DEEP};"
        f"strokeWidth=3;dashed=1;dashPattern=6 4;fixDash=1;align=center;verticalAlign=middle;"
        f"fontSize={W_DETAIL};{FONT}", 1265, 66, 165, 116, "pipe")

    d.add("meta", esc(
        f'<b>Metadata is content.</b><br><span style="font-size:{W_DETAIL}px;">Whatever you index is '
        f'readable by anyone who can query the index, <i>created_by_email</i> and <i>web_url</i> included. '
        f'The ACL applies before any column is returned, not just the chunk text.</span>'),
        note(), 20, 196, 880, 120, "pipe")
    d.add("cols", esc(
        f'<b>ACL_FILTER_COLUMNS</b><br><span style="font-size:{W_DETAIL}px;">source_system · site_id · '
        f'sensitivity<br><br><i>Your ACL can never be more expressive than the columns you '
        f'written at index time. Getting it wrong is a <b>rebuild</b>.</i></span>'),
        note(LAVA, WHITE), 920, 196, 880, 120, "pipe")

    seq = ["s12", "s34", "s56", "s7", "s8"]
    for i in range(len(seq) - 1):
        d.link(f"p{i}", seq[i], seq[i + 1], edge(),
               ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="pipe")
    d.link("p9a", "s8", "break", edge(LAVA_DEEP, 3, arrow="none"),
           ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="pipe")
    d.link("p9b", "break", "s9", edge(LAVA_DEEP, 3),
           ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="pipe")

    # ── Lane 3: query time ───────────────────────────────────────────────────────
    d.add("q", esc("SERVE  ·  two retrieval paths, two different enforcers"),
          zone(LAVA, WHITE, 56), 40, 1080, 1820, 560)

    d.add("agent", html("RAG agent", "runs on the", "<b>caller's</b> client"),
          node(LAVA) + "spacingLeft=58;", 20, 96, 230, 112, "q")
    d.badge("agentico", "agent-bricks", "agent", size=30)
    d.add("route", esc(f'<b style="font-size:{W_TITLE}px;">model<br>routes</b>'), decision(), 275, 100, 190, 104, "q")

    d.add("scim", html("SCIM /Me", "the caller's groups,", "resolved per request"),
          node(LAVA) + "spacingLeft=16;", 500, 76, 300, 150, "q")
    d.add("grants", html("declared grants table", "group &#8594; entitlement",
                         "<i>once one group is a tuple</i>"),
          node(LAVA) + "spacingLeft=16;", 830, 76, 300, 150, "q")
    d.add("guard", html("assert_enforceable()", "filter cols &#8594; index cols?",
                        f'<b style="color:{LAVA_DEEP};">raise, never warn</b>'),
          node(LAVA, WHITE, 3) + "spacingLeft=16;", 1160, 76, 300, 150, "q")
    d.add("idx", esc(f'<b style="font-size:{W_TITLE}px;">AI Search index</b>'
                     f'<br><span style="font-size:{W_DETAIL}px;">similarity + filter</span>'),
          store(LAVA_DEEP), 1500, 68, 300, 130, "q")
    d.badge("idxico", "ai-search", "idx", size=28, side="right")

    d.add("genie", html("Genie Agent", "generates SQL"), node(LAVA) + "spacingLeft=58;", 500, 250, 300, 110, "q")
    d.badge("genieico", "genie-agents", "genie", size=30)
    d.add("uc", html("Unity Catalog", "row filters + column masks",
                     f'<b style="color:#2E7D32;">evaluated per caller</b>'),
          node(GREEN, WHITE, 3) + "spacingLeft=58;", 830, 245, 300, 130, "q")
    d.badge("ucico", "unity-catalog", "uc", size=30)
    d.add("tbl", esc(f'<b style="font-size:{W_TITLE}px;">governed tables</b>'), store(GREEN), 1160, 250, 300, 120, "q")
    d.badge("tblico", "abac", "tbl", size=28, side="right")

    d.add("ans", html("Answer", "+ which control applied"),
          plain(NAVY) + f"fillColor={OAT_LIGHT};", 1500, 250, 300, 120, "q")

    d.add("deny", esc(
        f'<b style="color:{LAVA_DEEP};">no entitlement</b><br>'
        f'<span style="font-size:{W_DETAIL}px;">0 rows, and the model is never called. '
        f'A fluent answer from general knowledge is indistinguishable from a real retrieval.</span>'),
        note(LAVA_DEEP, WHITE), 20, 400, 560, 130, "q")

    d.add("drop", esc(
        f'<b style="color:{LAVA_DEEP};">Your filter, your problem</b><br>'
        f'<span style="font-size:{W_DETAIL}px;">A filter naming a column the index does not have is '
        f'refused at query time — a 500 to your caller unless you assert first.</span>'), note(LAVA_DEEP, WHITE), 600, 400, 590, 130, "q")

    d.add("sp", esc(
        f'<b style="color:{LAVA_DEEP};">Non-interactive callers</b><br>'
        f'<span style="font-size:{W_DETAIL}px;">On a service-principal path the SP is the evaluated '
        f'identity, so every human calling through it sees the union of what the SP was granted. '
        f'Review what the SP is granted, not the space.</span>'),
        note(LAVA_DEEP, WHITE), 1210, 400, 590, 130, "q")

    d.link("q1", "agent", "route", edge(), ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="q")
    d.link("q2", "route", "scim", edge(), "prose",
           [(482, 152), (482, 151)], "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="q")
    d.link("q3", "route", "genie", edge(), "numbers",
           [(482, 152), (482, 305)], "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="q")
    for i, (s, t) in enumerate([("scim", "grants"), ("grants", "guard"), ("guard", "idx")]):
        d.link(f"q4{i}", s, t, edge(), ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;",
               parent="q")
    d.link("q7", "guard", "deny", edge(LAVA_DEEP, 2, True), "0 rows",
           [(1310, 236), (300, 236), (300, 385)], "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", parent="q")
    d.link("q8", "genie", "uc", edge(GREEN), ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="q")
    d.link("q9", "uc", "tbl", edge(GREEN), ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="q")
    d.link("q10", "idx", "ans", edge(), "",
           [(1650, 198), (1650, 240)], "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", parent="q")
    d.link("q11", "tbl", "ans", edge(GREEN), "",
           [(1470, 310)], "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="q")

    d.add("foot", esc(
        f'<span style="font-size:{W_FOOT}px;color:{NAVY_DEEP};">Every failure marked here happens with no error, and sits on '
        f'a border this legend calls out. Where Unity Catalog enforces, a mistake raises; where your '
        f'code does, it returns rows.</span>'),
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={OAT};strokeColor=none;align=left;"
        f"spacingLeft=20;spacingTop=16;verticalAlign=top;fontSize={W_FOOT};{FONT}", 40, 1670, 1820, 76)

    d.write("architecture.drawio")


# ═════════════════════════════════════════════════════════════════════════════════
# Diagram 2 — decision tree
# ═════════════════════════════════════════════════════════════════════════════════
def decision_tree():
    d = Doc("rls-decision-tree", "Which enforcement path", 1820, 1900)

    d.add("t", title("Enforcement path selection",
                     'Who enforces access control on each path, and how it is verified.'),
          f"text;html=1;whiteSpace=wrap;strokeColor=none;fillColor=none;align=left;"
          f"verticalAlign=middle;{FONT}", 40, 24, 1200, 129)

    d.add("start", esc('<b>You need per-user access control<br>over retrieved content</b>'),
          f"ellipse;html=1;whiteSpace=wrap;fillColor={OAT_LIGHT};strokeColor={NAVY};"
          f"strokeWidth=2;align=center;verticalAlign=middle;fontSize={W_TITLE};fontColor={NAVY_DEEP};"
          f"{FONT}", 650, 168, 500, 118)

    d.add("d1", esc("<b>Is the content<br>structured?</b>"), decision(), 725, 350, 350, 150)
    d.add("d2", esc("<b>Interactive caller?</b><br>"
                    f'<span style="font-size:{W_DETAIL}px;color:{NAVY_SOFT};">a human, live</span>'),
          decision(), 240, 620, 340, 160)
    d.add("d3", esc("<b>Does the ACL fit the<br>index metadata columns?</b><br>"
                    f'<span style="font-size:{W_DETAIL}px;color:{NAVY_SOFT};">flat, per-chunk, no joins'
                    "</span>"), decision(), 1180, 600, 420, 190)

    outcomes = [
        ("uc", "unity-catalog", GREEN, "Unity Catalog RLS",
         "row filters and column masks, or an ABAC policy at catalog scope",
         "<b>The platform enforces.</b> Resolves per caller, and holds across the agent and front-end "
         "hops.<br><br>Test it against a case it has to deny.", 40, 900, 400, 330),
        ("sp", "sql-warehouse", LAVA_DEEP, "Review the SP's grants",
         "the service principal <b>is</b> the identity",
         "Every human calling through it sees the union of what the SP may read, with "
         "no differentiation between them. On this path that is the whole of your "
         "access control.", 470, 900, 400, 350),
        ("code", "ai-search", LAVA, "Code ACL + assert_enforceable",
         "you enforce, at query time",
         "Resolve groups per request from the caller's own token. A naming convention works until "
         "access is a <b>combination</b> of columns; then use a <b>declared table</b>."
         "<br><br>Refuse on error. Empty is the default. Malformed raises."
         "<br><br>Test the denial path: the happy path passes either way.",
         900, 900, 430, 390),
        ("pg", "lakebase", NAVY, "Consider pgvector on Lakebase",
         "move enforcement back into the database",
         "Your ACL becomes a row-level security policy again, evaluated by the engine rather "
         "than by your retrieval code.<br><br>A governance argument rather than a latency one, "
         "and the stronger of the two.", 1360, 900, 420, 390),
    ]
    for cid, ico, col, head, sub, body, x, y, w, h in outcomes:
        d.add(cid, esc(
            f'<b style="font-size:{W_TITLE}px;color:{NAVY_DEEP};">{head}</b><br>'
            f'<span style="font-size:{W_DETAIL}px;color:{NAVY_SOFT};">{sub}</span><br><br>'
            f'<span style="font-size:{W_DETAIL}px;color:{NAVY_DEEP};">{body}</span>'),
            f"rounded=0;html=1;whiteSpace=wrap;fillColor={WHITE};strokeColor={col};"
            f"strokeWidth=3;align=left;spacingLeft=12;spacingRight=10;verticalAlign=top;"
            f"spacingTop=64;fontSize={W_DETAIL};{FONT}", x, y, w, h)
        d.add(f"{cid}ico", "", icon(ico), x + 16, y + 14, 38, 38)

    d.add("d4", esc("<b>Does the chain need<br>UC Volumes or file ops?</b>"),
          decision(), 960, 1370, 380, 170)
    d.add("hostA", html("Databricks Apps", "the only host that reaches Volumes"),
          node(LAVA) + "spacingLeft=62;", 1400, 1390, 380, 130)
    d.add("hostAico", "", icon("databricks-apps"), 1416, 1430, 40, 40)
    d.add("hostB", html("Apps or Model Serving",
                        "write the chain host-agnostically", "and it stays a config change"),
          node(LAVA) + "spacingLeft=62;", 520, 1390, 400, 160)
    d.add("hostBico", "", icon("model-serving"), 536, 1445, 40, 40)

    d.link("c1", "start", "d1", edge(), ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    d.link("c2", "d1", "d2", edge(), "tables, rows, numbers", [(415, 425), (415, 560)],
           "exitX=0;exitY=0.5;entryX=0.5;entryY=0;")
    d.link("c3", "d1", "d3", edge(), "documents, prose", [(1390, 425), (1390, 560)],
           "exitX=1;exitY=0.5;entryX=0.5;entryY=0;")
    d.link("c4", "d2", "uc", edge(GREEN), "yes, a human asks", [(240, 700), (240, 860)],
           "exitX=0;exitY=0.5;entryX=0.5;entryY=0;")
    d.link("c5", "d2", "sp", edge(LAVA_DEEP), "no, a service principal",
           [(415, 830), (670, 830)], "exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    # The waypoint has to clear d3's own left edge (x=950). Routing to the target's
    # centre (987) would put it INSIDE the diamond, so the line crosses the shape and
    # its label -- the mirrored c4 edge only looks the same because uc's centre
    # happens to fall outside d2. Turn left of the node, then drop to the target.
    d.link("c6", "d3", "code", edge(LAVA), "yes, flat and per-chunk",
           [(1140, 695), (1140, 850), (1115, 850)],
           "exitX=0;exitY=0.5;entryX=0.5;entryY=0;")
    d.link("c7", "d3", "pg", edge(), "no, needs joins or&#10;external rules",
           [(1620, 695), (1620, 860)], "exitX=1;exitY=0.5;entryX=0.5;entryY=0;")
    d.link("c8", "code", "d4", edge(), ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    d.link("c9", "d4", "hostA", edge(), "yes", ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    d.link("c10", "d4", "hostB", edge(), "no", ports="exitX=0;exitY=0.5;entryX=1;entryY=0.5;")

    d.add("note", esc(
        f'<b style="font-size:{W_TITLE}px;color:{NAVY_DEEP};">Whichever branch you land on</b><br>'
        f'<span style="font-size:{W_FOOT}px;color:{NAVY_DEEP};">'
        f'<b>1.</b> Point the filter at something that must return nothing, and watch it return '
        f'nothing. A control you have only seen succeed is a control you have not tested.<br>'
        f'<b>2.</b> Make your two zeros distinguishable: "no entitlement" and "something broke" '
        f'look identical from outside.<br>'
        f'<b>3.</b> Assert on the identity that produced the answer. An answer arriving tells '
        f'you nothing about who it was filtered for.</span>'),
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={OAT};strokeColor=none;align=left;"
        f"spacingLeft=20;spacingTop=16;verticalAlign=top;fontSize={W_FOOT};{FONT}", 40, 1590, 1740, 150)
    d.write("decision-tree.drawio")

# ═════════════════════════════════════════════════════════════════════════════════
# Diagram 3 — build and serve, the two halves of the platform
# ═════════════════════════════════════════════════════════════════════════════════
def build_and_serve():
    d = Doc("build-serve", "Build and serve", 1880, 1260)

    d.add("t", title("AI RAG agent and index development",
                     "Build runs on a schedule and writes the index. Serve is a live "
                     "request path and only reads it."),
          f"text;html=1;whiteSpace=wrap;strokeColor=none;fillColor=none;align=left;"
          f"verticalAlign=middle;{FONT}", 40, 16, 1500, 72)

    # ---- BUILD ----
    d.add("build", esc("BUILD  ·  batch, scheduled"), zone(LAVA, WHITE, 56), 40, 180, 880, 860)

    d.add("src", html("Source systems", "SharePoint, fileshares.",
                      "Owners publish there;", "nothing is copied by hand."),
          node(OAT_LINE) + "spacingLeft=16;", 24, 80, 360, 160, "build")

    d.add("prep", html("Preprocessing", "raw &#8594; bronze &#8594; silver &#8594; gold",
                       "parse, chunk, enrich, embed"),
          node(LAVA) + "spacingLeft=66;", 490, 80, 364, 160, "build")
    d.badge("prepico", "delta-lake", "prep", size=30)

    d.add("idx", esc(f'<b style="font-size:{W_TITLE}px;">AI Search index</b>'
                     f'<br><span style="font-size:{W_DETAIL}px;color:{NAVY_SOFT};">'
                     f'written only here</span>'),
          store(LAVA_DEEP), 24, 300, 400, 130, "build")

    d.add("agentdev", html("Agent development",
                           "chain &#8594; tool &#8594; retriever &#8594; <b>ACL</b>",
                           "built and versioned separately,",
                           "then deployed as one endpoint"),
          node(LAVA) + "spacingLeft=66;", 24, 520, 500, 165, "build")
    d.badge("agentdevico", "agent-bricks", "agentdev", size=30)

    d.add("uc", html("Unity Catalog",
                     "one governance layer over both: lineage for every",
                     "artefact the pipeline writes, and the grants the",
                     "agent&apos;s ACL resolves against at query time"),
          node(GREEN, WHITE, 3) + "spacingLeft=66;", 24, 720, 830, 120, "build")
    d.badge("ucico2", "unity-catalog", "uc", size=30)

    d.add("acln", esc(
        f'<b style="color:{LAVA_DEEP};">The index has no row filter</b>'
        f'<br><span style="font-size:{W_DETAIL}px;">Whatever the ACL needs at query time has to be written '
        f'into a metadata column here, at build. Changing that later means a rebuild.</span>'),
        note(LAVA_DEEP, WHITE), 444, 300, 410, 160, "build")

    d.link("b1", "src", "prep", edge(), "on change",
           ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="build")
    d.link("b2", "prep", "idx", edge(LAVA_DEEP, 3), "writes",
           [(204, 268)], "exitX=0;exitY=1;entryX=0.5;entryY=0;", parent="build")
    d.link("b3", "agentdev", "idx", edge(NAVY, 2, True), "built against",
           ports="exitX=0.25;exitY=0;entryX=0.25;entryY=1;", parent="build")

    # ---- SERVE ----
    d.add("serve", esc("SERVE  ·  live request"), zone(LAVA, WHITE, 56), 960, 180, 880, 860)

    d.add("ui", html("User interface", "a web UI, Teams, …", "Asks questions, gets answers."),
          node(OAT_LINE) + "spacingLeft=66;", 24, 80, 400, 135, "serve")
    d.badge("uiico", "ms-teams", "ui", size=30)

    d.add("agent", html("Deployed agent", "chain &#8594; tool &#8594; <b>ACL</b> &#8594; data",
                        "the ACL narrows retrieval to the caller,",
                        "so <b>one agent serves every audience</b>"),
          node(LAVA, WHITE, 3) + "spacingLeft=66;", 24, 290, 360, 175, "serve")
    d.badge("agentico2", "model-serving", "agent", size=30)

    d.add("read", esc(f'<b style="font-size:{W_TITLE}px;">the same AI Search index</b>'
                      f'<br><span style="font-size:{W_DETAIL}px;color:{NAVY_SOFT};">'
                      f'read at query time, never written</span>'),
          store(LAVA_DEEP), 444, 80, 410, 135, "serve")

    d.add("gen", html("Genie Agent", "SQL over governed tables.",
                      "Unity Catalog evaluates the caller."),
          node(GREEN) + "spacingLeft=66;", 490, 300, 364, 155, "serve")
    d.badge("genico2", "genie-agents", "gen", size=30)

    d.add("who", esc(
        f'<b>Who enforces on each branch</b><br>'
        f'<span style="font-size:{W_DETAIL}px;">To the index: your ACL, in code, at query time.<br>'
        f'To Genie: Unity Catalog, per caller.<br><br>'
        f'Both run on the caller&apos;s credentials.</span>'),
        note(), 24, 520, 830, 175, "serve")

    d.link("s1", "ui", "agent", edge(), "request",
           ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;", parent="serve")
    d.link("s2", "agent", "read", edge(LAVA), "filtered query",
           ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="serve")
    d.link("s3", "agent", "gen", edge(GREEN), "data question",
           [(437, 378)], "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="serve")

    d.add("foot", esc(
        f'<span style="font-size:{W_FOOT}px;color:{NAVY_DEEP};">Enforcing the ACL at query time means no '
        f'per-audience index and no copy of the corpus outside Databricks. The trade is that the '
        f'access decision runs in code you wrote on the serve side, against columns you chose on '
        f'the build side.</span>'),
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={OAT};strokeColor=none;align=left;"
        f"spacingLeft=20;spacingTop=16;verticalAlign=top;fontSize={W_FOOT};{FONT}", 40, 1070, 1800, 76)
    d.write("build-and-serve.drawio")

# ═════════════════════════════════════════════════════════════════════════════════
# Diagram 4 — the governance boundary
# ═════════════════════════════════════════════════════════════════════════════════
def governance_boundary():
    """Where Unity Catalog stops governing, drawn as two zones and one crossing.

    The whole argument is the border colour: green on the left, deep lava on the
    right, and an arrow between them that takes the security context nowhere.
    """
    d = Doc("rls-governance-boundary", "Where platform enforcement stops", 1900, 940)

    d.add("t", title("Governance boundary: table to index",
                     "A governed table has its filters. The index built from it does not."),
          f"text;html=1;whiteSpace=wrap;strokeColor=none;fillColor=none;align=left;"
          f"verticalAlign=middle;{FONT}", 40, 16, 1400, 72)

    # ── Governed: the platform side ──────────────────────────────────────────────
    d.add("gov", esc("UNITY CATALOG GOVERNS THIS"), zone(GREEN, WHITE, 52), 40, 200, 700, 535)

    d.add("tbl", html("Governed table", "rows and columns in Unity Catalog"),
          node(GREEN), 30, 90, 640, 100, "gov")
    d.badge("tblico", "unity-catalog", "tbl", size=28)

    d.add("rf", html("Row filter", "a UDF, evaluated per caller"),
          node(GREEN) + "spacingLeft=18;", 30, 240, 305, 115, "gov")
    d.add("cm", html("Column mask", "also per caller"),
          node(GREEN) + "spacingLeft=18;", 365, 240, 305, 115, "gov")

    d.add("govnote", esc(
        f'<span style="font-size:{W_DETAIL}px;color:{NAVY_DEEP};">Attached to the object itself, so every '
        f'reader gets their own view of it — and a mistake here <b>gives notice</b>.</span>'),
        note(GREEN, WHITE), 30, 385, 640, 100, "gov")

    for cid, tgt in [("gl1", "rf"), ("gl2", "cm")]:
        d.link(cid, "tbl", tgt, edge(GREEN, 2, arrow="none"),
               ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;", parent="gov")

    # ── Ungoverned: your side ────────────────────────────────────────────────────
    d.add("ungov", esc("UNITY CATALOG DOES NOT GOVERN THIS"),
          zone(LAVA_DEEP, WHITE, 52), 1160, 200, 700, 535)

    d.add("idx", html("AI Search index", "a Unity Catalog object, with grants"),
          node(LAVA_DEEP), 30, 90, 640, 100, "ungov")
    d.badge("idxico", "ai-search", "idx", size=28)

    d.add("gone", esc(
        f'<b style="font-size:{W_TITLE}px;color:{LAVA_DEEP};">What did not come along</b><br>'
        f'<span style="font-size:{W_DETAIL}px;color:{NAVY_DEEP};">no row filter · no column mask<br>'
        f'filtering is a <b>query parameter</b> you pass from application code</span>'),
        node(LAVA_DEEP, WHITE, 2, dashed=True) + "spacingLeft=14;verticalAlign=middle;",
        30, 240, 640, 145, "ungov")

    d.add("ungovnote", esc(
        f'<span style="font-size:{W_DETAIL}px;color:{NAVY_DEEP};">Nothing validates your filter until '
        f'query time, and a wrong column name is <b>refused</b> there.</span>'),
        note(LAVA_DEEP, WHITE), 30, 415, 640, 100, "ungov")

    d.link("il", "idx", "gone", edge(LAVA_DEEP, 2, dashed=True, arrow="none"),
           ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;", parent="ungov")

    # ── The crossing ─────────────────────────────────────────────────────────────
    d.add("cross", esc(
        f'<b style="font-size:{W_TITLE}px;color:{NAVY_DEEP};">chunk &#8594; embed &#8594; index</b><br>'
        f'<span style="font-size:{W_DETAIL}px;color:{NAVY_SOFT};">an embedding is a<br>list of floats</span>'),
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={OAT_LIGHT};strokeColor={OAT_LINE};"
        f"strokeWidth=2;align=center;verticalAlign=middle;fontSize={W_TITLE};{FONT}", 790, 380, 320, 125)

    d.link("x1", "gov", "cross", edge(NAVY, 3), ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    d.link("x2", "cross", "ungov", edge(NAVY, 3), ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")

    d.add("xlbl", esc(
        f'<span style="font-size:{W_DETAIL}px;color:{LAVA_DEEP};"><b>the security context<br>'
        f'does not cross</b></span>'),
        f"text;html=1;whiteSpace=wrap;strokeColor=none;fillColor=none;align=center;"
        f"verticalAlign=middle;fontSize={W_DETAIL};{FONT}", 790, 520, 320, 70)

    d.add("foot", esc(
        f'<span style="font-size:{W_FOOT}px;color:{NAVY_DEEP};">Whatever access control applied to the '
        f'text is not in the vector. What arrives is what you deliberately wrote '
        f'into metadata columns alongside it — so your ACL can never be more expressive than the '
        f'columns you wrote at index time.</span>'),
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={OAT};strokeColor=none;align=left;"
        f"spacingLeft=20;spacingTop=16;verticalAlign=top;fontSize={W_FOOT};{FONT}", 40, 765, 1820, 76)
    d.write("governance-boundary.drawio")

# ═════════════════════════════════════════════════════════════════════════════════
# Diagram 5 — the ACL resolution flow
# ═════════════════════════════════════════════════════════════════════════════════
def acl_flow():
    """Caller to filtered query, with both closed exits drawn as prominently as the happy path.

    The two terminal states on the right (zero rows, PermissionError) are the point:
    every branch that cannot resolve an entitlement ends somewhere explicit.
    """
    d = Doc("rls-acl-flow", "How the ACL resolves per request", 1800, 1180)

    d.add("t", title("ACL resolution per request",
                     "Every branch that cannot resolve the caller ends closed."),
          f"text;html=1;whiteSpace=wrap;strokeColor=none;fillColor=none;align=left;"
          f"verticalAlign=middle;{FONT}", 40, 16, 1400, 72)

    # ── Row 1: resolve who is asking ─────────────────────────────────────────────
    d.add("caller", esc('<b>Caller</b><br>'
                        f'<span style="font-size:{W_DETAIL}px;color:{NAVY_SOFT};">a human, in a front end</span>'),
          f"ellipse;html=1;whiteSpace=wrap;fillColor={OAT_LIGHT};strokeColor={NAVY};"
          f"strokeWidth=2;align=center;verticalAlign=middle;fontSize={W_TITLE};fontColor={NAVY_DEEP};"
          f"{FONT}", 40, 190, 300, 120)

    d.add("tok", html("Their OBO token", "not the endpoint's identity"),
          node(OAT_LINE) + "spacingLeft=62;", 380, 190, 330, 120)
    d.add("tokico", "", icon("ms-person"), 396, 232, 38, 38)

    d.add("scim", html("SCIM /Me", "group memberships, resolved",
                       "with the caller's own credentials"),
          node(LAVA) + "spacingLeft=18;", 750, 185, 350, 130)

    d.add("groups", esc(
        f'<b style="font-size:{W_TITLE}px;">groups</b><br>'
        f'<span style="font-size:{W_DETAIL}px;color:{NAVY_DEEP};">[group-a, group-b, …]</span>'),
        plain(OAT_LINE, OAT_LIGHT), 1140, 190, 270, 120)

    d.add("grantmap", esc('<b>declared<br>grants table</b>'), decision(), 1450, 170, 310, 160)

    d.add("nogrant", esc(
        f'<span style="font-size:{W_DETAIL}px;color:{NAVY_DEEP};">an unmapped group<br>'
        f'<b>grants nothing</b></span>'),
        plain(OAT_LINE, OAT_LIGHT), 1500, 380, 260, 100)

    # ── Row 2: turn entitlements into a filter ───────────────────────────────────
    d.add("ent", esc(
        f'<b style="font-size:{W_TITLE}px;">Entitlements</b><br>'
        f'<span style="font-size:{W_DETAIL}px;color:{NAVY_DEEP};">source_systems · site_ids<br>'
        f'sensitivity_labels</span>'),
        node(LAVA, WHITE, 2) + "spacingLeft=18;verticalAlign=middle;", 40, 560, 340, 140)

    d.add("empty", esc('<b>is_empty?</b>'), decision(), 420, 555, 300, 150)

    d.add("filt", html("build_filter()", "entitlement over any", "caller-supplied filter"),
          node(LAVA) + "spacingLeft=18;", 760, 560, 340, 140)

    d.add("assert", esc('<b>assert_<br>enforceable</b>'), decision(), 1140, 550, 320, 160)

    d.add("query", html("AI Search query", "+ the entitlement filter"),
          node(GREEN) + "spacingLeft=62;", 1500, 565, 260, 130)
    d.add("queryico", "", icon("ai-search"), 1516, 610, 40, 40)

    # ── Terminal states, both closed ─────────────────────────────────────────────
    d.add("zero", esc(
        f'<b style="font-size:{W_TITLE}px;color:{LAVA_DEEP};">Return no rows</b><br>'
        f'<span style="font-size:{W_DETAIL}px;color:{NAVY_DEEP};">and an explicit denial naming which '
        f'groups granted nothing.<br><br><b>The model is never called.</b> A fluent answer from '
        f'general knowledge is indistinguishable from a real retrieval.</span>'),
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={WHITE};strokeColor={LAVA_DEEP};"
        f"strokeWidth=3;align=left;spacingLeft=12;spacingRight=10;verticalAlign=top;"
        f"spacingTop=18;fontSize={W_DETAIL};{FONT}", 40, 790, 560, 250)

    d.add("err", esc(
        f'<b style="font-size:{W_TITLE}px;color:{LAVA_DEEP};">PermissionError</b><br>'
        f'<span style="font-size:{W_DETAIL}px;color:{NAVY_DEEP};">a filter column that is not a column of the '
        f'index would not be applied, so the request stops rather than serving unfiltered '
        f'results.</span>'),
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={WHITE};strokeColor={LAVA_DEEP};"
        f"strokeWidth=3;align=left;spacingLeft=12;spacingRight=10;verticalAlign=top;"
        f"spacingTop=18;fontSize={W_DETAIL};{FONT}", 620, 790, 560, 250)

    # ── Edges ────────────────────────────────────────────────────────────────────
    for cid, s, t in [("a1", "caller", "tok"), ("a2", "tok", "scim"),
                      ("a3", "scim", "groups"), ("a4", "groups", "grantmap")]:
        d.link(cid, s, t, edge(), ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")

    d.link("a6", "grantmap", "nogrant", edge(NAVY, 2, dashed=True), "unmapped",
           ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")

    # both the mapped and the unmapped path arrive at the same entitlement object
    d.link("a5", "grantmap", "ent", edge(), "mapped",
           [(1605, 350), (210, 350)], "exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    d.link("a7", "nogrant", "ent", edge(NAVY, 2, dashed=True), "",
           [(1630, 530), (210, 530)], "exitX=0.5;exitY=1;entryX=0.5;entryY=0;")

    d.link("a8", "ent", "empty", edge(), ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    d.link("a10", "empty", "filt", edge(), "no",
           ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    d.link("a11", "filt", "assert", edge(), ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    d.link("a13", "assert", "query", edge(GREEN, 3), "ok",
           ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")

    d.link("a9", "empty", "zero", edge(LAVA_DEEP, 3), "yes",
           ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    d.link("a12", "assert", "err", edge(LAVA_DEEP, 3), "unknown column",
           ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")

    d.add("foot", esc(
        f'<span style="font-size:{W_FOOT}px;color:{NAVY_DEEP};">Empty means nothing, not everything. A '
        f'malformed mapping raises rather than resolving to empty, so "no entitlement" and '
        f'"something broke" tell themselves apart. A naming convention works while one group means '
        f'one thing; a declared table is what scales to a combination of columns.</span>'),
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={OAT};strokeColor=none;align=left;"
        f"spacingLeft=20;spacingTop=16;verticalAlign=top;fontSize={W_FOOT};{FONT}", 1200, 790, 560, 210)
    d.write("acl-flow.drawio")

# ═════════════════════════════════════════════════════════════════════════════════
# Narrow variants. One column, full-width boxes, stacked top to bottom.
# ═════════════════════════════════════════════════════════════════════════════════
X = 30                  # left margin
W = 760                 # inner box width
HALF = 350              # two boxes side by side inside a lane, 20px gutter


def _n_head(d, title, sub, h=96):
    d.add("t", n_title(title, sub),
          f"text;html=1;whiteSpace=wrap;strokeColor=none;fillColor=none;align=left;"
          f"verticalAlign=middle;{FONT}", X, 16, W, h)


def _n_foot(d, y, text, h=112):
    """The beige takeaway strip. Sized at N_FOOT rather than N_NOTE: it carries the
    summary of the whole diagram, so it should not be the smallest type on it."""
    d.add("foot", esc(f'<span style="font-size:{N_FOOT}px;color:{NAVY_DEEP};">{text}</span>'),
          f"rounded=0;html=1;whiteSpace=wrap;fillColor={OAT};strokeColor=none;align=left;"
          f"spacingLeft=18;spacingTop=14;verticalAlign=top;fontSize={N_FOOT};{FONT}",
          X, y, W, h)


def governance_boundary_narrow():
    d = Doc("rls-governance-narrow", "Governance boundary (narrow)", NARROW_W, 700)
    _n_head(d, "Governance boundary", "A governed table has its filters.<br>"
                                      "The index built from it does not.")

    d.add("gov", esc("UNITY CATALOG GOVERNS THIS"), zone(GREEN, WHITE, 46), X, 122, W, 240)
    d.add("tbl", n_html("Governed table", "rows and columns in Unity Catalog"),
          n_node(GREEN), 20, 62, 720, 74, "gov")
    d.badge("tblico", "unity-catalog", "tbl", size=32)
    d.add("rf", n_html("Row filter", "a UDF, evaluated per caller"),
          n_node(GREEN) + "spacingLeft=18;", 20, 152, HALF, 68, "gov")
    d.add("cm", n_html("Column mask", "also evaluated per caller"),
          n_node(GREEN) + "spacingLeft=18;", 410, 152, HALF, 68, "gov")
    for cid, tgt in (("gl1", "rf"), ("gl2", "cm")):
        d.link(cid, "tbl", tgt, edge(GREEN, 2, arrow="none", fsize=N_DETAIL),
               ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;", parent="gov")

    d.add("cross", esc(
        f'<b style="font-size:{N_TITLE}px;color:{NAVY_DEEP};">chunk &#8594; embed &#8594; index</b>'
        f'<br><span style="font-size:{N_DETAIL}px;color:{LAVA_DEEP};">'
        f'<b>the security context does not cross</b></span>'),
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={OAT_LIGHT};strokeColor={OAT_LINE};"
        f"strokeWidth=2;align=center;verticalAlign=middle;fontSize={N_TITLE};{FONT}",
        X + 230, 386, 300, 94)
    d.link("x1", "gov", "cross", edge(NAVY, 3, fsize=N_DETAIL), ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")

    d.add("ungov", esc("UNITY CATALOG DOES NOT GOVERN THIS"),
          zone(LAVA_DEEP, WHITE, 46), X, 486, W, 244)
    d.add("idx", n_html("AI Search index", "a Unity Catalog object, with grants"),
          n_node(LAVA_DEEP), 20, 62, 720, 74, "ungov")
    d.badge("idxico", "ai-search", "idx", size=32)
    d.add("gone", esc(
        f'<b style="font-size:{N_TITLE}px;color:{LAVA_DEEP};">What did not come along</b><br>'
        f'<span style="font-size:{N_DETAIL}px;color:{NAVY_DEEP};">no row filter, no column mask.'
        f'<br>Filtering is a query parameter from your code.</span>'),
        n_node(LAVA_DEEP, WHITE, 2, dashed=True) + "spacingLeft=18;", 20, 152, 720, 76, "ungov")
    d.link("il", "idx", "gone", edge(LAVA_DEEP, 2, dashed=True, arrow="none", fsize=N_DETAIL),
           ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;", parent="ungov")
    d.link("x2", "cross", "ungov", edge(NAVY, 3, fsize=N_DETAIL), ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")

    _n_foot(d, 748, "Nothing validates your filter until query time, and a wrong column name is "
                    "<b>refused</b> there.")
    d.write("governance-boundary-narrow.drawio")


def build_and_serve_narrow():
    d = Doc("rls-build-serve-narrow", "Build and serve (narrow)", NARROW_W, 1055)
    _n_head(d, "AI RAG agent and index development",
            "Build writes the index on a schedule.<br>Serve reads it on every request.")

    d.add("build", esc("BUILD  ·  batch, scheduled"), zone(LAVA, WHITE, 46), X, 122, W, 330)
    d.add("src", n_html("Source systems", "SharePoint, fileshares.",
                        "Owners publish there."),
          n_node(OAT_LINE) + "spacingLeft=18;", 20, 62, HALF, 112, "build")
    d.add("prep", n_html("Preprocessing", "raw &#8594; bronze &#8594; silver &#8594; gold",
                         "parse, chunk, enrich, embed"),
          n_node(LAVA) + "spacingLeft=18;", 410, 62, HALF, 112, "build")
    d.add("idx", esc(f'<b style="font-size:{N_TITLE}px;color:{NAVY_DEEP};">AI Search index</b>'
                     f'<br><span style="font-size:{N_DETAIL}px;color:{NAVY_SOFT};">'
                     f'written only here</span>'),
          store(LAVA) + f"fontSize={N_TITLE};", 410, 196, HALF, 100, "build")
    d.add("agent", n_html("Agent development", "chain &#8594; tool &#8594; retriever &#8594; ACL",
                          "versioned separately, deployed as one endpoint"),
          n_node(LAVA) + "spacingLeft=18;", 20, 196, HALF, 133, "build")
    d.link("b1", "src", "prep", edge(LAVA, fsize=N_DETAIL), "",
           ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="build")
    # Preprocessing writes the index, not the source systems: drop from prep's
    # bottom-left and enter the cylinder from above.
    d.link("b2", "prep", "idx", edge(LAVA, fsize=N_DETAIL), "writes",
           ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;", parent="build")
    d.link("b3", "agent", "idx", edge(NAVY, 2, dashed=True, fsize=N_DETAIL), "built against",
           ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="build")

    d.add("serve", esc("SERVE  ·  live request"), zone(LAVA, WHITE, 46), X, 482, W, 372)
    d.add("ui", n_html("User interface", "a web UI, Teams, …"),
          n_node(OAT_LINE) + "spacingLeft=18;", 20, 62, HALF, 70, "serve")
    d.badge("uiico", "ms-teams", "ui", size=30)
    d.add("dep", n_html("Deployed agent", "the ACL narrows retrieval to the caller,",
                        "so one agent serves every audience"),
          n_node(LAVA) + "spacingLeft=18;", 410, 62, HALF, 112, "serve")
    d.add("read", esc(f'<b style="font-size:{N_TITLE}px;color:{NAVY_DEEP};">the same index</b>'
                      f'<br><span style="font-size:{N_DETAIL}px;color:{NAVY_SOFT};">'
                      f'read at query time, never written</span>'),
          store(LAVA) + f"fontSize={N_TITLE};", 20, 186, HALF, 88, "serve")
    d.add("gen", n_html("Genie Agent", "SQL over governed tables.",
                        "Unity Catalog evaluates the caller."),
          n_node(GREEN) + "spacingLeft=18;", 410, 186, HALF, 88, "serve")
    d.add("who", esc(
        f'<span style="font-size:{N_DETAIL}px;color:{NAVY_DEEP};">To the index: <b>your ACL</b>, in '
        f'code. To Genie: <b>Unity Catalog</b>, per caller. Both on the caller\'s credentials.'
        f'</span>'),
        n_note(), 20, 288, 720, 62, "serve")
    # ui -> dep runs straight across. The agent then splits downward: left into the
    # index it filters, and straight down into the Genie Agent beneath it.
    d.link("s1", "ui", "dep", edge(fsize=N_DETAIL), "",
           ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="serve")
    d.link("s2", "dep", "read", edge(LAVA, fsize=N_DETAIL), "",
           ports="exitX=0;exitY=0.75;entryX=0.5;entryY=0;", parent="serve")
    d.link("s3", "dep", "gen", edge(GREEN, fsize=N_DETAIL), "",
           ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;", parent="serve")

    _n_foot(d, 878, "Enforcing the ACL at query time means no per-audience index and no copy of "
                    "the corpus outside Databricks. The trade is that the access decision runs in "
                    "code you wrote on the serve side.")
    d.write("build-and-serve-narrow.drawio")


def acl_flow_narrow():
    """One column, top to bottom: resolve the caller, then build and check the filter."""
    d = Doc("rls-acl-flow-narrow", "ACL resolution per request (narrow)", NARROW_W, 1080)
    _n_head(d, "ACL resolution per request",
            "Every branch that cannot resolve the caller ends closed.")

    y = 130
    steps = [
        ("caller", n_html("Caller", "a human, in a front end"), n_plain(NAVY, OAT_LIGHT), 66),
        ("tok", n_html("Their OBO token", "not the endpoint's identity"), n_node(OAT_LINE), 74),
        ("scim", n_html("SCIM /Me", "group memberships, resolved",
                        "with the caller's own credentials"),
         n_node(LAVA) + "spacingLeft=18;", 90),
        ("groups", n_html("groups", "[group-a, group-b, …]"), n_plain(OAT_LINE, OAT_LIGHT), 70),
    ]
    for cid, label, style, h in steps:
        d.add(cid, label, style, X, y, W, h)
        y += h + 26

    d.add("grantmap", esc(f'<b style="font-size:{N_TITLE}px;">declared grants table</b>'
                          f'<br><span style="font-size:{N_DETAIL}px;color:{NAVY_SOFT};">'
                          f'an unmapped group grants nothing</span>'),
          n_decision(), X + 40, y, W - 80, 110)
    y += 136

    d.add("ent", esc(
        f'<b style="font-size:{N_TITLE}px;">Entitlements</b><br>'
        f'<span style="font-size:{N_DETAIL}px;color:{NAVY_DEEP};">'
        f'source_systems · site_ids · sensitivity_labels</span>'),
        n_node(LAVA) + "spacingLeft=18;", X, y, W, 82)
    y += 108

    d.add("empty", esc(f'<b style="font-size:{N_TITLE}px;">is_empty?</b>'),
          n_decision(), X + 120, y, W - 240, 84)
    y += 110

    d.add("zero", esc(
        f'<b style="font-size:{N_TITLE}px;color:{LAVA_DEEP};">yes &#8594; return no rows</b><br>'
        f'<span style="font-size:{N_DETAIL}px;color:{NAVY_DEEP};">an explicit denial. '
        f'<b>The model is never called.</b></span>'),
        n_node(LAVA_DEEP, WHITE, 3) + "spacingLeft=18;", X, y, W, 82)
    y += 108

    d.add("filt", n_html("no &#8594; build_filter()", "entitlement over any caller-supplied filter"),
          n_node(LAVA) + "spacingLeft=18;", X, y, W, 74)
    y += 100

    d.add("assert", esc(f'<b style="font-size:{N_TITLE}px;">assert_enforceable</b>'),
          n_decision(), X + 80, y, W - 160, 84)
    y += 110

    d.add("err", esc(
        f'<b style="font-size:{N_TITLE}px;color:{LAVA_DEEP};">unknown column &#8594; '
        f'PermissionError</b><br><span style="font-size:{N_DETAIL}px;color:{NAVY_DEEP};">'
        f'the index cannot filter on it, so the request stops</span>'),
        n_node(LAVA_DEEP, WHITE, 3) + "spacingLeft=18;", X, y, W, 82)
    y += 108

    d.add("query", n_html("ok &#8594; AI Search query", "+ the entitlement filter"),
          n_node(GREEN) + "spacingLeft=48;", X, y, W, 74)
    d.add("qico", "", icon("ai-search"), X + 12, y + 20, 32, 32)
    y += 100

    # The happy path runs straight down. The two terminal states hang off their
    # decision to the left, so a reader does not read them as steps on the way through.
    main = ["caller", "tok", "scim", "groups", "grantmap", "ent", "empty",
            "filt", "assert", "query"]
    # A single column, read top to bottom. The two terminal boxes are labelled with the
    # branch that reaches them ("yes ->", "unknown column ->") and coloured deep lava, so
    # they read as exits rather than as steps the happy path passes through.
    chain = ["caller", "tok", "scim", "groups", "grantmap", "ent", "empty",
             "zero", "filt", "assert", "err", "query"]
    for i, (a, b) in enumerate(zip(chain, chain[1:])):
        terminal = b in ("zero", "err")
        d.link(f"n{i}", a, b, edge(LAVA_DEEP if terminal else NAVY, 3 if terminal else 2, fsize=N_DETAIL),
               ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")

    _n_foot(d, y + 10, "Empty means nothing, not everything. A malformed mapping raises rather "
                       "than resolving to empty, so \"no entitlement\" and \"something broke\" "
                       "tell themselves apart.")
    d.write("acl-flow-narrow.drawio")


def decision_tree_narrow():
    """The same two questions, asked one under the other."""
    d = Doc("rls-decision-narrow", "Enforcement path selection (narrow)", NARROW_W, 1160)
    _n_head(d, "Enforcement path selection",
            "Who enforces access control on each path,<br>and how it is verified.")

    d.add("start", esc(f'<b style="font-size:{N_TITLE}px;">You need per-user access control<br>'
                       f'over retrieved content</b>'),
          f"ellipse;html=1;whiteSpace=wrap;fillColor={OAT_LIGHT};strokeColor={NAVY};"
          f"strokeWidth=2;align=center;verticalAlign=middle;fontSize={N_TITLE};"
          f"fontColor={NAVY_DEEP};{FONT}", X + 40, 130, W - 80, 90)

    d.add("d1", esc(f'<b style="font-size:{N_TITLE}px;">Is the content structured?</b>'),
          n_decision(), X + 80, 254, W - 160, 92)

    d.add("uc", esc(
        f'<b style="font-size:{N_TITLE}px;color:{NAVY_DEEP};">yes &#8594; Unity Catalog RLS</b><br>'
        f'<span style="font-size:{N_DETAIL}px;color:{NAVY_DEEP};">Row filters and column masks, or '
        f'an ABAC policy at catalog scope. <b>The platform enforces</b>, per caller, and it holds '
        f'across the agent and front-end hops.</span>'),
        n_node(GREEN, WHITE, 3) + "spacingLeft=48;", X, 380, W, 108)
    d.add("ucico", "", icon("unity-catalog"), X + 12, 418, 30, 30)

    d.add("note1", esc(
        f'<span style="font-size:{N_DETAIL}px;color:{NAVY_DEEP};">On a non-interactive path the '
        f"SP's access is the access used. Review its grants.</span>"),
        n_note(LAVA_DEEP, WHITE), X, 508, W, 68)

    d.add("d2", esc(f'<b style="font-size:{N_TITLE}px;">no &#8594; does the ACL fit the '
                    f'index metadata columns?</b>'),
          n_decision(), X + 40, 606, W - 80, 116)

    d.add("code", esc(
        f'<b style="font-size:{N_TITLE}px;color:{NAVY_DEEP};">yes &#8594; code ACL + '
        f'assert_enforceable</b><br><span style="font-size:{N_DETAIL}px;color:{NAVY_DEEP};">'
        f'You enforce, at query time. Resolve groups per request from the caller\'s own token; map '
        f'via a declared table. Test the denial path.</span>'),
        n_node(LAVA, WHITE, 3) + "spacingLeft=48;", X, 756, W, 108)
    d.add("codeico", "", icon("ai-search"), X + 12, 794, 30, 30)

    d.add("pg", esc(
        f'<b style="font-size:{N_TITLE}px;color:{NAVY_DEEP};">no &#8594; consider pgvector on '
        f'Lakebase</b><br><span style="font-size:{N_DETAIL}px;color:{NAVY_DEEP};">Your ACL becomes '
        f'a row-level security policy the engine evaluates, rather than your retrieval code.</span>'),
        n_node(NAVY, WHITE, 3) + "spacingLeft=48;", X, 884, W, 96)
    d.add("pgico", "", icon("lakebase"), X + 12, 916, 30, 30)

    d.add("d3", esc(f'<b style="font-size:{N_TITLE}px;">Does the chain need UC Volumes '
                    f'or file operations?</b>'),
          n_decision(), X + 40, 1000, W - 80, 116)

    d.add("host", esc(
        f'<span style="font-size:{N_DETAIL}px;color:{NAVY_DEEP};">'
        f'<b>yes</b> &#8594; Databricks Apps is the only host that reaches Volumes.<br>'
        f'<b>no</b> &#8594; either host. Write the chain so it does not know which, and that stays '
        f'a configuration change.</span>'),
        n_note(LAVA, WHITE), X, 1140, W, 80)

    for i, (a, b) in enumerate((("start", "d1"), ("d1", "uc"), ("uc", "note1"),
                                ("note1", "d2"), ("d2", "code"), ("code", "pg"),
                                ("pg", "d3"), ("d3", "host"))):
        style = edge(NAVY, 2, fsize=N_DETAIL) if b not in ("uc",) else edge(GREEN, 3, fsize=N_DETAIL)
        d.link(f"t{i}", a, b, style, ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")

    d.write("decision-tree-narrow.drawio")


def architecture_narrow():
    """The three lanes stacked: identity, then build, then serve."""
    d = Doc("rls-architecture-narrow", "RLS architecture (narrow)", NARROW_W, 1430)
    _n_head(d, "Row-level security in a<br>Databricks RAG pipeline",
            "Border colour shows which layer enforces.", h=118)

    # Legend
    d.add("lg", esc(f'<span style="font-size:{N_DETAIL}px;color:{NAVY_DEEP};">'
                    f'<b><span style="color:{GREEN};">&#9632;</span> Unity Catalog enforces</b>'
                    f' &nbsp; <b><span style="color:{LAVA};">&#9632;</span> your code enforces</b>'
                    f'<br><b><span style="color:{LAVA_DEEP};">&#9632;</span> nothing enforces</b>'
                    f'</span>'),
          f"rounded=0;html=1;whiteSpace=wrap;fillColor={WHITE};strokeColor={OAT_LINE};"
          f"strokeWidth=1;align=left;spacingLeft=12;verticalAlign=middle;"
          f"fontSize={N_DETAIL};{FONT}", X, 148, W, 44)

    # ── IDENTITY ─────────────────────────────────────────────────────────────────
    d.add("id", esc("IDENTITY  ·  which caller reaches Unity Catalog"),
          zone(LAVA, WHITE, 46), X, 200, W, 300)
    d.add("usr", n_html("User asks a question", "in a web UI, Teams, …"),
          n_node(OAT_LINE) + "spacingLeft=48;", 20, 62, HALF, 112, "id")
    d.add("usrico", "", icon("ms-person"), 32, 103, 30, 30, "id")
    d.add("exch", n_html("RFC 8693 token exchange", "the front end returns an Entra token;",
                         "Databricks rejects it, so the bot swaps it"),
          n_node(OAT_LINE) + "spacingLeft=48;", 410, 62, HALF, 112, "id")
    d.add("exchico", "", icon("az-appreg"), 422, 103, 30, 30, "id")
    d.add("host", esc(
        f'<span style="font-size:{N_DETAIL}px;color:{NAVY_DEEP};">'
        f'<b>Apps</b> reads the token from a header and reaches Volumes.<br>'
        f'<b>Model Serving</b> holds it in the runtime, but not Volumes.</span>'),
        n_note(LAVA, WHITE), 20, 196, 720, 82, "id")
    d.link("i1", "usr", "exch", edge(fsize=N_DETAIL), "", ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;",
           parent="id")
    d.link("i2", "exch", "host", edge(fsize=N_DETAIL), "", ports="exitX=0.5;exitY=1;entryX=0.75;entryY=0;",
           parent="id")

    # ── BUILD ────────────────────────────────────────────────────────────────────
    d.add("bl", esc("BUILD  ·  where platform enforcement stops"),
          zone(LAVA, WHITE, 46), X, 530, W, 300)
    d.add("pipe", n_html("Gather &#8594; parse &#8594; chunk &#8594; enrich &#8594; embed",
                         "one governed Unity Catalog artefact per stage"),
          n_node(LAVA) + "spacingLeft=18;", 20, 62, HALF, 115, "bl")
    d.add("brk", esc(
        f'<b style="font-size:{N_TITLE}px;color:{LAVA_DEEP};">enforcement stops here</b><br>'
        f'<span style="font-size:{N_DETAIL}px;color:{NAVY_DEEP};">a vector is a list of floats; '
        f'the security context does not reach the index</span>'),
        n_node(LAVA_DEEP, WHITE, 3, dashed=True) + "spacingLeft=18;", 410, 62, HALF, 115, "bl")
    d.add("srv", n_html("AI Search index", "the ACL columns must be written here, at build"),
          n_node(LAVA) + "spacingLeft=48;", 20, 198, 720, 78, "bl")
    d.add("srvico", "", icon("ai-search"), 32, 222, 30, 30, "bl")
    d.link("p1", "pipe", "brk", edge(LAVA_DEEP, 3, fsize=N_DETAIL), "",
           ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="bl")
    d.link("p2", "brk", "srv", edge(LAVA_DEEP, 3, fsize=N_DETAIL), "",
           ports="exitX=0.5;exitY=1;entryX=0.75;entryY=0;", parent="bl")

    # ── SERVE ────────────────────────────────────────────────────────────────────
    d.add("sv", esc("SERVE  ·  two retrieval paths, two enforcers"),
          zone(LAVA, WHITE, 46), X, 860, W, 380)
    d.add("agent", n_html("RAG agent", "runs on the caller's credentials"),
          n_node(LAVA) + "spacingLeft=48;", 20, 62, HALF, 84, "sv")
    d.add("agentico", "", icon("agent-bricks"), 32, 89, 30, 30, "sv")
    d.add("acl", n_html("SCIM &#8594; grants table &#8594; assert_enforceable",
                        "raise, never warn"),
          n_node(LAVA) + "spacingLeft=18;", 410, 62, HALF, 94, "sv")
    d.add("idx2", n_html("AI Search index", "similarity + your filter"),
          n_node(LAVA) + "spacingLeft=18;", 20, 176, HALF, 88, "sv")
    d.add("genie", n_html("Genie Agent", "SQL, Unity Catalog per caller"),
          n_node(GREEN) + "spacingLeft=18;", 410, 176, HALF, 88, "sv")
    d.add("ans", esc(
        f'<b style="font-size:{N_TITLE}px;color:{NAVY_DEEP};">Answer + which control applied</b>'
        f'<br><span style="font-size:{N_DETAIL}px;color:{NAVY_DEEP};">so a citation traces back to '
        f'the permission that admitted it</span>'),
        n_node(NAVY, WHITE, 3) + "spacingLeft=18;", 20, 282, 720, 78, "sv")
    d.link("v1", "agent", "acl", edge(fsize=N_DETAIL), "", ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;",
           parent="sv")
    d.link("v2", "acl", "idx2", edge(LAVA, 2, fsize=N_DETAIL), "", ports="exitX=0;exitY=1;entryX=1;entryY=0.25;",
           parent="sv")
    d.link("v3", "acl", "genie", edge(GREEN, 2, fsize=N_DETAIL), "", ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;",
           parent="sv")
    d.link("v4", "idx2", "ans", edge(LAVA, 2, fsize=N_DETAIL), "", ports="exitX=0.5;exitY=1;entryX=0.25;entryY=0;",
           parent="sv")
    d.link("v5", "genie", "ans", edge(GREEN, 2, fsize=N_DETAIL), "", ports="exitX=0.5;exitY=1;entryX=0.75;entryY=0;",
           parent="sv")

    d.link("z1", "id", "bl", edge(NAVY, 3, fsize=N_DETAIL), "", ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    d.link("z2", "bl", "sv", edge(NAVY, 3, fsize=N_DETAIL), "", ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")

    _n_foot(d, 1270, "Every failure marked here happens with no error. Where Unity Catalog "
                     "enforces, a mistake raises; where your code does, it returns rows.")
    d.write("architecture-narrow.drawio")


if __name__ == "__main__":
    print("Generating Databricks-branded diagrams:")
    architecture()
    decision_tree()
    build_and_serve()
    governance_boundary()
    acl_flow()
    print("  narrow variants, for an article column:")
    governance_boundary_narrow()
    build_and_serve_narrow()
    acl_flow_narrow()
    decision_tree_narrow()
    architecture_narrow()
