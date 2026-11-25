mod backend;

use backend::{BackendSupervisor, StartupStatus};
use tauri::{Manager, State, WebviewWindowBuilder, tray::{TrayIconBuilder, TrayIconEvent}, menu::{Menu, MenuItem}};
#[cfg(debug_assertions)]
use std::path::PathBuf;

#[tauri::command]
fn backend_startup_status(supervisor: State<'_, BackendSupervisor>) -> StartupStatus {
  supervisor.status()
}

#[tauri::command]
fn backend_api_token(supervisor: State<'_, BackendSupervisor>) -> Result<String, String> {
  supervisor.api_token()
}

#[tauri::command]
fn backend_log_tail(supervisor: State<'_, BackendSupervisor>) -> Result<Vec<String>, String> {
  supervisor.log_tail()
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
        if let Err(error) = window.show() {
          log::warn!("Unable to restore the existing BlackMarket AI window: {error}");
        }
        if let Err(error) = window.set_focus() {
          log::warn!("Unable to focus the existing BlackMarket AI window: {error}");
        }
      }
    }))
    .invoke_handler(tauri::generate_handler![
      backend_startup_status,
      backend_api_token,
      backend_log_tail,
      retry_backend_startup
    ])
    .setup(|app| {
      let window_config = &app.config().app.windows[0];
      let window_builder = WebviewWindowBuilder::from_config(app.handle(), window_config)?;
      #[cfg(debug_assertions)]
      let window_builder = {
        let webview_profile = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
          .join("target")
          .join("blackmarket-webview-dev");
        std::fs::create_dir_all(&webview_profile)?;
        window_builder.data_directory(webview_profile)
      };
      let window = window_builder.visible(true).build()?;
      window.set_title("BlackMarket AI")?;
      window.show()?;
      window.set_focus()?;
      let show = MenuItem::with_id(app, "show", "Show BlackMarket AI", true, None::<&str>)?;
      let quit = MenuItem::with_id(app, "quit", "Quit BlackMarket AI", true, None::<&str>)?;
      let menu = Menu::with_items(app, &[&show, &quit])?;
      TrayIconBuilder::new()
        .tooltip("BlackMarket AI · paper engine")
        .menu(&menu)
        .on_menu_event(|app, event| match event.id().as_ref() {
          "show" => if let Some(window) = app.get_webview_window("main") { let _ = window.show(); let _ = window.set_focus(); },
          "quit" => app.exit(0),
          _ => {},
        })
        .on_tray_icon_event(|tray, event| {
          if let TrayIconEvent::DoubleClick { .. } = event {
            if let Some(window) = tray.app_handle().get_webview_window("main") { let _ = window.show(); let _ = window.set_focus(); }
          }
        })
        .build(app)?;
      let close_app = app.handle().clone();
      window.on_window_event(move |event| {
        if let tauri::WindowEvent::CloseRequested { api, .. } = event {
          api.prevent_close();
          if let Some(window) = close_app.get_webview_window("main") { let _ = window.hide(); }
        }
      });
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
