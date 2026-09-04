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
GREEN = "#71C5AD"      # accent — used here for "platform enforces"

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


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def html(title: str, *lines: str, tcol: str = NAVY_DEEP, tsize: int = 12) -> str:
    """Build an XML-escaped inline-HTML label: bold title over small grey detail lines.

    Consolidating into one value (rather than stacking text cells) is what keeps labels
    from overlapping — the problem the drawio skill calls out.
    """
    out = f'<b style="font-size:{tsize}px;color:{tcol};">{title}</b>'
    for ln in lines:
        out += f'<br><span style="font-size:10px;color:{NAVY_SOFT};">{ln}</span>'
    return esc(out)


# ── Text fitting ─────────────────────────────────────────────────────────────────
# draw.io does not grow a box to fit its label, so an under-sized box silently
# overlaps its own text. These estimate the rendered height of an inline-HTML label
# and assert the box is big enough, which turns a layout bug into a build failure.

_CH_W = {10: 5.35, 11: 5.85, 12: 6.4, 13: 6.9, 20: 10.6}


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
        f"fontSize=14;fontStyle=1;align=left;spacingLeft=14;verticalAlign=middle;"
        f"container=1;collapsible=0;{FONT}"
    )


def node(stroke: str, fill: str = WHITE, width: int = 2, dashed: bool = False) -> str:
    d = "dashed=1;dashPattern=6 4;fixDash=1;" if dashed else ""
    return (
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={fill};strokeColor={stroke};"
        f"strokeWidth={width};{d}align=left;spacingLeft=44;verticalAlign=middle;spacing=6;"
        f"fontSize=12;fontStyle=0;fontColor={NAVY_DEEP};{FONT}"
    )


def plain(stroke: str, fill: str = WHITE, width: int = 2) -> str:
    return (
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={fill};strokeColor={stroke};"
        f"strokeWidth={width};align=center;verticalAlign=middle;spacing=6;"
        f"fontSize=12;fontStyle=0;fontColor={NAVY_DEEP};{FONT}"
    )


def decision() -> str:
    return (
        f"rhombus;html=1;whiteSpace=wrap;fillColor={WHITE};strokeColor={NAVY};strokeWidth=2;"
        f"align=center;verticalAlign=middle;fontSize=12;fontStyle=0;fontColor={NAVY_DEEP};{FONT}"
    )


def store(stroke: str) -> str:
    return (
        f"shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=12;html=1;whiteSpace=wrap;"
        f"fillColor={WHITE};strokeColor={stroke};strokeWidth=2;align=center;verticalAlign=middle;"
        f"fontSize=11;fontStyle=0;fontColor={NAVY_DEEP};{FONT}"
    )


def note(stroke: str = OAT_LINE, fill: str = OAT_LIGHT) -> str:
    return (
        f"shape=note;size=14;html=1;whiteSpace=wrap;fillColor={fill};strokeColor={stroke};"
        f"strokeWidth=1;align=left;verticalAlign=top;spacing=8;fontSize=10;fontStyle=0;"
        f"fontColor={NAVY_DEEP};{FONT}"
    )


def icon(slug: str) -> str:
    return (
        f"shape=image;html=1;imageAspect=1;verticalAlign=middle;labelBackgroundColor=none;"
        f"image={ICONS[slug]};"
    )


def edge(color: str = NAVY, width: int = 2, dashed: bool = False, arrow: str = "block") -> str:
    d = "dashed=1;dashPattern=6 4;fixDash=1;" if dashed else ""
    return (
        f"edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;jettySize=auto;orthogonalLoop=1;"
        f"endArrow={arrow};endFill=1;strokeColor={color};strokeWidth={width};{d}"
        f"labelBackgroundColor={WHITE};labelBorderColor=none;fontSize=10;fontStyle=1;"
        f"fontColor={NAVY_DEEP};{FONT}"
    )


