import { useEffect, useRef, useState } from "react";
import type { AssistantResponse, ChatMessage, GameId, PreferenceSuggestion, Recommendation } from "../api/types";
import { EMPTY, useAppStore } from "../store/useAppStore";
import { RecommendationCard, type CardModel } from "./RecommendationCard";

const STARTERS: Record<GameId, string[]> = {
  valorant: [
    "I'm getting frame drops in VALORANT and want smoother competitive play. What should I change?",
    "What does anti-aliasing do?",
    "I care more about visibility than visual effects.",
    "Where is the minimap zoom setting?",
  ],
  cs2: [
    "I'm new to CS2. What should I change based on what I liked in VALORANT?",
    "I can't see enemies well in dark corners.",
    "What does Boost Player Contrast do?",
    "Where is the V-Sync setting?",
  ],
};

function recCard(r: Recommendation, response: AssistantResponse, state: CardModel["state"]): CardModel {
  const ai = response.provenance.source === "ai";
  return {
    key: r.settingId,
    label: r.label,
    path: r.path,
    from: r.currentDisplay,
    to: r.proposedDisplay,
    whatItDoes: r.whatItDoes,
    whatItDoesSource: r.whatItDoesSource,
    why: r.whyForGoal,
    whyOrigin: ai ? "written by the local AI" : "offline fallback rule, not AI",
    tradeoff: r.tradeoff,
    basedOn: r.basedOn ? [r.basedOn] : [],
    crossGame: Boolean(r.crossGame),
    dimensionLabel: r.dimensionLabel,
    verificationStatus: r.verificationStatus,
    sourceURL: r.sourceURL,
    provenance: ai ? "ai" : "fallback",
    state,
  };
}

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
          {dims.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
        </select>
        <select value={scope} onChange={(e) => setScope(e.target.value as "session" | "durable")} aria-label="Preference scope">
          <option value="session">this session only</option>
          <option value="durable">lasting (all games)</option>
        </select>
      </div>
      <p className="pref-quote">“{s.quote}”</p>
      <div className="pref-actions">
        <button type="button" className="btn btn-small btn-primary" onClick={() => { void confirm(s, scope, dim); setDone("saved"); }}>Save preference</button>
        <button type="button" className="btn btn-small btn-ghost" onClick={() => setDone("declined")}>No thanks</button>
      </div>
    </div>
  );
}

