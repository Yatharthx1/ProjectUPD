"""
generator.py  --  Phase 5: PDF Report Generation
Generates a professional water quality report from WQI results + recommendations.

Usage:
    from src.reports.generator import generate_pdf_report

    generate_pdf_report(
        wqi_result      = result,
        recommendations = recs,
        output_path     = "report.pdf",
        meta            = {
            "sample_id":  "S001",
            "location":   "Indore Zone A",
            "profile_id": "bis_drinking",
            "tested_by":  "Lab Name",
            "date":       "2026-04-03",
        }
    )

    # Batch (multiple samples in one PDF):
    generate_batch_report(results_list, recs_list, "batch_report.pdf", meta_list)
"""

import io
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, Image,
)


# ── Colour palette ─────────────────────────────────────────────────────────────

C_NAVY      = colors.HexColor("#0D2137")
C_BLUE      = colors.HexColor("#185FA5")
C_BLUE_LITE = colors.HexColor("#E6F1FB")
C_TEAL      = colors.HexColor("#0F6E56")
C_TEAL_LITE = colors.HexColor("#E1F5EE")
C_AMBER     = colors.HexColor("#BA7517")
C_AMBER_LT  = colors.HexColor("#FAEEDA")
C_RED       = colors.HexColor("#A32D2D")
C_RED_LITE  = colors.HexColor("#FCEBEB")
C_GREEN     = colors.HexColor("#3B6D11")
C_GREEN_LT  = colors.HexColor("#EAF3DE")
C_GRAY      = colors.HexColor("#5F5E5A")
C_GRAY_LT   = colors.HexColor("#F1EFE8")
C_WHITE     = colors.white
C_BLACK     = colors.HexColor("#1A1A18")

PAGE_W, PAGE_H = A4
MARGIN         = 18 * mm
CONTENT_W      = PAGE_W - 2 * MARGIN


# ── Classification helpers ──────────────────────────────────────────────────────

def _wqi_color(classification: str):
    return {
        "Excellent":  C_TEAL,
        "Good":       C_GREEN,
        "Poor":       C_AMBER,
        "Very Poor":  colors.HexColor("#993C1D"),
        "Unsuitable": C_RED,
        "UNSAFE":     C_RED,
    }.get(classification, C_GRAY)


def _status_color(status: str):
    return {
        "SAFE":          C_TEAL,
        "NON_COMPLIANT": C_AMBER,
        "UNSAFE":        C_RED,
        "UNKNOWN":       C_GRAY,
    }.get(status, C_GRAY)


def _zone_color(zone: str):
    return {
        "ideal":       C_TEAL,
        "acceptable":  C_GREEN,
        "permissible": C_AMBER,
        "breach":      C_RED,
        "deficient":   colors.HexColor("#993C1D"),
    }.get(zone or "", C_GRAY)


def _priority_color(priority: str):
    return {
        "CRITICAL": C_RED,
        "HIGH":     colors.HexColor("#993C1D"),
        "MEDIUM":   C_AMBER,
        "LOW":      C_TEAL,
    }.get(priority, C_GRAY)


# ── Style sheet ────────────────────────────────────────────────────────────────

