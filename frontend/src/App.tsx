import { useEffect } from "react";
import type { GameId } from "./api/types";
import { AssistantPanel } from "./adaptive/AssistantPanel";
import { ReviewTray } from "./adaptive/ReviewTray";
import { HistoryDrawer, Toasts } from "./components/chrome/HistoryDrawer";
import { StudyBar } from "./components/chrome/StudyBar";
import { useGameView } from "./components/settings/useGameView";
import { Cs2Menu } from "./games/cs2/Cs2Menu";
import { ValorantMenu } from "./games/valorant/ValorantMenu";
import { useAppStore } from "./store/useAppStore";

function GameSurface({ game }: { game: GameId }) {
  const view = useGameView(game);
  if (!view.catalog || !view.state) return <div className="game-surface loading">Loading settings…</div>;
  return (
    <section className={`game-surface surface-${game}`} aria-label={`${view.catalog.displayName} settings (simulated)`}>
      {game === "valorant" ? (
        <ValorantMenu view={view} />
      ) : (
        <Cs2Menu view={view} onOpenSearch={() => document.getElementById("global-search")?.focus()} />
      )}
      <div className="surface-watermark" aria-hidden>
        Unofficial academic simulation · {view.catalog.shortName} catalogue {view.catalog.catalogVersion}
      </div>
    </section>
  );
}

export function App() {
  const ready = useAppStore((s) => s.ready);
  const fatal = useAppStore((s) => s.fatal);
  const session = useAppStore((s) => s.session);
  const init = useAppStore((s) => s.init);

  useEffect(() => {
    void init();
  }, [init]);

  if (fatal) {
    return (
      <div className="fatal" role="alert">
        <h1>Cannot start the prototype</h1>
        <p>{fatal}</p>
        <p>Start the backend first (see README: <code>python scripts/dev.py</code>), then reload this page.</p>
      </div>
    );
  }
  if (!ready || !session) return <div className="boot">Loading the simulated settings…</div>;

  const game = session.selectedGame;
  const adaptive = session.condition === "adaptive";
  return (
    <div className={`app game-${game} ${adaptive ? "cond-adaptive" : "cond-baseline"}`} data-condition={session.condition} data-game={game}>
      <StudyBar />
      <main className="workspace">
        <GameSurface game={game} />
        {adaptive ? <AssistantPanel game={game} /> : null}
      </main>
      {adaptive ? <ReviewTray game={game} /> : null}
      <HistoryDrawer />
      <Toasts />
    </div>
  );
}
