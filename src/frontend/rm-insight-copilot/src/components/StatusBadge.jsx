const badgeTones = {
  segment: {
    "복합고관계형": "mint",
    "복합고관계": "mint",
    "거래·수신중심형": "blue",
    "수신중심": "blue",
    "거래활동중심": "amber",
    "여신중심": "violet",
    "균형·중간관계": "lime",
    "저거래·저수신형": "gray",
    "저관계": "gray"
  },
  weakening: {
    "입출금": "coral",
    "입출금활동": "coral",
    "자동이체": "amber",
    "자동이체활동": "amber",
    "채널": "blue",
    "채널활동": "blue",
    "카드": "violet",
    "카드활동": "violet",
    "복합 거래활동": "mint"
  },
  stage: {
    stored: "blue",
    generated: "violet"
  },
  priority: {
    URGENT: "coral",
    High: "coral",
    HIGH: "coral",
    MEDIUM_HIGH: "violet",
    Medium: "amber",
    MEDIUM: "amber",
    Watch: "blue",
    WATCH: "blue",
    Low: "gray",
    LOW: "gray"
  },
  riskBand: {
    G1_TOP_1: "coral",
    G2_1_TO_3: "amber",
    G3_3_TO_5: "violet",
    G4_5_TO_10: "blue",
    G5_REST: "gray"
  }
};

export function resolveBadgeTone(kind, value, fallback = "mint") {
  return badgeTones[kind]?.[value] ?? fallback;
}

export default function StatusBadge({ children, tone, kind, value }) {
  const resolvedTone = tone ?? resolveBadgeTone(kind, value ?? children);
  return <span className={`status-badge ${resolvedTone}`}>{children}</span>;
}
