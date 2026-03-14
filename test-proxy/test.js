"use strict";

const puppeteer = require("puppeteer");
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

// ─────────────────────────────────────────────
//  CONFIGURATION
// ─────────────────────────────────────────────
const DELAY_BETWEEN_PROXIES_MS = 10 * 1000; // minimum 30s between proxies — change here if needed
const DELAY_AFTER_LINK = 5 * 1000; // wait after link before opening earnapp dashboard
const CONTAINER_INIT_DELAY_MS = 10 * 1000; // wait after --start before opening earnapp link

const CHROMIUM_PATH = puppeteer.executablePath(); // ~/.cache/puppeteer/chrome/.../chrome

const TEST_PROXY_DIR = __dirname;
const SOURCE_DIR = path.join(TEST_PROXY_DIR, "..", "source");
const NODE_TEST_DIR = path.join(TEST_PROXY_DIR, "node-test");
const INPUT_FILE = path.join(TEST_PROXY_DIR, "input-proxy.txt");
const RESULT_FILE = path.join(TEST_PROXY_DIR, "result.txt");
const COOKIE_FILE = path.join(TEST_PROXY_DIR, "cookie.json");

const EARNAPP_DASHBOARD = "https://earnapp.com";

console.log(`Chromium: ${CHROMIUM_PATH}`);

// ─────────────────────────────────────────────
//  HELPERS
// ─────────────────────────────────────────────
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function readProxies() {
  const content = fs.readFileSync(INPUT_FILE, "utf-8");
  return content
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("#"));
}

function loadCookies() {
  const raw = fs.readFileSync(COOKIE_FILE, "utf-8");
  return JSON.parse(raw);
}

/** Copy source/ to node-test/ — recreate clean each time */
function copySource() {
  if (fs.existsSync(NODE_TEST_DIR)) {
    spawnSync("rm", ["-rf", NODE_TEST_DIR]);
  }
  spawnSync("cp", ["-r", SOURCE_DIR, NODE_TEST_DIR]);
}

/** Patch properties.conf inside node-test to enable earnapp and proxy */
function patchProperties() {
  const confPath = path.join(NODE_TEST_DIR, "properties.conf");
  let content = fs.readFileSync(confPath, "utf-8");
  content = content
    .replace(/^EARNAPP=.*$/m, "EARNAPP=true")
    .replace(/^USE_PROXIES=.*$/m, "USE_PROXIES=true")
    .replace(/^DEVICE_NAME=.*$/m, "DEVICE_NAME='test-proxy'");
  fs.writeFileSync(confPath, content);
}

/** Write single proxy to node-test/proxies.txt */
function setProxy(proxy) {
  const file = path.join(NODE_TEST_DIR, "proxies.txt");
  fs.writeFileSync(file, proxy + "\n");
}

/** Run a command inside node-test/, inherit stdio so output is visible */
function runInNode(cmd, args) {
  return spawnSync(cmd, args, {
    cwd: NODE_TEST_DIR,
    stdio: "inherit",
  });
}

/**
 * Run a command inside node-test/ and capture output for debugging.
 * Prints stdout/stderr and returns the result.
 */
function runInNodeDebug(cmd, args) {
  const result = spawnSync(cmd, args, {
    cwd: NODE_TEST_DIR,
    stdio: "pipe",
    encoding: "utf-8",
  });
  if (result.stdout) process.stdout.write(result.stdout);
  if (result.stderr) process.stderr.write(result.stderr);
  if (result.error) console.error("[spawnSync error]", result.error.message);
  console.log(`[exit code: ${result.status}]`);
  return result;
}

/** Start the node — always clean up first, then start */
function startNode() {
  // Verify node-test dir and key files exist before running
  const requiredFiles = ["internetIncome.sh", "properties.conf", "proxies.txt"];
  for (const f of requiredFiles) {
    const full = path.join(NODE_TEST_DIR, f);
    if (!fs.existsSync(full)) {
      throw new Error(`Missing required file in node-test/: ${f}`);
    }
  }

  console.log("[debug] Checking sudo access...");
  runInNodeDebug("sudo", ["-n", "true"]); // -n = non-interactive, fails fast if no NOPASSWD

  // console.log('[debug] Running --delete...');
  // runInNodeDebug('sudo', ['bash', 'internetIncome.sh', '--delete']);

  // console.log('[debug] Running --deleteBackup...');
  // runInNodeDebug('sudo', ['bash', 'internetIncome.sh', '--deleteBackup']);

  console.log("[debug] Running --start...");
  runInNodeDebug("sudo", ["bash", "internetIncome.sh", "--start"]);
}

