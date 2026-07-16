from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell


NOTEBOOK_PATH = Path("EDA/36개월 특성.ipynb")
nb = nbformat.read(NOTEBOOK_PATH, as_version=4)

# Remove prior generated sections so rerunning this updater is idempotent.
generated_markers = {
    "### 5-1. 지수 추이의 강건성 점검",
    "### 7-1. 다축 약화상태 후보 탐색",
    "### 7-2. 입출금·채널 중복성 점검",
    "### 7-3. 채널 제외 단순 금액감소 rolling y 후보",
    "### 7-2. 단순 금액감소 기반 rolling y 후보",
}
nb.cells = [
    cell
    for cell in nb.cells
    if not any(cell.source.startswith(marker) for marker in generated_markers)
    and "ROBUST_INDEX_CHECK_V1" not in cell.source
    and "MULTI_AXIS_WEAKENING_EXPLORATION_V1" not in cell.source
    and "CHANNEL_FLOW_OVERLAP_V1" not in cell.source
    and "SIMPLE_DORMANCY_Y_CANDIDATES_V1" not in cell.source
    and "CANDIDATE_STABILITY_V1" not in cell.source
]


def find_cell(startswith: str) -> int:
    for index, cell in enumerate(nb.cells):
        if cell.source.startswith(startswith):
            return index
    raise ValueError(f"Cell not found: {startswith}")


def find_cell_any(*prefixes: str) -> int:
    for prefix in prefixes:
        try:
            return find_cell(prefix)
        except ValueError:
            continue
    raise ValueError(f"Cells not found: {prefixes}")


nb.cells[find_cell("## tl;dr")].source = '''## tl;dr

이 노트북은 36개월이 모두 관측된 법인의 업종·지역과 다축 금융관계 추세를 점검합니다. 초기 6개월 평균 대비 지수는 축별 EDA 지표이며 종합점수가 아닙니다. 전체 합계·고객별 중앙값·상위 1% 영향 완화 결과와 rolling 다축 약화 민감도를 함께 보되, 여기서 y를 확정하지 않습니다.'''

nb.cells[find_cell("## Context & Methods")].source = '''## Context & Methods

### 분석 범위

- 기간: 2023.01~2025.12, 36개월
- 대상: 36개 달이 모두 관측된 법인
- 금융관계 축: 수신, 여신, 입출금, 외환, 카드, 채널, 자동이체, 상품관계폭
- 비교: 전체 코호트, 상위 업종·지역, 고객별 변화와 이상치 민감도

### Key Assumptions

- 관측행이 있는 월만 코호트 판단에 사용하며, 결측 고객-월을 0 활동으로 대체하지 않습니다.
- 업종·지역·등급·전담여부는 최근 관측월 기준 프로필을 사용하고 기간 중 변경 수를 별도로 확인합니다.
- 초기 6개월 평균 대비 지수는 각 축의 상대 추세 비교용이며 서로 다른 축을 합친 점수가 아닙니다.
- 금액은 명목금액이며 외부 경기·물가·제도 요인을 보정하지 않습니다.
- rolling 다축 약화 표의 임계값은 민감도 후보일 뿐 금융관계 휴면화 y가 아닙니다.'''