def _build_styles():
    base = getSampleStyleSheet()

    def s(name, parent="Normal", **kw):
        return ParagraphStyle(name, parent=base[parent], **kw)

    return {
        "cover_title":  s("cover_title",  "Title",
                          fontSize=24, textColor=C_WHITE,
                          leading=30, alignment=TA_LEFT, spaceAfter=4),
        "cover_sub":    s("cover_sub",    "Normal",
                          fontSize=11, textColor=colors.HexColor("#B5D4F4"),
                          leading=16, alignment=TA_LEFT),
        "cover_meta":   s("cover_meta",   "Normal",
                          fontSize=8.5, textColor=colors.HexColor("#85B7EB"),
                          leading=13, alignment=TA_LEFT),
        "section_head": s("section_head", "Heading1",
                          fontSize=12, textColor=C_NAVY,
                          leading=17, spaceBefore=12, spaceAfter=5),
        "body":         s("body",         "Normal",
                          fontSize=9, textColor=C_BLACK, leading=13),
        "body_sm":      s("body_sm",      "Normal",
                          fontSize=8, textColor=C_GRAY, leading=11),
        "table_hdr":    s("table_hdr",    "Normal",
                          fontSize=8, textColor=C_WHITE,
                          fontName="Helvetica-Bold",
                          alignment=TA_CENTER, leading=11),
        "table_cell":   s("table_cell",   "Normal",
                          fontSize=8, textColor=C_BLACK, leading=11),
        "table_cell_c": s("table_cell_c", "Normal",
                          fontSize=8, textColor=C_BLACK,
                          alignment=TA_CENTER, leading=11),
        "badge_text":   s("badge_text",   "Normal",
                          fontSize=9, textColor=C_WHITE,
                          fontName="Helvetica-Bold",
                          alignment=TA_CENTER, leading=12),
        "treatment":    s("treatment",    "Normal",
                          fontSize=8, textColor=C_BLACK, leading=12),
        "footer":       s("footer",       "Normal",
                          fontSize=7, textColor=C_GRAY,
                          alignment=TA_CENTER, leading=10),
    }


# ── Chart builders ──────────────────────────────────────────────────────────────

def _gauge_chart(wqi: float, classification: str,
                 width=55 * mm, height=38 * mm) -> Image:
    """Half-donut gauge for WQI score."""
    fig, ax = plt.subplots(figsize=(width / 28.35, height / 28.35), dpi=150)
    fig.patch.set_alpha(0)
    ax.set_aspect("equal")

    theta = np.linspace(np.pi, 0, 300)
    r_out, r_in = 1.0, 0.58
    ax.fill_between(np.cos(theta),
                    r_in  * np.sin(theta),
                    r_out * np.sin(theta),
                    color="#E8E7E0", zorder=1)

    pct   = min(wqi, 200) / 200.0
    angle = np.pi - pct * np.pi
    theta_fill = np.linspace(np.pi, angle, 300)
    clr_hex = {
        "Excellent": "#0F6E56", "Good": "#3B6D11",
        "Poor": "#BA7517",      "Very Poor": "#993C1D",
        "Unsuitable": "#A32D2D", "UNSAFE": "#A32D2D",
    }.get(classification, "#5F5E5A")
    ax.fill_between(np.cos(theta_fill),
                    r_in  * np.sin(theta_fill),
                    r_out * np.sin(theta_fill),
                    color=clr_hex, zorder=2)

    nx = np.cos(angle) * r_in * 0.85
    ny = np.sin(angle) * r_in * 0.85
    ax.annotate("", xy=(nx, ny), xytext=(0, 0),
                arrowprops=dict(arrowstyle="-|>", color="#0D2137",
                                lw=1.6, mutation_scale=10))
    ax.add_patch(plt.Circle((0, 0), 0.07, color="#0D2137", zorder=5))

    ax.text(0, -0.18, f"{wqi:.1f}", ha="center", va="center",
            fontsize=11, fontweight="bold", color="#0D2137")
    ax.text(0, -0.40, "WQI", ha="center", va="center",
            fontsize=6.5, color="#5F5E5A")

    ax.set_xlim(-1.15, 1.15)
    ax.set_ylim(-0.55, 1.1)
    ax.axis("off")
    plt.tight_layout(pad=0)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", transparent=True)
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=width, height=height)


