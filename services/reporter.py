import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

from core.state import state
from core.logger import get_logger

logger = get_logger("services.reporter")

def build_pdf(buffer: io.BytesIO, stats: dict):
    """Construit le PDF avec reportlab."""
    logger.debug("Initialisation du document PDF avec Reportlab (format A4)")
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Heading1"], fontSize=20, spaceAfter=6)
    h2_style = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=14, spaceAfter=4)
    body_style = styles["Normal"]

    g = stats["global"]
    domain = state.get("domain", "N/A")
    now = datetime.now().strftime("%d/%m/%Y à %H:%M")

    elements = []

    # Titre
    logger.debug(f"Génération de l'en-tête du PDF pour le domaine: {domain}")
    elements.append(Paragraph("📊 Rapport de Test de Charge", title_style))
    elements.append(Paragraph(f"Cible : <b>{domain}</b>", body_style))
    elements.append(Paragraph(f"Généré le : {now}", body_style))
    elements.append(Spacer(1, 0.5*cm))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
    elements.append(Spacer(1, 0.5*cm))

    # Stats globales
    logger.debug("Ajout du tableau des statistiques globales")
    elements.append(Paragraph("Résultats Globaux", h2_style))
    global_data = [
        ["Métrique", "Valeur"],
        ["Requêtes totales", str(g.get("num_requests", 0))],
        ["Échecs", str(g.get("num_failures", 0))],
        ["Taux d'erreur", f"{g.get('failure_rate', 0):.2f}%"],
        ["RPS moyen", f"{g.get('rps', 0):.1f} req/s"],
        ["Latence médiane", f"{g.get('median_response', 0):.1f} ms"],
        ["Latence P95", f"{g.get('p95_response', 0):.1f} ms"],
        ["Latence max", f"{g.get('max_response', 0):.1f} ms"],
    ]
    t = Table(global_data, colWidths=[9*cm, 7*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.black),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 0.5*cm))

    # Détail par endpoint
    endpoints = stats.get("endpoints", [])
    if endpoints:
        logger.debug(f"Ajout du tableau de détails pour {min(len(endpoints), 20)} endpoints")
        elements.append(Paragraph("Détail par URL", h2_style))
        ep_data = [["URL", "Requêtes", "Erreurs", "Médiane (ms)", "P95 (ms)", "RPS"]]
        for ep in endpoints[:20]:  # Limiter à 20 lignes
            name = ep["name"]
            if len(name) > 50:
                name = name[:47] + "..."
            ep_data.append([
                name,
                str(ep["requests"]),
                str(ep["failures"]),
                f"{ep['median']:.0f}",
                f"{ep['p95']:.0f}",
                f"{ep['rps']:.1f}",
            ])
        ep_table = Table(ep_data, colWidths=[6.5*cm, 2*cm, 2*cm, 2.5*cm, 2*cm, 2*cm])
        ep_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.black),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(ep_table)
    else:
        logger.debug("Aucun endpoint spécifique à ajouter au rapport PDF")

    logger.info("Finalisation du `build` du PDF")
    doc.build(elements)