/** Read earnapp link from earnapp.txt after --start */
function getEarnappLink() {
  const file = path.join(NODE_TEST_DIR, "earnapp.txt");
  if (!fs.existsSync(file)) return null;
  const lines = fs.readFileSync(file, "utf-8").split("\n");
  for (const line of lines) {
    const match = line.match(/https:\/\/earnapp\.com\/r\/\S+/);
    if (match) return match[0];
  }
  return null;
}

/** Stop and clean up node containers */
function stopNode() {
  runInNode("sudo", ["bash", "internetIncome.sh", "--delete"]);
  runInNode("sudo", ["bash", "internetIncome.sh", "--deleteBackup"]);
}

/** Get the outbound IP of a proxy via curl */
function getProxyIP(proxy) {
  const result = spawnSync("curl", [
    "--silent",
    "--max-time",
    "10",
    "--proxy",
    proxy,
    "https://api.ipify.org",
  ]);
  if (result.status === 0 && result.stdout) {
    return result.stdout.toString().trim();
  }
  return "unknown";
}

/** Append one result line to result.txt */
function writeResult(proxy, ip, success, reason) {
  const status = success ? "[OK  ]" : "[FAIL]";
  const line = `${status} ${proxy} | IP: ${ip} | ${reason}\n`;
  fs.appendFileSync(RESULT_FILE, line);
  console.log(line.trim());
}

// ─────────────────────────────────────────────
//  PUPPETEER ACTIONS  (fill in when ready)
// ─────────────────────────────────────────────

/**
 * Set earnapp.com cookies on the page and navigate to dashboard.
 * Called once at startup.
 */
async function loginWithCookies(page, cookies) {
  // Navigate first so the domain context exists for setCookie
  await page.goto("https://earnapp.com", {
    waitUntil: "networkidle2",
    timeout: 30000,
  });

  // Map cookie format from browser-export to Puppeteer
  const mapped = cookies.map((c) => ({
    name: c.name,
    value: c.value,
    domain: c.domain,
    path: c.path,
    secure: c.secure,
    httpOnly: c.httpOnly,
    sameSite: normalizeSameSite(c.sameSite),
    ...(c.expirationDate ? { expires: Math.floor(c.expirationDate) } : {}),
  }));

  await page.setCookie(...mapped);
  await page.goto(EARNAPP_DASHBOARD, {
    waitUntil: "networkidle2",
    timeout: 30000,
  });

  // Verify login: look for the "Dashboard" button by its stable class + role
  // <a href=".../dashboard/" class="btn_sign btn_sign_in" role="button">Dashboard</a>
  try {
    await page.waitForSelector('a.btn_sign_in[role="button"]', {
      timeout: 10000,
    });
    console.log("Login verified — Dashboard button found.");
  } catch {
    throw new Error(
      "Login failed — Dashboard button not found. Check cookie.json.",
    );
  }
}

/** Normalize sameSite value to Puppeteer-accepted format */
function normalizeSameSite(value) {
  if (!value) return undefined;
  const map = { strict: "Strict", lax: "Lax", no_restriction: "None" };
  return map[value.toLowerCase()] ?? undefined;
}

/**
 * Open the earnapp node link, confirm it was linked, then check the device
 * status on the passive-income dashboard.
 *
 * @returns {{ success: boolean, reason: string, ip: string }}
 */
