//! Tauri shell for the BACnet commissioning Python CLI (Tier B2 — desktop).
//!
//! Runs `python3 tools/runtime/app.py …` from the repository root. Override the
//! interpreter with `BACNET_COMMISSIONING_PYTHON3` if needed.

use std::path::PathBuf;
use std::process::{Command, Stdio};

use serde::Serialize;

const MAX_CAPTURE_BYTES: usize = 512 * 1024;

#[derive(Debug, Serialize)]
struct CliResult {
    exit_code: i32,
    stdout: String,
    stderr: String,
    python: String,
    repo_root: String,
}

fn repo_root() -> Result<PathBuf, String> {
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let root = manifest
        .parent()
        .and_then(|p| p.parent())
        .ok_or_else(|| "cannot resolve repository root from CARGO_MANIFEST_DIR".to_string())?;
    if !root.join("tools").join("runtime").join("app.py").is_file() {
        return Err(format!(
            "expected tools/runtime/app.py under {}; wrong layout?",
            root.display()
        ));
    }
    Ok(root.to_path_buf())
}

fn python_executable() -> String {
    std::env::var("BACNET_COMMISSIONING_PYTHON3").unwrap_or_else(|_| "python3".to_string())
}

fn validate_run_dir(run_dir: &str) -> Result<(), String> {
    let p = PathBuf::from(run_dir.trim());
    if run_dir.trim().is_empty() {
        return Err("run_dir is empty".to_string());
    }
    if !p.is_absolute() {
        return Err("run_dir must be an absolute path".to_string());
    }
    if !p.is_dir() {
        return Err(format!("run_dir is not a directory: {}", p.display()));
    }
    Ok(())
}

fn truncate(s: String) -> String {
    if s.len() <= MAX_CAPTURE_BYTES {
        return s;
    }
    let mut out = s;
    out.truncate(MAX_CAPTURE_BYTES);
    out.push_str("\n… [truncated]");
    out
}

/// Run `python3 tools/runtime/app.py` with the given argv tail (e.g. `["compile-import"]`).
#[tauri::command]
fn run_commissioning_cli(run_dir: String, argv: Vec<String>) -> Result<CliResult, String> {
    let root = repo_root()?;
    validate_run_dir(&run_dir)?;
    let py = python_executable();
    for a in &argv {
        if a.len() > 4096 {
            return Err("argument too long".to_string());
        }
    }

    let mut cmd = Command::new(&py);
    cmd.current_dir(&root);
    cmd.arg(root.join("tools").join("runtime").join("app.py"));
    for a in argv {
        cmd.arg(a);
    }
    cmd.arg("--run-dir");
    cmd.arg(&run_dir);
    cmd.stdin(Stdio::null());

    let output = cmd
        .output()
        .map_err(|e| format!("failed to run {py} {}: {e}", root.display()))?;

    let exit_code = output.status.code().unwrap_or(-1);
    let stdout = truncate(String::from_utf8_lossy(&output.stdout).into_owned());
    let stderr = truncate(String::from_utf8_lossy(&output.stderr).into_owned());

    Ok(CliResult {
        exit_code,
        stdout,
        stderr,
        python: py,
        repo_root: root.display().to_string(),
    })
}

#[tauri::command]
fn commissioning_paths() -> Result<serde_json::Value, String> {
    let root = repo_root()?;
    let py = python_executable();
    Ok(serde_json::json!({
        "repo_root": root.display().to_string(),
        "python": py,
        "cli": root.join("tools").join("runtime").join("app.py").display().to_string(),
    }))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            run_commissioning_cli,
            commissioning_paths
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