setup_index = find_cell("from pathlib import Path")
nb.cells[setup_index].source = '''from pathlib import Path
import sys
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from IPython.display import display, Markdown

PROJECT_ROOT = Path.cwd().resolve()
if not (PROJECT_ROOT / 'src').exists():
    PROJECT_ROOT = Path('/Users/gggyyu/Final_project')
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.preprocessing.financial_dormancy_cohort import (
    build_financial_relationship_axes,
    select_complete_36m_cohort,
)
from src.preprocessing.financial_dormancy_candidates import (
    DormancyCandidateConfig,
    build_simple_dormancy_candidates,
)

warnings.filterwarnings('ignore')
pd.set_option('display.max_columns', 100)
pd.set_option('display.float_format', lambda x: f'{x:,.2f}')
sns.set_theme(style='whitegrid', font_scale=0.95)
plt.rcParams['font.family'] = ['AppleGothic']
plt.rcParams['axes.unicode_minus'] = False

DATA_CANDIDATES = [
    Path('/Users/gggyyu/Desktop/(아이엠뱅크) 2026 교육용 데이터/(iM뱅크) 2026 교육용 법인 익명데이터.csv'),
    PROJECT_ROOT / 'data' / '법인 익명데이터.csv',
]
DATA_PATH = next((p for p in DATA_CANDIDATES if p.exists()), None)
if DATA_PATH is None:
    raise FileNotFoundError('원천 CSV를 찾지 못했습니다. DATA_CANDIDATES에 데이터 경로를 추가하세요.')

ID_COL, MONTH_COL = '법인ID', '기준년월'
PROFILE_COLS = ['업종_대분류', '업종_중분류', '사업장_시도', '사업장_시군구', '법인_고객등급', '전담고객여부']
DEPOSIT_COLS = ['요구불예금잔액', '거치식예금잔액', '적립식예금잔액', '수익증권잔액', '신탁잔액', '퇴직연금잔액']
LOAN_COLS = ['여신_운전자금대출잔액', '운전_할인어음잔액', '운전_당좌대출잔액', '운전_일반자금대출잔액', '운전_무역금융잔액', '운전_주택자금대출잔액', '운전_기업구매자금대출잔액', '운전_외상매출채권담보대출잔액', '운전_기타운전자금대출잔액', '여신_시설자금대출잔액', '시설_일반자금대출잔액', '시설_에너지절약시설대출잔액', '시설_주택자금대출잔액', '시설_기타시설자금대출잔액']
FLOW_COLS = ['요구불입금금액', '요구불출금금액']
FX_COLS = ['외환_수출실적금액', '외환_수입실적금액']
CARD_COLS = ['신용카드사용금액', '체크카드사용금액']
CHANNEL_COLS = ['창구거래금액', '인터넷뱅킹거래금액', '스마트뱅킹거래금액', '폰뱅킹거래금액', 'ATM거래금액']
AUTO_COLS = ['자동이체금액']
RAW_AMOUNT_COLS = DEPOSIT_COLS + LOAN_COLS + FLOW_COLS + FX_COLS + CARD_COLS + CHANNEL_COLS + AUTO_COLS
print(f'프로젝트 경로: {PROJECT_ROOT}')
print(f'원천 데이터: {DATA_PATH}')'''

cohort_index = find_cell_any("observed_month_sets =", "stable = select_complete_36m_cohort(")
nb.cells[cohort_index].source = '''stable = select_complete_36m_cohort(
    df,
    customer_id_col=ID_COL,
    month_col=MONTH_COL,
    expected_start='2023-01',
    expected_end='2025-12',
)
stable_ids = pd.Index(stable[ID_COL].drop_duplicates())

cohort_summary = pd.DataFrame({
    '구분': ['전체 법인', '36개월 전체 관측 법인', '완전관측 코호트 비중', '완전관측 코호트 법인-월'],
    '값': [df[ID_COL].nunique(), len(stable_ids), len(stable_ids) / df[ID_COL].nunique(), len(stable)]
})
display(cohort_summary)
assert stable.groupby(ID_COL)[MONTH_COL].nunique().eq(36).all()
assert len(stable) == len(stable_ids) * 36

profile_change = stable.groupby(ID_COL)[PROFILE_COLS].nunique(dropna=False).gt(1).sum().sort_values(ascending=False).rename('프로필이 변한 법인 수').reset_index()
profile_change.columns = ['프로필 컬럼', '프로필이 변한 법인 수']
display(profile_change)'''

