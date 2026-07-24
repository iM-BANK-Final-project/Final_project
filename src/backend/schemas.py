"""Public response models for the RM insight API."""

from typing import Annotated

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints, model_validator


ShortText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
NarrativeText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000)
]
CorporateId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
]
CustomerName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)
]
AsOfMonth = Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class Signal(BaseModel):
    label: str
    change: float | None
    recent: float
    previous: float


class Customer(BaseModel):
    id: str
    name: str
    industry: str
    region: str
    dedicated: str
    segment: str
    riskBand: str
    riskBandName: str
    riskBandOrder: int
    riskRank: int
    predictedPositive: bool
    threshold: float
    risk: float
    health: float
    clvRisk: float
    potentialLoss: float
    defenseRank: int | None
    weakeningType: str
    signals: list[Signal] = Field(default_factory=list)


class CustomerPage(BaseModel):
    items: list[Customer]
    page: int
    pageSize: int
    total: int


class Recommendation(BaseModel):
    id: str
    name: str
    segment: str
    weakeningType: str
    priority: str
    reason: str
    contact: str
    action: str
    summary: str


class RecommendationPage(BaseModel):
    items: list[Recommendation]
    page: int
    pageSize: int
    total: int


class MonthlyTrend(BaseModel):
    month: str
    risk: float
    thresholdShare: float
    thresholdCount: int
    eligibleCount: int
    isCurrent: bool


class SignalSummary(BaseModel):
    label: str
    value: int


class Overview(BaseModel):
    asOfMonth: str
    managedCustomerCount: int
    averageRisk: float
    thresholdShare: float
    potentialLossTotal: float
    monthlyTrend: list[MonthlyTrend]
    signalSummary: list[SignalSummary]


class RiskBandOption(BaseModel):
    value: str
    label: str
    order: int


class FilterOptions(BaseModel):
    asOfMonth: str
    segments: list[str]
    riskBands: list[RiskBandOption]
    industries: list[str]
    regions: list[str]
    dedicatedOptions: list[str]
    weakeningTypes: list[str]


class ShapFactor(BaseModel):
    feature: str
    featureValue: float | None
    impact: float
    rank: int


class Report(BaseModel):
    customer: Customer
    recommendation: Recommendation
    strategySummary: str
    shapAvailable: bool
    shapFactors: list[ShapFactor]


class ReportMetrics(BaseModel):
    risk: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
    clvRisk: FiniteFloat
    potentialLoss: FiniteFloat


class GeminiNarrative(BaseModel):
    riskSummary: NarrativeText
    valueAssessment: NarrativeText
    weakeningDrivers: NarrativeText
    contactStrategy: NarrativeText
    recommendedActions: Annotated[list[ShortText], Field(min_length=1, max_length=8)]
    caveats: Annotated[list[ShortText], Field(min_length=1, max_length=6)]


class GeneratedReport(GeminiNarrative):
    corporateId: CorporateId
    customerName: CustomerName
    asOfMonth: AsOfMonth
    generatedAt: AwareDatetime
    metrics: ReportMetrics
    shapFactors: Annotated[list[ShapFactor], Field(min_length=1, max_length=10)]

    @model_validator(mode="after")
    def validate_shap_ranks(self):
        ranks = [factor.rank for factor in self.shapFactors]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("SHAP 순위는 1부터 중복 없이 연속해야 합니다.")
        return self


class Health(BaseModel):
    status: str
    database: str
