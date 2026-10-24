import { Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { CaseDetailPage } from "./pages/CaseDetail";
import { CasesPage } from "./pages/Cases";
import { DashboardPage } from "./pages/Dashboard";
import { NotFoundPage } from "./pages/NotFound";
import { RegressionsPage } from "./pages/Regressions";
import { ReportPage } from "./pages/Report";
import { RunDetailPage } from "./pages/RunDetail";
import { RunsPage } from "./pages/Runs";
import { SafetyPage } from "./pages/Safety";

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<DashboardPage />} />
        <Route path="runs" element={<RunsPage />} />
        <Route path="runs/:runId" element={<RunDetailPage />} />
        <Route path="runs/:runId/cases/:caseId" element={<CaseDetailPage />} />
        <Route path="runs/:runId/report" element={<ReportPage />} />
        <Route path="cases" element={<CasesPage />} />
        <Route path="safety" element={<SafetyPage />} />
        <Route path="regressions" element={<RegressionsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
