"""In-memory PDF renderer for validated Gemini strategy reports."""

from io import BytesIO
import os
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    CondPageBreak,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.backend.schemas import GeneratedReport


class PdfGenerationError(RuntimeError):
    """Raised when a strategy report cannot be rendered safely."""


FONT_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/AppleGothic.ttf"),
    Path("/System/Library/Fonts/Supplemental/NotoSansGothic-Regular.ttf"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
)
FONT_NAME = "RMReportKorean"


def _resolve_font_path(font_path: Path | None) -> Path:
    if font_path is not None:
        candidate = Path(font_path).expanduser()
        if candidate.is_file():
            return candidate
        raise PdfGenerationError("사용할 수 있는 한국어 폰트를 찾지 못했습니다.")

    configured = os.getenv("RM_REPORT_FONT_PATH", "").strip()
    candidates = (Path(configured).expanduser(), *FONT_CANDIDATES) if configured else FONT_CANDIDATES
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise PdfGenerationError("사용할 수 있는 한국어 폰트를 찾지 못했습니다.")


def _register_font(font_path: Path) -> str:
    try:
        if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(FONT_NAME, str(font_path)))
    except Exception as error:
        raise PdfGenerationError("한국어 폰트를 PDF에 포함하지 못했습니다.") from error
    return FONT_NAME


def _paragraph(text: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)


def _styles(font_name: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "RMTitle",
            parent=base["Title"],
            fontName=font_name,
            fontSize=20,
            leading=27,
            textColor=colors.HexColor("#16352D"),
            alignment=TA_LEFT,
            spaceAfter=5 * mm,
        ),
        "meta": ParagraphStyle(
            "RMMeta",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=9,
            leading=14,
            textColor=colors.HexColor("#52645F"),
        ),
        "section": ParagraphStyle(
            "RMSection",
            parent=base["Heading2"],
            fontName=font_name,
            fontSize=12,
            leading=17,
            textColor=colors.HexColor("#173F35"),
            spaceBefore=4 * mm,
            spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "RMBody",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=9.5,
            leading=16,
            textColor=colors.HexColor("#263632"),
            wordWrap="CJK",
        ),
        "small": ParagraphStyle(
            "RMSmall",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=8,
            leading=12,
            textColor=colors.HexColor("#586A65"),
            wordWrap="CJK",
        ),
        "metric_label": ParagraphStyle(
            "RMMetricLabel",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#52645F"),
            alignment=TA_CENTER,
        ),
        "metric_value": ParagraphStyle(
            "RMMetricValue",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=13,
            leading=18,
            textColor=colors.HexColor("#113C32"),
            alignment=TA_CENTER,
        ),
    }


def _page_footer(canvas, document, font_name: str) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D8E2DE"))
    canvas.line(18 * mm, 14 * mm, A4[0] - 18 * mm, 14 * mm)
    canvas.setFont(font_name, 8)
    canvas.setFillColor(colors.HexColor("#667873"))
    canvas.drawString(18 * mm, 9 * mm, "RM Insight Copilot")
    canvas.drawRightString(A4[0] - 18 * mm, 9 * mm, f"페이지 {document.page}")
    canvas.restoreState()


