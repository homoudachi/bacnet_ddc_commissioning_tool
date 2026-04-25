const { invoke } = window.__TAURI__.core;

const runDirEl = () => document.querySelector("#run-dir");
const cmdEl = () => document.querySelector("#cmd");
const ctrlEl = () => document.querySelector("#ctrl");
const extraEl = () => document.querySelector("#extra");
const outEl = () => document.querySelector("#out");

function parseExtraArgs(line) {
  const s = line.trim();
  if (!s) return [];
  const parts = [];
  let cur = "";
  let quote = null;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (quote) {
      if (c === quote) {
        quote = null;
      } else {
        cur += c;
      }
      continue;
    }
    if (c === '"' || c === "'") {
      quote = c;
      continue;
    }
    if (c === " ") {
      if (cur.length) {
        parts.push(cur);
        cur = "";
      }
      continue;
    }
    cur += c;
  }
  if (cur.length) parts.push(cur);
  return parts;
}

function buildArgv(cmd) {
  const argv = [cmd];
  const ctrl = ctrlEl().value.trim();
  const needsCtrl = new Set([
    "commissioning-guided-next",
    "show-flow",
    "show-session",
  ]);
  if (needsCtrl.has(cmd) && ctrl) {
    argv.push("--controller-label", ctrl);
  }
  argv.push(...parseExtraArgs(extraEl().value));
  return argv;
}

async function showPaths() {
  outEl().textContent = "Loading…";
  try {
    const j = await invoke("commissioning_paths");
    outEl().textContent = JSON.stringify(j, null, 2);
  } catch (e) {
    outEl().textContent = String(e);
  }
}

async function runCli() {
  const runDir = runDirEl().value.trim();
  const cmd = cmdEl().value;
  if (!runDir) {
    outEl().textContent = "Set run directory (absolute path) first.";
    return;
  }
  outEl().textContent = "Running…";
  try {
    const argv = buildArgv(cmd);
    const res = await invoke("run_commissioning_cli", { runDir, argv });
    const lines = [
      `exit_code: ${res.exit_code}`,
      `python: ${res.python}`,
      `repo_root: ${res.repo_root}`,
      "",
      "--- stdout ---",
      res.stdout || "(empty)",
      "",
      "--- stderr ---",
      res.stderr || "(empty)",
    ];
    outEl().textContent = lines.join("\n");
  } catch (e) {
    outEl().textContent = String(e);
  }
}

window.addEventListener("DOMContentLoaded", () => {
  document.querySelector("#run-btn").addEventListener("click", runCli);
  document.querySelector("#paths-btn").addEventListener("click", showPaths);
});