def _bar_chart(sub_indices: dict,
               width=CONTENT_W, height=55 * mm) -> Image | None:
    """Horizontal bar chart of qi per parameter."""
    params = [p for p, v in sub_indices.items() if v.get("qi") is not None]
    if not params:
        return None

    values = [sub_indices[p]["qi"] for p in params]
    zones  = [sub_indices[p].get("zone", "") for p in params]
    clr_map = {
        "ideal": "#0F6E56", "acceptable": "#3B6D11",
        "permissible": "#BA7517", "breach": "#A32D2D",
        "deficient": "#993C1D",
    }
    bar_colors = [clr_map.get(z, "#888780") for z in zones]

    n  = len(params)
    fh = max(height / 28.35, n * 0.30 + 0.6)

    fig, ax = plt.subplots(figsize=(width / 28.35, fh), dpi=150)
    fig.patch.set_alpha(0)
    y_pos = np.arange(n)
    ax.barh(y_pos, values, color=bar_colors, height=0.55, edgecolor="none")

    for x, label, clr in [(50, "Acceptable", "#BA7517"), (100, "Limit", "#A32D2D")]:
        ax.axvline(x=x, color=clr, lw=0.8, linestyle="--", alpha=0.65)
        ax.text(x + 1, n - 0.5, label, fontsize=5.5, color=clr, va="top")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(params, fontsize=7, color="#1A1A18")
    ax.set_xlim(0, max(max(values) * 1.15, 115))
    ax.set_xlabel("Quality Index  (qi  —  lower is better)", fontsize=7, color="#5F5E5A")
    ax.tick_params(axis="x", labelsize=6, colors="#5F5E5A")
    ax.tick_params(axis="y", length=0)
    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#D3D1C7")
    ax.set_facecolor("none")
    plt.tight_layout(pad=0.3)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", transparent=True)
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=width, height=height)


def _pie_chart(results: list, width=CONTENT_W * 0.42, height=48 * mm) -> Image:
    """Donut pie for batch status distribution."""
    counts = {}
    for r in results:
        s = r.get("status", "ERROR")
        counts[s] = counts.get(s, 0) + 1

    colour_map = {
        "SAFE": "#0F6E56", "NON_COMPLIANT": "#BA7517",
        "UNSAFE": "#A32D2D", "ERROR": "#888780",
    }
    labels, sizes, clrs = [], [], []
    for k, v in counts.items():
        if v:
            labels.append(f"{k} ({v})")
            sizes.append(v)
            clrs.append(colour_map.get(k, "#888780"))

    fig, ax = plt.subplots(figsize=(width / 28.35, height / 28.35), dpi=150)
    fig.patch.set_alpha(0)
    wedges, _, autotexts = ax.pie(
        sizes, labels=None, colors=clrs, autopct="%1.0f%%",
        pctdistance=0.75, startangle=90,
        wedgeprops=dict(width=0.55, edgecolor="white", linewidth=1.5),
    )
    for at in autotexts:
        at.set_fontsize(7)
        at.set_color("white")
        at.set_fontweight("bold")
    ax.legend(wedges, labels, loc="lower center",
              bbox_to_anchor=(0.5, -0.25), ncol=2, fontsize=6.5, frameon=False)
    plt.tight_layout(pad=0)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", transparent=True)
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=width, height=height)


# ── Page header / footer ───────────────────────────────────────────────────────

def _page_chrome(canvas, doc, meta: dict):
    canvas.saveState()
    canvas.setFillColor(C_NAVY)
    canvas.rect(0, PAGE_H - 14 * mm, PAGE_W, 14 * mm, fill=1, stroke=0)
    canvas.setFillColor(C_WHITE)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(MARGIN, PAGE_H - 9 * mm, "BLUE -- Water Quality Report")
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#85B7EB"))
    sid = meta.get("sample_id", "")
    loc = meta.get("location", "")
    hdr = f"{sid}  |  {loc}" if sid and loc else sid or loc
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 9 * mm, hdr)

    canvas.setFillColor(C_GRAY_LT)
    canvas.rect(0, 0, PAGE_W, 10 * mm, fill=1, stroke=0)
    canvas.setFillColor(C_GRAY)
    canvas.setFont("Helvetica", 6.5)
    canvas.drawString(
        MARGIN, 4 * mm,
        f"Generated: {datetime.now().strftime('%d %b %Y  %H:%M')}  |  "
        f"Profile: {meta.get('profile_id', '--')}  |  "
        f"For informational purposes only. Verify with accredited laboratory."
    )
    canvas.drawRightString(PAGE_W - MARGIN, 4 * mm, f"Page {doc.page}")
    canvas.restoreState()


