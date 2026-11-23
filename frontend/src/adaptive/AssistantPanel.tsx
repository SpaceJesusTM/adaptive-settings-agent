import { useEffect, useState } from "react";
import type { GameId } from "../api/types";
import { gameName, timeAgo } from "../lib/format";
import { EMPTY, useAppStore } from "../store/useAppStore";
import { ModelStatusPill } from "../components/chrome/StudyBar";
import { Chat } from "./Chat";

export function PreferencesPanel({ game }: { game: GameId }) {
  const profile = useAppStore((s) => s.profile);
  const byId = useAppStore((s) => s.byId[game]);
  const displayValues = useAppStore((s) => s.displayValues);
  const removePreference = useAppStore((s) => s.removePreference);
  const clearGoals = useAppStore((s) => s.clearGoals);
  const addPreference = useAppStore((s) => s.addPreference);
  const addPersonalFact = useAppStore((s) => s.addPersonalFact);
  const removePersonalFact = useAppStore((s) => s.removePersonalFact);
  const [dim, setDim] = useState("input_latency");
  const [dir, setDir] = useState<"prioritize" | "deprioritize">("prioritize");
  const [scope, setScope] = useState<"session" | "durable">("durable");
  const [factKey, setFactKey] = useState("mouse_sensitivity");
  const [factValue, setFactValue] = useState("");
  if (!profile) return <p className="muted">Loading…</p>;
  const goals = profile.sessionGoals[game] ?? [];
  const conflicts = profile.conflicts?.[game] ?? [];
  const durable = profile.preferences.filter((p) => p.scope === "durable");
  const session = profile.preferences.filter((p) => p.scope === "session");
  const facts = profile.personalFacts ?? [];
  const factTypes = profile.personalFactTypes ?? [];
  const curVals = displayValues(game);

  const quickCaptures: { factKey: string; label: string; settingId: string }[] =
    game === "valorant"
      ? [
          { factKey: "mouse_sensitivity", label: "Remember Sensitivity", settingId: "val.general.sensitivity_aim" },
          { factKey: "push_to_talk_key", label: "Remember Push-to-Talk key", settingId: "val.controls.key_team_ptt" },
          { factKey: "ping_key", label: "Remember Ping key", settingId: "val.controls.key_ping" },
        ]
      : [
          { factKey: "mouse_sensitivity", label: "Remember Sensitivity", settingId: "cs2.kbmouse.mouse_sensitivity" },
          { factKey: "push_to_talk_key", label: "Remember Mic key", settingId: "cs2.kbmouse.key_mic" },
          { factKey: "ping_key", label: "Remember Ping key", settingId: "cs2.kbmouse.key_player_ping" },
        ];

  return (
    <div className="prefs">
      <section aria-label="Current session goal">
        <h4>1. Current goal · {gameName(game)} (this session)</h4>
        <p className="muted">Guides immediate suggestions right now; cleared when you start a new session or click Clear.</p>
        {goals.length === 0 ? <p className="muted">No active goal yet. Tell the assistant what you want in chat.</p> : null}
        {goals.map((g) => (
          <div key={g.id} className="goal-chip">
            <span>“{g.text}”</span>
            <small>Interpreted focus: {g.dimensions.map((d) => profile.dimensions.find((x) => x.id === d)?.label ?? d).join(", ")}</small>
          </div>
        ))}
        {conflicts.map((c, idx) => (
          <div key={idx} className="pref-conflict" role="note">
            <strong>Priority trade-off:</strong> {c.explanation}
          </div>
        ))}
        {goals.length ? (
          <button type="button" className="btn btn-small btn-ghost" onClick={() => void clearGoals(game)}>
            Clear goal
          </button>
        ) : null}
      </section>

      <section aria-label="General priorities">
        <h4>2. General priorities (this session &amp; lasting)</h4>
        <p className="muted">Confirmed weights that rank suggestions across chats. Lasting priorities carry across VALORANT and CS2.</p>
        {session.map((p) => (
          <div key={p.id} className="pref-item">
            <div>
              <span className={`dir dir-${p.direction}`}>
                {p.direction === "prioritize" ? "▲" : "▼"} {p.dimensionLabel}
              </span>
              <small className="pref-origin">This session only · {timeAgo(p.createdAt)}</small>
            </div>
            <button type="button" className="link" onClick={() => void removePreference(p.id)}>
              remove
            </button>
          </div>
        ))}
        {durable.length === 0 && session.length === 0 ? <p className="muted">No saved priorities yet.</p> : null}
        {durable.map((p) => (
          <div key={p.id} className="pref-item">
            <div>
              <span className={`dir dir-${p.direction}`}>
                {p.direction === "prioritize" ? "▲" : "▼"} {p.dimensionLabel}
              </span>
              <small className="pref-origin">
                Lasting across games{p.originGame ? ` · saved in ${gameName(p.originGame)}` : ""} · {p.source === "user_explicit" ? "added by you" : p.source === "chat_confirmed" ? "confirmed in chat" : "profile"} · {timeAgo(p.createdAt)}
              </small>
              {p.evidence.length ? (
                <ul className="evidence">
                  {p.evidence.slice(0, 3).map((e, i) => (
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
        <div className="pref-row" style={{ marginTop: 8 }}>
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
            Save priority
          </button>
        </div>
      </section>

      <section aria-label="Personal setup preferences">
        <h4>3. Personal setup facts (only when confirmed)</h4>
        <p className="muted">Optional habits like Push-to-Talk key or sensitivity. Used to help orient you in another game — never auto-applied.</p>
        {facts.length === 0 ? <p className="muted">None confirmed yet.</p> : null}
        {facts.map((f) => (
          <div key={f.id} className="pref-item">
            <div>
              <strong>{f.label}:</strong> <code>{f.valueText}</code>
              <small className="pref-origin">
                {f.originGame ? `from ${gameName(f.originGame)} · ` : ""}
                {f.source === "seed" ? "profile" : "confirmed by you"}
              </small>
            </div>
            <button type="button" className="link" onClick={() => void removePersonalFact(f.id)}>
              remove
            </button>
          </div>
        ))}
        <div className="pref-quick-facts">
          {quickCaptures.map((q) => {
            const val = curVals[q.settingId];
            if (val === undefined || val === "") return null;
            const s = byId?.[q.settingId];
            return (
              <button
                key={q.factKey}
                type="button"
                className="btn btn-small btn-ghost"
                onClick={() => void addPersonalFact(game, q.factKey, String(val), q.settingId, s ? `Captured from ${s.exactLabel}` : undefined)}
              >
                {q.label} ({String(val)})
              </button>
            );
          })}
        </div>
        {factTypes.length ? (
          <div className="pref-row" style={{ marginTop: 8 }}>
            <select value={factKey} onChange={(e) => setFactKey(e.target.value)} aria-label="Personal setup type">
              {factTypes.map((ft) => (
                <option key={ft.id} value={ft.id}>
                  {ft.label}
                </option>
              ))}
            </select>
            <input
              type="text"
              className="pref-fact-input"
              value={factValue}
              maxLength={80}
              placeholder={factTypes.find((ft) => ft.id === factKey)?.placeholder ?? "Value"}
              aria-label="Personal setup value"
              onChange={(e) => setFactValue(e.target.value)}
            />
            <button
              type="button"
              className="btn btn-small"
              disabled={!factValue.trim()}
              onClick={() => {
                void addPersonalFact(game, factKey, factValue.trim());
                setFactValue("");
              }}
            >
              Confirm fact
            </button>
          </div>
        ) : null}
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
          My Priorities
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
