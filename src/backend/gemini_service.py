import json
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.backend.schemas import GeminiNarrative

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")


class ReportGenerationError(RuntimeError):
    """Safe public failure raised when a strategy narrative cannot be generated."""


def _vertex_enabled() -> bool:
    value = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower()
    return value in {"1", "true", "yes", "y"}


def _make_client(force_api_key: bool = False):
    if (force_api_key or not _vertex_enabled()) and GEMINI_API_KEY:
        return genai.Client(api_key=GEMINI_API_KEY)

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID")
    if project_id:
        return genai.Client(
            vertexai=True,
            project=project_id,
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "global"),
        )

    if GEMINI_API_KEY:
        return genai.Client(api_key=GEMINI_API_KEY)

    raise RuntimeError("GEMINI_API_KEY 또는 GOOGLE_CLOUD_PROJECT 환경변수가 필요합니다.")


def ask_gemini(question: str, sector: str, context: str = "") -> str:
    if context:
        prompt = f"""
당신은 금융 문서 기반 챗봇입니다.
반드시 제공된 문서 문맥을 우선 참고해서 한국어로 답변하세요.
문서에 없는 내용은 추정이라고 분명히 밝히세요.

[업권]
{sector}

[문서 문맥]
{context}

[질문]
{question}
""".strip()
    else:
        prompt = f"""
당신은 금융 문서 기반 챗봇입니다.
현재 문서 문맥이 충분하지 않을 수 있습니다.
일반적인 금융 지식으로 답하되, 문서 근거가 없으면 그 점을 밝혀주세요.

[업권]
{sector}

[질문]
{question}
""".strip()

    try:
        client = _make_client()
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
    except Exception:
        if _vertex_enabled() and GEMINI_API_KEY:
            client = _make_client(force_api_key=True)
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )
        else:
            raise

    return (getattr(response, "text", None) or "응답을 생성하지 못했습니다.").strip()


def build_strategy_report_prompt(context: dict) -> str:
    evidence = json.dumps(context, ensure_ascii=False, allow_nan=False, indent=2)
    return f"""
당신은 기업금융 RM을 지원하는 전략 보고서 작성자입니다.
아래 [검증된 컨텍스트]에 있는 사실만 사용해 한국어로 작성하세요.

[필수 규칙]
- risk는 향후 6개월 Y_INTERVENE_M12_v2 지속거래약화 발생 가능성입니다.
- risk를 실제 해지, 부도, 확정 휴면 확률로 표현하지 마세요.
- CLV_Risk와 PotentialLoss는 시나리오 추정치이며 확정 손실액이 아닙니다.
- SHAP은 인과관계가 아닙니다. 모델 예측에 대한 기여도로만 설명하세요.
- 컨텍스트에 없는 재무정보, 사건, 상품 보유 사실을 만들지 마세요.
- 추천은 RM 검토가 필요한 초기 접촉 전략으로 표현하세요.
- 동일한 내용을 여러 섹션에 반복하지 마세요.

[검증된 컨텍스트]
{evidence}
""".strip()


def _generate_strategy_content(prompt: str, client=None):
    def invoke(active_client):
        return active_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GeminiNarrative,
                temperature=0.2,
            ),
        )

    if client is not None:
        return invoke(client)

    try:
        return invoke(_make_client())
    except Exception:
        if _vertex_enabled() and GEMINI_API_KEY:
            return invoke(_make_client(force_api_key=True))
        raise


def generate_strategy_report(context: dict, client=None) -> GeminiNarrative:
    """Generate a bounded narrative from the supplied authoritative report context."""

    try:
        prompt = build_strategy_report_prompt(context)
        response = _generate_strategy_content(prompt, client=client)
        payload = getattr(response, "parsed", None)
        if payload is None:
            payload = json.loads((getattr(response, "text", None) or "").strip())
        return GeminiNarrative.model_validate(payload)
    except Exception as error:
        raise ReportGenerationError("AI 보고서 생성에 실패했습니다.") from error