# ── Cover block ────────────────────────────────────────────────────────────────

def _cover_block(story, meta: dict, wqi_result: dict, styles: dict):
    status         = wqi_result.get("status", "UNKNOWN")
    classification = wqi_result.get("classification", "--")
    wqi            = wqi_result.get("wqi")
    wqi_disp       = f"{wqi:.1f}" if wqi is not None else "--"

    # Title band
    title_data = [
        [Paragraph("Water Quality Analysis Report", styles["cover_title"])],
        [Paragraph(meta.get("location", "Sample Report"), styles["cover_sub"])],
        [Spacer(1, 3 * mm)],
        [Paragraph(
            f"Sample ID: {meta.get('sample_id', '--')}  &nbsp;|&nbsp;  "
            f"Date: {meta.get('date', datetime.now().strftime('%d %b %Y'))}  &nbsp;|&nbsp;  "
            f"Standard: {meta.get('profile_id', '--')}",
            styles["cover_meta"],
        )],
    ]
    title_tbl = Table(title_data, colWidths=[CONTENT_W])
    title_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
        ("ROUNDEDCORNERS", [8]),
    ]))
    story.append(Spacer(1, 8 * mm))
    story.append(title_tbl)
    story.append(Spacer(1, 5 * mm))

    # Status badges
    badge_data = [[
        Paragraph(f"<b>{status}</b>",         styles["badge_text"]),
        Paragraph(f"<b>WQI: {wqi_disp}</b>",  styles["badge_text"]),
        Paragraph(f"<b>{classification}</b>",  styles["badge_text"]),
    ]]
    badge_tbl = Table(badge_data,
                      colWidths=[CONTENT_W / 3] * 3, rowHeights=[12 * mm])
    badge_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (0, 0), _status_color(status)),
        ("BACKGROUND",   (1, 0), (1, 0), C_BLUE),
        ("BACKGROUND",   (2, 0), (2, 0), _wqi_color(classification)),
        ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LINEAFTER",    (0, 0), (1, 0), 1, C_WHITE),
        ("ROUNDEDCORNERS", [6]),
    ]))
    story.append(badge_tbl)
    story.append(Spacer(1, 5 * mm))

    # Gauge + meta side by side
    if wqi is not None:
        gauge    = _gauge_chart(wqi, classification, width=58 * mm, height=40 * mm)
        meta_tbl = _meta_block(wqi_result, meta, styles)
        side_data = [[gauge, meta_tbl]]
        side_tbl  = Table(side_data, colWidths=[62 * mm, CONTENT_W - 62 * mm])
        side_tbl.setStyle(TableStyle([
            ("VALIGN",       (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING",   (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
        ]))
        story.append(side_tbl)

    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width=CONTENT_W, thickness=0.5,
                             color=C_GRAY_LT, spaceAfter=4 * mm))


def _meta_block(wqi_result: dict, meta: dict, styles: dict):
    conf      = wqi_result.get("confidence", 0)
    dominant  = wqi_result.get("dominant_issues", [])
    flags     = wqi_result.get("flags", [])
    n_crit    = sum(1 for f in flags if f.get("severity") == "critical")
    n_warn    = sum(1 for f in flags if f.get("severity") == "warning")

    rows = [
        ("Confidence",      f"{conf * 100:.0f}%"),
        ("Dominant issues", ", ".join(dominant) if dominant else "None"),
        ("Critical flags",  str(n_crit)),
        ("Warning flags",   str(n_warn)),
        ("Tested by",       meta.get("tested_by", "--")),
        ("Lab ref",         meta.get("lab_ref",   "--")),
    ]
    tbl_data = [
        [Paragraph(f"<b>{k}</b>", styles["body_sm"]),
         Paragraph(v, styles["body_sm"])]
        for k, v in rows
    ]
    tbl = Table(tbl_data,
                colWidths=[38 * mm, CONTENT_W - 62 * mm - 38 * mm])
    tbl.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("LINEBELOW",     (0, 0), (-1, -2), 0.3, C_GRAY_LT),
    ]))
    return tbl