axis_index = find_cell_any("stable['수신잔액합계']", "stable = build_financial_relationship_axes(stable)")
nb.cells[axis_index].source = '''stable = build_financial_relationship_axes(stable)
AMOUNT_METRIC_COLS = [
    '수신잔액합계', '여신잔액합계', '입출금금액', '외환거래금액',
    '카드사용금액', '채널거래금액', '자동이체금액'
]
LABEL_AMOUNT_METRIC_COLS = [
    '수신잔액합계', '여신잔액합계', '입출금금액',
    '외환거래금액', '카드사용금액', '자동이체금액'
]
METRIC_COLS = AMOUNT_METRIC_COLS + ['상품관계폭']

latest_profile = (stable.sort_values([ID_COL, MONTH_COL]).groupby(ID_COL).tail(1)[[ID_COL] + PROFILE_COLS].set_index(ID_COL))
activity_rate = stable.groupby(ID_COL)[METRIC_COLS].apply(lambda x: x.gt(0).mean()).add_suffix('_활성월비율')
customer_mean = stable.groupby(ID_COL)[METRIC_COLS].mean().add_suffix('_월평균')
customer_features = latest_profile.join(customer_mean).join(activity_rate).reset_index()
display(customer_features.head())'''

monthly_index = find_cell("monthly_total =")
nb.cells[monthly_index].source = '''monthly_total = stable.groupby(MONTH_COL)[METRIC_COLS].sum()
monthly_per_customer = stable.groupby(MONTH_COL)[METRIC_COLS].mean()
initial_6m_total = monthly_total.head(6).mean().replace(0, np.nan)
initial_6m_per_customer = monthly_per_customer.head(6).mean().replace(0, np.nan)
monthly_index = monthly_total.div(initial_6m_total).mul(100)

fig, axes = plt.subplots(2, 1, figsize=(16, 12), sharex=True)
monthly_total[AMOUNT_METRIC_COLS].plot(ax=axes[0], marker='o')
axes[0].set_title('36개월 전체 관측 법인의 월별 금융활동 합계')
axes[0].set_ylabel('금액')
axes[0].legend(bbox_to_anchor=(1.02, 1), loc='upper left')

monthly_index.plot(ax=axes[1], marker='o')
axes[1].axhline(100, color='gray', linestyle='--', linewidth=1)
axes[1].set_title('초기 6개월 평균 대비 축별 월별 지수 (초기 6개월 평균=100, 종합점수 아님)')
axes[1].set_ylabel('지수')
axes[1].set_xlabel('기준년월')
axes[1].legend(bbox_to_anchor=(1.02, 1), loc='upper left')
plt.tight_layout()
plt.show()

trend_summary = pd.DataFrame({
    '지표': METRIC_COLS,
    '초기 6개월 평균 합계': initial_6m_total.values,
    '마지막 달 합계': monthly_total.iloc[-1].values,
    '합계 변화율': (monthly_total.iloc[-1].values / initial_6m_total.values - 1),
    '초기 6개월 고객당 평균': initial_6m_per_customer.values,
    '마지막 달 고객당 평균': monthly_per_customer.iloc[-1].values,
})
display(trend_summary)'''

robust_markdown = new_markdown_cell('''### 5-1. 지수 추이의 강건성 점검

초기 6개월 평균 대비 지수는 축별 상대 추세를 비교하는 EDA 지표입니다. 첫 달 값이 0인 축과 단월 특이값을 피하면서 다음 세 관점을 함께 비교합니다.

1. 전체 법인 합계의 초기 6개월 평균 대비 지수
2. 법인별 초기 6개월 평균 대비 지수를 만든 뒤 월별 중앙값
3. 고객-월 금액의 상위 1%를 완화한 합계 지수

초기 6개월 평균이 0인 법인은 고객별 지수 중앙값에서 제외하고 그 수를 별도로 공개합니다.''')