function AssistantMessage({ game, msg }: { game: GameId; msg: ChatMessage }) {
  const res = msg.response!;
  const stage = useAppStore((s) => s.stage);
  const goToSetting = useAppStore((s) => s.goToSetting);
  const staged = useAppStore((s) => s.proposals[game]);
  const values = useAppStore((s) => s.states[game]?.values);
  const [showFiltered, setShowFiltered] = useState(false);
  const ai = res.provenance.source === "ai";
  const stagedIds = new Set((staged ?? []).flatMap((p) => p.items.filter((i) => i.status === "pending").map((i) => i.settingId)));

  const stateOf = (r: Recommendation): CardModel["state"] => {
    if (stagedIds.has(r.settingId)) return "staged";
    const cur = values?.[r.settingId]?.value;
    if (cur !== undefined && String(cur) === String(r.proposedValue)) return "applied";
    if (cur !== undefined && String(cur) !== String(r.currentValue)) return "changed";
    return "suggested";
  };
  const open = res.recommendations.filter((r) => stateOf(r) === "suggested");

  return (
    <div className="msg msg-assistant">
      <div className={`msg-prov ${ai ? "is-ai" : "is-fallback"}`}>
        {ai ? (
          <>Local AI · <code>{res.provenance.model}</code>{res.provenance.latencyMs ? ` · ${(res.provenance.latencyMs / 1000).toFixed(1)} s` : ""}</>
        ) : (
          <>Offline fallback — rule-based, not AI-generated{res.provenance.fallbackReason ? ` · ${res.provenance.fallbackReason}` : ""}</>
        )}
      </div>
      <p className="msg-text">{res.reply}</p>
      {res.validationNotes.map((n) => <p key={n} className="msg-note" role="note">⚠ {n}</p>)}
      {res.knownsAndUnknowns ? <p className="msg-unknowns"><span>What I can't know:</span> {res.knownsAndUnknowns}</p> : null}
      {res.clarifyingQuestion ? <p className="msg-question">{res.clarifyingQuestion}</p> : null}
      {res.recommendations.length ? (
        <div className="msg-recs">
          {res.recommendations.map((r) => (
            <RecommendationCard key={r.settingId} card={recCard(r, res, stateOf(r))}
              onShow={() => goToSetting(game, r.settingId, "assistant")}
              onStage={() => void stage(game, [r], ai ? "ai" : "fallback", msg.runId, `Chat: ${r.label}`)} />
          ))}
          {open.length > 1 ? (
            <button type="button" className="btn btn-primary stage-all" onClick={() => void stage(game, open, ai ? "ai" : "fallback", msg.runId, "Chat suggestions")}>
              Stage all {open.length} for review
            </button>
          ) : null}
        </div>
      ) : null}
      {res.explanations.map((e) => (
        <div key={e.settingId} className="explain-card">
          <div className="rec-title"><strong>{e.label}</strong><span className="rec-path">{e.path}</span></div>
          <div className="layer">
            <span className="layer-label">What it does <small>(catalogue{e.verificationStatus === "verified-game-files" ? ": Valve tooltip" : ""})</small></span>
            <p>{e.catalogDescription}</p>
          </div>
          {e.explanation && e.explanation !== e.catalogDescription ? (
            <div className="layer"><span className="layer-label">Assistant’s explanation <small>({ai ? "local AI" : "fallback"})</small></span><p>{e.explanation}</p></div>
          ) : null}
          {e.tradeoffs ? <div className="layer"><span className="layer-label">Trade-offs</span><p>{e.tradeoffs}</p></div> : null}
          <button type="button" className="btn btn-small" onClick={() => goToSetting(game, e.settingId, "assistant")}>Show in settings</button>
        </div>
      ))}
      {res.navigateTo ? (
        <button type="button" className="btn btn-small" onClick={() => goToSetting(game, res.navigateTo!.settingId, "assistant")}>
          Show {res.navigateTo.label} ({res.navigateTo.path})
        </button>
      ) : null}
      {res.preferenceSuggestions.map((p) => <PreferenceChip key={`${p.dimension}-${p.scope}`} s={p} />)}
      {res.filtered.length ? (
        <div className="msg-filtered">
          <button type="button" className="link" aria-expanded={showFiltered} onClick={() => setShowFiltered((v) => !v)}>
            {res.filtered.length} item{res.filtered.length > 1 ? "s" : ""} removed by safety checks
          </button>
          {showFiltered ? <ul>{res.filtered.map((f, i) => <li key={i}><code>{f.kind}</code> {f.reason}</li>)}</ul> : null}
        </div>
      ) : null}
    </div>
  );
}

export function Chat({ game }: { game: GameId }) {
  const thread = useAppStore((s) => s.chat[game] ?? EMPTY);
  const run = useAppStore((s) => s.runs[game]);
  const send = useAppStore((s) => s.sendChat);
  const cancel = useAppStore((s) => s.cancelRun);
  const clear = useAppStore((s) => s.clearChat);
  const prefill = useAppStore((s) => s.composerPrefill);
  const [text, setText] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    // Show progress at the bottom while running; show a new answer from its first line (answers can be long).
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
            <p>Describe what you want to improve. The assistant can find, explain and suggest real {game === "cs2" ? "CS2" : "VALORANT"} settings; you review and apply every change.</p>
            <div className="starters">
              {STARTERS[game].map((s) => <button key={s} type="button" className="starter" onClick={() => setText(s)}>{s}</button>)}
            </div>
          </div>
        ) : null}
        {thread.map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="msg msg-user"><p>{m.text}</p></div>
          ) : m.role === "assistant" && m.response ? (
            <AssistantMessage key={m.id} game={game} msg={m} />
          ) : (
            <div key={m.id} className="msg msg-system"><p>{m.text}</p></div>
          ),
        )}
        {run ? (
          <div className="msg msg-progress" aria-live="polite">
            <ol>{run.steps.map((s, i) => <li key={i} className={i === run.steps.length - 1 ? "is-current" : ""}>{s.label}</li>)}</ol>
            <span className="progress-time">{run.elapsedMs ? `${(run.elapsedMs / 1000).toFixed(1)} s` : ""}</span>
          </div>
        ) : null}
        <div ref={endRef} />
      </div>
      <div className="composer">
        <textarea ref={inputRef} value={text} rows={2} maxLength={1000} placeholder="Ask about a goal, a setting, or a preference…"
          aria-label="Message the assistant" disabled={Boolean(run)}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }} />
        <div className="composer-actions">
          {run ? (
            <button type="button" className="btn btn-danger" onClick={() => void cancel(game)}>Cancel</button>
          ) : (
            <button type="button" className="btn btn-primary" disabled={!text.trim()} onClick={submit}>Send</button>
          )}
          {thread.length ? <button type="button" className="btn btn-ghost btn-small" disabled={Boolean(run)} onClick={() => void clear(game)}>Clear chat</button> : null}
        </div>
      </div>
    </section>
  );
}
