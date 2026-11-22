import { useState } from "react";
import type { GameId } from "../api/types";
import { gameName } from "../lib/format";
import { EMPTY, useAppStore } from "../store/useAppStore";
import { AdaptiveWorkspace } from "./AdaptiveWorkspace";
import { Chat } from "./Chat";

export function StandaloneWorkspace() {
  const session = useAppStore((s) => s.session)!;
  const switchGame = useAppStore((s) => s.switchGame);
  const experimenterMode = useAppStore((s) => s.experimenterMode);
  const setExperimenterMode = useAppStore((s) => s.setExperimenterMode);
  const setHistoryOpen = useAppStore((s) => s.setHistoryOpen);
  const proposals = useAppStore((s) => s.proposals[session.selectedGame] ?? EMPTY);
  const [showChat, setShowChat] = useState(true);

  const game = session.selectedGame;
  const pendingCount = proposals
    .filter((p) => p.status === "pending")
    .reduce((n, p) => n + p.items.filter((i) => i.status === "pending").length, 0);

  if (session.condition !== "adaptive") {
    return (
      <div className="standalone-shell">
        <header className="studybar">
          <strong>Adaptive Workspace</strong>
          <span className="sb-sim-pill" role="note">
            Simulated settings — no real changes to VALORANT or CS2
          </span>
        </header>
        <div className="standalone-empty">
          <p>The Adaptive Workspace is only active in the adaptive study condition.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="standalone-shell" data-game={game}>
      <header className="studybar standalone-bar">
        <div className="sb-brand">
          <span className="sb-logo" aria-hidden>◆</span>
          <span className="sb-titles">
            <strong>Adaptive Workspace</strong>
            <small>{pendingCount ? `${pendingCount} change(s) pending` : "Standalone window"}</small>
          </span>
        </div>

        <span className="sb-sim-pill" role="note">
          Simulated settings — no real changes to VALORANT or CS2
        </span>

        <div className="sb-seg" role="group" aria-label="Game">
          {(["valorant", "cs2"] as GameId[]).map((g) => (
            <button key={g} type="button" aria-pressed={g === game} className={g === game ? "is-on" : ""} onClick={() => g !== game && void switchGame(g)}>
              {gameName(g)}
            </button>
          ))}
        </div>

        <button type="button" className="sb-btn" onClick={() => setHistoryOpen(true)}>
          History
        </button>

        <button type="button" className={`sb-btn ${showChat ? "is-accent" : ""}`} aria-pressed={showChat} onClick={() => setShowChat((v) => !v)}>
          {showChat ? "Hide chat" : "Show chat"}
        </button>

        <button type="button" className="sb-btn sb-btn-subtle" aria-pressed={experimenterMode} onClick={() => setExperimenterMode(!experimenterMode)}>
          {experimenterMode ? "Experimenter ✓" : "Experimenter"}
        </button>
      </header>

      <div className="standalone-grid">
        <div className="standalone-workspace-pane">
          <AdaptiveWorkspace game={game} mode="standalone" />
        </div>
        {showChat ? (
          <aside className="standalone-chat-pane" aria-label="Assistant chat (standalone)">
            <Chat game={game} />
          </aside>
        ) : null}
      </div>
    </div>
  );
}