robust_code = new_code_cell('''# ROBUST_INDEX_CHECK_V1
ordered = stable.sort_values([ID_COL, MONTH_COL]).copy()
customer_baseline = (
    ordered.groupby(ID_COL, sort=False).head(6)
    .groupby(ID_COL)[METRIC_COLS].mean()
    .replace(0, np.nan)
)
customer_index_rows = (
    ordered.set_index(ID_COL)[METRIC_COLS]
    .div(customer_baseline)
    .mul(100)
)
customer_index_rows[MONTH_COL] = ordered.set_index(ID_COL)[MONTH_COL]
customer_median_index = customer_index_rows.groupby(MONTH_COL)[METRIC_COLS].median()

winsor_caps = ordered[AMOUNT_METRIC_COLS].quantile(0.99)
winsorized = ordered.copy()
winsorized[AMOUNT_METRIC_COLS] = winsorized[AMOUNT_METRIC_COLS].clip(upper=winsor_caps, axis=1)
winsor_monthly_total = winsorized.groupby(MONTH_COL)[METRIC_COLS].sum()
winsor_initial_6m_total = winsor_monthly_total.head(6).mean().replace(0, np.nan)
winsor_monthly_index = winsor_monthly_total.div(winsor_initial_6m_total).mul(100)

baseline_check = pd.DataFrame({
    '지표': METRIC_COLS,
    '초기 6개월 평균 합계': initial_6m_total.values,
    '고객별 초기 6개월 평균 0 법인 수': customer_baseline.isna().sum().values,
    '상위 1% cap': [winsor_caps.get(metric, np.nan) for metric in METRIC_COLS],
})
display(baseline_check)

fig, axes = plt.subplots(4, 2, figsize=(17, 20), sharex=True)
for metric, ax in zip(METRIC_COLS, axes.ravel()):
    ax.plot(monthly_index.index, monthly_index[metric], label='전체 합계 지수', linewidth=2)
    ax.plot(customer_median_index.index, customer_median_index[metric], label='고객별 지수 중앙값', linewidth=2)
    ax.plot(winsor_monthly_index.index, winsor_monthly_index[metric], label='상위 1% 완화 합계 지수', linewidth=2)
    ax.axhline(100, color='gray', linestyle='--', linewidth=1)
    ax.set_title(metric)
    ax.set_ylabel('초기 6개월 평균=100')
axes[0, 0].legend(loc='best')
plt.tight_layout()
plt.show()

robust_last_month = pd.DataFrame({
    '지표': METRIC_COLS,
    '전체 합계 지수': monthly_index.iloc[-1].values,
    '고객별 지수 중앙값': customer_median_index.iloc[-1].values,
    '상위 1% 완화 합계 지수': winsor_monthly_index.iloc[-1].values,
})
display(robust_last_month)''')

monthly_index = find_cell("monthly_total =")
nb.cells[monthly_index + 1:monthly_index + 1] = [robust_markdown, robust_code]

customer_change_index = find_cell("first6 =")
multi_axis_markdown = new_markdown_cell('''### 7-1. 다축 약화상태 후보 탐색

여기서는 y를 확정하지 않습니다. rolling y의 미래 사건을 설계하기 전에, 기준월까지 관측 가능한 최근 3개월과 그 이전 6개월을 비교해 **동시에 약해진 축 수**가 데이터에서 어떻게 분포하는지 탐색합니다.

약화비율과 필요한 축 수를 여러 값으로 바꾸어 발생 규모가 지나치게 작거나 큰 조건을 걸러냅니다. 이 표는 후보 민감도이며 학습 정답이 아닙니다.''')

multi_axis_code = new_code_cell('''# MULTI_AXIS_WEAKENING_EXPLORATION_V1
rolling_source = stable.sort_values([ID_COL, MONTH_COL]).copy()
ratio_columns = []

for metric in METRIC_COLS:
    recent_3m = rolling_source.groupby(ID_COL, sort=False)[metric].transform(
        lambda values: values.rolling(3, min_periods=3).mean()
    )
    prior_6m = rolling_source.groupby(ID_COL, sort=False)[metric].transform(
        lambda values: values.shift(3).rolling(6, min_periods=6).mean()
    )
    ratio_col = f'{metric}_최근3개월_이전6개월비'
    rolling_source[ratio_col] = recent_3m.divide(prior_6m.replace(0, np.nan))
    ratio_columns.append(ratio_col)

sensitivity_rows = []
for ratio_threshold in [0.3, 0.5, 0.7]:
    weakened = rolling_source[ratio_columns].lt(ratio_threshold)
    for min_axes in [2, 3, 4]:
        candidate = weakened.sum(axis=1).ge(min_axes)
        eligible = rolling_source[ratio_columns].notna().sum(axis=1).ge(min_axes)
        candidate_eligible = candidate & eligible
        sensitivity_rows.append({
            '축별 최근/이전 비율 기준': ratio_threshold,
            '최소 동시 약화 축 수': min_axes,
            '판정가능 법인-월': int(eligible.sum()),
            '약화상태 법인-월': int(candidate_eligible.sum()),
            '약화상태 비율': candidate_eligible.sum() / eligible.sum() if eligible.sum() else np.nan,
            '해당 법인 수': rolling_source.loc[candidate_eligible, ID_COL].nunique(),
        })

weakening_sensitivity = pd.DataFrame(sensitivity_rows)
display(weakening_sensitivity)

reference_threshold = 0.5
rolling_source['동시약화축수_탐색용'] = rolling_source[ratio_columns].lt(reference_threshold).sum(axis=1)
axis_count_distribution = (
    rolling_source.loc[rolling_source[ratio_columns].notna().any(axis=1), '동시약화축수_탐색용']
    .value_counts()
    .sort_index()
    .rename_axis('동시 약화 축 수')
    .to_frame('법인-월 수')
)
axis_count_distribution['비율'] = axis_count_distribution['법인-월 수'] / axis_count_distribution['법인-월 수'].sum()
display(axis_count_distribution)

plt.figure(figsize=(10, 5))
sns.barplot(data=axis_count_distribution.reset_index(), x='동시 약화 축 수', y='법인-월 수', color='#2A9D8F')
plt.title('탐색 기준(최근3개월/이전6개월 < 0.5)의 동시 약화 축 수 분포')
plt.tight_layout()
plt.show()''')

