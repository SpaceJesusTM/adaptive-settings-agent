import { useEffect, useState } from "react";
import type { GameId } from "../api/types";
import { gameName, timeAgo } from "../lib/format";
import { EMPTY, useAppStore } from "../store/useAppStore";
import { ModelStatusPill } from "../components/chrome/StudyBar";
import { Chat } from "./Chat";

export function PreferencesPanel({ game }: { game: GameId }) {
  const profile = useAppStore((s) => s.profile);
  const removePreference = useAppStore((s) => s.removePreference);
  const clearGoals = useAppStore((s) => s.clearGoals);
  const addPreference = useAppStore((s) => s.addPreference);
  const [dim, setDim] = useState("input_latency");
  const [dir, setDir] = useState<"prioritize" | "deprioritize">("prioritize");
  const [scope, setScope] = useState<"session" | "durable">("durable");
  if (!profile) return <p className="muted">Loading…</p>;
  const goals = profile.sessionGoals[game] ?? [];
  const durable = profile.preferences.filter((p) => p.scope === "durable");
  const session = profile.preferences.filter((p) => p.scope === "session");

  return (
    <div className="prefs">
      <section aria-label="Current session goal">
        <h4>Current goal · this session · {gameName(game)}</h4>
        {goals.length === 0 ? <p className="muted">No goal stated yet. Goals you describe in chat appear here for this session.</p> : null}
        {goals.map((g) => (
          <div key={g.id} className="goal-chip">
            <span>“{g.text}”</span>
            <small>{g.dimensions.map((d) => profile.dimensions.find((x) => x.id === d)?.label ?? d).join(", ")}</small>
          </div>
        ))}
        {goals.length ? (
          <button type="button" className="btn btn-small btn-ghost" onClick={() => void clearGoals(game)}>
            Clear goal
          </button>
        ) : null}
      </section>
      <section aria-label="Session preferences">
        <h4>This session only</h4>
        {session.length === 0 ? <p className="muted">None.</p> : null}
        {session.map((p) => (
          <div key={p.id} className="pref-item">
            <span className={`dir dir-${p.direction}`}>
              {p.direction === "prioritize" ? "▲" : "▼"} {p.dimensionLabel}
            </span>
            <button type="button" className="link" onClick={() => void removePreference(p.id)}>
              remove
            </button>
          </div>
        ))}
      </section>
      <section aria-label="Lasting preferences">
        <h4>Lasting preferences · shared across games</h4>
        <p className="muted">Only abstract goals are shared between games — never setting values or controls.</p>
        {durable.length === 0 ? <p className="muted">None saved.</p> : null}
        {durable.map((p) => (
          <div key={p.id} className="pref-item">
            <div>
              <span className={`dir dir-${p.direction}`}>
                {p.direction === "prioritize" ? "▲" : "▼"} {p.dimensionLabel}
              </span>
              <small className="pref-origin">
                {p.originGame ? `from ${gameName(p.originGame)}` : ""} · {p.source.replace("_", " ")} · {timeAgo(p.createdAt)}
              </small>
              {p.evidence.length ? (
                <ul className="evidence">
                  {p.evidence.slice(0, 4).map((e, i) => (
                    <li key={i}>{e.detail}</li>
                  ))}
                </ul>
              ) : null}
            </div>
            <button type="button" className="link" onClick={() => void removePreference(p.id)}>
              remove
            </button>
          </div>
        ))}
      </section>
      <section aria-label="Add a preference">
        <h4>Add or correct a preference</h4>
        <div className="pref-row">
          <select value={dir} onChange={(e) => setDir(e.target.value as "prioritize" | "deprioritize")} aria-label="Direction">
            <option value="prioritize">Prioritize</option>
            <option value="deprioritize">De-prioritize</option>
          </select>
          <select value={dim} onChange={(e) => setDim(e.target.value)} aria-label="Goal">
            {profile.dimensions.map((d) => (
              <option key={d.id} value={d.id}>
                {d.label}
              </option>
            ))}
          </select>
          <select value={scope} onChange={(e) => setScope(e.target.value as "session" | "durable")} aria-label="Scope">
            <option value="durable">lasting</option>
            <option value="session">this session</option>
          </select>
          <button type="button" className="btn btn-small" onClick={() => void addPreference(game, dim, dir, scope)}>
            Save
          </button>
        </div>
      </section>
    </div>
  );
}