# ── Parameter table ────────────────────────────────────────────────────────────

def _param_table(sub_indices: dict, styles: dict) -> Table:
    headers = ["Parameter", "Value", "Zone", "qi", "Layer", "Impact"]
    hdr_row = [Paragraph(h, styles["table_hdr"]) for h in headers]
    rows    = [hdr_row]

    for param, info in sorted(sub_indices.items()):
        qi    = info.get("qi")
        zone  = info.get("zone") or "--"
        value = info.get("value")
        layer = info.get("layer") or "--"
        imp   = info.get("impact") or "--"

        qi_str  = f"{qi:.1f}"  if qi    is not None             else "--"
        val_str = f"{value:.3g}" if isinstance(value, (int, float)) else str(value or "--")

        rows.append([
            Paragraph(param,                            styles["table_cell"]),
            Paragraph(val_str,                          styles["table_cell_c"]),
            Paragraph(zone.replace("_", " ").title(),  styles["table_cell_c"]),
            Paragraph(qi_str,                           styles["table_cell_c"]),
            Paragraph(layer.replace("_", " "),         styles["table_cell_c"]),
            Paragraph(imp,                              styles["table_cell_c"]),
        ])

    col_w = [40 * mm, 20 * mm, 26 * mm, 14 * mm, 30 * mm, 20 * mm]
    tbl   = Table(rows, colWidths=col_w, repeatRows=1)

    cmds = [
        ("BACKGROUND",    (0, 0), (-1, 0), C_NAVY),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_WHITE, C_GRAY_LT]),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("ALIGN",         (0, 1), (0, -1),  "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("GRID",          (0, 0), (-1, -1), 0.2, C_GRAY_LT),
    ]
    # Colour zone text
    for i, (_, info) in enumerate(sorted(sub_indices.items()), start=1):
        z = info.get("zone") or ""
        cmds += [
            ("TEXTCOLOR", (2, i), (2, i), _zone_color(z)),
            ("FONTNAME",  (2, i), (2, i), "Helvetica-Bold"),
        ]
    tbl.setStyle(TableStyle(cmds))
    return tbl


# ── Flags table ────────────────────────────────────────────────────────────────

def _flags_table(flags: list, styles: dict):
    if not flags:
        return Paragraph("No flags raised.", styles["body_sm"])

    sev_bg = {
        "critical":  C_RED,
        "violation": colors.HexColor("#993C1D"),
        "warning":   C_AMBER,
        "info":      C_BLUE,
    }
    headers = ["Severity", "Parameter", "Code", "Message"]
    hdr_row = [Paragraph(h, styles["table_hdr"]) for h in headers]
    rows    = [hdr_row]

    for f in flags:
        rows.append([
            Paragraph(f.get("severity", "--").upper(), styles["table_cell_c"]),
            Paragraph(f.get("param",    "--"),          styles["table_cell"]),
            Paragraph(f.get("code",     "--"),          styles["table_cell"]),
            Paragraph(f.get("message",  "--"),          styles["table_cell"]),
        ])

    col_w = [22 * mm, 28 * mm, 38 * mm, CONTENT_W - 88 * mm]
    tbl   = Table(rows, colWidths=col_w, repeatRows=1)
    cmds  = [
        ("BACKGROUND",    (0, 0), (-1, 0), C_NAVY),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_WHITE, C_GRAY_LT]),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("ALIGN",         (3, 1), (3, -1),  "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("GRID",          (0, 0), (-1, -1), 0.2, C_GRAY_LT),
    ]
    for i, f in enumerate(flags, start=1):
        bg = sev_bg.get(f.get("severity", "info"), C_BLUE)
        cmds += [
            ("BACKGROUND", (0, i), (0, i), bg),
            ("TEXTCOLOR",  (0, i), (0, i), C_WHITE),
            ("FONTNAME",   (0, i), (0, i), "Helvetica-Bold"),
        ]
    tbl.setStyle(TableStyle(cmds))
    return tbl