async function verifyNodeOnDashboard(page, earnappLink) {
  // ── Step 1: open earnapp link, wait for one of two outcomes ──────────────
  await page.goto(earnappLink, { waitUntil: "networkidle2", timeout: 30000 });

  // Case 1 → newly linked:  link with href="/dashboard/me/passive-income" (stable href)
  // Case 2 → already linked: any element whose text contains "already linked" (stable text)
  try {
    await Promise.race([
      page.waitForSelector('a[href="/dashboard/me/passive-income"]', {
        timeout: 20000,
      }),
      page.waitForFunction(
        () => document.body.innerText.includes("already linked"),
        { timeout: 20000 },
      ),
    ]);
  } catch {
    return {
      success: false,
      reason: "Earnapp link page: confirmation element not found",
      ip: "unknown",
    };
  }

  const alreadyLinked = await page.evaluate(() =>
    document.body.innerText.includes("already linked"),
  );
  console.log(
    alreadyLinked
      ? "Note: device was already linked."
      : "Device linked successfully.",
  );
  await sleep(DELAY_AFTER_LINK);

  // ── Step 2: navigate to devices list ──────────────────────────────────────
  await page.goto("https://earnapp.com/dashboard/me/passive-income", {
    waitUntil: "networkidle2",
    timeout: 30000,
  });

  // Wait for at least one device name cell (stable semantic class)
  try {
    await page.waitForSelector("span.eadt_name", { timeout: 20000 });
  } catch {
    return {
      success: false,
      reason: "Devices table not found on passive-income page",
      ip: "unknown",
    };
  }

  // ── Step 3: derive device name from earnapp link ───────────────────────────
  // Link format:      https://earnapp.com/r/sdk-node-<32-hex>
  // Dashboard shows:  sdk-node-<last-8-hex>
  const uuidMatch = earnappLink.match(/sdk-node-([a-f0-9]+)$/i);
  if (!uuidMatch) {
    return {
      success: false,
      reason: "Cannot parse UUID from earnapp link",
      ip: "unknown",
    };
  }
  const deviceName = `sdk-node-${uuidMatch[1].slice(-8)}`;
  console.log(`Looking for device: ${deviceName}`);

  // ── Step 4: find matching row — retry until device appears (server delay) ─
  // Device may take a few seconds to register on EarnApp servers after linking.
  const FIND_TIMEOUT_MS = 60 * 1000; // max 60s waiting for device to appear
  const FIND_RETRY_MS = 4 * 1000; // reload and retry every 4s
  const findStart = Date.now();
  let targetRow = null;

  while (!targetRow) {
    const allNameEls = await page.$$("span.eadt_name");
    for (const nameEl of allNameEls) {
      const name = await nameEl.evaluate((el) => el.textContent.trim());
      if (name === deviceName) {
        targetRow = await nameEl.evaluateHandle((el) => el.closest("tr"));
        break;
      }
    }

    if (!targetRow) {
      if (Date.now() - findStart >= FIND_TIMEOUT_MS) {
        return {
          success: false,
          reason: `Device "${deviceName}" not found after ${FIND_TIMEOUT_MS / 1000}s`,
          ip: "unknown",
        };
      }
      console.log(
        `Device not visible yet, retrying in ${FIND_RETRY_MS / 1000}s...`,
      );
      await sleep(FIND_RETRY_MS);
      await page.reload({ waitUntil: "networkidle2", timeout: 30000 });
      await page.waitForSelector("span.eadt_name", { timeout: 20000 });
    }
  }

  // ── Step 5: click row to open detail panel ────────────────────────────────
  await targetRow.click();
  await sleep(2000); // wait for detail panel to animate/load

  // ── Step 6: check earning status (stable semantic classes) ────────────────
  const banTitleEl = await page.$("p.ead_ban_title");
  if (banTitleEl) {
    const banText = await banTitleEl.evaluate((el) => el.textContent.trim());
    if (banText.includes("not earning")) {
      const ipEl = await page.$(".ead_ban_ip .ead_ip");
      const ip = ipEl
        ? await ipEl.evaluate((el) => el.textContent.trim())
        : "unknown";
      return {
        success: false,
        reason: "Device is not earning — proxy blocked",
        ip,
      };
    }
  }

  // ── Proxy OK ──────────────────────────────────────────────────────────────
  // Wait for the IP element inside the detail panel to appear
  let ip = "unknown";
  try {
    await page.waitForSelector("li.ead_stat .ead_ips p", { timeout: 10000 });
    const goodIpEl = await page.$("li.ead_stat .ead_ips p");
    if (goodIpEl) ip = await goodIpEl.evaluate((el) => el.textContent.trim());
  } catch {
    // panel loaded but IP element not found — leave as 'unknown'
  }
  return { success: true, reason: "Proxy working — device is earning", ip };
}