export function TracePanel() {
  const traces = useAppStore((s) => s.traces);
  const load = useAppStore((s) => s.loadTraces);
  useEffect(() => {
    void load();
  }, [load]);
  return (
    <div className="traces">
      <div className="traces-head">
        <p className="muted">
          Per-request trace (experimenter log): source, model, read-only tools used, items removed by validation, latency.
        </p>
        <button type="button" className="btn btn-small" onClick={() => void load()}>
          Refresh
        </button>
      </div>
      <ol>
        {traces.map((t) => (
          <li key={t.runId} className={`trace trace-${t.status}`}>
            <div className="trace-top">
              <span className={`badge badge-${t.status}`}>{t.status}</span>
              <span>
                {gameName(t.game)} · {t.condition}
              </span>
              <span>{t.latencyMs ? `${(t.latencyMs / 1000).toFixed(1)} s` : ""}</span>
            </div>
            <div className="trace-goal">“{t.goalExcerpt}”</div>
            <div className="trace-meta">
              <span>source: {t.mode}</span>
              {t.model ? (
                <span>
                  model: <code>{t.model}</code>
                </span>
              ) : null}
            </div>
            {t.toolCalls?.length ? (
              <div className="trace-tools">tools: {t.toolCalls.map((c) => `${c.tool}${c.by === "model" ? "*" : ""}`).join(", ")}</div>
            ) : null}
            {t.validation?.filtered?.length ? <div className="trace-filtered">removed by validation: {t.validation.filtered.length}</div> : null}
            {t.error ? <div className="trace-error">{t.error}</div> : null}
          </li>
        ))}
      </ol>
      <p className="muted">* requested by the model through native tool calling; others were called by the workflow.</p>
    </div>
  );
}

export function AssistantPanel({ game }: { game: GameId }) {
  const experimenterMode = useAppStore((s) => s.experimenterMode);
  const openWorkspace = useAppStore((s) => s.openWorkspace);
  const proposals = useAppStore((s) => s.proposals[game] ?? EMPTY);
  const pins = useAppStore((s) => s.states[game]?.pins ?? EMPTY);
  const [tab, setTab] = useState<"main" | "prefs" | "trace">("main");

  useEffect(() => {
    if (!experimenterMode && tab === "trace") setTab("main");
  }, [experimenterMode, tab]);

  const pendingCount = proposals
    .filter((p) => p.status === "pending")
    .reduce((n, p) => n + p.items.filter((i) => i.status === "pending").length, 0);

  return (
    <aside className="assistant" aria-label="Assistant (adaptive condition)">
      <header className="assistant-head">
        <div className="assistant-head-row">
          <div>
            <strong>Assistant</strong>
            <small>Reviews changes in Workspace — nothing applies automatically.</small>
          </div>
          <button
            type="button"
            className="btn btn-small"
            onClick={() => openWorkspace(pendingCount > 0 ? "changes" : pins.length > 0 ? "pinned" : "discover")}
            title="Open Adaptive Workspace (Changes, Pinned, Discover)"
          >
            Workspace{pendingCount ? ` (${pendingCount})` : ""}
          </button>
        </div>
        {experimenterMode ? <ModelStatusPill /> : null}
      </header>
      <nav className="assistant-tabs" role="tablist" aria-label="Assistant views">
        <button type="button" role="tab" aria-selected={tab === "main"} className={tab === "main" ? "is-on" : ""} onClick={() => setTab("main")}>
          Chat
        </button>
        <button type="button" role="tab" aria-selected={tab === "prefs"} className={tab === "prefs" ? "is-on" : ""} onClick={() => setTab("prefs")}>
          Goals &amp; preferences
        </button>
        {experimenterMode ? (
          <button type="button" role="tab" aria-selected={tab === "trace"} className={tab === "trace" ? "is-on" : ""} onClick={() => setTab("trace")}>
            Trace
          </button>
        ) : null}
      </nav>
      {tab === "main" ? (
        <div className="assistant-main">
          <Chat game={game} />
        </div>
      ) : tab === "prefs" ? (
        <div className="assistant-scroll">
          <PreferencesPanel game={game} />
        </div>
      ) : (
        <div className="assistant-scroll">
          <TracePanel />
        </div>
      )}
    </aside>
  );
}