# ── Recommendations table ──────────────────────────────────────────────────────

def _rec_table(recommendations: list, styles: dict):
    if not recommendations:
        return Paragraph("No treatment recommendations.", styles["body_sm"])

    urgency_clr = {
        "immediate":  C_RED,
        "short_term": C_AMBER,
        "routine":    C_TEAL,
    }
    headers = ["Priority", "Parameter", "Urgency", "Treatment"]
    hdr_row = [Paragraph(h, styles["table_hdr"]) for h in headers]
    rows    = [hdr_row]

    for rec in recommendations:
        rows.append([
            Paragraph(rec.get("priority",  "--"),                       styles["table_cell_c"]),
            Paragraph(rec.get("parameter", "--"),                       styles["table_cell"]),
            Paragraph(rec.get("urgency",   "--").replace("_", " "),    styles["table_cell_c"]),
            Paragraph(rec.get("treatment", "--"),                       styles["treatment"]),
        ])

    col_w = [22 * mm, 28 * mm, 24 * mm, CONTENT_W - 74 * mm]
    tbl   = Table(rows, colWidths=col_w, repeatRows=1)
    cmds  = [
        ("BACKGROUND",    (0, 0), (-1, 0), C_NAVY),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_WHITE, C_GRAY_LT]),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("ALIGN",         (1, 1), (1, -1),  "LEFT"),
        ("ALIGN",         (3, 1), (3, -1),  "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("GRID",          (0, 0), (-1, -1), 0.2, C_GRAY_LT),
    ]
    for i, rec in enumerate(recommendations, start=1):
        p = rec.get("priority", "")
        u = rec.get("urgency",  "")
        if p:
            cmds += [
                ("TEXTCOLOR", (0, i), (0, i), _priority_color(p)),
                ("FONTNAME",  (0, i), (0, i), "Helvetica-Bold"),
            ]
        if u in urgency_clr:
            cmds += [
                ("TEXTCOLOR", (2, i), (2, i), urgency_clr[u]),
                ("FONTNAME",  (2, i), (2, i), "Helvetica-Bold"),
            ]
    tbl.setStyle(TableStyle(cmds))
    return tbl


# ── Batch summary table ────────────────────────────────────────────────────────

