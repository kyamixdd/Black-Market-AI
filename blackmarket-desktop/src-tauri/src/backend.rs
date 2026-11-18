use fs2::FileExt;
use serde::Serialize;
use std::{
    env,
    ffi::OsString,
    fs::{self, File, OpenOptions},
    io::{BufRead, BufReader, Read, Write},
    net::{SocketAddr, TcpStream},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex, MutexGuard},
    thread,
    time::{Duration, Instant},
};
use uuid::Uuid;

const API_ADDRESS: &str = "127.0.0.1:8765";
const STARTUP_TIMEOUT: Duration = Duration::from_secs(180);
const GRACEFUL_SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(30);
const CONNECT_TIMEOUT: Duration = Duration::from_millis(500);
const READ_TIMEOUT: Duration = Duration::from_secs(2);

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct StartupStatus {
    pub state: String,
    pub message: String,
    pub details: Option<String>,
    pub log_path: Option<String>,
}

impl StartupStatus {
    fn new(state: &str, message: impl Into<String>) -> Self {
        Self {
            state: state.to_owned(),
            message: message.into(),
            details: None,
            log_path: None,
        }
    }
}

struct Runtime {
    status: StartupStatus,
    child: Option<Child>,
    shutdown_token: Option<String>,
    api_token: Option<String>,
    process_lock: Option<File>,
    shutting_down: bool,
}

struct SharedRuntime(Mutex<Runtime>);

impl Drop for SharedRuntime {
    fn drop(&mut self) {
        let runtime = self.0.get_mut().unwrap_or_else(|error| error.into_inner());
        let shutdown_token = runtime.shutdown_token.take();
        stop_child(&mut runtime.child, shutdown_token.as_deref());
        drop(runtime.process_lock.take());
    }
}

#[derive(Clone)]
pub struct BackendSupervisor {
    runtime: Arc<SharedRuntime>,
    resource_dir: Option<PathBuf>,
    app_data_dir: Option<PathBuf>,
}

impl BackendSupervisor {
    pub fn new(resource_dir: Option<PathBuf>, app_data_dir: Option<PathBuf>) -> Self {
        Self {
            runtime: Arc::new(SharedRuntime(Mutex::new(Runtime {
                status: StartupStatus::new("queued", "Waiting to check the local backend."),
                child: None,
                shutdown_token: None,
                api_token: None,
                process_lock: None,
                shutting_down: false,
            }))),
            resource_dir,
            app_data_dir,
        }
    }

    pub fn start(&self) {
        {
            let mut runtime = self.lock_runtime();
            if runtime.shutting_down
                || runtime.status.state == "checking"
                || runtime.status.state == "starting"
            {
                return;
            }
            runtime.status = StartupStatus::new("checking", "Checking the local backend.");
        }
        self.spawn_startup();
    }

    pub fn retry(&self) {
        if self.lock_runtime().shutting_down {
            return;
        }
        self.stop_owned_backend();
        {
            let mut runtime = self.lock_runtime();
            if runtime.shutting_down {
                return;
            }
            runtime.status = StartupStatus::new("checking", "Retrying local backend startup.");
        }
        self.spawn_startup();
    }

    pub fn status(&self) -> StartupStatus {
        self.lock_runtime().status.clone()
    }

    pub fn api_token(&self) -> Result<String, String> {
        let runtime = self.lock_runtime();
        if runtime.status.state != "ready" {
            return Err("The backend is not ready.".to_owned());
        }
        runtime
            .api_token
            .clone()
            .ok_or_else(|| "The local API token is unavailable.".to_owned())
    }

    pub fn shutdown(&self) {
        {
            let mut runtime = self.lock_runtime();
            runtime.shutting_down = true;
        }
        self.stop_owned_backend();
    }

    fn is_shutting_down(&self) -> bool {
        self.lock_runtime().shutting_down
    }

