mod backend;

use backend::{BackendSupervisor, StartupStatus};
use tauri::{Manager, State};

#[tauri::command]
fn backend_startup_status(supervisor: State<'_, BackendSupervisor>) -> StartupStatus {
    supervisor.status()
}

#[tauri::command]
fn backend_api_token(supervisor: State<'_, BackendSupervisor>) -> Result<String, String> {
    supervisor.api_token()
}

#[tauri::command]
fn retry_backend_startup(supervisor: State<'_, BackendSupervisor>) {
    supervisor.retry();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| {
            if let Some(window) = app.get_webview_window("main") {
                if let Err(error) = window.set_focus() {
                    log::warn!("Unable to focus the existing BlackMarket AI window: {error}");
                }
            }
        }))
        .invoke_handler(tauri::generate_handler![
            backend_startup_status,
            backend_api_token,
            retry_backend_startup
        ])
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }
            let supervisor = BackendSupervisor::new(
                app.path().resource_dir().ok(),
                app.path().app_data_dir().ok(),
            );
            app.manage(supervisor.clone());
            supervisor.start();
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");
    app.run(|app_handle, event| {
        if matches!(event, tauri::RunEvent::Exit) {
            if let Some(supervisor) = app_handle.try_state::<BackendSupervisor>() {
                supervisor.shutdown();
            }
        }
    });
}
