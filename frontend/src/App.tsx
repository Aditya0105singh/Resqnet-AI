import { lazy, Suspense, useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useSim } from "./store/sim";
import { useSimSocket } from "./hooks/useSimSocket";
import { Footer, Toasts, TopBar } from "./components/Shell";
import { DecisionInspector } from "./components/DecisionInspector";
import { CommanderDrawer } from "./components/Commander";
import { Empty, Spinner } from "./components/ui";
import Command from "./pages/Command";

const Dispatch = lazy(() => import("./pages/Dispatch"));
const Home = lazy(() => import("./pages/Home"));
const Judge = lazy(() => import("./pages/Judge"));
const Agents = lazy(() => import("./pages/Agents"));
const Scenarios = lazy(() => import("./pages/Scenarios"));
const DecisionLab = lazy(() => import("./pages/DecisionLab"));
const Arena = lazy(() => import("./pages/Arena"));
const Replay = lazy(() => import("./pages/Replay"));
const Safety = lazy(() => import("./pages/Safety"));
const Reports = lazy(() => import("./pages/Reports"));
const Sos = lazy(() => import("./pages/Sos"));
const Crew = lazy(() => import("./pages/Crew"));
const Demo = lazy(() => import("./pages/Demo"));
const Research = lazy(() => import("./pages/Research"));

export default function App() {
  const bootstrap = useSim((s) => s.bootstrap);
  const sim = useSim((s) => s.sim);
  const conn = useSim((s) => s.conn);
  useEffect(() => {
    bootstrap();
  }, [bootstrap]);
  useSimSocket(sim?.id);
  const { pathname } = useLocation();
  useEffect(() => window.scrollTo(0, 0), [pathname]);
  const wide = pathname !== "/";

  return (
    <div className="fog min-h-full">
      <TopBar />
      <CommanderDrawer />
      <main className={wide ? "mx-auto max-w-[1680px] overflow-x-hidden" : "overflow-x-hidden"}>
        {conn === "offline" && !sim && pathname !== "/" ? (
          <Empty title="Backend unreachable" body="Start the API with scripts/start-backend (port 8000), then reload this page." />
        ) : (
          <Suspense fallback={<Spinner label="Loading…" />}>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/command" element={<Command />} />
              <Route path="/demo" element={<Demo />} />
              <Route path="/judge" element={<Judge />} />
              <Route path="/research" element={<Research />} />
              <Route path="/chaos" element={<Scenarios />} />
              <Route path="/audit" element={<Replay />} />
              <Route path="/dispatch" element={<Dispatch />} />
              <Route path="/agents" element={<Agents />} />
              <Route path="/scenarios" element={<Navigate to="/chaos" replace />} />
              <Route path="/decision-lab" element={<DecisionLab />} />
              <Route path="/arena" element={<Arena />} />
              <Route path="/replay" element={<Navigate to="/audit" replace />} />
              <Route path="/safety" element={<Safety />} />
              <Route path="/reports" element={<Reports />} />
              <Route path="/sos" element={<Sos />} />
              <Route path="/crew" element={<Crew />} />
              <Route path="/crew/:unitId" element={<Crew />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        )}
      </main>
      {pathname !== "/command" && !pathname.startsWith("/crew") && <Footer />}
      <DecisionInspector />
      <Toasts />
    </div>
  );
}
