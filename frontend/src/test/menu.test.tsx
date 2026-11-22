import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Setting } from "../api/types";
import { SettingControl } from "../components/controls/Controls";
import { useGameView } from "../components/settings/useGameView";
import { ValorantMenu } from "../games/valorant/ValorantMenu";
import { useAppStore } from "../store/useAppStore";
import { CATALOG, PROPOSAL, SETTINGS, STATE, session } from "./fixtures";

function Menu() {
  const view = useGameView("valorant");
  return <ValorantMenu view={view} />;
}

function seed(condition: "baseline" | "adaptive", withProposal = true) {
  const byId = Object.fromEntries(SETTINGS.map((s) => [s.id, s]));
  const byKey = Object.fromEntries(SETTINGS.map((s) => [s.key, s]));
  useAppStore.setState({
    session: session(condition),
    catalogs: { valorant: CATALOG },
    byId: { valorant: byId },
    byKey: { valorant: byKey },
    states: { valorant: STATE },
    proposals: { valorant: withProposal ? [PROPOSAL] : [] },
    nav: { valorant: { tabId: "video", subtabId: "graphics_quality" }, cs2: { tabId: "video", subtabId: "advanced" } },
    highlight: null,
    pendingVideo: {},
  });
}

const rowOrder = (container: HTMLElement) =>
  Array.from(container.querySelectorAll<HTMLElement>("[data-setting-id]")).map((el) => el.dataset.settingId);

describe("canonical menu parity between conditions", () => {
  beforeEach(() => seed("baseline"));

  it("renders the same rows in the same order in baseline and adaptive", () => {
    const baseline = render(<Menu />);
    const baseOrder = rowOrder(baseline.container);
    baseline.unmount();
    seed("adaptive");
    const adaptive = render(<Menu />);
    expect(rowOrder(adaptive.container)).toEqual(baseOrder);
    expect(baseOrder).toEqual(SETTINGS.map((s) => s.id));
  });

  it("shows no AI affordances in the baseline, even when proposals exist", () => {
    const { container } = render(<Menu />);
    expect(container.querySelectorAll(".row-tools")).toHaveLength(0);
    expect(screen.queryByText(/Staged/)).toBeNull();
    expect(screen.queryByTitle(/Locked from AI changes/)).toBeNull();
  });

  it("shows staged, lock and pin affordances on the original rows in the adaptive condition", () => {
    seed("adaptive");
    const { container } = render(<Menu />);
    const bloom = container.querySelector('[data-setting-id="val.video.bloom"]') as HTMLElement;
    expect(within(bloom).getByText("Staged → Off")).toBeInTheDocument();
    const vsync = container.querySelector('[data-setting-id="val.video.vsync"]') as HTMLElement;
    expect(within(vsync).getByTitle(/Locked from AI changes/)).toBeInTheDocument();
    expect(within(vsync).getByRole("button", { name: /Unlock VSync/ })).toBeInTheDocument();
  });

  it("highlights the existing row without reordering", () => {
    seed("adaptive");
    const { container } = render(<Menu />);
    const before = rowOrder(container);
    act(() => useAppStore.setState({ highlight: { game: "valorant", settingId: "val.video.anti_aliasing", nonce: 1, reason: "assistant" } }));
    const row = container.querySelector('[data-setting-id="val.video.anti_aliasing"]') as HTMLElement;
    expect(row.className).toContain("is-highlighted");
    expect(rowOrder(container)).toEqual(before);
  });

  it("disables a dependent child setting until its parent has the required value", () => {
    const { container } = render(<Menu />);
    const child = container.querySelector('[data-setting-id="val.video.fixed_orientation"]') as HTMLElement;
    expect(child.className).toContain("is-disabled");
    within(child).getAllByRole("radio").forEach((b) => expect(b).toBeDisabled());
  });
});

describe("controls", () => {
  const seg = SETTINGS[0];
  const dropdown = SETTINGS[2];

  it("segmented control supports click and arrow keys", async () => {
    const onChange = vi.fn();
    render(<SettingControl game="valorant" setting={seg} value="on" labelId="l" onChange={onChange} />);
    await userEvent.click(screen.getByRole("radio", { name: "Off" }));
    expect(onChange).toHaveBeenLastCalledWith("off");
    fireEvent.keyDown(screen.getByRole("radiogroup"), { key: "ArrowRight" });
    expect(onChange).toHaveBeenLastCalledWith("off");
  });

  it("dropdown only offers catalogue options", () => {
    const onChange = vi.fn();
    render(<SettingControl game="valorant" setting={dropdown} value="msaa_4x" labelId="l" onChange={onChange} />);
    const options = screen.getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["None", "MSAA 2x", "MSAA 4x"]);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "msaa_2x" } });
    expect(onChange).toHaveBeenCalledWith("msaa_2x");
  });

  it("slider text entry clamps to the verified range and commits on Enter", () => {
    const slider: Setting = { ...seg, id: "cs2.video.fps_max", game: "cs2", controlType: "slider", validOptions: null, min: 64, max: 1000, step: 1, precision: 0, unit: "FPS" };
    const onChange = vi.fn();
    render(<SettingControl game="cs2" setting={slider} value={400} labelId="l" onChange={onChange} />);
    const box = screen.getByLabelText(/value/);
    fireEvent.change(box, { target: { value: "5000" } });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith(1000);
  });

  it("keybind capture maps keys to the game's key names", async () => {
    const kb: Setting = { ...seg, id: "cs2.kbmouse.key_jump", game: "cs2", controlType: "keybind", validOptions: null, aiProposable: false };
    const onChange = vi.fn();
    render(<SettingControl game="cs2" setting={kb} value="SPACE" labelId="l" onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "SPACE" }));
    expect(screen.getByRole("button", { name: "Press a key…" })).toBeInTheDocument();
    fireEvent.keyDown(window, { code: "ControlLeft", key: "Control" });
    expect(onChange).toHaveBeenCalledWith("CTRL");
  });
});

describe("CS2-style explicit apply", () => {
  it("keeps edits pending locally without calling the API until Apply", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network must not be called"));
    const explicit = { ...SETTINGS[1], id: "cs2.video.vsync", game: "cs2" as const, applyMode: "explicit" as const };
    useAppStore.setState({
      byId: { cs2: { [explicit.id]: explicit } },
      byKey: { cs2: { [explicit.key]: explicit } },
      states: { cs2: { ...STATE, game: "cs2", values: { [explicit.id]: { value: "on", revision: 0 } } } },
      pendingVideo: {},
    });
    await useAppStore.getState().changeSetting("cs2", explicit.id, "off");
    expect(useAppStore.getState().pendingVideo.cs2).toEqual({ [explicit.id]: "off" });
    await useAppStore.getState().changeSetting("cs2", explicit.id, "on");
    expect(useAppStore.getState().pendingVideo.cs2).toEqual({});
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
