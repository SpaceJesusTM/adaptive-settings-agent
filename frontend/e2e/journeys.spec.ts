import { expect, test } from "@playwright/test";
import { api, askAssistant, openExperimenter, openTab, row, rowOrder, setup, value } from "./helpers";

test.describe("A. Browse and change manually", () => {
  test("baseline: change a VALORANT setting, see history, undo, survive reload", async ({ page }) => {
    await setup(page, { condition: "baseline" });
    await expect(page.locator(".assistant")).toHaveCount(0);
    await expect(page.locator(".row-tools")).toHaveCount(0);
    await openTab(page, "Video", "Graphics Quality");
    const bloom = row(page, "val.video.bloom");
    await bloom.getByRole("radio", { name: "Off" }).click();
    await expect(page.locator(".toast").last()).toContainText("Bloom: On → Off");
    expect(await value(page, "valorant", "val.video.bloom")).toBe("off");

    await page.reload();
    await openTab(page, "Video", "Graphics Quality");
    await expect(row(page, "val.video.bloom").getByRole("radio", { name: "Off" })).toHaveAttribute("aria-checked", "true");

    await page.getByRole("button", { name: "History" }).click();
    const item = page.locator(".history-item").first();
    await expect(item).toContainText("Manual change");
    await expect(item).toContainText("On → Off");
    await item.getByRole("button", { name: "Undo" }).click();
    await expect.poll(() => value(page, "valorant", "val.video.bloom")).toBe("on");
  });

  test("search takes the user to the canonical row and highlights it", async ({ page }) => {
    await setup(page, { condition: "baseline" });
    await page.getByLabel("Search settings").fill("anti-aliasing");
    await page.getByRole("option", { name: /Anti-Aliasing/ }).first().click();
    const r = row(page, "val.video.anti_aliasing");
    await expect(r).toBeVisible();
    await expect(r).toHaveClass(/is-highlighted/);
    await expect(page.getByRole("tab", { name: /^graphics quality$/i })).toHaveAttribute("aria-selected", "true");
  });

  test("CS2 video edits stay pending until Apply Changes", async ({ page }) => {
    await setup(page, { condition: "baseline", game: "cs2" });
    await openTab(page, "Video", "Advanced Video");
    await row(page, "cs2.video.vsync").getByRole("combobox").selectOption({ label: "Disabled" });
    await expect(page.locator(".cs2-pending-note")).toContainText("1 unapplied change");
    expect(await value(page, "cs2", "cs2.video.vsync")).toBe("1");
    await page.getByRole("button", { name: "Apply Changes" }).click();
    await expect.poll(() => value(page, "cs2", "cs2.video.vsync")).toBe("0");
    await expect(page.locator(".cs2-pending-note")).toHaveCount(0);
  });

  test("selecting a CS2 video preset changes its member settings together", async ({ page }) => {
    await setup(page, { condition: "baseline", game: "cs2" });
    await openTab(page, "Video", "Advanced Video");
    await row(page, "cs2.video.video_preset").getByRole("combobox").selectOption({ label: "Low" });
    await expect(row(page, "cs2.video.msaa").getByRole("combobox")).toHaveValue("0");
    await page.getByRole("button", { name: "Apply Changes" }).click();
    await expect.poll(() => value(page, "cs2", "cs2.video.global_shadow_quality")).toBe("0");
  });
});

