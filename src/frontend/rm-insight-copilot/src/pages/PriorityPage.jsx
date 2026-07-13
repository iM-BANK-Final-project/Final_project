import SectionHeader from "../components/SectionHeader.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { customers } from "../data/mockData.js";

export default function PriorityPage() {
  const sortedCustomers = [...customers].sort((a, b) => b.expectedLoss - a.expectedLoss);

  return (
    <main className="page">
      <SectionHeader
        eyebrow="CRM Priority"
        title="기대손실 기반 CRM 우선순위"
        description="금융관계 약화 위험과 고객가치 대리지표를 결합해 먼저 볼 고객을 정렬합니다. 현재 수치는 예시 데이터입니다."
      />
      <div className="filter-bar">
        <select defaultValue="교육 및 서비스">
          <option>교육 및 서비스</option>
          <option>제조</option>
          <option>도소매</option>
        </select>
        <select defaultValue="대구">
          <option>대구</option>
          <option>서울</option>
          <option>경기</option>
        </select>
        <select defaultValue="Y">
          <option>Y</option>
          <option>N</option>
        </select>
        <select defaultValue="상품관계폭 축소">
          <option>상품관계폭 축소</option>
          <option>외환거래 감소</option>
          <option>예금잔액 약화</option>
        </select>
      </div>
      <div className="table-panel">
        <table>
          <thead>
            <tr>
              <th>순위</th>
              <th>법인ID</th>
              <th>기업명</th>
              <th>업종</th>
              <th>지역</th>
              <th>전담</th>
              <th>휴면위험</th>
              <th>고객가치</th>
              <th>기대손실</th>
              <th>주요 약화 유형</th>
              <th>액션</th>
            </tr>
          </thead>
          <tbody>
            {sortedCustomers.map((customer, index) => (
              <tr key={customer.id}>
                <td>{index + 1}</td>
                <td>{customer.id}</td>
                <td><strong>{customer.name}</strong></td>
                <td>{customer.industry}</td>
                <td>{customer.region}</td>
                <td>{customer.dedicated}</td>
                <td>{customer.risk}%</td>
                <td>{customer.valueProxy}</td>
                <td>{customer.expectedLoss.toLocaleString()}백만원</td>
                <td><StatusBadge tone="mint">{customer.weakeningType}</StatusBadge></td>
                <td><button className="mini-button">추천 보기</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
