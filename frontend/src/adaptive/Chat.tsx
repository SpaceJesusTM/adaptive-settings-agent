import { useEffect, useRef, useState } from "react";
import type { ChatMessage, GameId, PreferenceSuggestion, ScopeOverride } from "../api/types";
import { EMPTY, useAppStore } from "../store/useAppStore";

const STARTERS: Record<GameId, string[]> = {
  valorant: [
    "I'm getting frame drops in VALORANT and want smoother competitive play. What should I change?",
    "What does anti-aliasing do?",
    "I care more about visibility than visual effects.",
    "Where is the minimap zoom setting?",
  ],
  cs2: [
    "I just installed CS2; configure everything for competitive FPS and clarity.",
    "I'm new to CS2. What should I change based on what I liked in VALORANT?",
    "What does Boost Player Contrast do?",
    "Where is the V-Sync setting?",
  ],
};

function PreferenceChip({ s }: { s: PreferenceSuggestion }) {
  const confirm = useAppStore((st) => st.confirmPreference);
  const dims = useAppStore((st) => st.profile?.dimensions ?? EMPTY);
  const [scope, setScope] = useState<"session" | "durable">(s.scope);
  const [dim, setDim] = useState(s.dimension);
  const [done, setDone] = useState<null | "saved" | "declined">(null);
  if (done) return <p className="pref-done">{done === "saved" ? "Preference saved." : "Not saved."}</p>;
  return (
    <div className="pref-suggest" role="group" aria-label="Preference suggestion">
      <span className="layer-label">Save this as a preference?</span>
      <div className="pref-row">
        <span>{s.direction === "prioritize" ? "Prioritize" : "De-prioritize"}</span>
        <select value={dim} onChange={(e) => setDim(e.target.value)} aria-label="Preference dimension">
          {dims.map((d) => (
            <option key={d.id} value={d.id}>
              {d.label}
            </option>
          ))}
        </select>
        <select value={scope} onChange={(e) => setScope(e.target.value as "session" | "durable")} aria-label="Preference scope">
          <option value="session">this session only</option>
          <option value="durable">lasting (all games)</option>
        </select>
      </div>
      <p className="pref-quote">“{s.quote}”</p>
      <div className="pref-actions">
        <button
          type="button"
          className="btn btn-small btn-primary"
          onClick={() => {
            void confirm(s, scope, dim);
            setDone("saved");
          }}
        >
          Save preference
        </button>
        <button type="button" className="btn btn-small btn-ghost" onClick={() => setDone("declined")}>
          No thanks
        </button>
      </div>
    </div>
  );
}