test.describe("Condition parity & participant vs experimenter presentation", () => {
  test("participant default hides A/B switcher, Study controls, Trace and model IDs", async ({ page }) => {
    await setup(page, { condition: "adaptive", aiMode: "fallback" });
    await expect(page.locator(".sb-sim-pill")).toBeVisible();
    await expect(page.getByRole("button", { name: "B · Adaptive" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Study controls" })).toHaveCount(0);
    await expect(page.getByRole("tab", { name: "Trace" })).toHaveCount(0);
    await expect(page.getByText(/Assistant offline — using basic suggestions/)).toBeVisible();

    await openExperimenter(page);
    await expect(page.getByRole("button", { name: "B · Adaptive" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Study controls" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Trace" })).toBeVisible();
  });

  for (const [game, tab, sub] of [
    ["valorant", "Video", "Graphics Quality"],
    ["cs2", "Video", "Advanced Video"],
  ] as const) {
    test(`${game}: identical canonical rows in both conditions`, async ({ page }) => {
      await setup(page, { condition: "baseline", game });
      await openTab(page, tab, sub);
      const baseline = await rowOrder(page);
      await openExperimenter(page);
      await page.getByRole("button", { name: "B · Adaptive" }).click();
      await expect(page.locator(".assistant")).toBeVisible();
      await openTab(page, tab, sub);
      expect(await rowOrder(page)).toEqual(baseline);
    });
  }
});

test.describe("B/D. Auto-staging, Adaptive Workspace, Pinned direct edits & Comprehensive setup", () => {
  test("chat auto-stages requested changes to Changes without applying; Apply and Undo work", async ({ page }) => {
    await setup(page, { condition: "adaptive", aiMode: "fallback" });
    const before = await api<{ values: Record<string, { value: unknown }> }>(page, "/api/games/valorant/state");
    await askAssistant(page, "I'm getting frame drops in VALORANT and want smoother competitive play. What should I change?");

    const msg = page.locator(".msg-assistant").last();
    await expect(msg.locator(".msg-prov")).toContainText("Assistant offline");
    await expect(msg.locator(".msg-staged-banner")).toContainText("ready to review — nothing has been applied");

    // Invariant: auto-stage does not modify actual stored values
    const afterStage = await api<{ values: Record<string, { value: unknown }> }>(page, "/api/games/valorant/state");
    expect(afterStage.values).toEqual(before.values);

    // Clicking Review N changes opens Workspace -> Changes
    await msg.getByRole("button", { name: /^Review \d+ changes?$/ }).click();
    await expect(page.locator(".aw-workspace.is-open .tray-item").first()).toBeVisible();

    await page.getByRole("button", { name: /^Apply selected changes/ }).click();
    await expect(page.locator(".toast").last()).toContainText("Applied");

    await page.getByRole("button", { name: "History" }).click();
    const item = page.locator(".history-item").first();
    await expect(item).toContainText("Fallback suggestion · user applied");
    await item.getByRole("button", { name: "Undo" }).click();
    await expect.poll(async () => {
      const now = await api<{ values: Record<string, { value: unknown }> }>(page, "/api/games/valorant/state");
      return Object.keys(before.values).every((k) => now.values[k]?.value === before.values[k].value);
    }).toBe(true);
  });

  test("comprehensive fresh-install setup stages >8 grouped changes across categories and applies cleanly", async ({ page }) => {
    await setup(page, { scenario: "fresh_install_comprehensive", condition: "adaptive", game: "cs2", aiMode: "fallback" });
    await askAssistant(page, "I just installed CS2; configure everything for competitive FPS and clarity.");

    const msg = page.locator(".msg-assistant").last();
    await expect(msg.locator(".msg-staged-banner")).toContainText(/\d+ changes ready to review/);
    await msg.getByRole("button", { name: /^Review \d+ changes?$/ }).click();

    await expect(page.locator(".aw-workspace .tray-section-group")).toHaveCount(3);
    const itemsCount = await page.locator(".aw-workspace .tray-item").count();
    expect(itemsCount).toBeGreaterThanOrEqual(12);

    await page.getByRole("button", { name: /^Apply selected changes/ }).click();
    await expect(page.locator(".toast").last()).toContainText(/Applied \d+ change/);
    expect(await value(page, "cs2", "cs2.video.vsync")).toBe("0");
    expect(await value(page, "cs2", "cs2.audio.eq_profile")).toBe("1");
  });

  test("Pinned allows direct manual edits (even when AI-locked), syncs with menu & undo, and guards CS2 Video drafts", async ({ page }) => {
    await setup(page, { condition: "adaptive", game: "valorant", aiMode: "fallback" });
    await openTab(page, "Video", "Graphics Quality");
    const vsync = row(page, "val.video.vsync");
    await vsync.hover();
    await vsync.getByRole("button", { name: /Pin VSync/ }).click();
    await vsync.getByRole("button", { name: /Lock VSync/ }).click();

    await page.getByRole("banner").getByRole("button", { name: /^Workspace/ }).click();
    await page.getByRole("tab", { name: /^Pinned/ }).click();
    const pinnedRow = page.locator('[data-pinned-id="val.video.vsync"]');
    await expect(pinnedRow).toContainText("AI locked");
    await pinnedRow.getByRole("radio", { name: "Off" }).click();
    await expect(pinnedRow).toContainText("Saved");
    await expect.poll(() => value(page, "valorant", "val.video.vsync")).toBe("off");
    expect(await api<unknown[]>(page, "/api/games/valorant/proposals")).toHaveLength(0);

    await pinnedRow.getByRole("button", { name: "Undo" }).click();
    await expect.poll(() => value(page, "valorant", "val.video.vsync")).toBe("on");
  });

  test("a locked setting is never suggested and cannot be applied through a proposal", async ({ page }) => {
    await setup(page, { condition: "adaptive", aiMode: "fallback" });
    await openTab(page, "Video", "Graphics Quality");
    const vsync = row(page, "val.video.vsync");
    await vsync.hover();
    await vsync.getByRole("button", { name: /Lock VSync/ }).click();
    await askAssistant(page, "I want lower input latency.");
    await page.getByRole("banner").getByRole("button", { name: /^Workspace/ }).click();
    await expect(page.locator(".aw-workspace .tray-item", { hasText: "VSync" })).toHaveCount(0);
    const prop = await api<{ status: string; items: { status: string }[] }>(page, "/api/proposals", "POST",
      { game: "valorant", source: "ai", items: [{ settingId: "val.video.vsync", proposedValue: "off" }] });
    expect(prop.items[0].status).toBe("blocked");
    expect(await value(page, "valorant", "val.video.vsync")).toBe("on");
  });

  test("preference correction is only saved after confirmation, with the chosen scope", async ({ page }) => {
    await setup(page, { condition: "adaptive", aiMode: "fallback" });
    await askAssistant(page, "I prefer visibility over visual effects, just for today.");
    const suggestion = page.locator(".pref-suggest").last();
    await expect(suggestion).toBeVisible();
    let profile = await api<{ preferences: unknown[] }>(page, "/api/profile");
    expect(profile.preferences).toHaveLength(0);
    await suggestion.getByRole("button", { name: "Save preference" }).click();
    await expect.poll(async () => (await api<{ preferences: { scope: string }[] }>(page, "/api/profile")).preferences.length).toBe(1);
    profile = await api<{ preferences: { scope: string }[] }>(page, "/api/profile");
    expect((profile.preferences[0] as { scope: string }).scope).toBe("session");
  });

  test("detached ?view=workspace loads independently, fills window height without footer bleed, hides main panels exclusively, and restores on close without reload", async ({
    page,
    context,
  }) => {
    await setup(page, { scenario: "fresh_install_comprehensive", condition: "adaptive", game: "valorant", aiMode: "fallback" });
    await expect(page.locator(".assistant")).toBeVisible();
    const detached = await context.newPage();
    await detached.setViewportSize({ width: 1280, height: 800 });
    await detached.goto("/?view=workspace&game=valorant");
    await expect(detached.locator(".standalone-shell")).toBeVisible();

    // Exclusive pop-out relocation: main window hides docked Assistant + Workspace and shows pop-out pill + Dock here
    await expect(page.locator(".assistant")).toHaveCount(0);
    await expect(page.locator(".aw-workspace")).toHaveCount(0);
    await expect(page.getByText(/Workspace popped out/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Dock here" })).toBeVisible();

    await detached.getByLabel("Message the assistant").fill("Configure everything for competitive FPS and clarity.");
    await detached.getByRole("button", { name: "Send" }).click();
    await detached.locator(".msg-assistant").last().waitFor({ timeout: 30_000 });
    await expect(detached.locator(".aw-workspace .tray-item").first()).toBeVisible();

    // Workspace pane uses full window height instead of being capped at 42vh
    const layoutMetrics = await detached.evaluate(() => {
      const body = document.querySelector(".aw-workspace.is-standalone .tray-body") as HTMLElement;
      const actions = document.querySelector(".aw-workspace.is-standalone .tray-actions") as HTMLElement;
      const maxHeight = getComputedStyle(body).maxHeight;
      body.scrollTop = Math.min(200, Math.max(0, body.scrollHeight - body.clientHeight));
      const bodyRect = body.getBoundingClientRect();
      const actionsRect = actions.getBoundingClientRect();
      return {
        maxHeight,
        bodyHeight: bodyRect.height,
        actionsBottom: actionsRect.bottom,
        bodyBottom: bodyRect.bottom,
      };
    });
    expect(layoutMetrics.maxHeight).toBe("none");
    expect(layoutMetrics.bodyHeight).toBeGreaterThan(500);
    expect(Math.abs(layoutMetrics.actionsBottom - layoutMetrics.bodyBottom)).toBeLessThanOrEqual(2);

    // Switching game updates URL ?game= and persists across reload
    await detached.getByRole("group", { name: "Game" }).getByRole("button", { name: "CS2" }).click();
    await expect.poll(() => new URL(detached.url()).searchParams.get("game")).toBe("cs2");
    await detached.reload();
    await expect(detached.getByRole("group", { name: "Game" }).getByRole("button", { name: "CS2" })).toHaveAttribute("aria-pressed", "true");

    // Main window picks up synchronized state
    await page.bringToFront();
    await expect(page.getByRole("group", { name: "Game" }).getByRole("button", { name: "CS2" })).toHaveAttribute("aria-pressed", "true");

    // Closing detached window restores main window Assistant without browser reload
    await detached.close();
    await expect(page.locator(".assistant")).toBeVisible({ timeout: 12_000 });
    await expect(page.getByText(/Workspace popped out/)).toHaveCount(0);
  });
});

test.describe("C/E. Discover & cross-game transfer", () => {
  test("Discover surfaces cross-game suggestions without copying numeric sensitivity values and holds cards across reload", async ({ page }) => {
    await setup(page, { scenario: "valorant_history_new_cs2", condition: "adaptive", game: "cs2", aiMode: "fallback" });
    const before = await api<{ values: Record<string, { value: unknown }> }>(page, "/api/games/cs2/state");
    await page.getByRole("banner").getByRole("button", { name: /^Workspace/ }).click();
    await page.getByRole("tab", { name: /^Discover/ }).click();

    const rn = page.locator(".rn");
    await expect(rn.locator(".rec-card").first()).toBeVisible();
    await expect(rn.locator(".rec-basis").first()).toContainText("in VALORANT");
    const labels = await rn.locator(".rec-title strong").allTextContents();
    expect(labels).not.toContain("Mouse Sensitivity");

    await page.reload();
    await page.getByRole("banner").getByRole("button", { name: /^Workspace/ }).click();
    await page.getByRole("tab", { name: /^Discover/ }).click();
    await expect(page.locator(".rn .rec-title strong")).toHaveCount(labels.length);

    await page.locator(".rn .rec-card").first().getByRole("button", { name: "Prepare for review" }).click();
    await expect(page.locator(".aw-workspace .tray-item").first()).toBeVisible();
    const after = await api<{ values: Record<string, { value: unknown }> }>(page, "/api/games/cs2/state");
    expect(after.values).toEqual(before.values);
  });

  test("experimenter simulated context event populates Discover", async ({ page }) => {
    await setup(page, { condition: "adaptive", aiMode: "fallback" });
    await openExperimenter(page);
    await page.getByRole("button", { name: "Study controls" }).click();
    await page.getByRole("button", { name: /Frame-rate dips/ }).click();
    await page.getByRole("banner").getByRole("button", { name: /^Workspace/ }).click();
    await page.getByRole("tab", { name: /^Discover/ }).click();
    await expect(page.locator(".rn-context")).toContainText("Simulated event");
    await expect(page.locator(".rn .rec-card").first()).toBeVisible();
  });
});

test.describe("VALORANT Crosshair & CS2 HUD Edge Positions & New tab", () => {
  test("VALORANT Crosshair profiles, SVG reactive preview, import code & reload persistence", async ({ page }) => {
    await setup(page, { condition: "baseline", game: "valorant" });
    await openTab(page, "Crosshair", "Primary");
    await expect(page.getByTestId("val-crosshair-bar")).toBeVisible();
    await expect(page.getByTestId("val-crosshair-preview")).toBeVisible();

    const dotRow = row(page, "val.crosshair.primary_center_dot");
    await dotRow.getByRole("radio", { name: "On" }).click();
    await expect.poll(() => value(page, "valorant", "val.crosshair.primary_center_dot")).toBe("on");

    await page.getByRole("button", { name: "Import Code" }).click();
    await page.getByRole("textbox", { name: "Crosshair profile code" }).fill("0;P;c;5;h;0;0l;4;0o;2;0a;1;0f;0;1b;0");
    await page.getByLabel("Imported profile name").fill("Pro Cyan");
    await page.getByRole("button", { name: "Import", exact: true }).click();
    await expect.poll(() => value(page, "valorant", "val.crosshair.primary_color")).toBe("cyan");

    await page.reload();
    await openTab(page, "Crosshair", "Primary");
    await expect(row(page, "val.crosshair.primary_color").getByRole("combobox")).toHaveValue("cyan");
  });

  test("CS2 Video → HUD Edge Positions live safezone preview saves via Done separately from Video Apply Changes", async ({ page }) => {
    await setup(page, { condition: "baseline", game: "cs2" });
    // Stage an unapplied Video change first
    await openTab(page, "Video", "Advanced Video");
    await row(page, "cs2.video.vsync").getByRole("combobox").selectOption({ label: "Disabled" });
    await expect(page.locator(".cs2-pending-note")).toContainText("1 unapplied change");

    // Open HUD Edge Positions -> live preview updates -> Done saves immediately without applying V-Sync!
    await openTab(page, "Video", "HUD Edge Positions");
    await expect(page.getByTestId("cs2-hud-edge-editor")).toBeVisible();
    await page.getByLabel("Horizontal Adjustment").fill("0.70");
    await expect(page.getByTestId("cs2-hud-safezone")).toHaveAttribute("style", /inset:\s*0%\s*15%|left:\s*15/);
    await page.getByRole("button", { name: "Done" }).click();
    await expect.poll(() => value(page, "cs2", "cs2.video.hud_edge_x")).toBe(0.7);
    expect(await value(page, "cs2", "cs2.video.vsync")).toBe("1");

    // Switching back to Video -> Advanced Video shows the unapplied V-Sync draft still pending
    await openTab(page, "Video", "Advanced Video");
    await expect(page.locator(".cs2-pending-note")).toContainText("1 unapplied change");

    // New tab works cleanly
    await page.getByRole("tab", { name: "New" }).click();
    await expect(page.getByTestId("cs2-promoted-tab")).toBeVisible();
  });
});

test.describe("Final HCI Pass journeys: History provenance, Aligned review, My Priorities, Adaptive Onboarding & Cross-Game Helper", () => {
  test("History displays truthful provenance + live state + safe Review & restage without silent apply", async ({ page }) => {
    await setup(page, { condition: "adaptive", game: "valorant", aiMode: "fallback" });
    await askAssistant(page, "I want lower input latency.");
    await page.getByRole("banner").getByRole("button", { name: /^Workspace/ }).click();
    await expect(page.locator(".aw-workspace .tray-item").first()).toBeVisible();
    await page.getByRole("button", { name: /Apply selected changes/ }).click();
    await expect.poll(() => value(page, "valorant", "val.video.vsync")).toBe("off");

    // Manual override makes the AI batch partially superseded ("Changed since" + "(now On)")
    await openTab(page, "Video", "Graphics Quality");
    await row(page, "val.video.vsync").getByRole("radio", { name: "On" }).click();
    await expect.poll(() => value(page, "valorant", "val.video.vsync")).toBe("on");

    await page.getByRole("button", { name: "History" }).click();
    const items = page.locator(".history-item");
    await expect(items.nth(0)).toContainText("Manual edit — no assistant rationale was recorded.");
    await expect(items.nth(1)).toContainText("Original request:");
    await expect(items.nth(1)).toContainText("Changed since");
    await expect(items.nth(1)).toContainText("(now On)");

    await items.nth(1).getByRole("button", { name: "Why suggested & trade-offs" }).click();
    await expect(items.nth(1).locator(".history-why-list")).toBeVisible();

    // Review & restage creates an editable draft without changing VSync yet
    await items.nth(1).getByRole("button", { name: "Review & restage" }).click();
    await expect(page.locator(".aw-workspace .tray-proposal")).toContainText("Restaged from history");
    expect(await value(page, "valorant", "val.video.vsync")).toBe("on");
  });

  test("well_configured_competitive surfaces already-aligned settings and makes zero forced changes", async ({ page }) => {
    await setup(page, { scenario: "well_configured_competitive", condition: "adaptive", game: "valorant", aiMode: "fallback" });
    const before = await api<{ values: Record<string, { value: unknown }> }>(page, "/api/games/valorant/state");
    await askAssistant(page, "Configure everything for competitive FPS and clarity.");
    await expect(page.locator(".msg-aligned-box")).toBeVisible();
    await expect(page.locator(".msg-aligned-box")).toContainText("No changes needed to apply");
    await expect(page.locator(".msg-aligned-box").getByRole("button", { name: "Show in settings" }).first()).toBeVisible();
    const after = await api<{ values: Record<string, { value: unknown }> }>(page, "/api/games/valorant/state");
    expect(after.values).toEqual(before.values);
  });

  test("My Priorities displays 3 clear sections and persists confirmed personal setup facts without modifying game settings", async ({ page }) => {
    await setup(page, { condition: "adaptive", game: "valorant", aiMode: "fallback" });
    const before = await api<{ values: Record<string, { value: unknown }> }>(page, "/api/games/valorant/state");
    await page.getByRole("tab", { name: "My Priorities" }).click();

    await expect(page.getByText(/1\. Current goal/)).toBeVisible();
    await expect(page.getByText(/2\. General priorities/)).toBeVisible();
    await expect(page.getByText(/3\. Personal setup facts/)).toBeVisible();

    await page.getByLabel("Personal setup type").selectOption("push_to_talk_key");
    await page.getByLabel("Personal setup value").fill("V");
    await page.getByRole("button", { name: "Confirm fact" }).click();
    await expect(page.locator(".prefs .pref-item", { hasText: "Push-to-talk key" })).toContainText("V");

    await page.reload();
    await page.getByRole("tab", { name: "My Priorities" }).click();
    await expect(page.locator(".prefs .pref-item", { hasText: "Push-to-talk key" })).toContainText("V");
    const after = await api<{ values: Record<string, { value: unknown }> }>(page, "/api/games/valorant/state");
    expect(after.values).toEqual(before.values);
  });

  test("valorant_onboarding_to_cs2 surfaces inspect-only onboarding cards, persists completion across games, and triggers VSync-Off companion follow-up", async ({
    page,
  }) => {
    await setup(page, { scenario: "valorant_onboarding_to_cs2", condition: "adaptive", game: "cs2", aiMode: "fallback" });
    await page.getByRole("banner").getByRole("button", { name: /^Workspace/ }).click();
    await page.getByRole("tab", { name: /^Discover/ }).click();

    const rn = page.locator(".rn");
    await expect(rn).toContainText("Getting started in CS2");
    await expect(rn.locator(".chip", { hasText: "Manual control" }).first()).toBeVisible();
    await expect(rn.getByRole("button", { name: "Mark checked" }).first()).toBeVisible();

    // Mark the first inspect card checked and confirm completion persists across game switch
    const firstCard = rn.locator(".rec-card").first();
    await firstCard.getByRole("button", { name: "Mark checked" }).click();
    await expect(firstCard.locator(".state-badge")).toHaveText("Checked");
    await expect(rn.locator(".rn-count")).toHaveText("2");

    await page.getByRole("group", { name: "Game" }).getByRole("button", { name: "VALORANT" }).click();
    await page.getByRole("group", { name: "Game" }).getByRole("button", { name: "CS2" }).click();
    await page.getByRole("tab", { name: /^Discover/ }).click();
    await expect(rn.locator(".rec-card").first().locator(".state-badge")).toHaveText("Checked");
    await expect(rn.locator(".rn-count")).toHaveText("2");

    // Mark remaining onboarding cards checked -> Revisit first-time checks appears
    const markBtns = rn.getByRole("button", { name: "Mark checked" });
    while ((await markBtns.count()) > 0) {
      const beforeCount = await markBtns.count();
      await markBtns.first().click();
      await expect(markBtns).toHaveCount(beforeCount - 1);
    }
    await expect(rn.getByRole("button", { name: "Revisit first-time checks" })).toBeVisible();

    // Turning VSync Off manually in VALORANT (default scenario where Reflex is Off) triggers a companion follow-up in Discover
    await setup(page, { scenario: "default", condition: "adaptive", game: "valorant", aiMode: "fallback" });
    await openTab(page, "Video", "Graphics Quality");
    await row(page, "val.video.vsync").getByRole("radio", { name: "Off" }).click();
    await expect.poll(() => value(page, "valorant", "val.video.vsync")).toBe("off");
    await page.getByRole("banner").getByRole("button", { name: /^Workspace/ }).click();
    await page.getByRole("tab", { name: /^Discover/ }).click();
    const valRn = page.locator(".rn");
    const refreshBtn = valRn.getByRole("button", { name: "Refresh" });
    if (await refreshBtn.isVisible()) await refreshBtn.click();
    await expect(valRn).toContainText("Something worth checking after your recent change");
    await expect(valRn).toContainText("NVIDIA Reflex Low Latency");
  });

  test("Grounded cross-game comparison answers push-to-talk and 360° sensitivity 0.35 -> 1.11 without mutating settings", async ({ page }) => {
    await setup(page, { scenario: "valorant_onboarding_to_cs2", condition: "adaptive", game: "cs2", aiMode: "fallback" });
    const before = await api<{ values: Record<string, { value: unknown }> }>(page, "/api/games/cs2/state");
    await askAssistant(page, "What is the CS2 equivalent of VALORANT push-to-talk and what is 0.35 VALORANT sensitivity in CS2?");

    const cgList = page.locator(".cg-list");
    await expect(cgList).toBeVisible();
    await expect(cgList).toContainText("1.11");
    await expect(cgList).toContainText("Hipfire");
    await expect(cgList.getByRole("button", { name: "Show in settings" }).first()).toBeVisible();

    const after = await api<{ values: Record<string, { value: unknown }> }>(page, "/api/games/cs2/state");
    expect(after.values).toEqual(before.values);
  });
});
