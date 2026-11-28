import { useEffect, useRef, useState } from "react";
import type { ChatMessage, GameId, PreferenceSuggestion, ScopeOverride } from "../api/types";
import { gameName } from "../lib/format";
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
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<null | "saved" | "declined">(null);
  if (done) return <p className="pref-done">{done === "saved" ? "Preference saved." : "Not saved."}</p>;
  return (
    <div className="pref-suggest" role="group" aria-label="Preference suggestion">
      <span className="layer-label">Save this as a preference?</span>
      <div className="pref-row">
        <span>{s.direction === "prioritize" ? "Prioritize" : "De-prioritize"}</span>
        <select value={dim} disabled={saving} onChange={(e) => setDim(e.target.value)} aria-label="Preference dimension">
          {dims.map((d) => (
            <option key={d.id} value={d.id}>
              {d.label}
            </option>
          ))}
        </select>
        <select
          value={scope}
          disabled={saving}
          onChange={(e) => setScope(e.target.value as "session" | "durable")}
          aria-label="Preference scope"
        >
          <option value="session">this session only</option>
          <option value="durable">lasting (all games)</option>
        </select>
      </div>
      <p className="pref-quote">“{s.quote}”</p>
      {error ? (
        <p className="pref-error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="pref-actions">
        <button
          type="button"
          className="btn btn-small btn-primary"
          disabled={saving}
          onClick={() => {
            setSaving(true);
            setError(null);
            void confirm(s, scope, dim).then((ok) => {
              setSaving(false);
              if (ok) {
                setDone("saved");
              } else {
                setError("Could not save preference. Please try again.");
              }
            });
          }}
        >
          {saving ? "Saving…" : "Save preference"}
        </button>
        <button type="button" className="btn btn-small btn-ghost" disabled={saving} onClick={() => setDone("declined")}>
          No thanks
        </button>
      </div>
    </div>
  );
}

export function participantStepLabel(raw?: string): string {
  const text = (raw || "").trim();
  if (!text) return "Thinking…";
  if (/^Reviewing .+ settings \(\d+\/\d+\)$/i.test(text)) return `${text}…`;
  if (text.startsWith("Reading your current settings")) return "Checking your settings…";
  if (
    text.startsWith("Asking local model") ||
    text.startsWith("Checking whether more") ||
    text.startsWith("Looking up:")
  ) {
    return "Checking relevant settings…";
  }
  if (text === "Writing suggestions") return "Drafting recommendations (nothing applied yet)…";
  if (text === "Refining suggestions") return "Refining recommendations…";
  if (text.startsWith("Checking suggestions against")) return "Validating suggestions (nothing applied yet)…";
  if (text.startsWith("Using basic offline suggestions")) return "Preparing offline suggestions…";
  return "Thinking…";
}

function AssistantMessage({ game, msg }: { game: GameId; msg: ChatMessage }) {
  const res = msg.response!;
  const experimenterMode = useAppStore((s) => s.experimenterMode);
  const requestFocus = useAppStore((s) => s.requestFocusInMainWindow);
  const navigateCrossGame = useAppStore((s) => s.navigateCrossGame);
  const undoMemoryUpdate = useAppStore((s) => s.undoMemoryUpdate);
  const openWorkspace = useAppStore((s) => s.openWorkspace);
  const stage = useAppStore((s) => s.stage);
  const proposals = useAppStore((s) => s.proposals[game] ?? EMPTY);
  const [showChecked, setShowChecked] = useState(false);
  const [showFiltered, setShowFiltered] = useState(false);
  const [undoneMemoryIds, setUndoneMemoryIds] = useState<Record<string, boolean>>({});

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
  const isStaged = reviewCount > 0 || Boolean(res.alreadyPendingCount) || Boolean(res.stagedProposalId);

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
              {res.provenance.source === "rules" ? "Catalogue and history rules" : "Offline fallback — rule-based, not AI-generated"}
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
            ) : res.stagedProposalId ? (
              <>Suggestions reviewed — check Changes for current status.</>
            ) : (
              <>Suggestions were not automatically staged — prepare them when ready to review.</>
            )}
            {res.plan?.partialCoverage ? (
              <span className="msg-partial-tag"> · Partial coverage ({res.plan.batchesCompleted}/{res.plan.batchesTotal} sections)</span>
            ) : null}
          </div>
          <div className="msg-staged-actions">
            {isStaged ? (
              <button type="button" className="btn btn-primary btn-small" onClick={() => openWorkspace("changes")}>
                Review {reviewCount || totalPendingInGame || res.recommendations.length} change{(reviewCount || totalPendingInGame || res.recommendations.length) === 1 ? "" : "s"}
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-primary btn-small"
                onClick={() =>
                  void stage(
                    game,
                    res.recommendations,
                    res.provenance.source,
                    msg.runId ?? null,
                    `Suggested changes (${res.recommendations.length})`,
                  )
                }
              >
                Prepare for review ({res.recommendations.length})
              </button>
            )}
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
                {(cov.tradeoffRetainedCount ?? res.plan?.tradeoffRetainedItems?.length ?? 0) > 0 ? (
                  <>
                    <strong>{cov.tradeoffRetainedCount ?? res.plan?.tradeoffRetainedItems?.length}</strong> retained due to trade-off,{" "}
                  </>
                ) : null}
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

      {res.recommendations.length === 0 &&
      res.plan &&
      (res.intent === "recommend" || res.plan.singleSettingHint) &&
      ((res.plan.alreadyAlignedItems?.length ?? 0) > 0 ||
        (res.plan.tradeoffRetainedItems?.length ?? 0) > 0 ||
        (res.plan.manualConsiderations?.length ?? 0) > 0) ? (
        <div className="msg-aligned-box" aria-label="Configuration review">
          <strong className="layer-label">No changes needed to apply</strong>
          {res.plan.alreadyAlignedItems?.length ? (
            <ul className="review-info-list">
              {res.plan.alreadyAlignedItems.slice(0, 5).map((a) => (
                <li key={a.settingId} className="review-info-item">
                  <div>
                    <strong>{a.label}</strong> <span className="chip">Already {a.currentDisplay}</span>
                    {a.why ? <span className="review-info-why"> — {a.why}</span> : null}
                  </div>
                  <button type="button" className="link" onClick={() => requestFocus(game, a.settingId)}>
                    Show in settings
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          {res.plan.tradeoffRetainedItems?.length ? (
            <div className="review-tradeoff-block">
              <span className="layer-label">Retained due to trade-off</span>
              <ul className="review-info-list">
                {res.plan.tradeoffRetainedItems.slice(0, 4).map((t) => (
                  <li key={t.settingId} className="review-info-item">
                    <div>
                      <strong>{t.label}</strong> <span className="chip chip-warn">Kept {t.currentDisplay}</span>
                      <span className="review-info-why"> — {t.reason}</span>
                    </div>
                    <button type="button" className="link" onClick={() => requestFocus(game, t.settingId)}>
                      Show in settings
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {res.plan.manualConsiderations?.length ? (
            <ul className="review-info-list">
              {res.plan.manualConsiderations.slice(0, 3).map((m) => (
                <li key={m.settingId} className="review-info-item">
                  <div>
                    <strong>{m.label}</strong> <span className="chip">Manual: {m.currentDisplay}</span>
                    <span className="review-info-why"> — {m.reason}</span>
                  </div>
                  <button type="button" className="link" onClick={() => requestFocus(game, m.settingId)}>
                    Show in settings
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {res.crossGameComparisons?.length ? (
        <div className="cg-list" aria-label="Cross-game comparisons">
          {res.crossGameComparisons.map((c) => (
            <div key={c.id} className="cg-card">
              <div className="cg-head">
                <strong>{c.topic}</strong>
                {c.sourceGame && c.targetGame ? (
                  <span className="chip cg-dir-chip">
                    {c.sourceGame.toUpperCase()} → {c.targetGame.toUpperCase()}
                  </span>
                ) : null}
                <span className="chip">{c.relationshipLabel}</span>
              </div>
              {c.sourceEvidenceLabel ? (
                <p className="cg-source-ev">
                  <strong>Source value used:</strong> {c.sourceEvidenceLabel}
                </p>
              ) : null}
              {c.discrepancyNote ? (
                <p className="cg-discrepancy" role="alert">
                  <strong>Value mismatch noticed:</strong> {c.discrepancyNote}
                </p>
              ) : null}
              <p className="cg-summary">{c.summary}</p>
              <div className="cg-cols">
                {c.valorantSettings.length ? (
                  <div className="cg-col">
                    <span className="layer-label">VALORANT</span>
                    <ul>
                      {c.valorantSettings.map((s) => (
                        <li key={s.settingId}>
                          {s.label}: <strong>{s.currentDisplay}</strong>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {c.cs2Settings.length ? (
                  <div className="cg-col">
                    <span className="layer-label">CS2</span>
                    <ul>
                      {c.cs2Settings.map((s) => (
                        <li key={s.settingId}>
                          {s.label}: <strong>{s.currentDisplay}</strong>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
              {c.sensitivityConversion ? (
                <div className="cg-sens-note">
                  {c.sensitivityConversion.convertible ? (
                    <>
                      <strong>360° hipfire estimate:</strong> {c.sensitivityConversion.formula}
                      <ul>
                        {c.sensitivityConversion.caveats.map((cv) => (
                          <li key={cv}>{cv}</li>
                        ))}
                      </ul>
                    </>
                  ) : (
                    <span>{c.sensitivityConversion.reason}</span>
                  )}
                </div>
              ) : null}
              <p className="cg-diff">{c.differences}</p>
              <p className="cg-safety">{c.safetyNote}</p>
              {c.targetNavigateId ? (
                <button
                  type="button"
                  className="btn btn-small"
                  onClick={() => void navigateCrossGame(c.targetNavigateGame ?? game, c.targetNavigateId!)}
                >
                  {c.targetNavigateGame && c.targetNavigateGame !== game
                    ? `Show in ${gameName(c.targetNavigateGame)} settings`
                    : "Show in settings"}
                </button>
              ) : null}
            </div>
          ))}
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

      {res.appliedMemoryUpdates?.length ? (
        <div className="msg-memory-list" aria-label="Saved to System Understanding">
          {res.appliedMemoryUpdates.map((m) => {
            const isUndone = Boolean(undoneMemoryIds[m.id]);
            return (
              <div key={m.id} className={`msg-memory-pill ${isUndone ? "is-undone" : ""}`}>
                <span>
                  {isUndone ? (
                    <>Removed from System Understanding: {m.label}</>
                  ) : (
                    <>
                      <strong>Saved to System Understanding:</strong> {m.label}
                    </>
                  )}
                </span>
                {!isUndone ? (
                  <button
                    type="button"
                    className="btn btn-small btn-ghost"
                    onClick={() => {
                      setUndoneMemoryIds((prev) => ({ ...prev, [m.id]: true }));
                      void undoMemoryUpdate(m);
                    }}
                  >
                    Undo
                  </button>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}

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
              <span className="progress-simple">
                {participantStepLabel(run.steps[run.steps.length - 1]?.label)}
              </span>
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