    fn lock_runtime(&self) -> MutexGuard<'_, Runtime> {
        self.runtime
            .0
            .lock()
            .unwrap_or_else(|error| error.into_inner())
    }

    fn spawn_startup(&self) {
        let supervisor = self.clone();
        let spawn_result = thread::Builder::new()
            .name("blackmarket-backend-startup".to_owned())
            .spawn(move || supervisor.start_backend());
        if let Err(error) = spawn_result {
            self.fail(
                format!("Could not start the backend supervisor thread: {error}"),
                None,
            );
        }
    }

    fn start_backend(&self) {
        if self.is_shutting_down() {
            return;
        }
        let project_root = match find_project_root(self.resource_dir.as_deref()) {
            Some(root) => root,
            None => {
                self.fail(
                    "The BlackMarket AI Python backend files were not found.".to_owned(),
                    None,
                );
                return;
            }
        };
        let log_path = self.backend_log_path();
        let dotenv_path = self.dotenv_path(&project_root);
        let api_token = match self.load_api_token(&project_root) {
            Ok(token) => token,
            Err(error) => {
                self.fail(
                    format!("Could not secure the local API authentication token: {error}"),
                    Some(log_path),
                );
                return;
            }
        };
        self.lock_runtime().api_token = Some(api_token.clone());

        match probe_health() {
            Probe::Ready => {
                self.ready("Connected to an already-running local backend.");
                return;
            }
            Probe::Starting => {
                self.wait_for_existing_backend(log_path);
                return;
            }
            Probe::Occupied(details) => {
                self.fail(
                    format!("Port 8765 is responding, but it is not a ready BlackMarket AI backend. {details}"),
                    Some(log_path),
                );
                return;
            }
            Probe::Unavailable => {}
        }

        let process_lock = match self.acquire_process_lock() {
            Ok(Some(file)) => file,
            Ok(None) => {
                self.wait_for_existing_backend(log_path);
                return;
            }
            Err(error) => {
                self.fail(
                    format!("Could not secure the single-backend startup lock: {error}"),
                    Some(log_path),
                );
                return;
            }
        };

        match probe_health() {
            Probe::Ready => {
                self.ready("Connected to an already-running local backend.");
                return;
            }
            Probe::Starting => {
                drop(process_lock);
                self.wait_for_existing_backend(log_path);
                return;
            }
            Probe::Occupied(details) => {
                drop(process_lock);
                self.fail(
                    format!("Port 8765 is occupied by a service that is not BlackMarket AI. {details}"),
                    Some(log_path),
                );
                return;
            }
            Probe::Unavailable => {}
        }

        let python = match find_python(&project_root) {
            Ok(python) => python,
            Err(error) => {
                drop(process_lock);
                self.fail(error, Some(log_path));
                return;
            }
        };

        if let Err(error) = fs::create_dir_all(
            log_path
                .parent()
                .unwrap_or_else(|| Path::new(".")),
        ) {
            drop(process_lock);
            self.fail(
                format!("Could not create the backend log directory: {error}"),
                Some(log_path),
            );
            return;
        }

        let log_file = match OpenOptions::new().create(true).append(true).open(&log_path) {
            Ok(file) => file,
            Err(error) => {
                drop(process_lock);
                self.fail(
                    format!("Could not open the backend log: {error}"),
                    Some(log_path),
                );
                return;
            }
        };

        let mut command = Command::new(&python.executable);
        let shutdown_token = Uuid::new_v4().simple().to_string();
        command
            .args(&python.prefix_args)
            .args(["-m", "src_tauri.backend.main"])
            .current_dir(&project_root)
            .env("PYTHONPATH", &project_root)
            .env("PYTHONUNBUFFERED", "1")
            .env("BLACKMARKET_API_HOST", "127.0.0.1")
            .env("BLACKMARKET_API_PORT", "8765")
            .env("BLACKMARKET_SHUTDOWN_TOKEN", &shutdown_token)
            .env("BLACKMARKET_API_TOKEN", &api_token)
            .env(
                "BLACKMARKET_DESKTOP_DEV",
                if cfg!(debug_assertions) { "1" } else { "0" },
            )
            .stdout(Stdio::from(match log_file.try_clone() {
                Ok(file) => file,
                Err(error) => {
                    drop(process_lock);
                    self.fail(
                        format!("Could not prepare backend log output: {error}"),
                        Some(log_path),
                    );
                    return;
                }
            }))
            .stderr(Stdio::from(log_file));
        if let Some(data_dir) = &self.app_data_dir {
            command
                .env("BLACKMARKET_DATA_DIR", data_dir)
                .env("BLACKMARKET_CONFIG_DIR", data_dir);
        }
        if let Some(env_file) = &dotenv_path {
            command.env("BLACKMARKET_ENV_FILE", env_file);
        }
        hide_console(&mut command);

        let mut runtime = self.lock_runtime();
        if runtime.shutting_down {
            drop(runtime);
            drop(process_lock);
            return;
        }

        let child = match command.spawn() {
            Ok(child) => child,
            Err(error) => {
                drop(runtime);
                drop(process_lock);
                self.fail(
                    format!(
                        "Could not launch Python ({}) from {}: {error}",
                        python.executable.display(),
                        project_root.display()
                    ),
                    Some(log_path),
                );
                return;
            }
        };

        runtime.status = StartupStatus {
            state: "starting".to_owned(),
            message: "Starting the Python engine and waiting for database, market services, and API readiness.".to_owned(),
            details: None,
            log_path: Some(log_path.display().to_string()),
        };
        runtime.child = Some(child);
        runtime.shutdown_token = Some(shutdown_token);
        runtime.process_lock = Some(process_lock);
        drop(runtime);

        self.wait_for_owned_backend(log_path);
    }

    fn wait_for_existing_backend(&self, log_path: PathBuf) {
        self.set_status(StartupStatus {
            state: "starting".to_owned(),
            message: "A local backend is starting; waiting for its readiness check.".to_owned(),
            details: None,
            log_path: Some(log_path.display().to_string()),
        });
        let deadline = Instant::now() + STARTUP_TIMEOUT;
        while Instant::now() < deadline {
            if self.is_shutting_down() {
                return;
            }
            match probe_health() {
                Probe::Ready => {
                    self.ready("Connected to the existing local backend.");
                    return;
                }
                Probe::Occupied(details) => {
                    self.fail(
                        format!("The service on port 8765 is not a ready BlackMarket AI backend. {details}"),
                        Some(log_path),
                    );
                    return;
                }
                Probe::Starting | Probe::Unavailable => thread::sleep(Duration::from_millis(500)),
            }
        }
        self.fail(
            "The existing backend did not become ready before the startup timeout.".to_owned(),
            Some(log_path),
        );
    }

    fn wait_for_owned_backend(&self, log_path: PathBuf) {
        let deadline = Instant::now() + STARTUP_TIMEOUT;
        while Instant::now() < deadline {
            if self.is_shutting_down() {
                return;
            }
            match probe_health() {
                Probe::Ready => {
                    self.ready("The local engine, API, database, and WebSocket service are ready.");
                    return;
                }
                Probe::Occupied(details) => {
                    self.fail(
                        format!("The backend API could not bind to port 8765. {details}"),
                        Some(log_path),
                    );
                    return;
                }
                Probe::Starting | Probe::Unavailable => {}
            }

            let child_status = {
                let mut runtime = self.lock_runtime();
                runtime.child.as_mut().map(Child::try_wait)
            };
            match child_status {
                Some(Ok(Some(exit))) => {
                    self.fail(
                        format!(
                            "The backend process exited before becoming ready ({exit}). {}",
                            read_log_tail(&log_path)
                        ),
                        Some(log_path),
                    );
                    return;
                }
                Some(Err(error)) => {
                    self.fail(
                        format!("Could not monitor the backend process: {error}"),
                        Some(log_path),
                    );
                    return;
                }
                Some(Ok(None)) | None => {}
            }
            thread::sleep(Duration::from_millis(500));
        }
        self.fail(
            format!(
                "The backend did not become ready within {} seconds. {}",
                STARTUP_TIMEOUT.as_secs(),
                read_log_tail(&log_path)
            ),
            Some(log_path),
        );
    }

    fn acquire_process_lock(&self) -> Result<Option<File>, String> {
        let data_dir = self
            .app_data_dir
            .as_ref()
            .ok_or_else(|| "The desktop application data directory is unavailable.".to_owned())?;
        fs::create_dir_all(data_dir).map_err(|error| error.to_string())?;
        let lock_path = data_dir.join("backend-startup.lock");
        let file = OpenOptions::new()
            .create(true)
            .read(true)
            .write(true)
            .open(&lock_path)
            .map_err(|error| error.to_string())?;
        match file.try_lock_exclusive() {
            Ok(()) => Ok(Some(file)),
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => Ok(None),
            Err(error) => Err(error.to_string()),
        }
    }

    fn dotenv_path(&self, project_root: &Path) -> Option<PathBuf> {
        if let Some(data_dir) = &self.app_data_dir {
            let candidate = data_dir.join(".env");
            if candidate.is_file() {
                return Some(candidate);
            }
        }
        let candidate = project_root.join(".env");
        candidate.is_file().then_some(candidate)
    }

    fn load_api_token(&self, project_root: &Path) -> Result<String, String> {
        // Prefer an explicitly configured shared token so the local engine can
        // authenticate requests from the hosted dashboard. Never log this value.
        if let Ok(token) = env::var("BLACKMARKET_API_TOKEN") {
            if !token.trim().is_empty() {
                return validate_api_token(token.trim());
            }
        }

        // Tauri-launched processes do not inherit Python's dotenv loader, so read
        // the project .env directly when a shared token was configured there.
        if let Some(dotenv_path) = self.dotenv_path(project_root) {
            if let Ok(contents) = fs::read_to_string(&dotenv_path) {
            for line in contents.lines() {
                let Some((key, value)) = line.split_once('=') else { continue };
                if key.trim() == "BLACKMARKET_API_TOKEN" {
                    let value = value.trim().trim_matches('"').trim_matches('\'');
                    if !value.is_empty() {
                        return validate_api_token(value);
                    }
                }
            }
        }

        // Standalone desktop use still gets a private per-install token.
        let data_dir = self
            .app_data_dir
            .as_ref()
            .ok_or_else(|| "The desktop application data directory is unavailable.".to_owned())?;
        fs::create_dir_all(data_dir).map_err(|error| error.to_string())?;
        let token_path = data_dir.join("api-token");
        let token = match OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&token_path)
        {
            Ok(mut file) => {
                let token = Uuid::new_v4().simple().to_string();
                file.write_all(token.as_bytes())
                    .and_then(|()| file.sync_all())
                    .map_err(|error| error.to_string())?;
                token
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                fs::read_to_string(&token_path).map_err(|error| error.to_string())?
            }
            Err(error) => return Err(error.to_string()),
        };
        validate_api_token(token.trim())
    }

    fn backend_log_path(&self) -> PathBuf {
        self.app_data_dir
            .as_ref()
            .map(|path| path.join("logs").join("backend.log"))
            .unwrap_or_else(|| PathBuf::from("backend.log"))
    }

    fn ready(&self, message: &str) {
        self.set_status(StartupStatus::new("ready", message));
    }

    fn fail(&self, message: String, log_path: Option<PathBuf>) {
        self.stop_owned_backend();
        let mut status = StartupStatus::new("failed", message);
        status.log_path = log_path.map(|path| path.display().to_string());
        status.details = status
            .log_path
            .as_deref()
            .map(|path| format!("Backend log: {path}"));
        self.set_status(status);
    }

    fn set_status(&self, status: StartupStatus) {
        self.lock_runtime().status = status;
    }

    fn stop_owned_backend(&self) {
        let (mut child, shutdown_token, process_lock) = {
            let mut runtime = self.lock_runtime();
            (
                runtime.child.take(),
                runtime.shutdown_token.take(),
                runtime.process_lock.take(),
            )
        };
        stop_child(&mut child, shutdown_token.as_deref());
        drop(process_lock);
    }
}

