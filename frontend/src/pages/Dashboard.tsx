import { useState, useMemo, useEffect, useRef } from "react";
import { RaceControls } from "@/components/RaceControls";
import { RaceResultsTable } from "@/components/RaceResultsTable";
import { KeyTakeaways } from "@/components/KeyTakeaways";
import { PaceDeltaChartCard } from "@/components/charts/PaceDeltaChartCard";
import { DriverFilterPanel } from "@/components/race/DriverFilterPanel";
import { StintSummaryTable } from "@/components/StintSummaryTable";
import { RawLapAccordion } from "@/components/RawLapAccordion";
import { useRaceAnalyzer } from "@/hooks/useRaceAnalyzer";
import { useRaceResults, type RaceResultsView } from "@/hooks/useRaceResults";
import { DRIVER_COLORS } from "@/components/charts/PaceDeltaChart";
import { cn } from "@/lib/utils";

type SectionId =
  | "home"
  | "race-overview"
  | "race-analyzer"
  | "full-season"
  | "driver-profile"
  | "constructor"
  | "how-it-works";

export default function Dashboard() {
  const [activeSection, setActiveSection] = useState<SectionId>("home");
  const [season, setSeason] = useState(2025);
  const [round, setRound] = useState(1);
  const [searchSeason, setSearchSeason] = useState(2025);
  const [searchRound, setSearchRound] = useState(1);
  const [overviewView, setOverviewView] = useState<RaceResultsView>("finish");

  const { data: raceResults, loading: loadingRace, error: errorRace } =
    useRaceResults({ season: searchSeason, round: searchRound, view: overviewView });
  const { data: analyzerData, loading: loadingAnalyzer, error: errorAnalyzer } =
    useRaceAnalyzer({ season: searchSeason, round: searchRound });

  const raceAnalyzerDrivers = useMemo(
    () =>
      analyzerData?.computed?.laps_with_delta?.length
        ? ([...new Set(
            analyzerData.computed.laps_with_delta
              .map((l) => l.driver)
              .filter(Boolean)
          )] as string[])
        : [],
    [analyzerData?.computed?.laps_with_delta]
  );

  const [selectedDrivers, setSelectedDrivers] = useState<Set<string>>(new Set());
  const driversKeyRef = useRef<string>("");
  useEffect(() => {
    if (raceAnalyzerDrivers.length === 0) return;
    const key = raceAnalyzerDrivers.slice().sort().join(",");
    if (driversKeyRef.current === key) return;
    driversKeyRef.current = key;
    setSelectedDrivers(new Set());
  }, [raceAnalyzerDrivers]);

  const driverColors = useMemo(() => {
    const out: Record<string, string> = {};
    raceAnalyzerDrivers.forEach((d, i) => {
      out[d] = DRIVER_COLORS[i % DRIVER_COLORS.length];
    });
    return out;
  }, [raceAnalyzerDrivers]);

  const handleSearch = () => {
    setSearchSeason(season);
    setSearchRound(round);
  };

  const navLinks: { id: SectionId; label: string }[] = [
    { id: "home", label: "Home" },
    { id: "race-overview", label: "Race Overview" },
    { id: "race-analyzer", label: "Race Analyzer" },
    { id: "full-season", label: "Full Season" },
    { id: "driver-profile", label: "Driver Profile" },
    { id: "constructor", label: "Constructor" },
    { id: "how-it-works", label: "How it Works" },
  ];

  return (
    <div className="relative min-h-screen text-[var(--color-text-muted)]">
      <div className="page-bg" aria-hidden="true">
        <div className="glow-blob glow-blob-1" />
        <div className="noise" />
      </div>
      <div className="relative mx-auto max-w-[1300px] px-4 py-4 sm:px-6 md:px-8">
        <nav className="sticky top-3 z-10 flex flex-wrap items-center justify-center gap-4 rounded-2xl border border-[var(--border)] bg-[var(--panel)]/80 py-4 px-5 backdrop-blur-[14px] sm:px-6 transition-[box-shadow,border-color] focus-within:ring-2 focus-within:ring-[var(--accent1)]/30 sm:gap-6">
          <div className="text-xl font-bold tracking-wide text-[var(--color-text-default)]">
            F1 Insights
          </div>
          <ul className="flex flex-wrap items-center justify-center gap-1 sm:gap-2">
            {navLinks.map(({ id, label }) => (
              <li key={id}>
                <a
                  href={`#${id}`}
                  className={cn(
                    "rounded-xl px-3.5 py-2 text-sm font-medium transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-[var(--accent1)]/40 focus:ring-offset-2 focus:ring-offset-[var(--bg)]",
                    activeSection === id
                      ? "bg-white/10 text-[var(--color-text-default)] shadow-sm"
                      : "text-[var(--color-text-muted)] hover:bg-white/5 hover:text-[var(--color-text-default)]"
                  )}
                  onClick={(e) => {
                    e.preventDefault();
                    setActiveSection(id);
                    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
                  }}
                >
                  {label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <section
          id="home"
          className={cn("pt-12 pb-16 md:pt-16 md:pb-20 lg:pt-20 lg:pb-24", activeSection !== "home" && "hidden")}
        >
          <div className="text-center">
            <div className="mb-6 inline-block rounded-2xl bg-[var(--color-quaternary)]/15 px-5 py-2.5 text-xs font-semibold uppercase tracking-wider text-[var(--color-quaternary)]">
              The smartest way to analyze Formula One.
            </div>
            <h1 className="font-serif text-3xl font-bold text-[var(--color-text-default)] sm:text-4xl md:text-5xl">
              All of Formula One, One analytics platform.
            </h1>
            <p className="mx-auto mt-5 max-w-xl text-lg text-[var(--color-text-muted)]">
              Gain invaluable predictive analytics and actionable insights
              empowering you to understand race performance, driver stats, and
              constructor standings.
            </p>
          </div>
          <div className="mx-auto mt-16 md:mt-20 max-w-4xl rounded-[20px] glass-panel px-6 py-12 sm:px-8 md:px-10 md:py-14">
            <div className="mb-10 text-center">
              <div className="mb-2 text-sm font-semibold uppercase tracking-wider text-[var(--color-secondary)]">
                Get proper data & race statistics
              </div>
              <h2 className="font-serif text-2xl font-bold text-[var(--color-text-default)]">
                Elements To Get You Started
              </h2>
              <p className="mt-2 text-[var(--color-text-muted)]">
                Gain invaluable predictive analytics and actionable insights,
                empowering you to make data-driven decisions about F1
                performance.
              </p>
            </div>
            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {[
                { nav: "race-overview", title: "Race Overview", desc: "View complete race results with finish positions, grid starts, fastest laps, and status for any Grand Prix." },
                { nav: "race-analyzer", title: "Race Analyzer", desc: "Dive into our performance score to see how drivers performed beyond their finishing position." },
                { nav: "full-season", title: "Full Season", desc: "Track championship standings and points across the entire season for drivers and constructors." },
                { nav: "driver-profile", title: "Driver Profile", desc: "Get detailed driver statistics, career highlights, and head-to-head comparisons." },
                { nav: "constructor", title: "Constructor", desc: "Analyze team performance, constructor standings, and reliability metrics." },
                { nav: "how-it-works", title: "How It Works", desc: "Learn how our performance score is calculated and what insights it reveals about race day." },
              ].map(({ nav, title, desc }) => (
                <button
                  key={nav}
                  type="button"
                  className="rounded-2xl border border-[var(--border)] glass-panel p-6 text-center transition-all duration-200 hover:-translate-y-0.5 hover:border-white/20 hover:shadow-[0_8px_32px_rgba(0,0,0,0.25),0_0_24px_rgba(99,102,241,0.12)] focus:outline-none focus:ring-2 focus:ring-[var(--accent1)]/40 focus:ring-offset-2 focus:ring-offset-[var(--bg)]"
                  onClick={() => {
                    setActiveSection(nav as SectionId);
                    document.getElementById(nav)?.scrollIntoView({ behavior: "smooth", block: "start" });
                  }}
                >
                  <h3 className="font-semibold text-[var(--color-text-default)]">
                    {title}
                  </h3>
                  <p className="mt-2 text-sm text-[var(--color-text-muted)]">
                    {desc}
                  </p>
                </button>
              ))}
            </div>
          </div>
        </section>

        <section
          id="race-overview"
          className={cn("pt-16 pb-20 md:pt-20 md:pb-24", activeSection !== "race-overview" && "hidden")}
        >
          <div className="mx-auto max-w-4xl">
            <h2 className="mb-8 text-center text-xl font-semibold text-[var(--color-text-default)] md:text-2xl">
              Race Overview
            </h2>
            <div className="mb-8 flex justify-center">
              <RaceControls
                season={season}
                round={round}
                onSeasonChange={setSeason}
                onRoundChange={setRound}
                onSearch={handleSearch}
                showViewToggle
                view={overviewView}
                onViewChange={setOverviewView}
                layout="stacked"
              />
            </div>
            <div className="min-h-[200px]">
              {loadingRace && (
                <div className="rounded-2xl glass-panel py-12 text-center text-[var(--color-text-muted)]">
                  Loading race data…
                </div>
              )}
              {errorRace && (
                <div className="rounded-2xl border-l-4 border-[var(--color-tertiary)] glass-panel px-5 py-4 text-center text-[var(--color-tertiary)]">
                  {errorRace}
                </div>
              )}
              {!loadingRace && !errorRace && !raceResults && (
                <div className="rounded-2xl glass-panel py-12 text-center text-[var(--color-text-muted)]">
                  Enter season and race to view results.
                </div>
              )}
              {!loadingRace && !errorRace && raceResults?.race_info && raceResults.results && (
                <RaceResultsTable
                  raceInfo={raceResults.race_info}
                  results={raceResults.results}
                  view={overviewView}
                />
              )}
            </div>
          </div>
        </section>

        <section
          id="race-analyzer"
          className={cn("pt-16 pb-20 md:pt-20 md:pb-24", activeSection !== "race-analyzer" && "hidden")}
        >
          <div className="mx-auto max-w-4xl">
            <h2 className="mb-8 text-center text-xl font-semibold text-[var(--color-text-default)] md:text-2xl">
              Race Analyzer
            </h2>
            <div className="mb-8 flex justify-center">
              <RaceControls
                season={season}
                round={round}
                onSeasonChange={setSeason}
                onRoundChange={setRound}
                onSearch={handleSearch}
              />
            </div>
            <div className="min-h-[200px] space-y-6">
              {loadingAnalyzer && (
                <div className="rounded-2xl glass-panel py-12 text-center text-[var(--color-text-muted)]">
                  Loading race analyzer…
                </div>
              )}
              {errorAnalyzer && (
                <div className="rounded-2xl border-l-4 border-[var(--color-tertiary)] glass-panel px-5 py-4 text-center text-[var(--color-tertiary)]">
                  {errorAnalyzer}
                </div>
              )}
              {analyzerData?.supported === false && (
                <div className="rounded-2xl border border-[var(--color-quaternary)]/50 glass-panel py-4 text-center text-amber-200">
                  {analyzerData.message ?? "Race analyzer not supported for this race."}
                </div>
              )}
              {!loadingAnalyzer &&
                !errorAnalyzer &&
                analyzerData?.race_meta &&
                analyzerData?.computed && (
                  <>
                    <div className="rounded-2xl glass-panel p-6 text-center">
                      <h2 className="text-[var(--color-text-default)] text-xl font-semibold">
                        {analyzerData.race_meta.name ?? "–"}
                      </h2>
                      <p className="mt-1 text-sm text-[var(--color-text-muted)]">
                        {analyzerData.race_meta.season} Season – Round{" "}
                        {analyzerData.race_meta.round} · Race Analyzer (FastF1)
                      </p>
                    </div>
                    <KeyTakeaways
                      insights={analyzerData.computed.insights ?? []}
                    />
                    {analyzerData.computed.laps_with_delta &&
                      analyzerData.computed.laps_with_delta.length > 0 && (
                        <>
                          <div className="rounded-2xl glass-panel p-4 sm:p-5">
                            <DriverFilterPanel
                              drivers={raceAnalyzerDrivers}
                              selected={selectedDrivers}
                              onChange={setSelectedDrivers}
                              driverColors={driverColors}
                            />
                          </div>
                          <PaceDeltaChartCard
                            lapsWithDelta={analyzerData.computed.laps_with_delta}
                            stintRanges={analyzerData.computed.stint_ranges ?? []}
                            title="Pace delta vs race-median (clean laps)"
                            height={360}
                            selectedDrivers={[...selectedDrivers]}
                            onSelectedDriversChange={(next) => setSelectedDrivers(next)}
                          />
                        </>
                      )}
                    {analyzerData.computed.stint_summary &&
                      analyzerData.computed.stint_summary.length > 0 && (
                      <StintSummaryTable
                        data={analyzerData.computed.stint_summary}
                      />
                    )}
                    {analyzerData.laps && analyzerData.laps.length > 0 && (
                      <RawLapAccordion laps={analyzerData.laps} />
                    )}
                  </>
                )}
              {!loadingAnalyzer &&
                !errorAnalyzer &&
                analyzerData?.race_meta &&
                (!analyzerData.computed?.laps_with_delta?.length) &&
                analyzerData.supported !== false && (
                <div className="rounded-2xl glass-panel py-12 text-center text-[var(--color-text-muted)]">
                  No lap delta data for this race. Try another race or ensure
                  FastF1 data is available.
                </div>
              )}
              {!loadingAnalyzer &&
                !errorAnalyzer &&
                !analyzerData?.race_meta &&
                analyzerData?.supported !== false && (
                <div className="rounded-2xl glass-panel py-12 text-center text-[var(--color-text-muted)]">
                  Enter season and race, then view Race Analyzer to see insights
                  and lap analysis.
                </div>
              )}
            </div>
          </div>
        </section>

        <section
          id="full-season"
          className={cn("pt-16 pb-20 md:pt-20 md:pb-24", activeSection !== "full-season" && "hidden")}
        >
          <div className="mx-auto max-w-4xl text-center">
            <h2 className="mb-8 text-xl font-semibold text-[var(--color-text-default)] md:text-2xl">
              Full Season Overview
            </h2>
            <p className="py-20 text-[var(--color-text-muted)]">
              Content coming soon.
            </p>
          </div>
        </section>

        <section
          id="driver-profile"
          className={cn("pt-16 pb-20 md:pt-20 md:pb-24", activeSection !== "driver-profile" && "hidden")}
        >
          <div className="mx-auto max-w-4xl text-center">
            <h2 className="mb-8 text-xl font-semibold text-[var(--color-text-default)] md:text-2xl">
              Driver Profile
            </h2>
            <p className="py-20 text-[var(--color-text-muted)]">
              Content coming soon.
            </p>
          </div>
        </section>

        <section
          id="constructor"
          className={cn("pt-16 pb-20 md:pt-20 md:pb-24", activeSection !== "constructor" && "hidden")}
        >
          <div className="mx-auto max-w-4xl text-center">
            <h2 className="mb-8 text-xl font-semibold text-[var(--color-text-default)] md:text-2xl">
              Constructor
            </h2>
            <p className="py-20 text-[var(--color-text-muted)]">
              Content coming soon.
            </p>
          </div>
        </section>

        <section
          id="how-it-works"
          className={cn("pt-16 pb-20 md:pt-20 md:pb-24", activeSection !== "how-it-works" && "hidden")}
        >
          <div className="mx-auto max-w-4xl text-center">
            <h2 className="mb-8 text-xl font-semibold text-[var(--color-text-default)] md:text-2xl">
              How It Works
            </h2>
            <p className="py-20 text-[var(--color-text-muted)]">
              Content coming soon.
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
