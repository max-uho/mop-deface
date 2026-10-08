#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use std::sync::Mutex;
use tauri::{Emitter, Manager};
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};
struct Session {
    child: Option<CommandChild>,
    temp: Option<tempfile::TempDir>,
    source: Option<std::path::PathBuf>,
    output: Option<std::path::PathBuf>,
    closing: bool,
}
struct State(Mutex<Session>);
#[tauri::command]
async fn start(
    app: tauri::AppHandle,
    state: tauri::State<'_, State>,
    mut request: serde_json::Value,
) -> Result<(), String> {
    let mut session = state.0.lock().map_err(|e| e.to_string())?;
    if session.child.is_some() {
        return Err("A job is already running".into());
    }
    let source = std::fs::canonicalize(request["source"].as_str().ok_or("Missing source")?)
        .map_err(|e| e.to_string())?;
    if !source.is_file() {
        return Err("Select a video file".into());
    }
    if request["action"] == "process" {
        session.source = Some(source.clone());
        session.temp = Some(
            tempfile::Builder::new()
                .prefix("deface-")
                .tempdir()
                .map_err(|e| e.to_string())?,
        );
        session.output = None;
        request["workdir"] = serde_json::json!(session.temp.as_ref().unwrap().path());
    } else if request["action"] == "probe" {
        session.temp = None;
        session.output = None;
        session.source = Some(source.clone());
    } else {
        return Err("Invalid action".into());
    }
    app.asset_protocol_scope()
        .allow_file(&source)
        .map_err(|e| e.to_string())?;
    request["source"] = serde_json::json!(source);
    let (mut rx, mut child) = app
        .shell()
        .sidecar("deface-worker")
        .map_err(|e| e.to_string())?
        .env("PYINSTALLER_RESET_ENVIRONMENT", "1")
        .spawn()
        .map_err(|e| e.to_string())?;
    child
        .write(format!("{}\n", request).as_bytes())
        .map_err(|e| e.to_string())?;
    session.child = Some(child);
    drop(session);
    tauri::async_runtime::spawn(async move {
        let mut completed = false;
        let mut terminal = false;
        let mut diagnostic = String::new();

        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(bytes) => {
                    if let Ok(value) = serde_json::from_slice::<serde_json::Value>(&bytes) {
                        if matches!(
                            value["type"].as_str(),
                            Some("complete" | "error" | "cancelled")
                        ) {
                            terminal = true;
                        }
                        if value["type"] == "complete" {
                            completed = true;
                            if let Some(path) = value["path"].as_str() {
                                let state = app.state::<State>();
                                let mut s = state.0.lock().unwrap();
                                let p = std::path::PathBuf::from(path);
                                if s.temp
                                    .as_ref()
                                    .is_some_and(|t| p == t.path().join("result.mp4"))
                                {
                                    let _ = app.asset_protocol_scope().allow_file(&p);
                                    s.output = Some(p);
                                }
                            }
                        }
                        let _ = app.emit("worker", value);
                    }
                }
                CommandEvent::Stderr(bytes) => {
                    diagnostic.push_str(&String::from_utf8_lossy(&bytes));
                    if diagnostic.len() > 3000 {
                        diagnostic = diagnostic
                            .chars()
                            .rev()
                            .take(2000)
                            .collect::<String>()
                            .chars()
                            .rev()
                            .collect();
                    }
                }
                CommandEvent::Terminated(_) => {
                    break;
                }
                _ => {}
            }
        }
        if !terminal {
            let _ = app.emit("worker", serde_json::json!({"type":"error", "message":format!("Processing backend stopped unexpectedly. {}", diagnostic)}));
        }
        let state = app.state::<State>();
        let mut s = state.0.lock().unwrap();
        s.child = None;
        if !completed {
            s.temp = None;
            s.output = None;
        }
        let closing = s.closing;
        drop(s);
        let _ = app.emit("worker", serde_json::json!({"type":"idle"}));
        if closing {
            app.exit(0);
        }
    });
    Ok(())
}
#[tauri::command]
fn cancel(state: tauri::State<State>) -> Result<(), String> {
    if let Some(child) = state.0.lock().unwrap().child.as_mut() {
        child.write(b"cancel\n").map_err(|e| e.to_string())?;
    }
    Ok(())
}
#[tauri::command]
async fn export(
    app: tauri::AppHandle,
    state: tauri::State<'_, State>,
    destination: String,
) -> Result<String, String> {
    let (output, source) = {
        let s = state.0.lock().unwrap();
        (
            s.output.clone().ok_or("No finished output")?,
            s.source.clone().ok_or("No source")?,
        )
    };
    let saved = destination.clone();
    tauri::async_runtime::spawn_blocking(move || copy_output(&source, &output, &destination))
        .await
        .map_err(|e| e.to_string())??;
    app.asset_protocol_scope()
        .allow_file(&saved)
        .map_err(|e| e.to_string())?;
    let mut s = state.0.lock().unwrap();
    s.output = Some(std::path::PathBuf::from(&saved));
    s.temp = None;
    Ok(saved)
}
fn copy_output(
    source: &std::path::PathBuf,
    output: &std::path::PathBuf,
    destination: &str,
) -> Result<(), String> {
    let dest = std::path::PathBuf::from(destination);
    if dest
        .extension()
        .is_none_or(|e| !e.eq_ignore_ascii_case("mp4"))
    {
        return Err("Export must use .mp4".to_string());
    }
    if std::fs::canonicalize(&dest).ok().as_ref() == Some(source) {
        return Err("Cannot overwrite the source".into());
    }
    // create_new prevents overwriting source aliases, existing files, and symlinks.
    use std::io::Write;
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&dest)
        .map_err(|e| format!("Choose a new filename: {e}"))?;
    let copied = (|| {
        let mut input = std::fs::File::open(output)?;
        std::io::copy(&mut input, &mut file)?;
        file.flush()?;
        file.sync_all()
    })();
    if let Err(e) = copied {
        drop(file);
        let _ = std::fs::remove_file(dest);
        return Err(e.to_string());
    }
    Ok(())
}

