// Executed by Windows Node so the isolated Edge CDP listener stays on loopback.
const { argv } = require("node:process");
const { spawn } = require("node:child_process");
const { isAbsolute } = require("node:path").win32;
const origin = "https://jiaowu.cqmu.edu.cn:8080";
const path = "/eams/courseTableForStd.action";
const shellPath = "/eams/teaResetPassword!search.action";
const calendarPath = "/eams/courseTableForStd!calendarCourseTable.action";
const portalOrigin = "https://portal.paas.cqmu.edu.cn";
const casOrigin = "https://cas.cqmu.edu.cn";
const endpoint = "http://127.0.0.1:9237";

function readPeriods(start, end, expectedOrigin, expectedPaths, expectedShell) {
  if (location.origin !== expectedOrigin) return null;
  const table = expectedPaths.includes(location.pathname)
    ? document.getElementById("courseTable")
    : location.pathname === expectedShell
      ? document.querySelector("#rightTD #courseTable")
      : null;
  if (table?.tagName !== "TABLE" || !table.rows[0]?.innerText.includes("第十八节")) {
    return null;
  }
  const occupied = {};
  for (const row of table.rows) {
    const day = Array.from(row.cells).slice(0, 2).map((cell) => cell.innerText.trim())
      .find((value) => /^\d{4}-\d{2}-\d{2}$/.test(value));
    if (!day || day < start || day > end) continue;
    const periods = new Set(occupied[day] || []);
    for (const cell of row.cells) {
      if (!cell.id.startsWith(day + "_") || !cell.innerText.trim()) continue;
      const spans = [...cell.innerText.matchAll(/[（(]([\d,，、\-–—\s]+)节[)）]/g)];
      if (!spans.length) throw Error("Unknown timetable cell format.");
      for (const [, span] of spans) {
        for (const bounds of span.trim().split(/[,，、]+/)) {
          const [first, last = first] = bounds.split(/[-–—]/).map(Number);
          if (!Number.isInteger(first) || !Number.isInteger(last)
              || first < 1 || last > 18 || last < first) throw Error("Invalid period.");
          for (let period = first; period <= last; period++) periods.add(period);
        }
      }
    }
    occupied[day] = [...periods].sort((a, b) => a - b);
  }
  return occupied;
}

async function debuggerRequest(path, method = "GET") {
  const response = await fetch(endpoint + path, {
    method, signal: AbortSignal.timeout(2000), redirect: "error",
  });
  if (!response.ok) throw Error("BROWSER_UNAVAILABLE");
  return response.json();
}

function evaluate(tab) {
  const socketURL = new URL(tab.webSocketDebuggerUrl);
  if (socketURL.origin !== "ws://127.0.0.1:9237" || !socketURL.pathname.startsWith("/devtools/page/")) {
    throw Error("Unexpected debugger endpoint.");
  }
  const socket = new WebSocket(socketURL);
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => finish(reject, Error("Timed out.")), 5000);
    const finish = (callback, value) => {
      clearTimeout(timer);
      socket.close();
      callback(value);
    };
    socket.addEventListener("error", () => finish(reject, Error("Debugger failed.")));
    socket.addEventListener("open", () => socket.send(JSON.stringify({
      id: 1,
      method: "Runtime.evaluate",
      params: {
        expression: "(" + readPeriods.toString() + ")(..." +
          JSON.stringify([argv[1], argv[2], origin, [path, calendarPath], shellPath]) + ")",
        returnByValue: true,
      },
    })));
    socket.addEventListener("message", ({ data }) => {
      const message = JSON.parse(data);
      if (message.id !== 1) return;
      if (message.error || message.result?.exceptionDetails) {
        finish(reject, Error("Unable to read timetable."));
        return;
      }
      finish(resolve, message.result.result.value ?? null);
    });
  });
}

async function listTabs() {
  try {
    return await debuggerRequest("/json/list");
  } catch {
    const [edge, profile] = argv.slice(3);
    if (!edge || !profile || !isAbsolute(edge) || !isAbsolute(profile)) {
      throw Error("BROWSER_UNAVAILABLE");
    }
    // This visible window is also the hand-off surface if the school asks for MFA.
    const browser = spawn(edge, [
      "--user-data-dir=" + profile,
      "--remote-debugging-address=127.0.0.1",
      "--remote-debugging-port=9237",
      "--no-first-run", "--no-default-browser-check",
      "--new-window", "about:blank",
    ], { detached: true, stdio: "ignore" });
    await new Promise((resolve, reject) => {
      browser.once("error", reject);
      browser.once("spawn", resolve);
    });
    browser.unref();
    for (let attempt = 0; attempt < 16; attempt++) {
      await new Promise((resolve) => setTimeout(resolve, 400));
      try {
        return await debuggerRequest("/json/list");
      } catch {
        // Edge may still be loading the local profile.
      }
    }
    throw Error("BROWSER_UNAVAILABLE");
  }
}

async function main() {
  const tabs = await listTabs();
  const calendars = tabs.filter(({type, url}) =>
    type === "page" && new URL(url).origin === origin && new URL(url).pathname === calendarPath);
  const tab = calendars[0] ?? await debuggerRequest(
    "/json/new?" + encodeURIComponent(origin + calendarPath), "PUT",
  );
  for (let attempt = 0; attempt < 12; attempt++) {
    const target = (await debuggerRequest("/json/list")).find(({id}) => id === tab.id);
    if (!target) throw Error("BROWSER_UNAVAILABLE");
    const address = new URL(target.url);
    if ([portalOrigin, casOrigin].includes(address.origin)
        || (address.origin === origin && /login/i.test(address.pathname))) {
      throw Error("LOGIN_REQUIRED");
    }
    if (address.origin === origin && [path, calendarPath, shellPath].includes(address.pathname)) {
      const result = await evaluate(target);
      if (result !== null) {
        console.log(JSON.stringify(result));
        return;
      }
    }
    if (!["about:", "https:"].includes(address.protocol)
        || (address.protocol === "https:" && address.origin !== origin)) {
      throw Error("BROWSER_UNAVAILABLE");
    }
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  throw Error("TIMETABLE_UNAVAILABLE");
}

main().catch((error) => {
  if (["LOGIN_REQUIRED", "TIMETABLE_UNAVAILABLE", "BROWSER_UNAVAILABLE"].includes(error.message)) {
    console.error(error.message);
  }
  process.exit(1);
});