def _batch_table(results: list, meta_list: list, styles: dict) -> Table:
    headers = ["ID", "Location", "WQI", "Status", "Classification"]
    hdr_row = [Paragraph(h, styles["table_hdr"]) for h in headers]
    rows    = [hdr_row]

    for result, meta in zip(results, meta_list):
        wqi  = result.get("wqi")
        stat = result.get("status", "--")
        cls  = result.get("classification", "--")
        rows.append([
            Paragraph(meta.get("sample_id", "--"),  styles["table_cell_c"]),
            Paragraph(meta.get("location",  "--"),  styles["table_cell"]),
            Paragraph(f"{wqi:.1f}" if wqi else "--", styles["table_cell_c"]),
            Paragraph(stat, styles["table_cell_c"]),
            Paragraph(cls,  styles["table_cell_c"]),
        ])

    col_w = [16 * mm, 42 * mm, 18 * mm, 30 * mm, 28 * mm]
    tbl   = Table(rows, colWidths=col_w, repeatRows=1)
    cmds  = [
        ("BACKGROUND",    (0, 0), (-1, 0), C_NAVY),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_WHITE, C_GRAY_LT]),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("ALIGN",         (1, 1), (1, -1),  "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 3),
        ("GRID",          (0, 0), (-1, -1), 0.2, C_GRAY_LT),
        ("FONTSIZE",      (0, 0), (-1, -1), 7),
    ]
    for i, result in enumerate(results, start=1):
        cmds += [
            ("TEXTCOLOR", (3, i), (3, i), _status_color(result.get("status", ""))),
            ("FONTNAME",  (3, i), (3, i), "Helvetica-Bold"),
            ("TEXTCOLOR", (4, i), (4, i), _wqi_color(result.get("classification", ""))),
            ("FONTNAME",  (4, i), (4, i), "Helvetica-Bold"),
        ]
    tbl.setStyle(TableStyle(cmds))
    return tbl


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_pdf_report(
    wqi_result:      dict,
    recommendations: "dict | list",
    output_path:     str,
    meta:            dict = None,
) -> str:
    """
    Generate a single-sample PDF water quality report.

    Args:
        wqi_result:      Output from calculate_wqi().
        recommendations: Output from get_recommendations() (dict) OR list of rec dicts.
        output_path:     Path to write the PDF.
        meta:            Optional dict: sample_id, location, profile_id,
                         tested_by, lab_ref, date.

    Returns:
        Absolute path of the generated PDF.
    """
    meta   = meta or {}
    styles = _build_styles()

    if isinstance(recommendations, dict):
        rec_list = recommendations.get("recommendations", [])
        rec_sum  = recommendations.get("summary", {})
    else:
        rec_list = recommendations
        rec_sum  = {}

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=18 * mm, bottomMargin=14 * mm,
        title="Water Quality Report",
        author="BLUE",
    )

    def on_page(canvas, doc):
        _page_chrome(canvas, doc, meta)

    story = []

    # Cover
    _cover_block(story, meta, wqi_result, styles)

    # Parameter analysis
    story.append(Paragraph("Parameter Analysis", styles["section_head"]))
    story.append(Paragraph(
        "Measured parameters, scored Quality Index (qi), zone classification, and layer.",
        styles["body"]))
    story.append(Spacer(1, 3 * mm))
    sub = wqi_result.get("sub_indices", {})
    if sub:
        story.append(_param_table(sub, styles))
    story.append(Spacer(1, 4 * mm))

    # Bar chart
    bar = _bar_chart(sub, width=CONTENT_W, height=52 * mm)
    if bar:
        story.append(Paragraph(
            "Quality Index per parameter  (0 = ideal, 100 = at limit, >100 = breach):",
            styles["body_sm"]))
        story.append(Spacer(1, 2 * mm))
        story.append(bar)
    story.append(Spacer(1, 5 * mm))

    # Flags
    story.append(Paragraph("Diagnostic Flags", styles["section_head"]))
    story.append(Spacer(1, 2 * mm))
    story.append(_flags_table(wqi_result.get("flags", []), styles))
    story.append(Spacer(1, 5 * mm))

    # Treatment
    story.append(Paragraph("Treatment Recommendations", styles["section_head"]))
    if rec_sum:
        c, h, m, l = (rec_sum.get(k, 0) for k in ("critical", "high", "medium", "low"))
        story.append(Paragraph(
            f"<b>{c}</b> critical  &nbsp;  <b>{h}</b> high  "
            f"&nbsp;  <b>{m}</b> medium  &nbsp;  <b>{l}</b> low",
            styles["body"]))
    story.append(Spacer(1, 3 * mm))
    story.append(_rec_table(rec_list, styles))
    story.append(Spacer(1, 5 * mm))

    # Disclaimer
    story.append(HRFlowable(width=CONTENT_W, thickness=0.5, color=C_GRAY_LT))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "<b>Disclaimer:</b> This report is generated automatically by BLUE "
        "and is intended for informational purposes only. Results must be verified "
        "by an accredited laboratory before any regulatory or public health decisions.",
        styles["body_sm"]))

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return str(Path(output_path).resolve())


