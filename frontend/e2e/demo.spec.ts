import { expect, test } from "@playwright/test";

test.describe.configure({ mode: "serial" });

test("guided demo runs end to end on the real engine", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto("/demo");
  await page.getByRole("button", { name: "Run the whole demo" }).click();
  await expect(page.getByText("8/8 steps done")).toBeVisible({ timeout: 90_000 });
  // what each step actually returned
  await expect(page.getByText(/Understood: 5 people, needs elderly/)).toBeVisible();
  await expect(page.getByText(/not recognised, so nothing is guessed/)).toBeVisible();
  await expect(page.getByText(/citizen SOS RPT-\d+ at N43/)).toBeVisible();
  await expect(page.getByText(/committed, with [BG]\d+ chosen from \d+ feasible bid/)).toBeVisible();
  await expect(page.getByText(/\[TRIPLE_FAILURE\]|\[CLOSE_EDGE\]/).first()).toBeVisible();
  await expect(page.getByText(/0 grounding warning/)).toBeVisible();
  await expect(page.getByText(/Coordinator outage, multi-agent − centralised: service rate \+/)).toBeVisible();
  expect(errors).toEqual([]);
});

test("citizen SOS is placed and approved by a dispatcher in the UI", async ({ browser }) => {
  const ctx = await browser.newContext();
  const citizen = await ctx.newPage();
  await citizen.goto("/command");
  await citizen.getByRole("button", { name: "New run" }).waitFor();
  await citizen.goto("/sos");
  await citizen.getByRole("button", { name: "മലയാളം" }).click();
  await citizen.getByRole("button", { name: "Send SOS" }).click();
  await expect(citizen.getByText("Riverside Shiva Temple (N44)")).toBeVisible();
  await expect(citizen.getByText(/A dispatcher is confirming the location/)).toBeVisible();

  const dispatcher = await ctx.newPage();
  await dispatcher.goto("/command");
  await dispatcher.getByRole("button", { name: /Approvals ·/ }).click();
  await expect(dispatcher.getByText("Open citizen SOS at N44")).toBeVisible();
  await dispatcher.getByRole("button", { name: "Place & approve" }).click();
  await expect(dispatcher.getByText(/approved by dispatcher/).first()).toBeVisible();

  await citizen.bringToFront();
  await expect(citizen.getByText(/Received and in the queue|Help is assigned/)).toBeVisible();
  await ctx.close();
});

test("crew update queued without signal is rejected after the mission is cancelled", async ({ page, request }) => {
  await page.goto("/command");
  await page.getByRole("button", { name: "New run" }).waitFor();
  const sim = await page.evaluate(() => localStorage.getItem("resqnet.sim"));
  await page.goto("/crew/B1");
  await page.getByRole("button", { name: "Take crew control" }).click();
  let mission: string | undefined;
  for (let i = 0; i < 30 && !mission; i++) {
    const v = await (await request.get(`/api/simulations/${sim}/crew/B1`)).json();
    mission = v.mission?.assignment;
    if (!mission) await request.post(`/api/simulations/${sim}/step`, { data: { ticks: 1 } });
  }
  expect(mission).toBeTruthy();
  await page.getByRole("button", { name: "Accept mission" }).click();
  await expect(page.getByText("applied")).toBeVisible();
  await page.getByLabel("simulate no signal").check();
  await page.getByRole("button", { name: "Depart", exact: true }).click();
  await expect(page.getByText("queued", { exact: true })).toBeVisible();
  await request.post(`/api/simulations/${sim}/events`, { data: { type: "CANCEL_ASSIGNMENT", params: { assignment_id: mission, reason: "closer unit sent" } } });
  await page.getByLabel("simulate no signal").uncheck();
  await expect(page.getByText("rejected")).toBeVisible();
  await expect(page.getByText(/your depart update was not applied/)).toBeVisible();
});

test("evidence page renders the committed compliance matrix", async ({ page }) => {
  await page.goto("/research");
  await expect(page.getByRole("heading", { name: "PS 27 compliance and build checklist" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Simultaneous triple failure" })).toBeVisible();
  await page.getByRole("navigation", { name: "Documents" }).getByRole("link", { name: "Assumptions" }).click();
  await expect(page.getByRole("heading", { name: "Modelling assumptions and limitations" })).toBeVisible();
});

test("home page, navigation menus, new-run dialog and failure menu work", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /rescue keeps going/ })).toBeVisible();
  await page.getByRole("navigation", { name: "Main" }).getByRole("button", { name: "Results" }).click();
  await page.getByRole("menuitem", { name: /Benchmarks/ }).click();
  await expect(page).toHaveURL(/\/arena$/);
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Live console" }).click();
  await page.getByRole("button", { name: "New run" }).click();
  await expect(page.getByRole("dialog", { name: "Start a new run" })).toBeVisible();
  await page.getByRole("button", { name: /Aluva, Kerala/ }).click();
  await page.getByRole("button", { name: "Launch" }).click();
  await expect(page.getByText(/Aluva, Kerala · Multi-agent/)).toBeVisible();
  await page.getByRole("button", { name: "Simulate failure" }).click();
  await page.getByRole("menuitem", { name: /Flood surge/ }).click();
  await expect(page.getByText(/Flood surge \+0.5 m/).first()).toBeVisible();
  expect(errors).toEqual([]);
});
