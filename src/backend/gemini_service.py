import json
import os
import re
from copy import deepcopy

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.backend.schemas import GeminiNarrative
from src.backend.shap_report_rules import prepare_shap_report_evidence

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

CANONICAL_CAVEATS = (
    "Y는 실제 해지·부도·확정 휴면이 아닌 지속거래약화 proxy 예측입니다.",
    "SHAP은 인과관계나 확률 변화량이 아닌 모델 예측 기여도입니다.",
    "CLV_Risk와 PotentialLoss는 확정 손실액이 아닌 시나리오 추정치입니다.",
)
EVENT_PROBABILITY_TERMS = re.compile(r"(?:실제\s*)?(?:해지|부도|휴면)\s*확률")
NEARBY_EVENT_NEGATION = re.compile(
    r"^\s*(?:(?:은|는|이|가)?\s*아(?:니|닙)|(?:이)?라고\s*볼\s*수\s*없|(?:으)?로\s*해석하지\s*않)"
)
SHAP_TERM = re.compile(r"SHAP", re.IGNORECASE)
SHAP_QUANTIFIED_CHANGE = re.compile(
    r"(?:\d+(?:\.\d+)?\s*(?:%p|퍼센트포인트|percentage\s+points?|bp|bps|basis\s+points?|%|퍼센트)|\d+(?:\.\d+)?\s*만큼)",
    re.IGNORECASE,
)
SHAP_CAUSAL_CONNECTOR = re.compile(r"(?:이므로|따라서|때문(?:에|으로)?|영향(?:으로|때문)?|결과로)")
RISK_TERM = r"(?:위험(?:도|점수|확률|가능성)?|리스크)"
RISK_UP_WORDING = re.compile(
    rf"{RISK_TERM}\s*(?:을|를|은|는|이|가)?\s*(?:\d+(?:\.\d+)?\s*만큼\s*)?(?:높|상승|증가|악화|올리|올렸|올)|악화\s*요인"
)
PROTECTIVE_WORDING = re.compile(
    rf"{RISK_TERM}\s*(?:을|를|은|는|이|가)?\s*(?:\d+(?:\.\d+)?\s*만큼\s*)?(?:낮|하락|감소|완화|내리|내렸|내)|(?:방어|보호)(?:적|\s*(?:요인|효과|신호))"
)
LOCAL_CLAUSE_BOUNDARY = re.compile(
    r"[,;]|(?:그러나|하지만|반면|다만|이고|이며|이나|지만|으나|는데)(?=\s)"
)
CONTRAST_MARKERS = frozenset({"그러나", "하지만", "반면", "다만", "지만", "으나", "는데"})
DIRECTION_ATTRIBUTION = re.compile(r"(?:요인|기여)")


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
    enriched = deepcopy(context)
    enriched["shapAnalysis"] = prepare_shap_report_evidence(enriched["shapFactors"])
    evidence = json.dumps(enriched, ensure_ascii=False, allow_nan=False, indent=2)
    return f"""
당신은 기업금융 RM을 지원하는 전략 보고서 작성자입니다.
아래 [검증된 컨텍스트]에 있는 사실만 사용해 한국어로 작성하세요.

[필수 규칙]
- risk는 향후 6개월 Y_INTERVENE_M12_v2 지속거래약화 발생 가능성입니다.
- risk를 실제 해지, 부도, 확정 휴면 확률로 표현하지 마세요.
- CLV_Risk와 PotentialLoss는 시나리오 추정치이며 확정 손실액이 아닙니다.
- 모든 원시 Top 10 항목을 권위 있는 입력 근거로 검토하세요. 같은 그룹의 유사 피처는 종합 신호로 결합하고 각 피처를 개별적으로 모두 언급할 필요는 없습니다.
- 같은 그룹의 유사 피처는 하나의 종합 신호로 묶어 반복적인 문장을 피하세요.
- 모델은 FS2_R1_DACK_DYNAMIC 56개 피처만 사용하며, 업종·지역·고객등급·전담여부는 모델 피처가 아닙니다.
- SHAP은 인과관계가 아닙니다. 인과관계나 확률 변화량이 아닌 모델 예측 기여도이므로 SHAP 값으로 확률이나 인과를 주장하지 마세요.
- 피처 값이 컨텍스트에 없으면 값을 추정하거나 만들어내지 마세요.
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


def postprocess_strategy_narrative(
    narrative: GeminiNarrative, shap_evidence: dict
) -> GeminiNarrative:
    """Normalize fixed terminology and enforce bounded SHAP narrative safety."""

    normalized = narrative.model_dump()
    for field in ("riskSummary", "valueAssessment", "weakeningDrivers", "contactStrategy"):
        normalized[field] = _normalize_event_probability_term(normalized[field])
    normalized["recommendedActions"] = [
        _normalize_event_probability_term(item) for item in normalized["recommendedActions"]
    ]
    normalized["caveats"] = [
        _normalize_event_probability_term(item) for item in normalized["caveats"]
    ]

    _reject_unsafe_shap_claims(normalized, shap_evidence)
    normalized["caveats"] = _bounded_caveats(normalized["caveats"])
    return GeminiNarrative.model_validate(normalized)


def _normalize_event_probability_term(text: str) -> str:
    def replace(match: re.Match) -> str:
        if NEARBY_EVENT_NEGATION.match(match.string[match.end() :]):
            return match.group(0)
        return "지속거래약화 가능성"

    return EVENT_PROBABILITY_TERMS.sub(replace, text)


def _reject_unsafe_shap_claims(narrative: dict, shap_evidence: dict) -> None:
    directions = {
        item["feature"]: item["direction"]
        for item in shap_evidence["localShapTop10"]
    }
    texts = [
        narrative[field]
        for field in ("riskSummary", "valueAssessment", "weakeningDrivers", "contactStrategy")
    ] + narrative["recommendedActions"] + narrative["caveats"]

    for text in texts:
        for sentence in re.split(r"(?<=[!?])\s*|(?<!\d)\.(?:\s*|$)|\n+", text):
            for clause in _local_clauses(sentence):
                if _has_shap_linked_probability_claim(clause):
                    raise ValueError("SHAP 값을 확률 또는 비율 변화로 설명할 수 없습니다.")
            for feature, direction, clause in _feature_direction_clauses(sentence, directions):
                if direction == "risk_down" and RISK_UP_WORDING.search(clause):
                    raise ValueError("SHAP 방향과 반대되는 위험 상승 설명입니다.")
                if direction == "risk_up" and PROTECTIVE_WORDING.search(clause):
                    raise ValueError("SHAP 방향과 반대되는 보호 설명입니다.")
                if direction == "neutral" and (
                    RISK_UP_WORDING.search(clause) or PROTECTIVE_WORDING.search(clause)
                ):
                    raise ValueError("중립 SHAP 피처의 위험 방향을 단정할 수 없습니다.")


def _has_shap_linked_probability_claim(sentence: str) -> bool:
    if not (SHAP_TERM.search(sentence) and SHAP_QUANTIFIED_CHANGE.search(sentence)):
        return False
    return bool(
        SHAP_CAUSAL_CONNECTOR.search(sentence)
        or RISK_UP_WORDING.search(sentence)
        or PROTECTIVE_WORDING.search(sentence)
    )


def _local_clauses(sentence: str) -> list[str]:
    return [clause for clause in LOCAL_CLAUSE_BOUNDARY.split(sentence) if clause]


def _feature_direction_clauses(sentence: str, directions: dict[str, str]):
    positions = sorted(
        (sentence.find(feature), feature)
        for feature in directions
        if feature in sentence
    )
    for index, (start, feature) in enumerate(positions):
        previous_feature_end = (
            positions[index - 1][0] + len(positions[index - 1][1])
            if index > 0
            else 0
        )
        preceding_boundaries = list(
            LOCAL_CLAUSE_BOUNDARY.finditer(sentence, previous_feature_end, start)
        )
        clause_start = (
            preceding_boundaries[-1].end()
            if preceding_boundaries
            else previous_feature_end
        )
        next_feature_start = (
            positions[index + 1][0] if index + 1 < len(positions) else len(sentence)
        )
        boundary = LOCAL_CLAUSE_BOUNDARY.search(
            sentence, start + len(feature), next_feature_start
        )
        if boundary is not None and boundary.group(0).strip() in CONTRAST_MARKERS:
            following_clause = sentence[boundary.end() : next_feature_start]
            if DIRECTION_ATTRIBUTION.search(following_clause):
                boundary = None
        end = min(
            next_feature_start,
            boundary.start() if boundary is not None else len(sentence),
        )
        yield feature, directions[feature], sentence[clause_start:end]


def _bounded_caveats(caveats: list[str]) -> list[str]:
    unrelated = []
    for caveat in caveats:
        if _is_overlapping_limitation(caveat):
            continue
        if caveat not in unrelated:
            unrelated.append(caveat)
        if len(unrelated) == 3:
            break
    return unrelated + list(CANONICAL_CAVEATS)


def _is_overlapping_limitation(caveat: str) -> bool:
    lower = caveat.lower()
    if "shap" in lower and any(term in caveat for term in ("인과", "확률", "기여", "변화량")):
        return True
    if any(term in lower for term in ("clv_risk", "potentialloss")) and any(
        term in caveat for term in ("확정 손실", "시나리오", "추정")
    ):
        return True
    return any(term in caveat for term in ("해지", "부도", "휴면", "지속거래약화")) and any(
        term in caveat for term in ("확률", "proxy", "예측", "아닌", "아닙니다", "아니")
    )


def generate_strategy_report(context: dict, client=None) -> GeminiNarrative:
    """Generate a bounded narrative from the supplied authoritative report context."""

    try:
        prompt = build_strategy_report_prompt(context)
        response = _generate_strategy_content(prompt, client=client)
        payload = getattr(response, "parsed", None)
        if payload is None:
            payload = json.loads((getattr(response, "text", None) or "").strip())
        narrative = GeminiNarrative.model_validate(payload)
        shap_evidence = prepare_shap_report_evidence(context["shapFactors"])
        return postprocess_strategy_narrative(narrative, shap_evidence)
    except Exception as error:
        raise ReportGenerationError("AI 보고서 생성에 실패했습니다.") from error