function AssistantMessage({ game, msg }: { game: GameId; msg: ChatMessage }) {
  const res = msg.response!;
  const experimenterMode = useAppStore((s) => s.experimenterMode);
  const requestFocus = useAppStore((s) => s.requestFocusInMainWindow);
  const openWorkspace = useAppStore((s) => s.openWorkspace);
  const proposals = useAppStore((s) => s.proposals[game] ?? EMPTY);
  const [showChecked, setShowChecked] = useState(false);
  const [showFiltered, setShowFiltered] = useState(false);

  const ai = res.provenance.source === "ai";
  const linkedProposal = res.stagedProposalId ? proposals.find((p) => p.id === res.stagedProposalId) : undefined;
  const livePendingInProposal = linkedProposal
    ? linkedProposal.items.filter((i) => i.status === "pending").length
    : 0;
  const totalPendingInGame = proposals
    .filter((p) => p.status === "pending")
    .reduce((n, p) => n + p.items.filter((i) => i.status === "pending").length, 0);
  const reviewCount = livePendingInProposal || (res.stagedCount ?? 0);
  const cov = res.plan?.coverage;

  return (
    <div className="msg msg-assistant">
      {experimenterMode ? (
        <div className={`msg-prov ${ai ? "is-ai" : "is-fallback"}`}>
          {ai ? (
            <>
              Local AI · <code>{res.provenance.model}</code>
              {res.provenance.latencyMs ? ` · ${(res.provenance.latencyMs / 1000).toFixed(1)} s` : ""}
              {res.plan ? ` · scope=${res.plan.scope}` : ""}
            </>
          ) : (
            <>
              Offline fallback — rule-based, not AI-generated
              {res.provenance.fallbackReason ? ` · ${res.provenance.fallbackReason}` : ""}
            </>
          )}
        </div>
      ) : !ai ? (
        <div className="msg-prov is-fallback">Assistant offline — using basic suggestions (not AI)</div>
      ) : null}

      <p className="msg-text">{res.reply}</p>

      {res.validationNotes.map((n) => (
        <p key={n} className="msg-note" role="note">
          ⚠ {n}
        </p>
      ))}
      {res.knownsAndUnknowns ? (
        <p className="msg-unknowns">
          <span>Note:</span> {res.knownsAndUnknowns}
        </p>
      ) : null}
      {res.clarifyingQuestion ? <p className="msg-question">{res.clarifyingQuestion}</p> : null}

      {res.recommendations.length > 0 ? (
        <div className="msg-staged-banner" role="status">
          <div className="msg-staged-info">
            {reviewCount > 0 ? (
              <>
                <strong>{reviewCount} change{reviewCount === 1 ? "" : "s"} ready to review</strong> — nothing has been applied.
              </>
            ) : res.alreadyPendingCount ? (
              <>
                Already queued in your <strong>Changes</strong> list ({totalPendingInGame} pending). Nothing has been applied.
              </>
            ) : (
              <>Suggestions reviewed — check Changes for current status.</>
            )}
            {res.plan?.partialCoverage ? (
              <span className="msg-partial-tag"> · Partial coverage ({res.plan.batchesCompleted}/{res.plan.batchesTotal} sections)</span>
            ) : null}
          </div>
          <div className="msg-staged-actions">
            <button type="button" className="btn btn-primary btn-small" onClick={() => openWorkspace("changes")}>
              Review {reviewCount || totalPendingInGame || res.recommendations.length} change{(reviewCount || totalPendingInGame || res.recommendations.length) === 1 ? "" : "s"}
            </button>
            {cov ? (
              <button
                type="button"
                className="btn btn-small btn-ghost"
                aria-expanded={showChecked}
                onClick={() => setShowChecked((v) => !v)}
              >
                {showChecked ? "Hide summary" : "What I checked"}
              </button>
            ) : null}
          </div>
          {showChecked && cov ? (
            <div className="msg-checked">
              <p>
                Evaluated {cov.evaluatedCount} catalogue settings: <strong>{cov.proposedCount}</strong> prepared,{" "}
                <strong>{cov.alreadyAlignedCount}</strong> already aligned,{" "}
                <strong>{cov.lockedCount}</strong> locked, <strong>{cov.manualCount}</strong> manual/personal excluded.
              </p>
              <ul className="msg-checked-list">
                {res.recommendations.slice(0, 8).map((r) => (
                  <li key={r.settingId}>
                    <span>{r.label}</span>: {r.currentDisplay} → <strong>{r.proposedDisplay}</strong>
                  </li>
                ))}
                {res.recommendations.length > 8 ? <li>…and {res.recommendations.length - 8} more in Changes</li> : null}
              </ul>
              {res.plan?.manualConsiderations?.length ? (
                <p className="msg-checked-manual">
                  Personal/manual settings to check yourself:{" "}
                  {res.plan.manualConsiderations.slice(0, 5).map((m) => m.label).join(", ")}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {res.explanations.map((e) => (
        <div key={e.settingId} className="explain-card">
          <div className="rec-title">
            <strong>{e.label}</strong>
            <span className="rec-path">{e.path}</span>
          </div>
          <div className="layer">
            <span className="layer-label">
              What it does {experimenterMode ? <small>(catalogue{e.verificationStatus === "verified-game-files" ? ": Valve tooltip" : ""})</small> : null}
            </span>
            <p>{e.catalogDescription}</p>
          </div>
          {e.explanation && e.explanation !== e.catalogDescription ? (
            <div className="layer">
              <span className="layer-label">Why it matters</span>
              <p>{e.explanation}</p>
            </div>
          ) : null}
          {e.tradeoffs ? (
            <div className="layer">
              <span className="layer-label">Trade-offs</span>
              <p>{e.tradeoffs}</p>
            </div>
          ) : null}
          <button type="button" className="btn btn-small" onClick={() => requestFocus(game, e.settingId)}>
            Show in settings
          </button>
        </div>
      ))}

      {res.navigateTo ? (
        <button type="button" className="btn btn-small" onClick={() => requestFocus(game, res.navigateTo!.settingId)}>
          Show {res.navigateTo.label} ({res.navigateTo.path})
        </button>
      ) : null}

      {res.preferenceSuggestions.map((p) => (
        <PreferenceChip key={`${p.dimension}-${p.scope}`} s={p} />
      ))}

      {experimenterMode && res.filtered.length ? (
        <div className="msg-filtered">
          <button type="button" className="link" aria-expanded={showFiltered} onClick={() => setShowFiltered((v) => !v)}>
            {res.filtered.length} item{res.filtered.length > 1 ? "s" : ""} removed by safety checks
          </button>
          {showFiltered ? (
            <ul>
              {res.filtered.map((f, i) => (
                <li key={i}>
                  <code>{f.kind}</code> {f.reason}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

const SCOPE_LABELS: { id: ScopeOverride; label: string; title: string }[] = [
  { id: "auto", label: "Auto", title: "Match request breadth automatically" },
  { id: "focused", label: "Focused", title: "1–3 highest-impact settings only" },
  { id: "comprehensive", label: "Full setup", title: "Audit all applicable settings across categories" },
];

export function Chat({ game }: { game: GameId }) {
  const thread = useAppStore((s) => s.chat[game] ?? EMPTY);
  const run = useAppStore((s) => s.runs[game]);
  const experimenterMode = useAppStore((s) => s.experimenterMode);
  const scopeOverride = useAppStore((s) => s.scopeOverride);
  const setScopeOverride = useAppStore((s) => s.setScopeOverride);
  const send = useAppStore((s) => s.sendChat);
  const cancel = useAppStore((s) => s.cancelRun);
  const clear = useAppStore((s) => s.clearChat);
  const prefill = useAppStore((s) => s.composerPrefill);
  const [text, setText] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (run) {
      endRef.current?.scrollIntoView({ block: "end" });
      return;
    }
    const msgs = endRef.current?.parentElement?.querySelectorAll(".msg");
    const last = msgs && msgs.length ? msgs[msgs.length - 1] : null;
    if (last) last.scrollIntoView({ block: "start" });
  }, [thread.length, run, run?.steps?.length]);

  useEffect(() => {
    if (prefill && prefill.game === game) {
      setText(prefill.text);
      inputRef.current?.focus();
    }
  }, [prefill, game]);

  const submit = () => {
    const t = text.trim();
    if (!t || run) return;
    setText("");
    void send(game, t);
  };

  return (
    <section className="chat" aria-label="Assistant chat">
      <div className="chat-thread" role="log" aria-live="polite">
        {thread.length === 0 && !run ? (
          <div className="chat-empty">
            <p>
              Ask about any setting or goal in {game === "cs2" ? "CS2" : "VALORANT"}. Suggested changes are prepared in{" "}
              <strong>Workspace → Changes</strong> for your review; nothing changes until you apply them.
            </p>
            <div className="starters">
              {STARTERS[game].map((s) => (
                <button key={s} type="button" className="starter" onClick={() => setText(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {thread.map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="msg msg-user">
              <p>{m.text}</p>
            </div>
          ) : m.role === "assistant" && m.response ? (
            <AssistantMessage key={m.id} game={game} msg={m} />
          ) : (
            <div key={m.id} className="msg msg-system">
              <p>{m.text}</p>
            </div>
          ),
        )}

        {run ? (
          <div className="msg msg-progress" aria-live="polite">
            {experimenterMode ? (
              <ol>
                {run.steps.map((s, i) => (
                  <li key={i} className={i === run.steps.length - 1 ? "is-current" : ""}>
                    {s.label}
                  </li>
                ))}
              </ol>
            ) : (
              <span className="progress-simple">Thinking…</span>
            )}
            <span className="progress-time">{run.elapsedMs ? `${(run.elapsedMs / 1000).toFixed(1)} s` : ""}</span>
          </div>
        ) : null}
        <div ref={endRef} />
      </div>

      <div className="composer">
        <div className="composer-scope" role="group" aria-label="Recommendation breadth">
          <span className="scope-label">Scope:</span>
          {SCOPE_LABELS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              aria-pressed={scopeOverride === opt.id}
              className={`scope-pill ${scopeOverride === opt.id ? "is-on" : ""}`}
              title={opt.title}
              onClick={() => setScopeOverride(opt.id)}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <textarea
          ref={inputRef}
          value={text}
          rows={2}
          maxLength={1000}
          placeholder="Ask about a goal, a full setup, a setting, or a preference…"
          aria-label="Message the assistant"
          disabled={Boolean(run)}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <div className="composer-actions">
          {run ? (
            <button type="button" className="btn btn-danger" onClick={() => void cancel(game)}>
              Cancel
            </button>
          ) : (
            <button type="button" className="btn btn-primary" disabled={!text.trim()} onClick={submit}>
              Send
            </button>
          )}
          {thread.length ? (
            <button type="button" className="btn btn-ghost btn-small" disabled={Boolean(run)} onClick={() => void clear(game)}>
              Clear chat
            </button>
          ) : null}
        </div>
      </div>
    </section>
  );
}
