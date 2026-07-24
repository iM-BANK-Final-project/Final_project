import { BarChart3, FileText, Lightbulb, ListChecks } from "lucide-react";

const navItems = [
  { id: "risk", label: "지속거래약화 예측", icon: BarChart3 },
  { id: "priority", label: "CRM 우선순위", icon: ListChecks },
  { id: "recommendations", label: "맞춤 추천", icon: Lightbulb },
  { id: "report", label: "AI 리포트", icon: FileText }
];

export default function TopNav({ activePage, onPageChange }) {
  return (
    <header className="top-nav">
      <button className="brand" onClick={() => onPageChange("overview")} aria-label="Overview">
        <span className="brand-mark">
          <img src="/brand-assets/im-bank-logo.png" alt="iM Bank" />
        </span>
        <span>
          <strong>RM 인사이트 코파일럿</strong>
          <small>Corporate Banking</small>
        </span>
      </button>
      <nav className="nav-menu" aria-label="Primary navigation">
        {navItems.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className={activePage === id ? "nav-item active" : "nav-item"}
            onClick={() => onPageChange(id)}
          >
            <Icon size={17} />
            {label}
          </button>
        ))}
      </nav>
    </header>
  );
}