fn stop_child(child: &mut Option<Child>, shutdown_token: Option<&str>) {
    if let Some(mut child) = child.take() {
        let mut exited = match child.try_wait() {
            Ok(Some(_)) => true,
            Ok(None) => false,
            Err(error) => {
                log::warn!("Unable to inspect the managed backend process: {error}");
                false
            }
        };

        if !exited {
            if let Some(token) = shutdown_token {
                match request_graceful_shutdown(token) {
                    Ok(()) => match wait_for_child_exit(&mut child, GRACEFUL_SHUTDOWN_TIMEOUT) {
                        Ok(true) => exited = true,
                        Ok(false) => log::warn!(
                            "The backend did not stop gracefully within {} seconds.",
                            GRACEFUL_SHUTDOWN_TIMEOUT.as_secs()
                        ),
                        Err(error) => {
                            log::warn!("Unable to monitor graceful backend shutdown: {error}")
                        }
                    },
                    Err(error) => {
                        log::warn!("Graceful backend shutdown request failed: {error}")
                    }
                }
            }

            if !exited {
                if let Err(error) = child.kill() {
                    if !matches!(child.try_wait(), Ok(Some(_))) {
                        log::warn!("Unable to stop the managed backend process: {error}");
                    }
                }
            }
        }

        if let Err(error) = child.wait() {
            log::warn!("Unable to wait for the managed backend process: {error}");
        }
    }
}