customer_change_index = find_cell("first6 =")
nb.cells[customer_change_index + 1:customer_change_index + 1] = [multi_axis_markdown, multi_axis_code]

overlap_markdown = new_markdown_cell('''### 7-2. 입출금·채널 중복성 점검

입출금금액은 요구불계좌의 입·출금 규모이고, 채널거래금액은 그 거래가 창구·인터넷·스마트·폰·ATM에서 처리된 규모입니다. 두 축은 의미가 완전히 같지는 않지만 동일 거래활동을 중복 집계할 수 있으므로 원값 상관과 50% 감소 플래그의 동시발생을 확인합니다.

채널거래금액은 y 판정축에서 제외하고, 이후 모델 feature와 약화 원인 설명에는 유지합니다.''')

overlap_code = new_code_cell('''# CHANNEL_FLOW_OVERLAP_V1
overlap_config = DormancyCandidateConfig(
    amount_axes=('입출금금액', '채널거래금액'),
    recent_months=3,
    reference_months=6,
    future_months=3,
    drop_threshold=0.5,
    min_axes_candidates=(2,),
)
overlap_panel = build_simple_dormancy_candidates(stable, overlap_config)
flow_decline = overlap_panel['50%이상감소_입출금금액'].astype(bool)
channel_decline = overlap_panel['50%이상감소_채널거래금액'].astype(bool)
overlap_valid = (
    overlap_panel['금액감소율_입출금금액'].notna()
    & overlap_panel['금액감소율_채널거래금액'].notna()
)
flow_decline_valid = flow_decline[overlap_valid]
channel_decline_valid = channel_decline[overlap_valid]
both_decline = flow_decline_valid & channel_decline_valid
either_decline = flow_decline_valid | channel_decline_valid

channel_flow_overlap = pd.DataFrame({
    '점검지표': [
        '원금액 Pearson 상관',
        '원금액 Spearman 상관',
        '채널금액≤입출금금액 비율',
        '입출금 50% 감소 비율',
        '채널 50% 감소 비율',
        '입출금 감소 중 채널도 감소 비율',
        '감소 플래그 Jaccard',
    ],
    '값': [
        stable['입출금금액'].corr(stable['채널거래금액'], method='pearson'),
        stable['입출금금액'].corr(stable['채널거래금액'], method='spearman'),
        stable['채널거래금액'].le(stable['입출금금액']).mean(),
        flow_decline_valid.mean(),
        channel_decline_valid.mean(),
        both_decline.sum() / flow_decline_valid.sum(),
        both_decline.sum() / either_decline.sum(),
    ],
})
display(channel_flow_overlap)

assert channel_flow_overlap.loc[channel_flow_overlap['점검지표'].eq('원금액 Spearman 상관'), '값'].notna().all()
assert overlap_valid.any()
''')