def title(txt: str, sub: str) -> str:
    return esc(
        f'<b style="font-size:20px;color:{NAVY_DEEP};">{txt}</b>'
        f'<br><span style="font-size:12px;color:{NAVY_SOFT};">{sub}</span>'
    )


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
    d = Doc("rls-architecture", "RLS reference architecture", 1720, 1140)

    d.add("title", title(
        "Row-level security in a Databricks RAG pipeline",
        "Border colour says who enforces access control."),
        f"text;html=1;whiteSpace=wrap;strokeColor=none;fillColor=none;align=left;"
        f"verticalAlign=middle;{FONT}", 40, 18, 940, 75)

    # Legend
    d.add("lg", esc(f'<b style="color:{NAVY_DEEP};">Who enforces</b>'),
          f"rounded=0;html=1;fillColor={WHITE};strokeColor={OAT_LINE};strokeWidth=2;"
          f"verticalAlign=top;align=left;spacingLeft=10;spacingTop=6;fontSize=11;"
          f"container=1;collapsible=0;{FONT}", 1270, 16, 410, 196)
    for i, (lbl, col) in enumerate([
        ("Unity Catalog enforces, and gives notice when it goes wrong", GREEN),
        ("Your code enforces, however you wrote it", LAVA),
        ("Nothing enforces here at all", LAVA_DEEP),
        ("Outside Databricks", OAT_LINE),
    ]):
        d.add(f"lgr{i}", esc(f'<span style="color:{NAVY_DEEP};">{lbl}</span>'),
              f"rounded=0;html=1;fillColor={WHITE};strokeColor={col};strokeWidth=3;"
              f"align=left;spacingLeft=8;fontSize=10;{FONT}", 12, 30 + i * 38, 386, 34, "lg")

    # ── Lane 1: identity ─────────────────────────────────────────────────────────
    d.add("idlane", esc("IDENTITY  ·  which caller reaches Unity Catalog"), zone(LAVA, WHITE, 46), 40, 150, 1230, 204)

    d.add("usr", html("User", "asks a question"), node(OAT_LINE), 20, 76, 130, 68, "idlane")
    d.badge("usrico", "ms-person", "usr", size=30)
    d.add("teams", html("Microsoft Teams", "Bot Framework OAuth",
                        f'<b style="color:{LAVA_DEEP};">returns an <b>Entra</b> token</b>'),
          node(OAT_LINE), 160, 72, 190, 78, "idlane")
    d.badge("teamsico", "ms-teams", "teams", size=34)
    d.add("exch", html("RFC 8693 exchange", "POST /oidc/v1/token",
                       f'<b style="color:{LAVA_DEEP};">needs an account-level policy</b>'),
          node(OAT_LINE), 385, 72, 195, 78, "idlane")
    d.badge("exchico", "az-appreg", "exch", size=32)

    d.add("apps", html("Databricks Apps", "x-forwarded-access-token",
                       f'<b style="color:#2E7D32;">widest scope, reaches Volumes</b>'),
          node(LAVA), 620, 56, 250, 62, "idlane")
    d.badge("appsico", "databricks-apps", "apps", size=30)
    d.add("msrv", html("Model Serving", "ModelServingUserCredentials()",
                       f'<b style="color:{LAVA_DEEP};">no Volumes, no file operations</b>'),
          node(LAVA), 620, 130, 250, 62, "idlane")
    d.badge("msrvico", "model-serving", "msrv", size=30)

    d.add("warn1", esc(
        f'<b style="color:{LAVA_DEEP};">Silent</b><br>'
        f'<span style="font-size:10px;">Below <b>mlflow 2.22.1</b> OBO is off by default and the '
        f'agent answers as the <b>endpoint</b>. No error, no warning, no log line.</span>'),
        note(LAVA_DEEP, WHITE), 905, 62, 200, 100, "idlane")

    for cid, s, t in [("e1", "usr", "teams"), ("e2", "teams", "exch")]:
        d.link(cid, s, t, edge(), ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    d.link("e3", "exch", "apps", edge(), "user token",
           [(600, 131), (600, 107)], "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="idlane")
    d.link("e4", "exch", "msrv", edge(), "user token",
           [(600, 111), (600, 161)], "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="idlane")

    # ── Lane 2: indexing ─────────────────────────────────────────────────────────
    d.add("pipe", esc("BUILD  ·  the pipeline, and where platform enforcement stops"),
          zone(LAVA, WHITE, 46), 40, 378, 1640, 200)

    stages = [
        ("s12", "1–2 Gather · Load", "Volume &#8594; bronze", 20, 150),
        ("s34", "3–4 Parse · Chunk", "silver text &#8594; chunks", 190, 150),
        ("s7", "7 Combine", "gold one-big-table", 545, 140),
        ("s8", "8 Embed", "index source", 705, 130),
    ]
    for cid, t, sub, x, w in stages:
        d.add(cid, html(t, sub), plain(LAVA), x, 66, w, 66, "pipe")

    d.add("s56", html("5–6 Enrich · Join",
                      f'<b style="color:{LAVA_DEEP};">where ACL columns</b>',
                      f'<b style="color:{LAVA_DEEP};">are carried</b>'),
          plain(LAVA, WHITE, 3), 360, 66, 165, 66, "pipe")

    d.add("s9", html("9 Serve", "AI Search index"), plain(LAVA_DEEP, WHITE, 3) +
          "align=left;spacingLeft=40;", 980, 66, 170, 66, "pipe")
    d.badge("s9ico", "ai-search", "s9", size=28)

    d.add("break", esc(
        f'<b style="color:{LAVA_DEEP};font-size:11px;">enforcement<br>stops here</b>'
        f'<br><span style="font-size:10px;color:{NAVY_SOFT};">a vector is a<br>list of floats</span>'),
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={WHITE};strokeColor={LAVA_DEEP};"
        f"strokeWidth=3;dashed=1;dashPattern=6 4;fixDash=1;align=center;verticalAlign=middle;"
        f"fontSize=10;{FONT}", 862, 58, 106, 82, "pipe")

    d.add("meta", esc(
        f'<b>Metadata is content.</b><br><span style="font-size:10px;">Whatever you index is '
        f'readable by anyone who can query the index, <i>created_by_email</i> and <i>web_url</i> included. '
        f'The ACL applies before any column is returned, not just the chunk text.</span>'),
        note(), 1180, 62, 210, 100, "pipe")
    d.add("cols", esc(
        f'<b>ACL_FILTER_COLUMNS</b><br><span style="font-size:10px;">source_system · site_id · '
        f'sensitivity<br><br><i>Your ACL can never be more expressive than the columns you '
        f'carried at index time. Getting it wrong is a <b>rebuild</b>.</i></span>'),
        note(LAVA, WHITE), 1410, 62, 200, 100, "pipe")

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
          zone(LAVA, WHITE, 46), 40, 602, 1640, 360)

    d.add("agent", html("RAG agent", "runs on the", "<b>caller's</b> client"),
          node(LAVA) + "spacingLeft=42;", 20, 128, 150, 66, "q")
    d.badge("agentico", "agent-bricks", "agent", size=30)
    d.add("route", esc('<b style="font-size:11px;">model<br>routes</b>'), decision(), 195, 146, 120, 70, "q")

    d.add("scim", html("SCIM /Me", "the caller's groups,", "resolved per request"),
          node(LAVA) + "spacingLeft=12;", 350, 62, 180, 88, "q")
    d.add("grants", html("declared grants table", "group &#8594; entitlement",
                         "<i>once one group is a tuple</i>"),
          node(LAVA) + "spacingLeft=12;", 550, 62, 195, 88, "q")
    d.add("guard", html("assert_enforceable()", "axes &#8594; index columns?",
                        f'<b style="color:{LAVA_DEEP};">raise, never warn</b>'),
          node(LAVA, WHITE, 3) + "spacingLeft=12;", 765, 62, 200, 88, "q")
    d.add("idx", esc('<b style="font-size:11px;">AI Search index</b>'
                     '<br><span style="font-size:10px;">similarity + filter</span>'),
          store(LAVA_DEEP), 980, 56, 160, 76, "q")
    d.badge("idxico", "ai-search", "idx", size=28, side="right")

    d.add("genie", html("Genie space", "generates SQL"), node(LAVA) + "spacingLeft=42;", 355, 252, 160, 60, "q")
    d.badge("genieico", "genie-agents", "genie", size=30)
    d.add("uc", html("Unity Catalog", "row filters + column masks",
                     f'<b style="color:#2E7D32;">evaluated per caller</b>'),
          node(GREEN, WHITE, 3) + "spacingLeft=42;", 555, 252, 210, 73, "q")
    d.badge("ucico", "unity-catalog", "uc", size=30)
    d.add("tbl", esc('<b style="font-size:11px;">governed tables</b>'), store(GREEN), 800, 246, 150, 72, "q")
    d.badge("tblico", "abac", "tbl", size=28, side="right")

    d.add("ans", html("Answer", "+ which control applied"),
          plain(NAVY) + f"fillColor={OAT_LIGHT};", 1250, 148, 160, 66, "q")

    d.add("deny", esc(
        f'<b style="color:{LAVA_DEEP};">no entitlement</b><br>'
        f'<span style="font-size:10px;">0 rows, and the model is never called. '
        f'A fluent answer from general knowledge is indistinguishable from a real retrieval.</span>'),
        note(LAVA_DEEP, WHITE), 980, 148, 175, 92, "q")

    d.add("drop", esc(
        f'<b style="color:{LAVA_DEEP};">Silently ignored</b><br>'
        f'<span style="font-size:10px;">A filter naming a column the index does not have stops '
        f'constraining. No error, no log line, and a plausible row count.</span>'), note(LAVA_DEEP, WHITE), 1190, 56, 220, 84, "q")

    d.add("sp", esc(
        f'<b style="color:{LAVA_DEEP};">Non-interactive callers</b><br>'
        f'<span style="font-size:10px;">On a service-principal path the SP is the evaluated '
        f'identity, so every human calling through it sees the union of what the SP was granted. '
        f'Review what the SP is granted, not the space.</span>'),
        note(LAVA_DEEP, WHITE), 1190, 246, 220, 109, "q")

    d.link("q1", "agent", "route", edge(), ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="q")
    d.link("q2", "route", "scim", edge(), "prose",
           [(335, 181), (335, 96)], "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="q")
    d.link("q3", "route", "genie", edge(), "numbers",
           [(335, 181), (335, 282)], "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="q")
    for i, (s, t) in enumerate([("scim", "grants"), ("grants", "guard"), ("guard", "idx")]):
        d.link(f"q4{i}", s, t, edge(), ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;",
               parent="q")
    d.link("q7", "guard", "deny", edge(LAVA_DEEP, 2, True), "0 rows",
           [(835, 194)], "exitX=0.5;exitY=1;entryX=0;entryY=0.5;", parent="q")
    d.link("q8", "genie", "uc", edge(GREEN), ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="q")
    d.link("q9", "uc", "tbl", edge(GREEN), ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="q")
    d.link("q10", "idx", "ans", edge(), "",
           [(1170, 94), (1170, 165)], "exitX=1;exitY=0.5;entryX=0;entryY=0.25;", parent="q")
    d.link("q11", "tbl", "ans", edge(GREEN), "",
           [(1170, 282), (1170, 198)], "exitX=1;exitY=0.5;entryX=0;entryY=0.75;", parent="q")

    d.add("foot", esc(
        f'<span style="font-size:12px;color:{NAVY_DEEP};">Every silent failure marked here sits on '
        f'a lava or deep-lava border. Where Unity Catalog enforces, a mistake raises; where your '
        f'code does, it returns rows.</span>'),
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={OAT};strokeColor=none;align=left;"
        f"spacingLeft=16;spacingTop=10;verticalAlign=top;fontSize=12;{FONT}", 40, 986, 1640, 81)

    d.add("cred", esc(f'<span style="color:{NAVY_SOFT};">OneDNA · onedna.nl · '
                      f'Databricks RAG row-level security</span>'),
          f"text;html=1;align=right;verticalAlign=middle;fontSize=11;{FONT}", 1180, 1082, 500, 36)
    d.write("architecture.drawio")


# ═════════════════════════════════════════════════════════════════════════════════
# Diagram 2 — decision tree
# ═════════════════════════════════════════════════════════════════════════════════
def decision_tree():
    d = Doc("rls-decision-tree", "Which enforcement path", 1440, 1020)

    d.add("t", title("Which enforcement path should you use?",
                     'Who enforces it, and how would you know if they stopped.'),
          f"text;html=1;whiteSpace=wrap;strokeColor=none;fillColor=none;align=left;"
          f"verticalAlign=middle;{FONT}", 40, 20, 960, 73)

    d.add("start", esc('<b>You need per-user access control<br>over retrieved content</b>'),
          f"ellipse;html=1;whiteSpace=wrap;fillColor={OAT_LIGHT};strokeColor={NAVY};"
          f"strokeWidth=2;align=center;verticalAlign=middle;fontSize=13;fontColor={NAVY_DEEP};"
          f"{FONT}", 560, 100, 290, 68)

    d.add("d1", esc("<b>Is the content<br>structured?</b>"), decision(), 615, 214, 180, 96)
    d.add("d2", esc("<b>Interactive caller?</b><br>"
                    f'<span style="font-size:10px;color:{NAVY_SOFT};">a human, live</span>'),
          decision(), 245, 382, 185, 96)
    d.add("d3", esc("<b>Does the ACL fit the<br>index metadata columns?</b><br>"
                    f'<span style="font-size:10px;color:{NAVY_SOFT};">flat, per-chunk, no joins'
                    "</span>"), decision(), 950, 372, 225, 116)

    outcomes = [
        ("uc", "unity-catalog", GREEN, "Unity Catalog RLS",
         "row filters and column masks, or an ABAC policy at catalog scope",
         "<b>The platform enforces.</b> Resolves per caller, and survives the agent and Teams "
         "hops.<br><br>Verify it by breaking it.", 60, 570, 240, 178),
        ("sp", "sql-warehouse", LAVA_DEEP, "Review the SP's grants",
         "the service principal <b>is</b> the identity",
         "Every human calling through it sees the union of what the SP may read, with "
         "no differentiation between them. On this path that is the whole of your "
         "access control.", 340, 570, 245, 196),
        ("code", "ai-search", LAVA, "Code ACL + assert_enforceable",
         "you enforce, at query time",
         "Resolve groups per request from the caller's own token. A naming convention works until "
         "access is a <b>combination</b> of columns; then use a <b>declared table</b>."
         "<br><br>Fail closed. Empty is the default. Malformed raises."
         "<br><br>Test by breaking it: the happy path passes either way.",
         860, 570, 255, 210),
        ("pg", "lakebase", NAVY, "Consider pgvector on Lakebase",
         "move enforcement back into the database",
         "Your ACL becomes a row-level security policy again, evaluated by the engine rather "
         "than by your retrieval code.<br><br>A governance argument rather than a latency one, "
         "and the stronger of the two.", 1160, 570, 235, 210),
    ]
    for cid, ico, col, head, sub, body, x, y, w, h in outcomes:
        d.add(cid, esc(
            f'<b style="font-size:13px;color:{NAVY_DEEP};">{head}</b><br>'
            f'<span style="font-size:10px;color:{NAVY_SOFT};">{sub}</span><br><br>'
            f'<span style="font-size:10px;color:{NAVY_DEEP};">{body}</span>'),
            f"rounded=0;html=1;whiteSpace=wrap;fillColor={WHITE};strokeColor={col};"
            f"strokeWidth=3;align=left;spacingLeft=12;spacingRight=10;verticalAlign=top;"
            f"spacingTop=40;fontSize=12;{FONT}", x, y, w, h)
        d.add(f"{cid}ico", "", icon(ico), x + 12, y + 10, 26, 26)

    d.add("d4", esc("<b>Does the chain need<br>UC Volumes or file ops?</b>"),
          decision(), 875, 830, 225, 106)
    d.add("hostA", html("Databricks Apps", "the only host that reaches Volumes"),
          node(LAVA) + "spacingLeft=42;", 1160, 848, 235, 66)
    d.add("hostAico", "", icon("databricks-apps"), 1170, 864, 28, 28)
    d.add("hostB", html("Apps or Model Serving",
                        "write the chain host-agnostically", "and it stays a config change"),
          node(LAVA) + "spacingLeft=42;", 590, 848, 250, 78)
    d.add("hostBico", "", icon("model-serving"), 610, 864, 28, 28)

    d.link("c1", "start", "d1", edge(), ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    d.link("c2", "d1", "d2", edge(), "tables, rows, numbers", [(337, 262)],
           "exitX=0;exitY=0.5;entryX=0.5;entryY=0;")
    d.link("c3", "d1", "d3", edge(), "documents, prose", [(1062, 262)],
           "exitX=1;exitY=0.5;entryX=0.5;entryY=0;")
    d.link("c4", "d2", "uc", edge(GREEN), "yes, a human asks", [(180, 430)],
           "exitX=0;exitY=0.5;entryX=0.5;entryY=0;")
    d.link("c5", "d2", "sp", edge(LAVA_DEEP), "no, a service principal",
           [(337, 526), (462, 526)], "exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    # The waypoint has to clear d3's own left edge (x=950). Routing to the target's
    # centre (987) would put it INSIDE the diamond, so the line crosses the shape and
    # its label -- the mirrored c4 edge only looks the same because uc's centre
    # happens to fall outside d2. Turn left of the node, then drop to the target.
    d.link("c6", "d3", "code", edge(LAVA), "yes, flat and per-chunk",
           [(910, 430), (910, 530), (987, 530)],
           "exitX=0;exitY=0.5;entryX=0.5;entryY=0;")
    d.link("c7", "d3", "pg", edge(), "no, needs joins or&#10;external rules",
           [(1277, 430)], "exitX=1;exitY=0.5;entryX=0.5;entryY=0;")
    d.link("c8", "code", "d4", edge(), ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    d.link("c9", "d4", "hostA", edge(), "yes", ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    d.link("c10", "d4", "hostB", edge(), "no", ports="exitX=0;exitY=0.5;entryX=1;entryY=0.5;")

    d.add("note", esc(
        f'<b style="font-size:13px;color:{NAVY_DEEP};">Whichever branch you land on</b><br>'
        f'<span style="font-size:11px;color:{NAVY_DEEP};">'
        f'<b>1.</b> Point the filter at something that must return nothing, and watch it return '
        f'nothing. Until you have seen it fail on purpose, you have only seen it succeed.<br>'
        f'<b>2.</b> Make your two zeros distinguishable: "no entitlement" and "something broke" '
        f'look identical from outside.<br>'
        f'<b>3.</b> Assert on the identity that produced the answer. An answer arriving tells '
        f'you nothing about who it was filtered for.</span>'),
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={OAT};strokeColor=none;align=left;"
        f"spacingLeft=14;spacingTop=10;verticalAlign=top;fontSize=11;{FONT}", 60, 810, 490, 146)

    d.add("cred", esc(f'<span style="color:{NAVY_SOFT};">OneDNA · onedna.nl</span>'),
          f"text;html=1;align=right;verticalAlign=middle;fontSize=11;{FONT}", 1000, 958, 395, 36)
    d.write("decision-tree.drawio")



# ═════════════════════════════════════════════════════════════════════════════════
# Diagram 3 — build and serve, the two halves of the platform
# ═════════════════════════════════════════════════════════════════════════════════
def build_and_serve():
    d = Doc("build-serve", "Build and serve", 1520, 820)

    d.add("t", title("Two halves of the same platform",
                     "Build runs on a schedule and writes the index. Serve is a live "
                     "request path and only reads it."),
          f"text;html=1;whiteSpace=wrap;strokeColor=none;fillColor=none;align=left;"
          f"verticalAlign=middle;{FONT}", 40, 20, 1000, 62)

    # ---- BUILD ----
    d.add("build", esc("BUILD  ·  batch, scheduled"), zone(LAVA, WHITE, 46), 40, 100, 660, 560)

    d.add("src", html("Source systems", "SharePoint, fileshares.",
                      "Owners publish there;", "nothing is copied by hand."),
          node(OAT_LINE) + "spacingLeft=12;", 24, 60, 200, 96, "build")

    d.add("prep", html("Preprocessing", "raw &#8594; bronze &#8594; silver &#8594; gold",
                       "parse, chunk, enrich, embed"),
          node(LAVA) + "spacingLeft=48;", 250, 60, 250, 96, "build")
    d.badge("prepico", "delta-lake", "prep", size=30)

    d.add("idx", esc('<b style="font-size:12px;">AI Search index</b>'
                     '<br><span style="font-size:10px;color:' + NAVY_SOFT + ';">'
                     'written only here</span>'),
          store(LAVA_DEEP), 24, 200, 250, 76, "build")

    d.add("agentdev", html("Agent development",
                           "chain &#8594; tool &#8594; retriever &#8594; <b>ACL</b>",
                           "built and versioned separately,",
                           "then deployed as one endpoint"),
          node(LAVA) + "spacingLeft=48;", 24, 320, 300, 96, "build")
    d.badge("agentdevico", "agent-bricks", "agentdev", size=30)

    d.add("uc", html("Unity Catalog",
                     "one governance layer over both: lineage for every",
                     "artefact the pipeline writes, and the grants the",
                     "agent&apos;s ACL resolves against at query time"),
          node(GREEN, WHITE, 3) + "spacingLeft=48;", 24, 440, 610, 100, "build")
    d.badge("ucico2", "unity-catalog", "uc", size=30)

    d.add("acln", esc(
        f'<b style="color:{LAVA_DEEP};">The index has no row filter</b>'
        f'<br><span style="font-size:10px;">Whatever the ACL needs at query time has to be written '
        f'into a metadata column here, at build. Changing that later means a rebuild.</span>'),
        note(LAVA_DEEP, WHITE), 300, 196, 335, 100, "build")

    d.link("b1", "src", "prep", edge(), "on change",
           ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="build")
    d.link("b2", "prep", "idx", edge(LAVA_DEEP, 3), "writes",
           [(160, 178)], "exitX=0;exitY=1;entryX=0.5;entryY=0;", parent="build")
    d.link("b3", "agentdev", "idx", edge(NAVY, 2, True), "built against",
           ports="exitX=0.25;exitY=0;entryX=0.25;entryY=1;", parent="build")

    # ---- SERVE ----
    d.add("serve", esc("SERVE  ·  live request"), zone(LAVA, WHITE, 46), 740, 100, 720, 560)

    d.add("ui", html("User interface", "Teams, web UI.", "Asks questions, gets answers."),
          node(OAT_LINE) + "spacingLeft=48;", 24, 60, 230, 80, "serve")
    d.badge("uiico", "ms-teams", "ui", size=30)

    d.add("agent", html("Deployed agent", "chain &#8594; tool &#8594; <b>ACL</b> &#8594; data",
                        "the ACL narrows retrieval to the caller,",
                        "so <b>one agent serves every audience</b>"),
          node(LAVA, WHITE, 3) + "spacingLeft=48;", 24, 180, 330, 96, "serve")
    d.badge("agentico2", "model-serving", "agent", size=30)

    d.add("read", esc('<b style="font-size:12px;">the same AI Search index</b>'
                      '<br><span style="font-size:10px;color:' + NAVY_SOFT + ';">'
                      'read at query time, never written</span>'),
          store(LAVA_DEEP), 410, 170, 250, 76, "serve")

    d.add("gen", html("Genie space", "SQL over governed tables.",
                      "Unity Catalog evaluates the caller."),
          node(GREEN) + "spacingLeft=48;", 410, 300, 250, 80, "serve")
    d.badge("genico2", "genie-agents", "gen", size=30)

    d.add("who", esc(
        f'<b>Who enforces on each branch</b><br>'
        f'<span style="font-size:10px;">To the index: your ACL, in code, at query time.<br>'
        f'To Genie: Unity Catalog, per caller.<br><br>'
        f'Both run on the caller&apos;s credentials.</span>'),
        note(), 24, 300, 350, 130, "serve")

    d.link("s1", "ui", "agent", edge(), "request",
           ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;", parent="serve")
    d.link("s2", "agent", "read", edge(LAVA), "filtered query",
           ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="serve")
    d.link("s3", "agent", "gen", edge(GREEN), "data question",
           [(385, 228), (385, 340)], "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", parent="serve")

    d.add("foot", esc(
        f'<span style="font-size:11px;color:{NAVY_DEEP};">Enforcing the ACL at query time means no '
        f'per-audience index and no copy of the corpus outside Databricks. The trade is that the '
        f'access decision runs in code you wrote on the serve side, against columns you chose on '
        f'the build side weeks earlier.</span>'),
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={OAT};strokeColor=none;align=left;"
        f"spacingLeft=16;spacingTop=10;verticalAlign=top;fontSize=11;{FONT}", 40, 686, 1420, 70)

    d.add("cred", esc(f'<span style="color:{NAVY_SOFT};">OneDNA · onedna.nl</span>'),
          f"text;html=1;align=right;verticalAlign=middle;fontSize=11;{FONT}", 1060, 758, 400, 36)
    d.write("build-and-serve.drawio")



# ═════════════════════════════════════════════════════════════════════════════════
# Diagram 4 — the governance boundary
# ═════════════════════════════════════════════════════════════════════════════════
def governance_boundary():
    """Where Unity Catalog stops governing, drawn as two zones and one crossing.

    The whole argument is the border colour: green on the left, deep lava on the
    right, and an arrow between them that carries the security context nowhere.
    """
    d = Doc("rls-governance-boundary", "Where platform enforcement stops", 1280, 560)

    d.add("t", title("What the index does not inherit",
                     "A governed table carries its filters. The index built from it does not."),
          f"text;html=1;whiteSpace=wrap;strokeColor=none;fillColor=none;align=left;"
          f"verticalAlign=middle;{FONT}", 40, 20, 900, 72)

    # ── Governed: the platform side ──────────────────────────────────────────────
    d.add("gov", esc("UNITY CATALOG GOVERNS THIS"), zone(GREEN, WHITE, 42), 40, 120, 470, 330)

    d.add("tbl", html("Governed table", "rows and columns in Unity Catalog"),
          node(GREEN), 30, 68, 410, 62, "gov")
    d.badge("tblico", "unity-catalog", "tbl", size=28)

    d.add("rf", html("Row filter", "a UDF, evaluated per caller"),
          node(GREEN) + "spacingLeft=14;", 30, 158, 196, 62, "gov")
    d.add("cm", html("Column mask", "also per caller"),
          node(GREEN) + "spacingLeft=14;", 244, 158, 196, 62, "gov")

    d.add("govnote", esc(
        f'<span style="font-size:10px;color:{NAVY_DEEP};">Attached to the object itself, so every '
        f'reader gets their own view of it — and a mistake here <b>gives notice</b>.</span>'),
        note(GREEN, WHITE), 30, 240, 410, 62, "gov")

    for cid, tgt in [("gl1", "rf"), ("gl2", "cm")]:
        d.link(cid, "tbl", tgt, edge(GREEN, 2, arrow="none"),
               ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;", parent="gov")

    # ── Ungoverned: your side ────────────────────────────────────────────────────
    d.add("ungov", esc("UNITY CATALOG DOES NOT GOVERN THIS"),
          zone(LAVA_DEEP, WHITE, 42), 770, 120, 470, 330)

    d.add("idx", html("AI Search index", "a Unity Catalog object, with grants"),
          node(LAVA_DEEP), 30, 68, 410, 62, "ungov")
    d.badge("idxico", "ai-search", "idx", size=28)

    d.add("gone", esc(
        f'<b style="font-size:11px;color:{LAVA_DEEP};">What did not come along</b><br>'
        f'<span style="font-size:10px;color:{NAVY_DEEP};">no row filter · no column mask<br>'
        f'filtering is a <b>query parameter</b> you pass from application code</span>'),
        node(LAVA_DEEP, WHITE, 2, dashed=True) + "spacingLeft=14;verticalAlign=middle;",
        30, 158, 410, 76, "ungov")

    d.add("ungovnote", esc(
        f'<span style="font-size:10px;color:{NAVY_DEEP};">A filter naming a column the index does '
        f'not have is <b>ignored</b>. No error, no log line, and a plausible row count.</span>'),
        note(LAVA_DEEP, WHITE), 30, 246, 410, 56, "ungov")

    d.link("il", "idx", "gone", edge(LAVA_DEEP, 2, dashed=True, arrow="none"),
           ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;", parent="ungov")

    # ── The crossing ─────────────────────────────────────────────────────────────
    d.add("cross", esc(
        f'<b style="font-size:11px;color:{NAVY_DEEP};">chunk &#8594; embed &#8594; index</b><br>'
        f'<span style="font-size:10px;color:{NAVY_SOFT};">an embedding is a<br>list of floats</span>'),
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={OAT_LIGHT};strokeColor={OAT_LINE};"
        f"strokeWidth=2;align=center;verticalAlign=middle;fontSize=11;{FONT}", 540, 236, 200, 74)

    d.link("x1", "gov", "cross", edge(NAVY, 3), ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    d.link("x2", "cross", "ungov", edge(NAVY, 3), ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")

    d.add("xlbl", esc(
        f'<span style="font-size:10px;color:{LAVA_DEEP};"><b>the security context<br>'
        f'does not cross</b></span>'),
        f"text;html=1;whiteSpace=wrap;strokeColor=none;fillColor=none;align=center;"
        f"verticalAlign=middle;fontSize=10;{FONT}", 540, 320, 200, 46)

    d.add("foot", esc(
        f'<span style="font-size:11px;color:{NAVY_DEEP};">Whatever access control applied to the '
        f'text is not in the vector. The only thing that survives is what you deliberately wrote '
        f'into metadata columns alongside it — so your ACL can never be more expressive than the '
        f'columns you carried at index time.</span>'),
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={OAT};strokeColor=none;align=left;"
        f"spacingLeft=16;spacingTop=10;verticalAlign=top;fontSize=11;{FONT}", 40, 472, 1200, 56)

    d.add("cred", esc(f'<span style="color:{NAVY_SOFT};">OneDNA · onedna.nl</span>'),
          f"text;html=1;align=right;verticalAlign=middle;fontSize=11;{FONT}", 840, 528, 400, 26)
    d.write("governance-boundary.drawio")


# ═════════════════════════════════════════════════════════════════════════════════
# Diagram 5 — the ACL resolution flow
# ═════════════════════════════════════════════════════════════════════════════════
def acl_flow():
    """Caller to filtered query, with both closed exits drawn as prominently as the happy path.

    The two terminal states on the right (zero rows, PermissionError) are the point:
    every branch that cannot resolve an entitlement ends somewhere explicit.
    """
    d = Doc("rls-acl-flow", "How the ACL resolves per request", 1560, 680)

    d.add("t", title("How the ACL resolves, per request",
                     "Every branch that cannot answer \"who is asking\" ends closed."),
          f"text;html=1;whiteSpace=wrap;strokeColor=none;fillColor=none;align=left;"
          f"verticalAlign=middle;{FONT}", 40, 18, 900, 68)

    # ── Row 1: resolve who is asking ─────────────────────────────────────────────
    d.add("caller", esc('<b>Caller</b><br>'
                        f'<span style="font-size:10px;color:{NAVY_SOFT};">a human, in Teams</span>'),
          f"ellipse;html=1;whiteSpace=wrap;fillColor={OAT_LIGHT};strokeColor={NAVY};"
          f"strokeWidth=2;align=center;verticalAlign=middle;fontSize=12;fontColor={NAVY_DEEP};"
          f"{FONT}", 40, 116, 180, 66)

    d.add("tok", html("Their OBO token", "not the endpoint's identity"),
          node(OAT_LINE) + "spacingLeft=44;", 270, 114, 210, 70)
    d.add("tokico", "", icon("ms-person"), 280, 134, 28, 28)

    d.add("scim", html("SCIM /Me", "group memberships, resolved",
                       "with the caller's own credentials"),
          node(LAVA) + "spacingLeft=14;", 530, 110, 230, 78)

    d.add("groups", esc(
        f'<b style="font-size:11px;">groups</b><br>'
        f'<span style="font-size:10px;color:{NAVY_DEEP};">[group-a, group-b, …]</span>'),
        plain(OAT_LINE, OAT_LIGHT), 810, 116, 190, 66)

    d.add("grantmap", esc('<b>declared<br>grants table</b>'), decision(), 1050, 100, 190, 100)

    d.add("nogrant", esc(
        f'<span style="font-size:10px;color:{NAVY_DEEP};">an unmapped group<br>'
        f'<b>grants nothing</b></span>'),
        plain(OAT_LINE, OAT_LIGHT), 1300, 120, 190, 60)

    # ── Row 2: turn entitlements into a filter ───────────────────────────────────
    d.add("ent", esc(
        f'<b style="font-size:12px;">Entitlements</b><br>'
        f'<span style="font-size:10px;color:{NAVY_DEEP};">source_systems · site_ids<br>'
        f'sensitivity_labels</span>'),
        node(LAVA, WHITE, 2) + "spacingLeft=14;verticalAlign=middle;", 40, 300, 220, 82)

    d.add("empty", esc('<b>is_empty?</b>'), decision(), 310, 296, 180, 90)

    d.add("filt", html("build_filter()", "entitlement over any", "caller-supplied filter"),
          node(LAVA) + "spacingLeft=14;", 540, 302, 220, 78)

    d.add("assert", esc('<b>assert_<br>enforceable</b>'), decision(), 810, 292, 200, 98)

    d.add("query", html("AI Search query", "+ the entitlement filter"),
          node(GREEN) + "spacingLeft=44;", 1060, 306, 240, 70)
    d.add("queryico", "", icon("ai-search"), 1070, 322, 30, 30)

    # ── Terminal states, both closed ─────────────────────────────────────────────
    d.add("zero", esc(
        f'<b style="font-size:12px;color:{LAVA_DEEP};">Return no rows</b><br>'
        f'<span style="font-size:10px;color:{NAVY_DEEP};">and an explicit denial naming which '
        f'groups granted nothing.<br><br><b>The model is never called.</b> A fluent answer from '
        f'general knowledge is indistinguishable from a real retrieval.</span>'),
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={WHITE};strokeColor={LAVA_DEEP};"
        f"strokeWidth=3;align=left;spacingLeft=12;spacingRight=10;verticalAlign=top;"
        f"spacingTop=12;fontSize=11;{FONT}", 290, 490, 260, 150)

    d.add("err", esc(
        f'<b style="font-size:12px;color:{LAVA_DEEP};">PermissionError</b><br>'
        f'<span style="font-size:10px;color:{NAVY_DEEP};">an axis that is not a column of the '
        f'index would not be applied, so the request stops rather than serving unfiltered '
        f'results.</span>'),
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={WHITE};strokeColor={LAVA_DEEP};"
        f"strokeWidth=3;align=left;spacingLeft=12;spacingRight=10;verticalAlign=top;"
        f"spacingTop=12;fontSize=11;{FONT}", 790, 490, 260, 128)

    # ── Edges ────────────────────────────────────────────────────────────────────
    for cid, s, t in [("a1", "caller", "tok"), ("a2", "tok", "scim"),
                      ("a3", "scim", "groups"), ("a4", "groups", "grantmap")]:
        d.link(cid, s, t, edge(), ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")

    d.link("a6", "grantmap", "nogrant", edge(NAVY, 2, dashed=True), "unmapped",
           ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")

    # both the mapped and the unmapped path arrive at the same entitlement object
    d.link("a5", "grantmap", "ent", edge(), "mapped",
           [(1145, 232), (150, 232)], "exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    d.link("a7", "nogrant", "ent", edge(NAVY, 2, dashed=True), "",
           [(1395, 256), (150, 256)], "exitX=0.5;exitY=1;entryX=0.5;entryY=0;")

    d.link("a8", "ent", "empty", edge(), ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    d.link("a10", "empty", "filt", edge(), "no",
           ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    d.link("a11", "filt", "assert", edge(), ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    d.link("a13", "assert", "query", edge(GREEN, 3), "ok",
           ports="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")

    d.link("a9", "empty", "zero", edge(LAVA_DEEP, 3), "yes",
           ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    d.link("a12", "assert", "err", edge(LAVA_DEEP, 3), "unknown axis",
           ports="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")

    d.add("foot", esc(
        f'<span style="font-size:11px;color:{NAVY_DEEP};">Empty means nothing, not everything. A '
        f'malformed mapping raises rather than resolving to empty, so "no entitlement" and '
        f'"something broke" tell themselves apart. A naming convention works while one group means '
        f'one thing; a declared table is what survives a combination of columns.</span>'),
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={OAT};strokeColor=none;align=left;"
        f"spacingLeft=16;spacingTop=10;verticalAlign=top;fontSize=11;{FONT}", 1090, 490, 430, 128)

    d.add("cred", esc(f'<span style="color:{NAVY_SOFT};">OneDNA · onedna.nl</span>'),
          f"text;html=1;align=right;verticalAlign=middle;fontSize=11;{FONT}", 1120, 636, 400, 26)
    d.write("acl-flow.drawio")


if __name__ == "__main__":
    print("Generating Databricks-branded diagrams:")
    architecture()
    decision_tree()
    build_and_serve()
    governance_boundary()
    acl_flow()