fn request_graceful_shutdown(token: &str) -> Result<(), String> {
    let address: SocketAddr = API_ADDRESS.parse().expect("valid backend address");
    let mut stream = TcpStream::connect_timeout(&address, CONNECT_TIMEOUT)
        .map_err(|error| error.to_string())?;
    stream
        .set_read_timeout(Some(READ_TIMEOUT))
        .map_err(|error| error.to_string())?;
    let request = format!(
        "POST /_internal/shutdown HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer {token}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    );
    stream
        .write_all(request.as_bytes())
        .map_err(|error| error.to_string())?;

    let mut reader = BufReader::new(stream);
    let mut status_line = String::new();
    reader
        .read_line(&mut status_line)
        .map_err(|error| error.to_string())?;
    if status_line.split_whitespace().nth(1) == Some("200") {
        Ok(())
    } else {
        Err(format!(
            "The local API returned an unexpected response: {}",
            status_line.trim()
        ))
    }
}

fn wait_for_child_exit(child: &mut Child, timeout: Duration) -> Result<bool, String> {
    let deadline = Instant::now() + timeout;
    loop {
        match child.try_wait().map_err(|error| error.to_string())? {
            Some(_) => return Ok(true),
            None if Instant::now() < deadline => thread::sleep(Duration::from_millis(100)),
            None => return Ok(false),
        }
    }
}

#[derive(Debug, PartialEq, Eq)]
enum Probe {
    Ready,
    Starting,
    Unavailable,
    Occupied(String),
}

fn probe_health() -> Probe {
    let address: SocketAddr = API_ADDRESS.parse().expect("valid backend address");
    let mut stream = match TcpStream::connect_timeout(&address, CONNECT_TIMEOUT) {
        Ok(stream) => stream,
        Err(_) => return Probe::Unavailable,
    };
    if stream.set_read_timeout(Some(READ_TIMEOUT)).is_err()
        || stream
            .write_all(
                b"GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
            )
            .is_err()
    {
        return Probe::Unavailable;
    }
    let mut response = String::new();
    if stream.read_to_string(&mut response).is_err() {
        return Probe::Unavailable;
    }
    parse_health_response(&response)
}

fn validate_api_token(token: &str) -> Result<String, String> {
    if !(32..=128).contains(&token.len())
        || !token.bytes().all(|byte| byte.is_ascii_hexdigit())
    {
        return Err(
            "The API token must contain 32 to 128 hexadecimal characters.".to_owned(),
        );
    }
    Ok(token.to_owned())
}

fn parse_health_response(response: &str) -> Probe {
    let Some((headers, body)) = response.split_once("\r\n\r\n") else {
        return Probe::Occupied("The health response was incomplete.".to_owned());
    };
    let status = headers.lines().next().unwrap_or_default();
    if !status.contains(" 200 ") {
        return Probe::Occupied(format!("Unexpected health response: {status}"));
    }
    let Ok(payload) = serde_json::from_str::<serde_json::Value>(body) else {
        return Probe::Occupied("The health endpoint did not return valid JSON.".to_owned());
    };
    if payload.get("backend_ready").and_then(|value| value.as_bool()) != Some(true) {
        return Probe::Starting;
    }
    if payload.get("database_connected").and_then(|value| value.as_bool()) != Some(true)
        || payload
            .get("websocket_connected")
            .and_then(|value| value.as_bool())
            != Some(true)
    {
        return Probe::Starting;
    }
    Probe::Ready
}

struct PythonLauncher {
    executable: OsString,
    prefix_args: Vec<OsString>,
}

fn find_python(project_root: &Path) -> Result<PythonLauncher, String> {
    let mut candidates = Vec::new();
    if let Some(configured) = env::var_os("BLACKMARKET_PYTHON") {
        candidates.push(PythonLauncher {
            executable: configured,
            prefix_args: Vec::new(),
        });
    } else {
        for path in [
            project_root.join("venv").join("Scripts").join("python.exe"),
            project_root.join(".venv").join("Scripts").join("python.exe"),
            project_root.join("venv").join("bin").join("python"),
            project_root.join(".venv").join("bin").join("python"),
        ] {
            if path.is_file() {
                candidates.push(PythonLauncher {
                    executable: path.into_os_string(),
                    prefix_args: Vec::new(),
                });
            }
        }
        candidates.push(PythonLauncher {
            executable: OsString::from("python"),
            prefix_args: Vec::new(),
        });
        #[cfg(windows)]
        candidates.push(PythonLauncher {
            executable: OsString::from("py"),
            prefix_args: vec![OsString::from("-3")],
        });
    }

    let mut failures = Vec::new();
    for candidate in candidates {
        match python_version(&candidate, project_root) {
            Ok((major, minor)) if major > 3 || (major == 3 && minor >= 10) => {
                return Ok(candidate)
            }
            Ok((major, minor)) => failures.push(format!(
                "{} is Python {major}.{minor}; Python 3.10 or later is required",
                candidate.executable.to_string_lossy()
            )),
            Err(error) => failures.push(error),
        }
    }
    Err(format!(
        "No usable Python 3.10+ interpreter was found. Install the project environment or set BLACKMARKET_PYTHON. {}",
        failures.join("; ")
    ))
}

fn python_version(
    python: &PythonLauncher,
    project_root: &Path,
) -> Result<(u32, u32), String> {
    let output = Command::new(&python.executable)
        .args(&python.prefix_args)
        .arg("--version")
        .current_dir(project_root)
        .output()
        .map_err(|error| format!("{} could not be started: {error}", python.executable.to_string_lossy()))?;
    let version = format!(
        "{} {}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    let number = version
        .split_whitespace()
        .find(|part| part.starts_with("3.") || part.starts_with("2."))
        .ok_or_else(|| format!("Could not read the Python version from: {}", version.trim()))?;
    let mut parts = number.split('.');
    let major = parts
        .next()
        .and_then(|part| part.parse::<u32>().ok())
        .ok_or_else(|| format!("Invalid Python version: {number}"))?;
    let minor = parts
        .next()
        .and_then(|part| part.parse::<u32>().ok())
        .ok_or_else(|| format!("Invalid Python version: {number}"))?;
    Ok((major, minor))
}

fn find_project_root(resource_dir: Option<&Path>) -> Option<PathBuf> {
    let current_dir = env::current_dir().ok();
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let mut candidates = Vec::new();
    if let Some(path) = current_dir {
        candidates.extend(path.ancestors().map(Path::to_path_buf));
    }
    if let Some(path) = resource_dir {
        candidates.extend(path.ancestors().map(Path::to_path_buf));
        candidates.push(path.join("blackmarket_backend"));
    }
    if cfg!(debug_assertions) {
        if let Some(root) = manifest_dir.parent().and_then(Path::parent) {
            candidates.push(root.to_path_buf());
        }
    }
    candidates
        .into_iter()
        .find(|path| path.join("config.py").is_file() && path.join("src_tauri/backend/main.py").is_file())
}

fn read_log_tail(path: &Path) -> String {
    match fs::read_to_string(path) {
        Ok(contents) => {
            let tail: String = contents.chars().rev().take(4000).collect();
            let tail: String = tail.chars().rev().collect();
            if tail.trim().is_empty() {
                "Backend log is empty.".to_owned()
            } else {
                format!("Recent backend log:\n{tail}")
            }
        }
        Err(error) => format!("Backend log could not be read: {error}"),
    }
}

fn hide_console(command: &mut Command) {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let _ = command;
}

#[cfg(test)]
mod tests {
    use super::{parse_health_response, validate_api_token, Probe};

    #[test]
    fn health_check_requires_backend_database_and_websocket_readiness() {
        let ready = "HTTP/1.1 200 OK\r\ncontent-type: application/json\r\n\r\n{\"backend_ready\":true,\"database_connected\":true,\"websocket_connected\":true}";
        assert_eq!(parse_health_response(ready), Probe::Ready);

        let starting = "HTTP/1.1 200 OK\r\ncontent-type: application/json\r\n\r\n{\"backend_ready\":true,\"database_connected\":true,\"websocket_connected\":false}";
        assert_eq!(parse_health_response(starting), Probe::Starting);
    }

    #[test]
    fn health_check_rejects_unrelated_or_malformed_services() {
        assert!(matches!(
            parse_health_response("HTTP/1.1 404 Not Found\r\n\r\n{}"),
            Probe::Occupied(_)
        ));
        assert!(matches!(
            parse_health_response("HTTP/1.1 200 OK\r\n\r\nnot-json"),
            Probe::Occupied(_)
        ));
    }
}
    #[test]
    fn accepts_local_and_shared_hex_api_tokens() {
        assert!(validate_api_token(&"a".repeat(32)).is_ok());
        assert!(validate_api_token(&"b".repeat(64)).is_ok());
    }

    #[test]
    fn rejects_weak_or_non_hex_api_tokens() {
        assert!(validate_api_token("short").is_err());
        assert!(validate_api_token(&"g".repeat(64)).is_err());
        assert!(validate_api_token(&"a".repeat(129)).is_err());
    }