def render_strategy_report_pdf(
    report: GeneratedReport, font_path: Path | None = None
) -> bytes:
    """Render a validated report envelope into an A4 PDF held only in memory."""

    try:
        validated = GeneratedReport.model_validate(report)
        font_name = _register_font(_resolve_font_path(font_path))
        styles = _styles(font_name)
        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=18 * mm,
            leftMargin=18 * mm,
            topMargin=18 * mm,
            bottomMargin=20 * mm,
            title=f"{validated.customerName} AI 전략 보고서",
            author="RM Insight Copilot",
        )

        story = [
            _paragraph("AI 지속거래약화 전략 보고서", styles["title"]),
            _paragraph(
                f"기업명: {validated.customerName} | "
                f"법인ID: {validated.corporateId} | "
                f"기준월: {validated.asOfMonth}",
                styles["meta"],
            ),
            Spacer(1, 4 * mm),
        ]

        metric_data = [
            [
                _paragraph("지속거래약화 위험", styles["metric_label"]),
                _paragraph("CLV_Risk", styles["metric_label"]),
                _paragraph("PotentialLoss", styles["metric_label"]),
            ],
            [
                _paragraph(f"{validated.metrics.risk:,.2f}%", styles["metric_value"]),
                _paragraph(
                    f"{validated.metrics.clvRisk:,.2f} 백만원",
                    styles["metric_value"],
                ),
                _paragraph(
                    f"{validated.metrics.potentialLoss:,.2f} 백만원",
                    styles["metric_value"],
                ),
            ],
        ]
        metric_table = Table(metric_data, colWidths=[(A4[0] - 36 * mm) / 3] * 3)
        metric_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF5F2")),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#C5D8D1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D7E5E0")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.append(metric_table)

        sections = (
            ("종합 위험 요약", validated.riskSummary),
            ("고객가치 및 잠재손실 해석", validated.valueAssessment),
            ("주요 약화 원인", validated.weakeningDrivers),
            ("RM 접촉 전략", validated.contactStrategy),
        )
        for title, body in sections:
            story.append(
                KeepTogether(
                    [_paragraph(title, styles["section"]), _paragraph(body, styles["body"])]
                )
            )

        story.extend(
            [
                _paragraph("실행 권고사항", styles["section"]),
                *[
                    _paragraph(f"{index}. {action}", styles["body"])
                    for index, action in enumerate(validated.recommendedActions, start=1)
                ],
                _paragraph("분석 유의사항", styles["section"]),
                *[
                    _paragraph(f"- {caveat}", styles["body"])
                    for caveat in validated.caveats
                ],
                CondPageBreak(105 * mm),
                _paragraph("주요 SHAP Value (상위 10개)", styles["section"]),
            ]
        )

        shap_data = [
            [
                _paragraph("순위", styles["small"]),
                _paragraph("특성", styles["small"]),
                _paragraph("특성값", styles["small"]),
                _paragraph("SHAP Value", styles["small"]),
            ]
        ]
        for factor in validated.shapFactors:
            feature_value = "-" if factor.featureValue is None else f"{factor.featureValue:,.4f}"
            shap_data.append(
                [
                    _paragraph(factor.rank, styles["small"]),
                    _paragraph(factor.feature, styles["small"]),
                    _paragraph(feature_value, styles["small"]),
                    _paragraph(f"{factor.impact:+.6f}", styles["small"]),
                ]
            )
        shap_table = Table(shap_data, colWidths=[12 * mm, 88 * mm, 30 * mm, 34 * mm], repeatRows=1)
        shap_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDEBE6")),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#BFD1CB")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.extend(
            [
                shap_table,
                Spacer(1, 5 * mm),
                _paragraph(
                    f"생성 시각: {validated.generatedAt.isoformat()}", styles["small"]
                ),
                _paragraph(
                    "본 보고서의 위험확률은 향후 6개월 Y_INTERVENE_M12_v2 "
                    "지속거래약화 발생 가능성입니다. 실제 해지·부도·확정 휴면 "
                    "확률이 아니며, CLV_Risk와 PotentialLoss는 확정 회계손실이 아닙니다. "
                    "SHAP은 인과관계가 아닌 모델 예측 기여도입니다.",
                    styles["small"],
                ),
            ]
        )

        footer = lambda canvas, doc: _page_footer(canvas, doc, font_name)
        document.build(story, onFirstPage=footer, onLaterPages=footer)
        return buffer.getvalue()
    except PdfGenerationError:
        raise
    except Exception as error:
        raise PdfGenerationError("PDF 보고서를 생성하지 못했습니다.") from error
