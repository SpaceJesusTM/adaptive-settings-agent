import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { AdaptiveWorkspace } from "../adaptive/AdaptiveWorkspace";
import { AssistantPanel, PreferencesPanel } from "../adaptive/AssistantPanel";
import { Chat, participantStepLabel } from "../adaptive/Chat";
import { RelevantNow } from "../adaptive/RelevantNow";
import { StandaloneWorkspace } from "../adaptive/StandaloneWorkspace";
import { HistoryDrawer, Toasts } from "../components/chrome/HistoryDrawer";
import { StudyBar } from "../components/chrome/StudyBar";
import { HudEdgeEditor } from "../games/cs2/HudEdgeEditor";
import { ValorantCrosshairPreview } from "../games/valorant/ValorantCrosshairPreview";
import { useAppStore } from "../store/useAppStore";
import { CATALOG, PROPOSAL, SETTINGS, STATE, session } from "./fixtures";

function seedAdaptive(extra: Record<string, unknown> = {}) {
  const byId = Object.fromEntries(SETTINGS.map((s) => [s.id, s]));
  const byKey = Object.fromEntries(SETTINGS.map((s) => [s.key, s]));
  useAppStore.setState({
    ready: true,
    session: session("adaptive"),
    experimenterMode: false,
    workspaceOpen: true,
    detachedWorkspaceActive: false,
    workspaceTab: "changes",
    trayOpen: true,
    modelStatus: {
      state: "not_configured",
      indicator: "unavailable",
      indicatorLabel: "Ollama unavailable",
      model: "gemma4:12b-it-q4_K_M",
      baseUrl: "http://127.0.0.1:11434",
      ollamaVersion: null,
      details: null,
      capabilities: [],
      message: "Offline",
      aiMode: "local",
    },
    catalogs: { valorant: CATALOG },
    byId: { valorant: byId },
    byKey: { valorant: byKey },
    states: { valorant: { ...STATE, pins: ["val.video.bloom", "val.video.vsync"], locks: ["val.video.vsync"] } },
    proposals: { valorant: [PROPOSAL] },
    pendingVideo: {},
    pinnedFeedback: {},
    scenarios: [{ name: "default", title: "Default", description: "Default", synthetic: true }],
    contextTypes: [],
    relevantNow: {
      valorant: {
        game: "valorant",
        items: [],
        trigger: null,
        createdAt: null,
        updateAvailable: false,
        hasEvidence: false,
      },
    },
    ...extra,
  });
}

