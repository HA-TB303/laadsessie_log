"""Minimale PDF-generator (alleen standaardbibliotheek) en het maandrapport."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, tzinfo

PAGE_W, PAGE_H = 595.28, 841.89  # A4
MARGIN = 45

_HELV = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
         556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
         1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
         667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
         333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
         556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]
_HELV_B = [278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
           556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
           975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
           667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
           333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,
           611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584]

MONTHS = ["januari", "februari", "maart", "april", "mei", "juni", "juli",
          "augustus", "september", "oktober", "november", "december"]
DAYS = ["ma", "di", "wo", "do", "vr", "za", "zo"]

INK = (0.13, 0.15, 0.18)
MUTED = (0.42, 0.45, 0.5)
ACCENT = (0.0, 0.45, 0.42)
RULE = (0.82, 0.84, 0.86)
BAND = (0.95, 0.96, 0.97)


def text_width(s: str, size: float, bold: bool = False) -> float:
    table = _HELV_B if bold else _HELV
    total = 0
    for ch in s:
        o = ord(ch)
        total += table[o - 32] if 32 <= o <= 126 else 556
    return total * size / 1000


def _esc(s: str) -> str:
    raw = s.encode("cp1252", "replace").decode("latin-1")
    return raw.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class PDF:
    def __init__(self) -> None:
        self.pages: list[list[str]] = []
        self.ops: list[str] = []

    def new_page(self) -> None:
        self.ops = []
        self.pages.append(self.ops)

    def text(self, x, y, s, size=10, bold=False, color=INK, align="left"):
        if align == "right":
            x -= text_width(s, size, bold)
        elif align == "center":
            x -= text_width(s, size, bold) / 2
        font = "F2" if bold else "F1"
        self.ops.append(
            f"BT {color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg /{font} {size} Tf "
            f"{x:.2f} {y:.2f} Td ({_esc(s)}) Tj ET"
        )

    def rect(self, x, y, w, h, color):
        self.ops.append(f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")

    def line(self, x1, y1, x2, y2, color=RULE, width=0.6):
        self.ops.append(
            f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} RG {width} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S"
        )

    def output(self) -> bytes:
        objs: list[bytes] = []
        n_pages = len(self.pages)
        # 1 catalog, 2 pages, 3 F1, 4 F2, daarna per pagina: page + content
        kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(n_pages))
        objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
        for name in ("Helvetica", "Helvetica-Bold"):
            objs.append(
                f"<< /Type /Font /Subtype /Type1 /BaseFont /{name} /Encoding /WinAnsiEncoding >>".encode()
            )
        for i, ops in enumerate(self.pages):
            stream = "\n".join(ops).encode("latin-1")
            objs.append(
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {6 + 2 * i} 0 R >>".encode()
            )
            objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, obj in enumerate(objs, 1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
        for off in offsets:
            out += f"{off:010d} 00000 n \n".encode()
        out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        return bytes(out)


# ---------------------------------------------------------------- opmaak
def num(v: float, decimals: int = 2) -> str:
    s = f"{v:,.{decimals}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def euro(v: float) -> str:
    return "€ " + num(v, 2)


def duration(seconds: float) -> str:
    m = int(round(seconds / 60))
    return f"{m // 60}:{m % 60:02d}"


class _Report:
    def __init__(self, pdf: PDF, title: str, footer: str) -> None:
        self.pdf = pdf
        self.title = title
        self.footer = footer
        self.y = 0.0
        self.page_no = 0

    def page(self) -> None:
        self.pdf.new_page()
        self.page_no += 1
        self.pdf.text(MARGIN, PAGE_H - 30, self.title, 8, color=MUTED)
        self.pdf.text(PAGE_W - MARGIN, PAGE_H - 30, f"Pagina {self.page_no}", 8, color=MUTED, align="right")
        self.pdf.text(MARGIN, 25, self.footer, 7, color=MUTED)
        self.y = PAGE_H - 60

    def need(self, h: float) -> bool:
        if self.y - h < 50:
            self.page()
            return True
        return False

    def table(self, cols, rows, size=8.5, row_h=14, band=True, bold_rows=()):
        """cols: lijst (kop, breedte, uitlijning)."""
        def header():
            x = MARGIN
            for title, w, align in cols:
                tx = x + w - 4 if align == "right" else x + 4
                self.pdf.text(tx, self.y - 10, title, size, bold=True, color=MUTED, align=align)
                x += w
            self.pdf.line(MARGIN, self.y - 14, MARGIN + sum(c[1] for c in cols), self.y - 14, INK, 0.8)
            self.y -= row_h + 3

        self.need(row_h * 3)
        header()
        for i, row in enumerate(rows):
            if self.need(row_h):
                header()
            if band and i % 2 == 1:
                self.pdf.rect(MARGIN, self.y - row_h + 3, sum(c[1] for c in cols), row_h, BAND)
            x = MARGIN
            bold = i in bold_rows
            for (title, w, align), cell in zip(cols, row):
                tx = x + w - 4 if align == "right" else x + 4
                self.pdf.text(tx, self.y - 7, str(cell), size, bold=bold, align=align)
                x += w
            self.y -= row_h


def build_report(
    sessions: list[dict],
    year: int,
    month: int,
    tz: tzinfo,
    info: dict,
    provisional: bool,
    tariff_name: str = "Zonneplan",
    tariff_label: str = "dynamisch kwartiertarief",
    tarief_vast: bool = False,
) -> bytes:
    pdf = PDF()
    period = f"{MONTHS[month - 1]} {year}"
    generated = datetime.now(tz)
    rep = _Report(
        pdf,
        f"Laadrapport {period}",
        f"Gegenereerd op {generated:%d-%m-%Y %H:%M} door Home Assistant (laadsessie_log)",
    )
    rep.page()
    W = PAGE_W - 2 * MARGIN

    # Titel
    pdf.rect(MARGIN, rep.y - 4, 4, 30, ACCENT)
    pdf.text(MARGIN + 14, rep.y + 8, f"Laadrapport {period}", 20, bold=True)
    pdf.text(MARGIN + 14, rep.y - 6, "Declaratie thuisladen elektrische auto", 10, color=MUTED)
    rep.y -= 30
    if provisional:
        pdf.text(PAGE_W - MARGIN, rep.y + 38, "VOORLOPIG", 10, bold=True, color=(0.75, 0.35, 0.0), align="right")
        pdf.text(PAGE_W - MARGIN, rep.y + 26, "maand nog niet afgesloten", 8, color=MUTED, align="right")

    # Gegevens
    rep.y -= 10
    for label, value in info.items():
        if value:
            pdf.text(MARGIN, rep.y, label, 9, color=MUTED)
            pdf.text(MARGIN + 110, rep.y, str(value), 9)
            rep.y -= 13
    rep.y -= 10

    total_kwh = sum(s["kwh"] for s in sessions)
    total_cost = sum(s["kosten"] for s in sessions)
    avg = total_cost / total_kwh if total_kwh else 0

    # Kerncijfers
    tiles = [
        ("Laadsessies", str(len(sessions))),
        ("Geladen energie", f"{num(total_kwh)} kWh"),
        ("Gem. tarief per kWh", "\u20ac " + num(avg, 4) if total_kwh else "-"),
        ("Totaal te declareren", euro(total_cost)),
    ]
    tw = (W - 3 * 8) / 4
    for i, (label, value) in enumerate(tiles):
        x = MARGIN + i * (tw + 8)
        pdf.rect(x, rep.y - 46, tw, 50, BAND)
        pdf.text(x + 10, rep.y - 12, label, 8, color=MUTED)
        last = i == len(tiles) - 1
        pdf.text(x + 10, rep.y - 34, value, 13 if not last else 14, bold=True, color=ACCENT if last else INK)
    rep.y -= 70

    # Grafiek kWh per dag
    days_in_month = (datetime(year + (month == 12), month % 12 + 1, 1) - datetime(year, month, 1)).days
    per_day = defaultdict(float)
    for s in sessions:
        for q in s["kwartieren"]:
            d = datetime.fromisoformat(q["start"]).astimezone(tz)
            if d.year == year and d.month == month:
                per_day[d.day] += q["kwh"]
    if per_day:
        pdf.text(MARGIN, rep.y, "Geladen energie per dag (kWh)", 10, bold=True)
        rep.y -= 12
        ch_h = 90
        base = rep.y - ch_h
        peak = max(per_day.values())
        step = max(5, round(peak / 3 / 5) * 5) if peak > 10 else max(1, round(peak / 3))
        top = step * (int(peak // step) + 1)
        label_w = 26
        bw = (W - label_w) / days_in_month
        g = step
        pdf.line(MARGIN + label_w, base, MARGIN + W, base, MUTED, 0.6)
        while g <= top:
            gy = base + ch_h * g / top
            pdf.line(MARGIN + label_w, gy, MARGIN + W, gy, RULE, 0.4)
            pdf.text(MARGIN + label_w - 4, gy - 3, num(g, 0), 7, color=MUTED, align="right")
            g += step
        for day in range(1, days_in_month + 1):
            x = MARGIN + label_w + (day - 1) * bw
            v = per_day.get(day, 0)
            if v:
                pdf.rect(x + bw * 0.18, base, bw * 0.64, ch_h * v / top, ACCENT)
            if day == 1 or day % 5 == 0:
                pdf.text(x + bw / 2, base - 10, str(day), 7, color=MUTED, align="center")
        rep.y = base - 28

    # Sessie-overzicht
    pdf.text(MARGIN, rep.y, "Overzicht laadsessies", 12, bold=True)
    rep.y -= 8
    cols = [("Datum", 72, "left"), ("Start", 42, "left"), ("Einde", 62, "left"), ("Duur", 40, "right"),
            ("kWh", 58, "right"), ("Gem. €/kWh", 72, "right"), ("Kosten", 72, "right"),
            ("Opm.", W - 418, "left")]
    rows = []
    any_fb = any_partial = any_unknown = False
    for s in sessions:
        st = datetime.fromisoformat(s["start"]).astimezone(tz)
        en = datetime.fromisoformat(s["einde"]).astimezone(tz)
        end_txt = f"{en:%H:%M}" if en.date() == st.date() else f"{en:%d-%m %H:%M}"
        notes = []
        if s.get("terugval"):
            notes.append("T")
            any_fb = True
        if any(q["bron"] == "onbekend" for q in s["kwartieren"]):
            notes.append("?")
            any_unknown = True
        if s.get("onvolledig"):
            notes.append("O")
            any_partial = True
        rows.append([
            f"{DAYS[st.weekday()]} {st:%d-%m-%Y}", f"{st:%H:%M}", end_txt,
            duration((en - st).total_seconds()), num(s["kwh"]),
            num(s["kosten"] / s["kwh"], 4) if s["kwh"] else "-", euro(s["kosten"]), " ".join(notes),
        ])
    rows.append(["Totaal", "", "", "", num(total_kwh), num(avg, 4) if total_kwh else "-", euro(total_cost), ""])
    if sessions:
        rep.table(cols, rows, bold_rows=(len(rows) - 1,))
    else:
        pdf.text(MARGIN, rep.y - 12, "Geen laadsessies in deze maand.", 9, color=MUTED)
        rep.y -= 20

    # Toelichting
    notes = [
        "Energie is gemeten door de laadpaal; de verdeling over kwartieren volgt het gemeten laadvermogen.",
        f"Tarief: {tariff_label} van {tariff_name} (all-in, incl. energiebelasting en btw).",
    ]
    if any_fb:
        notes.append(f"T = terugvaltarief: {tariff_name}-tarief was niet beschikbaar; laatst bekende tarief op hetzelfde")
        notes.append("      kwartier van de meest recente periode met een bekend tarief gebruikt (zie specificatie).")
    if any_unknown:
        notes.append("? = voor een of meer kwartieren was geen tarief bekend; deze zijn met € 0 meegeteld.")
    if any_partial:
        notes.append("O = onvolledige sessie: begin van de sessie lag voor de start van de registratie.")
    notes.append("Sessies worden toegerekend aan de maand waarin ze eindigen.")
    rep.y -= 14
    rep.need(14 * len(notes) + 16)
    pdf.text(MARGIN, rep.y, "Toelichting", 10, bold=True)
    rep.y -= 14
    for n in notes:
        pdf.text(MARGIN, rep.y, n, 8, color=MUTED)
        rep.y -= 11

    # Specificatie per kwartier (overgeslagen bij een vast tarief: elke regel zou toch
    # hetzelfde tarief tonen, dat voegt niets toe aan het overzicht hierboven).
    if sessions and not tarief_vast:
        rep.page()
        pdf.text(MARGIN, rep.y, "Specificatie per kwartier", 14, bold=True)
        rep.y -= 12
        qcols = [("Kwartier", 110, "left"), ("kWh", 70, "right"), ("Tarief €/kWh", 90, "right"),
                 ("Kosten", 80, "right"), ("Tariefbron", W - 350, "left")]
        for s in sessions:
            st = datetime.fromisoformat(s["start"]).astimezone(tz)
            en = datetime.fromisoformat(s["einde"]).astimezone(tz)
            rep.need(60)
            rep.y -= 14
            pdf.text(MARGIN, rep.y, f"Sessie {DAYS[st.weekday()]} {st:%d-%m-%Y %H:%M} – {en:%d-%m %H:%M}", 10, bold=True)
            pdf.text(PAGE_W - MARGIN, rep.y, f"{num(s['kwh'])} kWh  ·  {euro(s['kosten'])}", 10,
                     bold=True, align="right")
            rep.y -= 4
            qrows = []
            for q in s["kwartieren"]:
                qs = datetime.fromisoformat(q["start"]).astimezone(tz)
                if q["bron"] == "zonneplan":
                    src = tariff_name
                elif q["bron"] == "terugval":
                    src = f"Terugval ({datetime.fromisoformat(q['terugval_datum']):%d-%m-%Y})"
                else:
                    src = "Onbekend"
                qrows.append([
                    f"{qs:%d-%m %H:%M}", num(q["kwh"], 3),
                    num(q["prijs"], 4) if q["prijs"] is not None else "-", euro(q["kosten"]), src,
                ])
            rep.table(qcols, qrows, size=8, row_h=12)
    return pdf.output()
