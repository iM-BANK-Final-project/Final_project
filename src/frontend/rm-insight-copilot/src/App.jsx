import { useEffect, useState } from "react";
import LoginPage from "./components/LoginPage.jsx";
import SplashScreen from "./components/SplashScreen.jsx";
import TopNav from "./components/TopNav.jsx";
import AiReportPage from "./pages/AiReportPage.jsx";
import DormancyRiskPage from "./pages/DormancyRiskPage.jsx";
import OverviewPage from "./pages/OverviewPage.jsx";
import PriorityPage from "./pages/PriorityPage.jsx";
import RecommendationsPage from "./pages/RecommendationsPage.jsx";

const pages = {
  overview: OverviewPage,
  risk: DormancyRiskPage,
  priority: PriorityPage,
  recommendations: RecommendationsPage,
  report: AiReportPage
};

export const DEMO_SESSION_KEY = "rm-copilot-demo-authenticated";

const DEMO_USERNAME = "test";
const DEMO_PASSWORD = "1234";

function hasAuthenticatedSession() {
  try {
    return window.sessionStorage.getItem(DEMO_SESSION_KEY) === "true";
  } catch {
    return false;
  }
}

export default function App() {
  const [activePage, setActivePage] = useState("overview");
  const [selectedCustomerId, setSelectedCustomerId] = useState(null);
  const [entryPhase, setEntryPhase] = useState(() =>
    hasAuthenticatedSession() ? "service" : "login"
  );
  const ActivePage = pages[activePage];

  const openRecommendation = (corporateId) => {
    setSelectedCustomerId(corporateId);
    setActivePage("recommendations");
  };

  useEffect(() => {
    if (entryPhase !== "splash") return undefined;

    const timer = window.setTimeout(() => setEntryPhase("service"), 2700);
    return () => window.clearTimeout(timer);
  }, [entryPhase]);

  const handleLogin = (username, password) => {
    if (username !== DEMO_USERNAME || password !== DEMO_PASSWORD) {
      return false;
    }

    try {
      window.sessionStorage.setItem(DEMO_SESSION_KEY, "true");
    } catch {
      // Storage may be unavailable in restricted browser modes; the current
      // in-memory demo session can still continue.
    }

    setEntryPhase("splash");
    return true;
  };

  if (entryPhase === "login") {
    return <LoginPage onLogin={handleLogin} />;
  }

  if (entryPhase === "splash") {
    return <SplashScreen />;
  }

  const pageProps = {
    overview: { onPageChange: setActivePage },
    priority: { onRecommendationOpen: openRecommendation },
    recommendations: { selectedCustomerId },
    report: { selectedCustomerId }
  }[activePage] ?? {};

  return (
    <div className="app-shell">
      <TopNav activePage={activePage} onPageChange={setActivePage} />
      <ActivePage {...pageProps} />
    </div>
  );
}