#[tauri::command]
fn licenses(app: tauri::AppHandle) -> Result<String, String> {
    let path = app
        .path()
        .resolve(
            "licenses/THIRD_PARTY.txt",
            tauri::path::BaseDirectory::Resource,
        )
        .map_err(|e| e.to_string())?;
    let mut text = std::fs::read_to_string(path).map_err(|e| e.to_string())?;
    if let Ok(path) = app.path().resolve(
        "licenses/RUST_LICENSES.txt",
        tauri::path::BaseDirectory::Resource,
    ) {
        if let Ok(rust) = std::fs::read_to_string(path) {
            text.push_str(&rust);
        }
    }
    Ok(text)
}
fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(State(Mutex::new(Session {
            child: None,
            temp: None,
            source: None,
            output: None,
            closing: false,
        })))
        .invoke_handler(tauri::generate_handler![start, cancel, export, licenses])
        .build(tauri::generate_context!())
        .expect("Unable to start Deface")
        .run(|app, event| {
            if let tauri::RunEvent::ExitRequested { api, .. } = event {
                let state = app.state::<State>();
                let mut s = state.0.lock().unwrap();
                s.closing = true;
                if let Some(child) = s.child.as_mut() {
                    let _ = child.write(b"cancel\n");
                    api.prevent_exit();
                    let _ = app.emit("worker", serde_json::json!({"type":"closing"}));
                }
            }
        });
}

#[cfg(test)]
mod tests {
    use super::copy_output;
    #[test]
    fn exports_new_files_and_protects_source_aliases() {
        let temp = tempfile::tempdir().unwrap();
        let source = temp.path().join("vidéo original.mp4");
        let output = temp.path().join("processed.mp4");
        std::fs::write(&source, b"original").unwrap();
        std::fs::write(&output, b"anonymized").unwrap();
        assert!(copy_output(&source, &output, source.to_str().unwrap()).is_err());
        let alias = temp.path().join("alias.mp4");
        std::fs::hard_link(&source, &alias).unwrap();
        assert!(copy_output(&source, &output, alias.to_str().unwrap()).is_err());
        let dest = temp.path().join("日本語 export.mp4");
        copy_output(&source, &output, dest.to_str().unwrap()).unwrap();
        assert_eq!(std::fs::read(&dest).unwrap(), b"anonymized");
        assert!(copy_output(&source, &output, dest.to_str().unwrap()).is_err());
        assert_eq!(std::fs::read(source).unwrap(), b"original");
    }
    #[test]
    fn failed_copy_removes_partial_destination() {
        let temp = tempfile::tempdir().unwrap();
        let source = temp.path().join("source.mp4");
        let missing = temp.path().join("missing.mp4");
        let destination = temp.path().join("export.mp4");
        assert!(copy_output(&source, &missing, destination.to_str().unwrap()).is_err());
        assert!(!destination.exists());
    }
}