describe("participant vs experimenter presentation", () => {
  beforeEach(() => seedAdaptive());

  it("hides study condition, model IDs, Study controls and Trace in participant mode, and reveals them in experimenter mode", async () => {
    render(
      <>
        <StudyBar />
        <AssistantPanel game="valorant" />
      </>,
    );
    expect(screen.getByText(/Simulated settings/)).toBeInTheDocument();
    expect(screen.getByText(/Assistant offline — using basic suggestions/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "B · Adaptive" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Study controls" })).toBeNull();
    expect(screen.queryByRole("tab", { name: "Trace" })).toBeNull();
    expect(screen.queryByText(/gemma4:12b-it-q4_K_M/)).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Experimenter" }));
    expect(screen.getByRole("button", { name: "B · Adaptive" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Study controls" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Trace" })).toBeInTheDocument();
  });
});

describe("AdaptiveWorkspace Pinned & Changes behavior", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    seedAdaptive();
  });

  it("Pinned renders direct manual SettingControls, saves directly without staging, and allows editing AI-locked settings", async () => {
    const spy = vi.spyOn(api, "changeSetting").mockResolvedValue({
      batchId: "bat_pin_1",
      game: "valorant",
      source: "manual",
      sourceLabel: "Manual change",
      label: "VSync",
      condition: "adaptive",
      values: {},
      proposalId: null,
      undoesBatchId: null,
      undoneByBatchId: null,
      undoable: true,
      createdAt: new Date().toISOString(),
      gameRevision: 1,
      events: [],
    });
    vi.spyOn(api, "state").mockResolvedValue({
      ...STATE,
      pins: ["val.video.bloom", "val.video.vsync"],
      locks: ["val.video.vsync"],
      values: { ...STATE.values, "val.video.vsync": { value: "off", revision: 1 } },
    });
    vi.spyOn(api, "proposals").mockResolvedValue([PROPOSAL]);
    vi.spyOn(api, "thread").mockResolvedValue([]);
    vi.spyOn(api, "profile").mockResolvedValue({ preferences: [], sessionGoals: { valorant: [], cs2: [] }, context: { valorant: null, cs2: null }, evidence: [], dimensions: [] });
    vi.spyOn(api, "relevantNow").mockResolvedValue({ game: "valorant", items: [], trigger: null, createdAt: null, updateAvailable: false });

    seedAdaptive({ workspaceTab: "pinned" });
    render(<AdaptiveWorkspace game="valorant" mode="docked" />);

    const vsyncRow = screen.getByText("VSync").closest("li") as HTMLElement;
    expect(within(vsyncRow).getByText(/AI locked/)).toBeInTheDocument();
    await userEvent.click(within(vsyncRow).getByRole("radio", { name: "Off" }));
    expect(spy).toHaveBeenCalledWith("valorant", "val.video.vsync", "off", 0);
    expect(within(vsyncRow).getByRole("status")).toHaveTextContent(/Saved/);
    expect(within(vsyncRow).getByRole("button", { name: "Undo" })).toBeInTheDocument();
  });

  it("Pinned guards conflicting unapplied CS2 video edits instead of silently discarding them", async () => {
    const spy = vi.spyOn(api, "changeSetting");
    const cs2Vsync = {
      ...SETTINGS[0],
      id: "cs2.video.vsync",
      game: "cs2" as const,
      applyMode: "explicit" as const,
      validOptions: [
        { value: "0", label: "Disabled" },
        { value: "1", label: "Enabled" },
      ],
    };
    useAppStore.setState({
      session: { ...session("adaptive"), selectedGame: "cs2" },
      workspaceTab: "pinned",
      byId: { cs2: { "cs2.video.vsync": cs2Vsync } },
      byKey: { cs2: { vsync: cs2Vsync } },
      states: {
        cs2: {
          game: "cs2",
          gameRevision: 0,
          values: { "cs2.video.vsync": { value: "1", revision: 0 } },
          pins: ["cs2.video.vsync"],
          locks: [],
          pendingProposalIds: [],
          hardware: {},
        },
      },
      pendingVideo: { cs2: { "cs2.video.vsync": "0" } },
      proposals: { cs2: [] },
    });

    render(<AdaptiveWorkspace game="cs2" mode="docked" />);
    const row = screen.getByText("VSync").closest("li") as HTMLElement;
    expect(within(row).getByText(/Unapplied Video menu draft/)).toBeInTheDocument();
    await userEvent.click(within(row).getByRole("radio", { name: "Disabled" }));
    expect(spy).not.toHaveBeenCalled();
    expect(within(row).getByRole("button", { name: /Save now & clear Video draft/ })).toBeInTheDocument();
  });
});

