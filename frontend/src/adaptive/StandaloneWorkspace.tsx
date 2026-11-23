import { useEffect, useState } from "react";
import type { GameId } from "../api/types";
import { ExperimenterDrawer } from "../components/chrome/ExperimenterDrawer";
import { ModelStatusPill } from "../components/chrome/StudyBar";
import { gameName } from "../lib/format";
import { EMPTY, useAppStore } from "../store/useAppStore";
import { AdaptiveWorkspace } from "./AdaptiveWorkspace";
import { PreferencesPanel, TracePanel } from "./AssistantPanel";
import { Chat } from "./Chat";

export function StandaloneWorkspace() {
  const session = useAppStore((s) => s.session)!;
  const switchGame = useAppStore((s) => s.switchGame);
  const setCondition = useAppStore((s) => s.setCondition);
  const experimenterMode = useAppStore((s) => s.experimenterMode);
  const setExperimenterMode = useAppStore((s) => s.setExperimenterMode);
  const setHistoryOpen = useAppStore((s) => s.setHistoryOpen);
  const proposals = useAppStore((s) => s.proposals[session.selectedGame] ?? EMPTY);
  const [showChat, setShowChat] = useState(true);
  const [controlsOpen, setControlsOpen] = useState(false);
  const [chatTab, setChatTab] = useState<"main" | "prefs" | "trace">("main");

  useEffect(() => {
    if (!experimenterMode && chatTab === "trace") setChatTab("main");
  }, [experimenterMode, chatTab]);

  const game = session.selectedGame;
  const pendingCount = proposals
    .filter((p) => p.status === "pending")
    .reduce((n, p) => n + p.items.filter((i) => i.status === "pending").length, 0);

  if (session.condition !== "adaptive") {
    return (
      <div className="standalone-shell">
        <header className="studybar standalone-bar">
          <strong>Adaptive Workspace</strong>
          <span className="sb-sim-pill" role="note">
            Simulated settings — no real changes to VALORANT or CS2
          </span>
          {experimenterMode ? (
            <button type="button" className="sb-btn is-accent" onClick={() => void setCondition("adaptive")}>
              Switch to B · Adaptive
            </button>
          ) : null}
          <button
            type="button"
            className={`sb-btn sb-btn-subtle ${experimenterMode ? "is-on" : ""}`}
            aria-pressed={experimenterMode}
            onClick={() => {
              const next = !experimenterMode;
              setExperimenterMode(next);
              if (!next) setControlsOpen(false);
            }}
          >
            {experimenterMode ? "Experimenter ✓" : "Experimenter"}
          </button>
        </header>
        <div className="standalone-empty">
          <p>The Adaptive Workspace is only active in the adaptive study condition.</p>
          {experimenterMode ? (
            <button type="button" className="btn btn-primary" onClick={() => void setCondition("adaptive")}>
              Switch study condition to B · Adaptive
            </button>
          ) : null}
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

        {!experimenterMode ? <ModelStatusPill compact /> : null}

        {experimenterMode ? (
          <div className="sb-controls">
            <button type="button" className="sb-btn" aria-expanded={controlsOpen} onClick={() => setControlsOpen((o) => !o)}>
              Study controls
            </button>
            {controlsOpen ? <ExperimenterDrawer onClose={() => setControlsOpen(false)} /> : null}
          </div>
        ) : null}

        <button
          type="button"
          className={`sb-btn sb-btn-subtle ${experimenterMode ? "is-on" : ""}`}
          aria-pressed={experimenterMode}
          onClick={() => {
            const next = !experimenterMode;
            setExperimenterMode(next);
            if (!next) setControlsOpen(false);
          }}
        >
          {experimenterMode ? "Experimenter ✓" : "Experimenter"}
        </button>
      </header>

      <div className="standalone-grid">
        <div className="standalone-workspace-pane">
          <AdaptiveWorkspace game={game} mode="standalone" />
        </div>
        {showChat ? (
          <aside className="standalone-chat-pane" aria-label="Assistant chat (standalone)">
            {experimenterMode ? (
              <div className="assistant-head">
                <ModelStatusPill />
              </div>
            ) : null}
            <nav className="assistant-tabs" role="tablist" aria-label="Standalone assistant views">
              <button type="button" role="tab" aria-selected={chatTab === "main"} className={chatTab === "main" ? "is-on" : ""} onClick={() => setChatTab("main")}>
                Chat
              </button>
              <button type="button" role="tab" aria-selected={chatTab === "prefs"} className={chatTab === "prefs" ? "is-on" : ""} onClick={() => setChatTab("prefs")}>
                Goals &amp; preferences
              </button>
              {experimenterMode ? (
                <button type="button" role="tab" aria-selected={chatTab === "trace"} className={chatTab === "trace" ? "is-on" : ""} onClick={() => setChatTab("trace")}>
                  Trace
                </button>
              ) : null}
            </nav>
            {chatTab === "main" ? (
              <div className="assistant-main">
                <Chat game={game} />
              </div>
            ) : chatTab === "prefs" ? (
              <div className="assistant-scroll">
                <PreferencesPanel game={game} />
              </div>
            ) : (
              <div className="assistant-scroll">
                <TracePanel />
              </div>
            )}
          </aside>
        ) : null}
      </div>
    </div>
  );
}