/**
 * Delete the linked node from the earnapp dashboard.
 * Assumes page is currently on the passive-income devices list (or navigates there).
 */
async function deleteNodeOnDashboard(page, earnappLink) {
  // Derive device name (same logic as verifyNodeOnDashboard)
  const uuidMatch = earnappLink.match(/sdk-node-([a-f0-9]+)$/i);
  if (!uuidMatch)
    throw new Error("Cannot parse UUID from earnapp link for deletion");
  const deviceName = `sdk-node-${uuidMatch[1].slice(-8)}`;

  // Navigate fresh to ensure we're on the right page
  await page.goto("https://earnapp.com/dashboard/me/passive-income", {
    waitUntil: "networkidle2",
    timeout: 30000,
  });
  await page.waitForSelector("span.eadt_name", { timeout: 20000 });

  // ── Step 1: find the target row ───────────────────────────────────────────
  const allNameEls = await page.$$("span.eadt_name");
  let targetRow = null;
  for (const nameEl of allNameEls) {
    const name = await nameEl.evaluate((el) => el.textContent.trim());
    if (name === deviceName) {
      targetRow = await nameEl.evaluateHandle((el) => el.closest("tr"));
      break;
    }
  }
  if (
    !targetRow ||
    !(await targetRow.evaluate((el) => el && el.tagName === "TR"))
  ) {
    console.warn(
      `deleteNodeOnDashboard: device "${deviceName}" not found — skipping`,
    );
    return;
  }

  // ── Step 2: click the ⋮ context menu trigger in the last actions td ───────
  // Stable selector: td.eadt_actions_td → button.ea_context_menu_trigger
  const triggerBtn = await targetRow.$(
    "td.eadt_actions_td button.ea_context_menu_trigger",
  );
  if (!triggerBtn)
    throw new Error("Context menu trigger button not found in row");
  await triggerBtn.click();

  // ── Step 3: click "Delete" menu item by text ──────────────────────────────
  await page.waitForSelector("li.ea_context_menu_item", { timeout: 5000 });
  const menuItems = await page.$$("li.ea_context_menu_item");
  let deleteMenuBtn = null;
  for (const item of menuItems) {
    const text = await item.evaluate((el) => el.textContent.trim());
    if (text.includes("Delete")) {
      deleteMenuBtn = await item.$("button.ea_context_menu_button");
      break;
    }
  }
  if (!deleteMenuBtn)
    throw new Error('"Delete" option not found in context menu');
  await deleteMenuBtn.click();

  // ── Step 4: click "Delete permanently" in confirm popup (text-based) ──────
  await page.waitForFunction(
    () => document.body.innerText.includes("Delete permanently"),
    { timeout: 10000 },
  );
  await page.evaluate(() => {
    const btn = [...document.querySelectorAll("button")].find((b) =>
      b.textContent.trim().includes("Delete permanently"),
    );
    if (btn) btn.click();
    else throw new Error('"Delete permanently" button not found in popup');
  });

  // ── Step 5: wait for success message (stable semantic class) ──────────────
  try {
    await page.waitForSelector("p.eaa_text", { timeout: 10000 });
    const msg = await page.$eval("p.eaa_text", (el) => el.textContent.trim());
    console.log(`Delete result: ${msg}`);
  } catch {
    console.warn("deleteNodeOnDashboard: success confirmation not detected");
  }
}

