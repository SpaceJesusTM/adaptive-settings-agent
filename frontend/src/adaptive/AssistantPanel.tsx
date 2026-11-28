import { useEffect, useState } from "react";
import type { GameId } from "../api/types";
import { gameName, timeAgo } from "../lib/format";
import { EMPTY, useAppStore } from "../store/useAppStore";
import { ModelStatusPill } from "../components/chrome/StudyBar";
import { Chat } from "./Chat";

export function PreferencesPanel({ game }: { game: GameId }) {
  const profile = useAppStore((s) => s.profile);
  const catalogue = useAppStore((s) => s.catalogs[game]);
  const removePreference = useAppStore((s) => s.removePreference);
  const clearGoals = useAppStore((s) => s.clearGoals);
  const addPreference = useAppStore((s) => s.addPreference);
  const addPersonalFact = useAppStore((s) => s.addPersonalFact);
  const removePersonalFact = useAppStore((s) => s.removePersonalFact);
  const goToSetting = useAppStore((s) => s.requestFocusInMainWindow);
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
  const observed = profile.observed;
  const keySettings = observed?.keySettings ?? [];
  const discrepancies = observed?.discrepancies ?? [];
  const tentativeSignals = observed?.tentativeSignals ?? [];
  const recentActions = observed?.recentActions ?? [];

  const sourceCategoryLabel = (cat?: string) => {
    switch (cat) {
      case "explicit_statement":
        return "explicitly stated";
      case "manual_change":
        return "manual edit";
      case "ai_applied":
        return "applied suggestion";
      case "scenario_seed":
        return "scenario preset";
      case "rejected_or_dismissed":
        return "dismissed";
      case "user_checked":
        return "checked";
      default:
        return "observed";
    }
  };

  return (
    <div className="prefs su-panel" aria-label="System Understanding">
      <div className="su-intro">
        <strong>System Understanding</strong>
        <small>What guides suggestions automatically — without needing manual setup first.</small>
      </div>

      <section aria-label="Current goal">
        <h4>Current goal · {gameName(game)}</h4>
        <p className="muted">Derived automatically from what you ask in chat for this session.</p>
        {goals.length === 0 ? (
          <p className="muted">
            No active session goal yet. Mention a goal in Chat (e.g. smoother FPS or clearer visibility) and I&apos;ll adapt automatically.
          </p>
        ) : null}
        {goals.map((g) => (
          <div key={g.id} className="goal-chip">
            <span>“{g.text}”</span>
            <small>Focus: {g.dimensions.map((d) => profile.dimensions.find((x) => x.id === d)?.label ?? d).join(", ")}</small>
            {g.protectedSettingIds?.length ? (
              <details>
                <summary>Settings kept unchanged ({g.protectedSettingIds.length})</summary>
                <ul>
                  {catalogue?.settings.filter((s) => g.protectedSettingIds?.includes(s.id)).map((s) => (
                    <li key={s.id}>{s.exactLabel}</li>
                  ))}
                </ul>
              </details>
            ) : null}
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

      <section aria-label="What I have noticed">
        <h4>What I&apos;ve noticed automatically</h4>
        <p className="muted">Live observations from your simulated menus — never treats defaults or presets as personal intent.</p>
        {discrepancies.length ? (
          <div className="su-discrepancy-list" role="alert">
            {discrepancies.map((d) => (
              <div key={d.factId} className="su-discrepancy">
                <strong>Notice mismatch ({gameName(d.game)})</strong>
                <p>{d.explanation}</p>
                <div className="su-discrepancy-actions">
                  <button type="button" className="link" onClick={() => goToSetting(d.game, d.settingId)}>
                    Show live setting
                  </button>
                  <button type="button" className="link" onClick={() => void removePersonalFact(d.factId)}>
                    Remove outdated note
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : null}
        {tentativeSignals.length ? (
          <div className="su-tentative-list">
            {tentativeSignals.map((sig) => (
              <div key={sig.dimension} className="su-tentative">
                <span className="chip chip-tentative">Tentative — not saved</span>
                <p>{sig.explanation}</p>
              </div>
            ))}
          </div>
        ) : null}
        {keySettings.length ? (
          <div className="su-observed-list">
            {keySettings.map((k) => (
              <div key={`${k.game}-${k.settingId}`} className="pref-item su-obs-item">
                <div>
                  <span className="su-obs-head">
                    <strong>{k.label}</strong> ({gameName(k.game)}): <code>{k.display}</code>
                  </span>
                  <small className="pref-origin">
                    <span className={`chip ${k.deliberate ? "chip-deliberate" : "chip-observed"}`}>{k.sourceLabel}</span>
                  </small>
                </div>
                <button type="button" className="link" onClick={() => goToSetting(k.game, k.settingId)}>
                  show
                </button>
              </div>
            ))}
          </div>
        ) : null}
        {recentActions.length ? (
          <details className="su-recent-details">
            <summary>Recent session activity ({recentActions.length})</summary>
            <ul className="evidence">
              {recentActions.map((a) => (
                <li key={a.batchId}>{a.summary} · {timeAgo(a.createdAt)}</li>
              ))}
            </ul>
          </details>
        ) : null}
      </section>

      <section aria-label="What you asked me to remember">
        <h4>What you&apos;ve asked me to remember</h4>
        <p className="muted">Confirmed priorities &amp; personal notes (saved via Chat or manual controls below).</p>
        {session.length === 0 && durable.length === 0 && facts.length === 0 ? (
          <p className="muted">Nothing explicitly saved yet. You can tell me in Chat anytime (e.g. &ldquo;Remember I prefer V for push-to-talk&rdquo;).</p>
        ) : null}
        {session.map((p) => (
          <div key={p.id} className="pref-item">
            <div>
              <span className={`dir dir-${p.direction}`}>
                {p.direction === "prioritize" ? "▲" : "▼"} {p.dimensionLabel}
              </span>
              <small className="pref-origin">This session only{p.appliesToGame ? ` · ${gameName(p.appliesToGame)}` : ""} · {timeAgo(p.createdAt)}</small>
            </div>
            <button type="button" className="link" onClick={() => void removePreference(p.id)}>
              remove
            </button>
          </div>
        ))}
        {durable.map((p) => (
          <div key={p.id} className="pref-item">
            <div>
              <span className={`dir dir-${p.direction}`}>
                {p.direction === "prioritize" ? "▲" : "▼"} {p.dimensionLabel}
              </span>
              <small className="pref-origin">
                {p.appliesToGame ? `Lasting in ${gameName(p.appliesToGame)}` : "Lasting across games"} ·{" "}
                {p.source === "chat_explicit"
                  ? "remembered from chat"
                  : p.source === "chat_confirmed"
                    ? "confirmed in chat"
                    : p.source === "user_explicit"
                      ? "added manually"
                      : "profile"}{" "}
                · {timeAgo(p.createdAt)}
              </small>
              {p.evidence.length ? (
                <ul className="evidence">
                  {p.evidence.slice(0, 3).map((e, i) => (
                    <li key={i}>
                      <span className="ev-cat">[{sourceCategoryLabel(e.sourceCategory)}]</span> {e.detail}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
            <button type="button" className="link" onClick={() => void removePreference(p.id)}>
              remove
            </button>
          </div>
        ))}
        {facts.map((f) => (
          <div key={f.id} className="pref-item">
            <div>
              <strong>{f.label}:</strong> <code>{f.valueText}</code>
              <small className="pref-origin">
                {f.originGame ? `${gameName(f.originGame)} · ` : ""}
                {f.source === "chat_explicit"
                  ? "remembered from chat"
                  : f.source === "seed"
                    ? "profile"
                    : "confirmed by you"}
              </small>
            </div>
            <button type="button" className="link" onClick={() => void removePersonalFact(f.id)}>
              remove
            </button>
          </div>
        ))}

        <details className="pref-manual-details">
          <summary>Add or edit manually</summary>
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
                Save note
              </button>
            </div>
          ) : null}
        </details>
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
  const relevantNow = useAppStore((s) => s.relevantNow[game]);
  const seenDiscoverIds = useAppStore((s) => s.seenDiscoverIds[game] ?? EMPTY);
  const [tab, setTab] = useState<"main" | "prefs" | "trace">("main");

  useEffect(() => {
    if (!experimenterMode && tab === "trace") setTab("main");
  }, [experimenterMode, tab]);

  const pendingCount = proposals
    .filter((p) => p.status === "pending")
    .reduce((n, p) => n + p.items.filter((i) => i.status === "pending").length, 0);
  const unseenDiscoverCount = (relevantNow?.items ?? []).filter(
    (c) => (c.state === "suggested" || c.state === "changed") && !seenDiscoverIds.includes(c.cardId || c.settingId),
  ).length;

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
            onClick={() =>
              openWorkspace(pendingCount > 0 ? "changes" : unseenDiscoverCount > 0 ? "discover" : pins.length > 0 ? "pinned" : "discover")
            }
            title="Open Adaptive Workspace (Changes, Pinned, Discover)"
          >
            Workspace{pendingCount ? ` (${pendingCount})` : ""}
            {unseenDiscoverCount > 0 ? <span className="discover-unseen-dot" aria-label={`${unseenDiscoverCount} new Discover items`} /> : null}
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