simple_y_markdown = new_markdown_cell('''### 7-3. 채널 제외 단순 금액감소 rolling y 후보

복잡한 점수나 가중합 없이 금액 감소만 사용합니다.

```text
축별 큰 감소 = 최근 3개월 평균이 바로 이전 6개월 평균의 50% 이하
y(t)=1 = 현재는 해당 상태가 아니지만, 향후 3개월 안에 큰 감소 축이 기준 개수 이상 발생
```

수신·여신·입출금·외환·카드·자동이체 6개 축을 각각 판정합니다. 채널거래금액은 입출금과의 중복을 피하기 위해 y에서 제외합니다. 이전 6개월 평균이 0인 축은 감소 판정에서 제외합니다.

- `Y_단순휴면_2축`: 넓은 후보
- `Y_단순휴면_3축`: 중간 후보
- `Y_단순휴면_4축`: 엄격한 후보

세 후보를 나란히 비교하며, 이 단계에서는 어느 하나를 최종 y로 확정하지 않습니다.''')

simple_y_code = new_code_cell('''# SIMPLE_DORMANCY_Y_CANDIDATES_V1
candidate_config = DormancyCandidateConfig(
    amount_axes=tuple(LABEL_AMOUNT_METRIC_COLS),
    recent_months=3,
    reference_months=6,
    future_months=3,
    drop_threshold=0.5,
    min_axes_candidates=(2, 3, 4),
)
candidate_panel = build_simple_dormancy_candidates(stable, candidate_config)

candidate_summary_rows = []
for min_axes in candidate_config.min_axes_candidates:
    eligible_col = f'학습가능_{min_axes}축'
    target_col = f'Y_단순휴면_{min_axes}축'
    eligible = candidate_panel[eligible_col]
    labels = candidate_panel.loc[eligible, target_col].astype(bool)
    candidate_summary_rows.append({
        'y 후보': f'향후3개월_{min_axes}축이상_50%감소',
        '학습가능 법인-월': int(eligible.sum()),
        'y=1 법인-월': int(labels.sum()),
        'y=1 비율': labels.mean(),
        'y=1 경험 법인 수': candidate_panel.loc[eligible & candidate_panel[target_col].fillna(False), ID_COL].nunique(),
    })

candidate_summary = pd.DataFrame(candidate_summary_rows)
display(candidate_summary)

monthly_candidate_rates = []
for min_axes in candidate_config.min_axes_candidates:
    eligible_col = f'학습가능_{min_axes}축'
    target_col = f'Y_단순휴면_{min_axes}축'
    monthly = (
        candidate_panel.loc[candidate_panel[eligible_col]]
        .groupby(MONTH_COL)[target_col]
        .mean()
        .rename(f'{min_axes}축 이상')
    )
    monthly_candidate_rates.append(monthly)

monthly_candidate_rate = pd.concat(monthly_candidate_rates, axis=1)
ax = monthly_candidate_rate.plot(figsize=(14, 5), marker='o')
ax.set_title('기준월별 단순 휴면 y 후보 발생률')
ax.set_ylabel('향후 3개월 y=1 비율')
ax.set_xlabel('기준년월')
plt.tight_layout()
plt.show()

main_min_axes = 3
main_target = 'Y_단순휴면_3축'
main_eligible = candidate_panel['학습가능_3축']
main_positive = main_eligible & candidate_panel[main_target].fillna(False)

future_reason_rate = pd.DataFrame({
    '금융축': LABEL_AMOUNT_METRIC_COLS,
    'y=1 중 미래3개월 감소 포함 비율': [
        candidate_panel.loc[main_positive, f'미래3개월감소_{axis}'].mean()
        for axis in LABEL_AMOUNT_METRIC_COLS
    ],
}).sort_values('y=1 중 미래3개월 감소 포함 비율', ascending=False)
display(future_reason_rate)

def candidate_group_rate(group_col, min_axes):
    target_col = f'Y_단순휴면_{min_axes}축'
    eligible_col = f'학습가능_{min_axes}축'
    overall_rate = candidate_panel.loc[candidate_panel[eligible_col], target_col].mean()
    grouped = (
        candidate_panel.loc[candidate_panel[eligible_col]]
        .groupby(group_col, dropna=False)
        .agg(
            법인월수=(target_col, 'size'),
            y_1_법인월=(target_col, 'sum'),
            y_1_비율=(target_col, 'mean'),
            법인수=(ID_COL, 'nunique'),
        )
        .query('법인월수 >= 100')
    )
    grouped['전체대비차이'] = grouped['y_1_비율'] - overall_rate
    grouped['후보'] = f'{min_axes}축 이상'
    grouped['구분'] = group_col
    return grouped

industry_candidate_rate = pd.concat(
    [candidate_group_rate('업종_대분류', min_axes) for min_axes in candidate_config.min_axes_candidates]
).sort_values(['후보', 'y_1_비율'], ascending=[True, False])
region_candidate_rate = pd.concat(
    [candidate_group_rate('사업장_시도', min_axes) for min_axes in candidate_config.min_axes_candidates]
).sort_values(['후보', 'y_1_비율'], ascending=[True, False])
display(industry_candidate_rate)
display(region_candidate_rate)

# CANDIDATE_STABILITY_V1
monthly_eligible_counts = pd.DataFrame({
    f'{min_axes}축 이상': candidate_panel.loc[candidate_panel[f'학습가능_{min_axes}축']].groupby(MONTH_COL).size()
    for min_axes in candidate_config.min_axes_candidates
})
monthly_stability_summary = pd.DataFrame({
    '월평균 발생률': monthly_candidate_rate.mean(),
    '월최소 발생률': monthly_candidate_rate.min(),
    '월최대 발생률': monthly_candidate_rate.max(),
    '월표준편차': monthly_candidate_rate.std(),
    '월변동계수': monthly_candidate_rate.std().divide(monthly_candidate_rate.mean().replace(0, np.nan)),
    '월최소 학습가능 법인월': monthly_eligible_counts.min(),
    '월최대 학습가능 법인월': monthly_eligible_counts.max(),
})
display(monthly_stability_summary)

segment_stability_summary = pd.concat([
    industry_candidate_rate.groupby(['후보', '구분'])['y_1_비율'].agg(['min', 'max', 'mean', 'std']).assign(세그먼트='업종'),
    region_candidate_rate.groupby(['후보', '구분'])['y_1_비율'].agg(['min', 'max', 'mean', 'std']).assign(세그먼트='지역'),
]).rename(columns={'min': '최소발생률', 'max': '최대발생률', 'mean': '평균발생률', 'std': '표준편차'})
display(segment_stability_summary)

assert monthly_candidate_rate.notna().any().all()
assert industry_candidate_rate['법인월수'].ge(100).all()
assert region_candidate_rate['법인월수'].ge(100).all()

# LABEL_DENOMINATOR_AND_REPEAT_AUDIT_V1
label_denominator_audit = (
    candidate_panel.loc[main_eligible]
    .groupby('판정가능축수', dropna=False)
    .agg(
        학습가능_법인월=(main_target, 'size'),
        y_1_법인월=(main_target, 'sum'),
        y_1_비율=(main_target, 'mean'),
        법인수=(ID_COL, 'nunique'),
    )
)
display(label_denominator_audit)

positive_counts_by_customer = candidate_panel.loc[main_positive].groupby(ID_COL).size()
repeat_positive_summary = pd.DataFrame({
    '지표': [
        'y=1 경험 법인 수',
        'y=1 법인-월 수',
        '법인별 y=1 중앙값',
        '법인별 y=1 90% 분위수',
        '법인별 y=1 최대값',
        '2회 이상 반복 양성 법인 비율',
    ],
    '값': [
        positive_counts_by_customer.size,
        positive_counts_by_customer.sum(),
        positive_counts_by_customer.median(),
        positive_counts_by_customer.quantile(0.9),
        positive_counts_by_customer.max(),
        positive_counts_by_customer.ge(2).mean(),
    ],
})
repeat_positive_distribution = positive_counts_by_customer.value_counts().sort_index().rename_axis('법인별 y=1 횟수').to_frame('법인 수')
display(repeat_positive_summary)
display(repeat_positive_distribution)

assert label_denominator_audit['학습가능_법인월'].sum() == int(main_eligible.sum())
assert positive_counts_by_customer.sum() == int(main_positive.sum())
''')

