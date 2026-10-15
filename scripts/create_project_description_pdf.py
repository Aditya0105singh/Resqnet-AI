from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf" / "RESQNET_AI_Project_Description.pdf"

NAVY = colors.HexColor("#102A43")
BLUE = colors.HexColor("#147D92")
TEAL = colors.HexColor("#0F9D8C")
PALE = colors.HexColor("#EAF7F5")
INK = colors.HexColor("#243B53")
MUTED = colors.HexColor("#627D98")
LINE = colors.HexColor("#D9E2EC")


def footer(canvas, doc):
    canvas.saveState()
    width, _ = A4
    canvas.setStrokeColor(LINE)
    canvas.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 9 * mm, "RESQNET AI  |  Project Overview")
    canvas.drawRightString(width - 18 * mm, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(
        str(OUT), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=17 * mm, bottomMargin=20 * mm,
        title="RESQNET AI - Project Description",
        author="RESQNET AI Project Team",
        subject="Multi-agent flood rescue coordination digital twin",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates(PageTemplate(id="project", frames=[frame], onPage=footer))

    base = getSampleStyleSheet()
    title = ParagraphStyle("TitleX", parent=base["Title"], fontName="Helvetica-Bold", fontSize=27,
                           leading=31, textColor=NAVY, spaceAfter=5)
    subtitle = ParagraphStyle("Subtitle", parent=base["Normal"], fontName="Helvetica", fontSize=11.5,
                              leading=16, textColor=BLUE, spaceAfter=12)
    h2 = ParagraphStyle("H2X", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=14,
                        leading=17, textColor=NAVY, spaceBefore=8, spaceAfter=5, keepWithNext=True)
    body = ParagraphStyle("BodyX", parent=base["BodyText"], fontName="Helvetica", fontSize=9.6,
                          leading=14, textColor=INK, spaceAfter=6)
    bullet = ParagraphStyle("BulletX", parent=body, leftIndent=12, firstLineIndent=-7, bulletIndent=0,
                            spaceAfter=3.5)
    small = ParagraphStyle("Small", parent=body, fontSize=8.3, leading=11)
    quote = ParagraphStyle("Quote", parent=body, fontName="Helvetica-Bold", fontSize=11.5,
                           leading=16, textColor=NAVY, alignment=TA_CENTER, spaceAfter=0)

    story = [
        Paragraph("RESQNET AI", title),
        Paragraph("Explainable multi-agent flood-rescue coordination and disaster-response simulation platform", subtitle),
    ]

    callout = Table([[Paragraph(
        "<b>Project in one sentence</b><br/>RESQNET AI is a digital twin that simulates how autonomous emergency teams coordinate rescue resources, routes, and shelter capacity during floods and infrastructure failures.",
        body)]], colWidths=[doc.width])
    callout.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE), ("BOX", (0, 0), (-1, -1), 0.8, TEAL),
        ("LEFTPADDING", (0, 0), (-1, -1), 11), ("RIGHTPADDING", (0, 0), (-1, -1), 11),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [callout, Spacer(1, 5 * mm)]

    story += [
        Paragraph("Project overview", h2),
        Paragraph(
            "RESQNET AI creates a synthetic digital model of a flooded city. Rescue boats, ground teams, incident coordinators, and shelters act as cooperating agents. Together they decide which emergencies to serve, which safe routes to use, and where rescued people can be accommodated.", body),
        Paragraph(
            "The platform is designed as a research and decision-support simulator. It helps study whether decentralized coordination can remain effective, safe, fair, reproducible, and explainable when disaster conditions change quickly.", body),
        Paragraph("The problem being addressed", h2),
        Paragraph("Flood response teams must make urgent decisions while facing:", body),
    ]
    for item in [
        "Multiple SOS reports arriving at the same time",
        "Limited rescue boats, ground vehicles, and shelter capacity",
        "Flooded roads, bridge closures, and changing route conditions",
        "Delayed, duplicated, contradictory, or false reports",
        "Communication blackouts and incomplete local information",
        "Sudden equipment, infrastructure, and shelter failures",
    ]:
        story.append(Paragraph(f"- {item}", bullet))

    story += [
        Paragraph("How coordination works", h2),
        Paragraph(
            "Every emergency becomes an incident. Available agents evaluate incidents using travel time, route risk, victim urgency, shelter availability, information reliability, and fairness between neighbourhoods. In the decentralized strategy, agents bid for suitable incidents; incident agents compare proposals; shelter capacity is reserved; and an independent safety layer validates every commitment.", body),
        Paragraph(
            "If a route closes, a resource fails, or a shelter loses capacity, affected assignments are reconsidered and agents negotiate an alternative plan.", body),
        Paragraph("Core capabilities", h2),
    ]

    features = [
        ("Live command centre", "City map, flood conditions, incidents, rescue units, shelters, assignments, activity feeds, and performance indicators."),
        ("Multi-agent coordination", "Contract-net bidding, deferred acceptance, route planning, and shelter reservations."),
        ("Strategy comparison", "Decentralized, centralized, and greedy coordination can be tested under identical conditions."),
        ("Scenario simulation", "Normal flood, flash flood, bridge closure, resource shortage, shelter overflow, conflicting information, and triple failure."),
        ("Safety shield", "Blocks unsafe routes, double-booking, excessive loads, stale decisions, invalid reservations, and disabled resources."),
        ("Explainable decisions", "Shows why an agent was selected, which alternatives were rejected, and which safety checks were applied."),
        ("Replay and audit", "Records events and decisions for inspection and deterministic reconstruction of a run."),
        ("Decision lab and benchmarks", "Supports counterfactual experiments, adversarial failures, repeated trials, and comparative reports."),
    ]
    rows = []
    for name, detail in features:
        rows.append([Paragraph(f"<b>{name}</b>", small), Paragraph(detail, small)])
    table = Table(rows, colWidths=[45 * mm, doc.width - 45 * mm], repeatRows=0)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F0F4F8")),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [table, Paragraph("Technology architecture", h2)]

    tech = [
        [Paragraph("<b>Frontend</b>", small), Paragraph("React, TypeScript, Vite, Zustand, Recharts, React Flow, Tailwind CSS", small)],
        [Paragraph("<b>Backend</b>", small), Paragraph("Python and FastAPI", small)],
        [Paragraph("<b>Live updates</b>", small), Paragraph("WebSockets", small)],
        [Paragraph("<b>Persistence</b>", small), Paragraph("SQLite and event-sourced simulation state", small)],
    ]
    tech_table = Table(tech, colWidths=[34 * mm, doc.width - 34 * mm])
    tech_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -2), 0.35, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [
        tech_table,
        Paragraph("Project objective", h2),
        Paragraph(
            "The central goal is to demonstrate and evaluate transparent multi-agent decision-making for emergency coordination. The system provides a controlled environment for analysing response time, rescue outcomes, unmet demand, resource use, fairness, robustness, and safety across difficult disaster scenarios.", body),
        Spacer(1, 3 * mm),
    ]
    pitch = Table([[Paragraph(
        '"RESQNET AI is an explainable multi-agent digital twin for testing safe, adaptive, and fair flood-rescue coordination."',
        quote)]], colWidths=[doc.width])
    pitch.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F0F4F8")),
        ("LINEABOVE", (0, 0), (-1, 0), 2, BLUE),
        ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story += [pitch, Spacer(1, 3 * mm), Paragraph(
        "Current scope: This implementation uses synthetic simulation data. It is not yet connected to live emergency services, field sensors, or real-world dispatch systems.", small)]

    doc.build(story)
    print(OUT)


if __name__ == "__main__":
    build()