describe("Crosshair and HUD Edge reactive previews", () => {
  it("VALORANT crosshair preview reacts to center dot and custom hex color", () => {
    const { container } = render(
      <ValorantCrosshairPreview
        mode="primary"
        values={{
          "val.crosshair.primary_color": "custom",
          "val.crosshair.primary_custom_color": "#00FFAA",
          "val.crosshair.primary_center_dot": "on",
          "val.crosshair.primary_center_dot_thickness": 4,
          "val.crosshair.primary_show_inner": "on",
        }}
      />,
    );
    const rects = Array.from(container.querySelectorAll("rect"));
    expect(rects.some((r) => r.getAttribute("width") === "4" && r.getAttribute("height") === "4")).toBe(true);
    const groups = Array.from(container.querySelectorAll("g"));
    expect(groups.some((g) => g.getAttribute("fill") === "#00FFAA")).toBe(true);
  });

  it("CS2 HUD Edge editor applies Valve safezone inset math dynamically", () => {
    const { container } = render(
      <HudEdgeEditor
        view={{
          game: "cs2",
          adaptive: false,
          byId: {},
          byKey: {},
          values: { "cs2.video.hud_edge_x": 0.7, "cs2.video.hud_edge_y": 0.8 },
          pending: {},
          staged: {},
        } as never}
      />,
    );
    const safezone = container.querySelector('[data-testid="cs2-hud-safezone"]') as HTMLElement;
    expect(safezone.style.left).toBe("15%");
    expect(safezone.style.top).toBe("10%");
  });
});

describe("PreferenceChip confirmation and participant progress feedback", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    seedAdaptive();
  });

  it("awaits backend response before showing Preference saved and allows retry on failure", async () => {
    const assistantMsg = {
      id: "msg_a1",
      role: "assistant" as const,
      runId: "run_1",
      createdAt: new Date().toISOString(),
      response: {
        intent: "preference",
        reply: "I can save this preference - confirm it below.",
        knownsAndUnknowns: null,
        goalDimensions: ["visibility"],
        recommendations: [],
        explanations: [],
        navigateTo: null,
        preferenceSuggestions: [
          {
            dimension: "visibility",
            dimensionLabel: "Visibility & clarity",
            direction: "prioritize" as const,
            scope: "durable" as const,
            quote: "I care more about visibility",
            game: "valorant" as const,
          },
        ],
        clarifyingQuestion: null,
        filtered: [],
        validationNotes: [],
        provenance: { source: "ai" as const, model: "local", indicator: "connected" },
      },
    };
    const addPrefSpy = vi
      .spyOn(api, "addPreference")
      .mockRejectedValueOnce(new Error("Network error"))
      .mockResolvedValueOnce({ id: "pref_1" });
    vi.spyOn(api, "state").mockResolvedValue(STATE);
    vi.spyOn(api, "proposals").mockResolvedValue([PROPOSAL]);
    vi.spyOn(api, "thread").mockResolvedValue([assistantMsg]);
    vi.spyOn(api, "profile").mockResolvedValue({
      preferences: [],
      sessionGoals: { valorant: [], cs2: [] },
      context: { valorant: null, cs2: null },
      evidence: [],
      dimensions: [{ id: "visibility", label: "Visibility & clarity" }],
    });
    vi.spyOn(api, "relevantNow").mockResolvedValue({
      game: "valorant",
      items: [],
      trigger: null,
      createdAt: null,
      updateAvailable: false,
    });

    seedAdaptive({
      profile: {
        preferences: [],
        sessionGoals: { valorant: [], cs2: [] },
        context: { valorant: null, cs2: null },
        evidence: [],
        dimensions: [{ id: "visibility", label: "Visibility & clarity" }],
      },
      chat: { valorant: [assistantMsg] },
    });

    render(<Chat game="valorant" />);
    await userEvent.click(screen.getByRole("button", { name: "Save preference" }));
    expect(addPrefSpy).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("alert")).toHaveTextContent(/Could not save preference/);
    expect(screen.queryByText("Preference saved.")).toBeNull();

    // Retry succeeds
    await userEvent.click(screen.getByRole("button", { name: "Save preference" }));
    expect(addPrefSpy).toHaveBeenCalledTimes(2);
    expect(await screen.findByText("Preference saved.")).toBeInTheDocument();
  });

  it("maps backend run steps to participant-safe labels without leaking model tags or tool names", () => {
    expect(participantStepLabel("Asking local model gemma4:12b-it-q4_K_M")).toBe("Checking relevant settings…");
    expect(participantStepLabel("Looking up: get_setting_details")).toBe("Checking relevant settings…");
    expect(participantStepLabel("Reviewing Video settings (1/2)")).toBe("Reviewing Video settings (1/2)…");
    expect(participantStepLabel("Writing suggestions")).toBe("Drafting recommendations (nothing applied yet)…");
    expect(participantStepLabel("Checking suggestions against the catalogue, locks and allowed values")).toBe(
      "Validating suggestions (nothing applied yet)…",
    );
  });
});

