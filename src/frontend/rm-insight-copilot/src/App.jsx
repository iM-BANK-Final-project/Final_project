import { useEffect, useState } from "react";
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

export default function App() {
  const [activePage, setActivePage] = useState("overview");
  const [showSplash, setShowSplash] = useState(true);
  const ActivePage = pages[activePage];

  useEffect(() => {
    const timer = window.setTimeout(() => setShowSplash(false), 2700);
    return () => window.clearTimeout(timer);
  }, []);

  if (showSplash) {
    return <SplashScreen />;
  }

  return (
    <div className="app-shell">
      <TopNav activePage={activePage} onPageChange={setActivePage} />
      <ActivePage onPageChange={setActivePage} />
    </div>
  );
}
