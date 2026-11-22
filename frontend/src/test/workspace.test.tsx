import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { AdaptiveWorkspace } from "../adaptive/AdaptiveWorkspace";
import { AssistantPanel } from "../adaptive/AssistantPanel";
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