// ─────────────────────────────────────────────
//  MAIN
// ─────────────────────────────────────────────
async function main() {
  const proxies = readProxies();
  if (proxies.length === 0) {
    console.error("No proxies found in input-proxy.txt — aborting.");
    process.exit(1);
  }

  const cookies = loadCookies();
  if (cookies.length === 0) {
    console.error("cookie.json is empty — fill in your earnapp cookies first.");
    process.exit(1);
  }

  // Init result file
  const header = [
    `Test started: ${new Date().toISOString()}`,
    `Total proxies: ${proxies.length}`,
    "=".repeat(70),
    "",
  ].join("\n");
  fs.writeFileSync(RESULT_FILE, header);

  // Launch browser
  const browser = await puppeteer.launch({
    executablePath: CHROMIUM_PATH,
    headless: false, // set true for headless
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--start-maximized"],
    defaultViewport: null,
  });

  const page = await browser.newPage();

  // Login once with cookies
  await loginWithCookies(page, cookies);

  const results = { success: [], fail: [] };

  for (let i = 0; i < proxies.length; i++) {
    const proxy = proxies[i];
    const label = `[${i + 1}/${proxies.length}]`;
    console.log(`\n${"─".repeat(70)}`);
    console.log(`${label} Testing proxy: ${proxy}`);

    let ip = "unknown";
    let success = false;
    let reason = "";

    try {
      // ── Step 1: get proxy IP ──────────────────────────────────────────
      console.log("Resolving proxy IP...");
      ip = getProxyIP(proxy);
      console.log(`Proxy IP: ${ip}`);

      // ── Step 2: copy source and configure ────────────────────────────
      console.log("Copying source...");
      copySource();
      patchProperties();
      setProxy(proxy);

      // ── Step 3: start node ────────────────────────────────────────────
      console.log("Starting node (internetIncome.sh --start)...");
      startNode();
      console.log(
        `Waiting ${CONTAINER_INIT_DELAY_MS / 1000}s for container to initialize...`,
      );
      await sleep(CONTAINER_INIT_DELAY_MS);

      // ── Step 4: get earnapp link ──────────────────────────────────────
      const earnappLink = getEarnappLink();
      if (!earnappLink) {
        reason = "No earnapp link found in earnapp.txt after --start";
        throw new Error(reason);
      }
      console.log(`EarnApp link: ${earnappLink}`);

      // ── Step 5: verify node on dashboard ─────────────────────────────
      // eslint-disable-next-line @typescript-eslint/await-thenable
      const verifyResult = await verifyNodeOnDashboard(page, earnappLink);
      success = verifyResult.success;
      reason = verifyResult.reason;
      // prefer IP reported by EarnApp dashboard over curl result
      if (verifyResult.ip && verifyResult.ip !== "unknown")
        ip = verifyResult.ip;

      // ── Step 6: delete node from dashboard ───────────────────────────
      if (success) {
        await deleteNodeOnDashboard(page, earnappLink);
      }
    } catch (err) {
      success = false;
      reason = reason || err.message;
      console.error(`Error: ${err.message}`);
    } finally {
      // ── Step 7: stop containers ───────────────────────────────────────
      console.log("Stopping containers (--delete + --deleteBackup)...");
      try {
        stopNode();
      } catch (e) {
        console.warn("stopNode error:", e.message);
      }

      // ── Step 8: write result ──────────────────────────────────────────
      writeResult(proxy, ip, success, reason);
      (success ? results.success : results.fail).push(`${proxy} (IP: ${ip})`);
    }

    // ── Step 9: wait before next proxy ───────────────────────────────
    if (i < proxies.length - 1) {
      console.log(
        `\nWaiting ${DELAY_BETWEEN_PROXIES_MS / 1000}s before next proxy...`,
      );
      await sleep(DELAY_BETWEEN_PROXIES_MS);
    }
  }

  // ── Write summary ─────────────────────────────────────────────────────
  const summary = [
    "",
    "=".repeat(70),
    "SUMMARY",
    "=".repeat(70),
    `Success (${results.success.length}):`,
    results.success.length ? results.success.join("\n") : "  (none)",
    "",
    `Fail (${results.fail.length}):`,
    results.fail.length ? results.fail.join("\n") : "  (none)",
    "",
    `Test finished: ${new Date().toISOString()}`,
  ].join("\n");

  fs.appendFileSync(RESULT_FILE, summary + "\n");
  console.log(summary);

  await browser.close();
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