def generate_batch_report(
    results:     list,
    rec_list:    list,
    output_path: str,
    meta_list:   list = None,
    batch_title: str  = "Batch Water Quality Report",
) -> str:
    """
    Generate a multi-sample batch PDF report.

    Args:
        results:     List of wqi_result dicts.
        rec_list:    List of recommendations (same order).
        output_path: Output PDF path.
        meta_list:   List of meta dicts (same order), or None.
        batch_title: Cover page title.

    Returns:
        Absolute path of the generated PDF.
    """
    meta_list = meta_list or [{} for _ in results]
    styles    = _build_styles()
    batch_meta = {"location": batch_title, "profile_id": "--", "sample_id": "BATCH"}

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=18 * mm, bottomMargin=14 * mm,
        title=batch_title, author="BLUE",
    )

    def on_page(canvas, doc):
        _page_chrome(canvas, doc, batch_meta)

    story = []

    # Batch cover
    story.append(Spacer(1, 8 * mm))
    hdr_data = [
        [Paragraph(batch_title, styles["cover_title"])],
        [Paragraph(
            f"{len(results)} samples  |  {datetime.now().strftime('%d %b %Y')}",
            styles["cover_sub"])],
    ]
    hdr_tbl = Table(hdr_data, colWidths=[CONTENT_W])
    hdr_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("ROUNDEDCORNERS", [8]),
    ]))
    story.append(hdr_tbl)
    story.append(Spacer(1, 5 * mm))

    safe   = sum(1 for r in results if r.get("status") == "SAFE")
    nc     = sum(1 for r in results if r.get("status") == "NON_COMPLIANT")
    unsafe = sum(1 for r in results if r.get("status") == "UNSAFE")
    wqi_v  = [r["wqi"] for r in results if r.get("wqi") is not None]
    avg    = sum(wqi_v) / len(wqi_v) if wqi_v else None

    sm_data = [[
        Paragraph(f"<b>{safe}</b><br/>Safe",           styles["badge_text"]),
        Paragraph(f"<b>{nc}</b><br/>Non-compliant",    styles["badge_text"]),
        Paragraph(f"<b>{unsafe}</b><br/>Unsafe",       styles["badge_text"]),
        Paragraph(f"<b>{avg:.1f}</b><br/>Avg WQI" if avg else "<b>--</b><br/>Avg WQI",
                  styles["badge_text"]),
    ]]
    sm_tbl = Table(sm_data, colWidths=[CONTENT_W / 4] * 4, rowHeights=[13 * mm])
    sm_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), C_TEAL),
        ("BACKGROUND", (1, 0), (1, 0), C_AMBER),
        ("BACKGROUND", (2, 0), (2, 0), C_RED),
        ("BACKGROUND", (3, 0), (3, 0), C_BLUE),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("LINEAFTER",  (0, 0), (2, 0), 1, C_WHITE),
        ("ROUNDEDCORNERS", [6]),
    ]))
    story.append(sm_tbl)
    story.append(Spacer(1, 5 * mm))

    # Pie + sample table
    pie = _pie_chart(results, width=CONTENT_W * 0.4, height=50 * mm)
    pair = Table([[pie, _batch_table(results, meta_list, styles)]],
                 colWidths=[CONTENT_W * 0.4, CONTENT_W * 0.6])
    pair.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))
    story.append(pair)
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width=CONTENT_W, thickness=0.5, color=C_GRAY_LT))

    # Per-sample pages
    for result, recs, meta in zip(results, rec_list, meta_list):
        story.append(PageBreak())
        _cover_block(story, meta, result, styles)

        sub = result.get("sub_indices", {})
        if sub:
            story.append(Paragraph("Parameter Analysis", styles["section_head"]))
            story.append(_param_table(sub, styles))
            story.append(Spacer(1, 4 * mm))

        story.append(Paragraph("Diagnostic Flags", styles["section_head"]))
        story.append(_flags_table(result.get("flags", []), styles))
        story.append(Spacer(1, 4 * mm))

        rec_items = recs.get("recommendations", recs) if isinstance(recs, dict) else recs
        story.append(Paragraph("Treatment Recommendations", styles["section_head"]))
        story.append(_rec_table(rec_items, styles))

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return str(Path(output_path).resolve())
