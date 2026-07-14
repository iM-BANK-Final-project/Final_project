"""Public response models for the RM insight read API."""

from pydantic import BaseModel, Field


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
    riskLevel: str
    risk: float
    health: float
    valueProxy: float
    priorityScore: float
    priorityRank: int
    weakeningType: str
    profitability: float | None
    defenseValue: float | None
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
    managed: int


class SignalSummary(BaseModel):
    label: str
    value: int


class Overview(BaseModel):
    asOfMonth: str
    managedCustomerCount: int
    averageRisk: float
    highRiskShare: float
    priorityValueTotal: float
    monthlyTrend: list[MonthlyTrend]
    signalSummary: list[SignalSummary]


class FilterOptions(BaseModel):
    asOfMonth: str
    segments: list[str]
    riskLevels: list[str]
    industries: list[str]
    regions: list[str]
    dedicatedOptions: list[str]
    weakeningTypes: list[str]


class ShapFactor(BaseModel):
    feature: str
    featureValue: float
    impact: float
    rank: int


class Report(BaseModel):
    customer: Customer
    recommendation: Recommendation
    strategySummary: str
    shapAvailable: bool
    shapFactors: list[ShapFactor]


class Health(BaseModel):
    status: str
    database: str
