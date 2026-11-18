// Executed by Windows Node so the isolated Edge CDP listener stays on loopback.
const { argv } = require("node:process");
const origin = "https://jiaowu.cqmu.edu.cn:8080";
const path = "/eams/courseTableForStd.action";
const shellPath = "/eams/teaResetPassword!search.action";
const endpoint = "http://127.0.0.1:9237";

function readPeriods(start, end, expectedOrigin, expectedPath, expectedShell) {
  if (location.origin !== expectedOrigin) throw Error("The tab navigated away.");
  const table = location.pathname === expectedPath
    ? document.getElementById("courseTable")
    : location.pathname === expectedShell
      ? document.querySelector("#rightTD #courseTable")
      : null;
  if (table?.tagName !== "TABLE" || !table.rows[0]?.innerText.includes("第十八节")) {
    throw Error("Open the personal teaching calendar.");
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

async function main() {
  const response = await fetch(endpoint + "/json/list", {
    signal: AbortSignal.timeout(2000),
    redirect: "error",
  });
  if (!response.ok) throw Error("Unavailable browser.");
  const tabs = (await response.json()).filter(({ type, url }) => {
    if (type !== "page") return false;
    const address = new URL(url);
    return address.origin === origin && [path, shellPath].includes(address.pathname);
  });
  if (tabs.length !== 1) throw Error("Open exactly one personal timetable tab.");
  const socketURL = new URL(tabs[0].webSocketDebuggerUrl);
  if (socketURL.origin !== "ws://127.0.0.1:9237" || !socketURL.pathname.startsWith("/devtools/page/")) {
    throw Error("Unexpected debugger endpoint.");
  }
  const socket = new WebSocket(socketURL);
  const out = await new Promise((resolve, reject) => {
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
          JSON.stringify([argv[1], argv[2], origin, path, shellPath]) + ")",
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
      finish(resolve, message.result.result.value);
    });
  });
  console.log(JSON.stringify(out));
}
main().catch(() => { process.exit(1); });