describe("StandaloneWorkspace & HistoryDrawer", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    seedAdaptive();
    window.history.replaceState(null, "", "/");
  });

  it("StandaloneWorkspace renders Study controls and Trace only when Experimenter mode is toggled on", async () => {
    seedAdaptive({
      traces: [],
      profile: {
        preferences: [],
        sessionGoals: { valorant: [], cs2: [] },
        context: { valorant: null, cs2: null },
        evidence: [],
        dimensions: [],
      },
    });
    vi.spyOn(api, "traces").mockResolvedValue([]);
    render(<StandaloneWorkspace />);

    expect(screen.getByRole("tab", { name: "Chat" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "My Priorities" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Study controls" })).toBeNull();
    expect(screen.queryByRole("tab", { name: "Trace" })).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Experimenter" }));
    expect(screen.getByRole("button", { name: "Study controls" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Trace" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Trace" }));

    await userEvent.click(screen.getByRole("button", { name: /Experimenter ✓/ }));
    expect(screen.queryByRole("button", { name: "Study controls" })).toBeNull();
    expect(screen.queryByRole("tab", { name: "Trace" })).toBeNull();
    expect(screen.getByRole("tab", { name: "Chat" })).toHaveAttribute("aria-selected", "true");
  });

  it("HistoryDrawer broadcasts navigation and shows a detached toast in ?view=workspace", async () => {
    window.history.replaceState(null, "", "/?view=workspace&game=valorant");
    try {
      seedAdaptive({
        historyOpen: true,
        toasts: [],
        history: {
          valorant: [
            {
              batchId: "bat_1",
              game: "valorant",
              source: "manual",
              sourceLabel: "Manual change",
              label: "VSync",
              condition: "adaptive",
              values: {},
              proposalId: null,
              undoesBatchId: null,
              undoneByBatchId: null,
              undoable: true,
              createdAt: new Date().toISOString(),
              gameRevision: 1,
              events: [
                {
                  eventId: "ev_1",
                  settingId: "val.video.vsync",
                  label: "VSync",
                  path: "Video > Graphics Quality > VSync",
                  oldValue: "on",
                  newValue: "off",
                  oldDisplay: "On",
                  newDisplay: "Off",
                },
              ],
            },
          ],
        },
      });
      render(
        <>
          <HistoryDrawer />
          <Toasts />
        </>,
      );

      await userEvent.click(screen.getByRole("button", { name: "VSync" }));
      expect(await screen.findByText(/Highlighted VSync in the main settings window/)).toBeInTheDocument();
    } finally {
      window.history.replaceState(null, "", "/");
    }
  });
});

describe("Final HCI Pass unit coverage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    seedAdaptive();
  });

  it("HistoryDrawer renders honest missing provenance on manual edits, AI rationale with trade-offs, live (now ...) diff, and Review & restage", async () => {
    const restageSpy = vi.spyOn(api, "restageHistory").mockResolvedValue({
      proposal: PROPOSAL,
      stagedCount: 1,
      alreadyAlignedItems: [],
      manualConsiderations: [],
      lockedItems: [],
      unavailableItems: [],
      message: "Restaged 1 change for review.",
    });
    vi.spyOn(api, "proposals").mockResolvedValue([PROPOSAL]);
    vi.spyOn(api, "state").mockResolvedValue(STATE);

    seedAdaptive({
      historyOpen: true,
      history: {
        valorant: [
          {
            batchId: "bat_manual",
            game: "valorant",
            source: "manual",
            sourceLabel: "Manual change",
            label: "VSync",
            condition: "adaptive",
            values: {},
            proposalId: null,
            undoesBatchId: null,
            undoneByBatchId: null,
            undoable: true,
            superseded: false,
            supersededCount: 0,
            createdAt: new Date().toISOString(),
            gameRevision: 2,
            provenance: { hasRecordedRationale: false },
            events: [
              {
                eventId: "ev_m",
                settingId: "val.video.vsync",
                label: "VSync",
                path: "Video > Graphics Quality > VSync",
                oldValue: "on",
                newValue: "off",
                oldDisplay: "On",
                newDisplay: "Off",
                currentDisplay: "Off",
                stillCurrent: true,
              },
            ],
          },
          {
            batchId: "bat_ai",
            game: "valorant",
            source: "proposal",
            sourceLabel: "Assistant suggestion applied",
            label: "Bloom",
            condition: "adaptive",
            values: {},
            proposalId: "prop_1",
            undoesBatchId: null,
            undoneByBatchId: null,
            undoable: false,
            superseded: true,
            supersededCount: 1,
            createdAt: new Date().toISOString(),
            gameRevision: 1,
            provenance: {
              hasRecordedRationale: true,
              userRequest: "Boost FPS without losing clarity",
              planReason: "Focused competitive tuning",
              restagedFromBatchId: null,
            },
            events: [
              {
                eventId: "ev_a",
                settingId: "val.video.bloom",
                label: "Bloom",
                path: "Video > Graphics Quality > Bloom",
                oldValue: "on",
                newValue: "off",
                oldDisplay: "On",
                newDisplay: "Off",
                currentDisplay: "On",
                stillCurrent: false,
                why: "Reduces post-process glow",
                tradeoff: "Slightly less stylized lighting",
                wasEditedByUser: false,
              },
            ],
          },
        ],
      },
    });

    render(<HistoryDrawer />);
    expect(screen.getByText(/Manual edit — no assistant rationale was recorded/)).toBeInTheDocument();
    expect(screen.getByText(/Boost FPS without losing clarity/)).toBeInTheDocument();
    expect(screen.getByText("Changed since")).toBeInTheDocument();
    expect(screen.getByText(/\(now On\)/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Why suggested & trade-offs" }));
    expect(screen.getByText(/Reduces post-process glow/)).toBeInTheDocument();
    expect(screen.getByText(/Slightly less stylized lighting/)).toBeInTheDocument();

    const restageBtns = screen.getAllByRole("button", { name: "Review & restage" });
    await userEvent.click(restageBtns[1]);
    expect(restageSpy).toHaveBeenCalledWith("bat_ai");
  });

  it("AdaptiveWorkspace surfaces Already aligned and Needs your decision without applying checkboxes to informational items", async () => {
    const propWithPlan = {
      ...PROPOSAL,
      plan: {
        scope: "comprehensive" as const,
        reason: "Full visual clarity audit",
        alreadyAlignedItems: [
          {
            settingId: "val.video.anti_aliasing",
            label: "Anti-Aliasing",
            path: "Video > Graphics Quality > Anti-Aliasing",
            currentDisplay: "MSAA 4x",
            why: "Edges are already clean.",
          },
        ],
        manualConsiderations: [
          {
            settingId: "val.video.rotate",
            label: "Rotate",
            path: "Video > Graphics Quality > Rotate",
            currentDisplay: "Rotate",
            reason: "Minimap orientation depends on habit",
          },
        ],
        lockedItems: [],
        unavailableItems: [],
      },
    };
    seedAdaptive({ proposals: { valorant: [propWithPlan] }, workspaceTab: "changes" });
    render(<AdaptiveWorkspace game="valorant" mode="docked" />);

    expect(screen.getByText("Already aligned (1)")).toBeInTheDocument();
    expect(screen.getByText("Needs your decision (1)")).toBeInTheDocument();

    // Only the real pending change ("Bloom") has an apply checkbox
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Apply selected changes (1)" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Show list" }));
    expect(screen.getByText("Edges are already clean.", { exact: false })).toBeInTheDocument();
  });

  it("My Priorities displays Goal, General priorities, Personal setup facts, conflict warnings, and saves manual facts", async () => {
    const addFactSpy = vi.spyOn(api, "addPersonalFact").mockResolvedValue({ id: "pf_2" });
    vi.spyOn(api, "profile").mockResolvedValue({
      preferences: [],
      sessionGoals: { valorant: [], cs2: [] },
      context: { valorant: null, cs2: null },
      evidence: [],
      dimensions: [],
      personalFacts: [],
      personalFactTypes: [],
      conflicts: { valorant: [], cs2: [] },
    });
    vi.spyOn(api, "relevantNow").mockResolvedValue({ game: "valorant", items: [], trigger: null, createdAt: null, updateAvailable: false });

    seedAdaptive({
      profile: {
        preferences: [
          {
            id: "pref_vis",
            dimension: "visibility",
            dimensionLabel: "Visibility & clarity",
            direction: "prioritize",
            scope: "durable",
            source: "user_explicit",
            originGame: "valorant",
            note: null,
            evidence: [{ source: "manual", detail: "High clarity", timestamp: new Date().toISOString() }],
            createdAt: new Date().toISOString(),
          },
        ],
        sessionGoals: {
          valorant: [{ id: "g1", text: "Highest competitive FPS", dimensions: ["performance"], createdAt: new Date().toISOString() }],
          cs2: [],
        },
        context: { valorant: null, cs2: null },
        evidence: [],
        dimensions: [{ id: "performance", label: "Framerate & performance" }],
        personalFacts: [
          {
            id: "pf_1",
            factKey: "push_to_talk_key",
            label: "Push-to-Talk key",
            valueText: "V",
            originGame: "valorant",
            sourceSettingId: null,
            source: "user_explicit",
            note: null,
            createdAt: new Date().toISOString(),
          },
        ],
        personalFactTypes: [
          { id: "mouse_sensitivity", label: "Mouse sensitivity (in-game)", placeholder: "e.g., 0.35 (VALORANT)" },
          { id: "push_to_talk_key", label: "Push-to-Talk key", placeholder: "e.g., V" },
        ],
        conflicts: {
          valorant: [
            {
              goalDimension: "performance",
              preferenceDimension: "visibility",
              preferenceDirection: "prioritize",
              explanation: "Framerate vs Visibility trade-off.",
            },
          ],
          cs2: [],
        },
      },
    });

    render(<PreferencesPanel game="valorant" />);
    expect(screen.getByText(/1\. Current goal/)).toBeInTheDocument();
    expect(screen.getByText(/2\. General priorities/)).toBeInTheDocument();
    expect(screen.getByText(/3\. Personal setup facts/)).toBeInTheDocument();
    expect(screen.getByText(/Priority trade-off:/)).toBeInTheDocument();
    expect(screen.getByText("V")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Personal setup value"), "0.35");
    await userEvent.click(screen.getByRole("button", { name: "Confirm fact" }));
    expect(addFactSpy).toHaveBeenCalledWith(
      expect.objectContaining({ factKey: "mouse_sensitivity", valueText: "0.35", originGame: "valorant", source: "user_explicit" }),
    );
  });

  it("Discover renders inspect-only manual controls with Mark checked instead of Prepare for review", async () => {
    const checkSpy = vi.spyOn(api, "markDiscoverChecked").mockResolvedValue({
      game: "cs2",
      items: [],
      trigger: null,
      createdAt: null,
      updateAvailable: false,
    });
    seedAdaptive({
      session: { ...session("adaptive"), selectedGame: "cs2" },
      openCards: { onb_ptt: true },
      relevantNow: {
        cs2: {
          game: "cs2",
          trigger: null,
          createdAt: new Date().toISOString(),
          updateAvailable: false,
          canRevisitOnboarding: false,
          items: [
            {
              cardId: "onb_ptt",
              checkId: "onb_ptt",
              kind: "inspect",
              triggerGroup: "onboarding",
              triggerLabel: "Getting started in CS2",
              settingId: "cs2.kbmouse.key_mic",
              label: "Use Mic",
              path: "Keyboard / Mouse > Communication Options > Use Mic",
              currentDisplay: "K",
              targetValue: "K",
              targetDisplay: "Check manually (never auto-changed)",
              whatItDoes: "Push-to-talk keybind.",
              whatItDoesSource: "official-doc",
              why: "You confirmed Push-to-Talk V in VALORANT.",
              whyBasis: "editorial",
              tradeoff: null,
              basedOn: ["Confirmed Push-to-Talk key = V (from VALORANT)"],
              crossGame: true,
              dimensionLabel: "Audio & comms",
              verificationStatus: "verified-game-files",
              sourceURL: "https://example.org",
              state: "suggested",
            },
          ],
        },
      },
    });

    render(<RelevantNow game="cs2" />);
    expect(screen.getByRole("heading", { name: "Getting started in CS2" })).toBeInTheDocument();
    expect(screen.getByText("Manual control")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Prepare for review" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Mark checked" }));
    expect(checkSpy).toHaveBeenCalledWith("cs2", "onb_ptt");
  });

  it("Chat renders Cross-Game Comparison cards with 360° hipfire estimate and Show in settings button", () => {
    const cgMsg = {
      id: "msg_cg",
      role: "assistant" as const,
      runId: "run_cg",
      createdAt: new Date().toISOString(),
      response: {
        intent: "explain" as const,
        reply: "Here is the comparison.",
        knownsAndUnknowns: null,
        goalDimensions: ["controls_input"],
        recommendations: [],
        explanations: [],
        navigateTo: null,
        preferenceSuggestions: [],
        crossGameComparisons: [
          {
            id: "cg_sensitivity",
            topic: "Mouse Sensitivity (360° hipfire)",
            relationship: "approximate_conversion" as const,
            relationshipLabel: "Approximate 360° math",
            summary: "Raw numbers differ across engines.",
            valorantSettings: [{ settingId: "val.general.sensitivity_aim", label: "Sensitivity: Aim", currentDisplay: "0.35" }],
            cs2Settings: [{ settingId: "cs2.kbmouse.mouse_sensitivity", label: "Mouse Sensitivity", currentDisplay: "1.25" }],
            sensitivityConversion: {
              convertible: true,
              valorantSens: 0.35,
              cs2Sens: 1.11,
              formula: "VALORANT 0.35 × (0.07 / 0.022) ≈ CS2 1.11",
              caveats: ["Hipfire 360° yaw only — ADS/scoped feel and FOV still differ."],
            },
            differences: "CS2 uses 90° 4:3 base HFOV vs VALORANT 103°.",
            safetyNote: "Sensitivities are personal; inspect manually.",
            targetNavigateId: "cs2.kbmouse.mouse_sensitivity",
          },
        ],
        clarifyingQuestion: null,
        filtered: [],
        validationNotes: [],
        provenance: { source: "ai" as const, model: "local", indicator: "connected" },
      },
    };
    seedAdaptive({
      session: { ...session("adaptive"), selectedGame: "cs2" },
      chat: { cs2: [cgMsg] },
    });
    render(<Chat game="cs2" />);
    expect(screen.getByText("Mouse Sensitivity (360° hipfire)")).toBeInTheDocument();
    expect(screen.getByText(/VALORANT 0\.35 × \(0\.07 \/ 0\.022\) ≈ CS2 1\.11/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show in settings" })).toBeInTheDocument();
  });
});