multi_axis_code_index = find_cell("# MULTI_AXIS_WEAKENING_EXPLORATION_V1")
nb.cells[multi_axis_code_index + 1:multi_axis_code_index + 1] = [
    overlap_markdown,
    overlap_code,
    simple_y_markdown,
    simple_y_code,
]

takeaway_markdown_index = find_cell("## Takeaways")
nb.cells[takeaway_markdown_index].source = '''## Takeaways

아래 자동 요약은 이번 실행 데이터의 수치를 바탕으로 작성됩니다. 새 y는 아직 확정되지 않았으며, 다축 약화 민감도 표는 후보 조건의 규모와 안정성을 비교하기 위한 탐색 결과입니다.'''

takeaway_code_index = find_cell("top_industry =")
nb.cells[takeaway_code_index].source = '''top_industry = industry_composition.index[0]
top_region = region_composition.index[0]
channel_change = trend_summary.loc[trend_summary['지표'].eq('채널거래금액'), '합계 변화율'].iloc[0]
deposit_change = trend_summary.loc[trend_summary['지표'].eq('수신잔액합계'), '합계 변화율'].iloc[0]
candidate_3axis = candidate_summary.loc[candidate_summary['y 후보'].eq('향후3개월_3축이상_50%감소')].iloc[0]
candidate_3axis_monthly = monthly_stability_summary.loc['3축 이상']
repeat_positive_rate = repeat_positive_summary.loc[repeat_positive_summary['지표'].eq('2회 이상 반복 양성 법인 비율'), '값'].iloc[0]

display(Markdown(f\'''### 실행 결과 요약

- 완전관측 코호트는 **{len(stable_ids):,}개 법인**이며, 전체 법인의 **{len(stable_ids) / df[ID_COL].nunique():.1%}**입니다.
- 법인 수 기준 최대 업종은 **{top_industry}**, 최대 지역은 **{top_region}**입니다.
- 초기 6개월 평균 대비 마지막 달의 수신잔액합계 변화율은 **{deposit_change:+.1%}**, 채널거래금액 변화율은 **{channel_change:+.1%}**입니다.
- 초기 6개월 평균 대비 지수는 축별 추세 비교용이며 종합 금융활동 점수가 아닙니다.
- 전체 합계, 고객별 중앙값, 상위 1% 영향 완화 결과가 다르면 대형 법인 또는 기준구간의 영향을 먼저 확인해야 합니다.
- 채널을 제외한 단순 3축 후보는 학습가능 법인-월 중 **{candidate_3axis['y=1 비율']:.1%}**이며, **{int(candidate_3axis['y=1 경험 법인 수']):,}개 법인**이 한 번 이상 y=1을 경험합니다.
- 3축 후보의 월별 발생률은 **{candidate_3axis_monthly['월최소 발생률']:.1%}~{candidate_3axis_monthly['월최대 발생률']:.1%}** 범위입니다.
- y=1 경험 법인 중 **{repeat_positive_rate:.1%}**는 두 개 이상의 기준월에서 반복 양성입니다. 모델 분할과 평가에서 법인-월 행의 독립성을 가정하지 않습니다.

### 다음 분석 연결

- 다축 약화 민감도 표에서 표본 규모와 집단별 안정성을 비교합니다.
- 업종·지역의 전체 대비 발생률 차이와 월별 변동을 확인했습니다. 판정가능축수별 발생률 차이와 반복 양성이 커서, 등급·전담여부·계절성 및 사건 단위 평가를 최종 y 승인 전에 추가합니다.
- 2축은 넓은 후보, 3축은 중간 후보, 4축은 엄격한 후보로 비교하며 현재 결과만으로 최종 y를 확정하지 않습니다.\'''))'''

nbformat.validate(nb)
nbformat.write(nb, NOTEBOOK_PATH)
print(f"updated: {NOTEBOOK_PATH} ({len(nb.cells)} cells)")
