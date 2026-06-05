use std::sync::Mutex;

use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

/// Holds the bundled Python engine process so we can shut it down on exit.
struct Engine(Mutex<Option<CommandChild>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .manage(Engine(Mutex::new(None)))
        .setup(|app| {
            // In a packaged build, launch the bundled DeutschX engine (the Python API
            // sidecar). In `tauri dev` the engine is started separately by run-dev.sh,
            // so we skip it there to avoid a port clash.
            if !tauri::is_dev() {
                let command = app.shell().sidecar("deutschx-server")?;
                let (mut rx, child) = command.spawn()?;
                app.state::<Engine>().0.lock().unwrap().replace(child);
                // Drain the engine's output so it never blocks on a full pipe.
                tauri::async_runtime::spawn(async move {
                    while rx.recv().await.is_some() {}
                });
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while running tauri application")
        .run(|app, event| {
            if let RunEvent::ExitRequested { .. } = event {
                if let Some(child) = app.state::<Engine>().0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        });
}
