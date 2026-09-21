# Oryn

Oryn is a cross-device workspace capture and restoration application.

It captures the state of your development workspace, stores the snapshot in the cloud, and allows you to restore that workspace from another device.

The goal is simple:

> Capture your working context on one device and restore it on another.

Oryn does not migrate running processes or clone an entire operating system. Instead, it captures supported application and workspace state and reconstructs it on another machine.

---

## Features

### Authentication

- User registration
- User login
- JWT-based authentication
- Cloud-backed user accounts

### Workspace Snapshots

Oryn can capture a snapshot of your current workspace and store it in Oryn Cloud.

A snapshot can contain:

- Workspace information
- Project files
- VS Code state
- Active file information
- Editor state
- Unsaved editor content
- Browser URLs

### VS Code

Oryn supports capturing and restoring VS Code workspaces.

It can capture:

- Workspace/project information
- Project files
- File contents
- Active file
- Editor state
- Unsaved file content

When restoring a workspace on another device, Oryn can reconstruct the project files if the project does not already exist locally.

### Browser

Oryn can capture browser URLs and restore them on another device.

Current browser support:

- Google Chrome
- HTTP/HTTPS URLs

Browser capture currently works differently depending on the operating system:

- **Linux:** reads Chrome's session state
- **Windows:** uses live Chrome interaction to read open tabs

### Cloud Synchronization

Snapshots are uploaded to Oryn Cloud.

This allows a workspace captured on one machine to be retrieved and restored from another machine.

---

## How It Works

```text
                  Device A
                     |
                     | Capture
                     v
             +------------------+
             | Workspace        |
             | Snapshot         |
             +--------+---------+
                      |
                      | Upload
                      v
             +------------------+
             |    Oryn Cloud    |
             |                  |
             |    PostgreSQL    |
             +--------+---------+
                      |
                      | Download
                      v
             +------------------+
             | Workspace        |
             | Restoration      |
             +--------+---------+
                      |
                      v
                  Device B
```

Oryn captures workspace state rather than migrating running processes.

The restored workspace is reconstructed on the destination device using the information stored in the snapshot.

---

## Architecture

```text
+--------------------------------------+
|            Oryn Desktop              |
|                                      |
|  GUI                                 |
|   |                                  |
|   +-- VS Code Adapter                |
|   |                                  |
|   +-- Browser Adapter                |
|   |                                  |
|   +-- Snapshot System                |
|                |                     |
|                v                     |
|          Cloud Client                |
+----------------+---------------------+
                 |
                 | HTTPS
                 v
+--------------------------------------+
|             Oryn Cloud               |
|                                      |
|               FastAPI                |
|                  |                   |
|                  v                   |
|              PostgreSQL              |
+--------------------------------------+
```

### Desktop Application

The desktop application is written in Python.

The main components include:

- GUI
- Application adapters
- Snapshot model
- Cloud client
- Authentication/session handling

### Application Adapters

Oryn uses application-specific adapters to capture and restore supported applications.

Current adapters:

```text
oryn/
└── applications/
    ├── browsers/
    │   └── adapter.py
    │
    └── vscode/
        └── adapter.py
```

Each adapter is responsible for application-specific capture and restoration logic.

### Backend

The Oryn backend uses:

- FastAPI
- PostgreSQL
- JWT authentication
- Argon2 password hashing

The backend provides APIs for:

- Users
- Authentication
- Workspaces
- Snapshots

---

## Supported Platforms

| Platform | Status |
|---|---|
| Windows x64 | Supported |
| Linux x86_64 | Supported |
| macOS | Not currently supported |

---

# Installation

## Windows

Download the latest Windows installer from the GitHub Releases page.

Download:

```text
Oryn-Setup.exe
```

Run the installer and follow the installation steps.

Oryn will be available from the Start Menu and desktop shortcut.

---

## Linux

Download the Linux AppImage from the GitHub Releases page.

Example:

```text
Oryn-0.1.0-linux-x86_64.AppImage
```

Make it executable:

```bash
chmod +x Oryn-0.1.0-linux-x86_64.AppImage
```

Run:

```bash
./Oryn-0.1.0-linux-x86_64.AppImage
```

The distributed AppImage does not require Python or a Python virtual environment.

---

# Using Oryn

## 1. Login

Launch Oryn and log into your Oryn account.

## 2. Open Your Workspace

Open the development environment you want to capture.

For the current MVP, VS Code and Google Chrome are supported.

## 3. Capture

Use the **Capture** action in Oryn.

Oryn collects the supported workspace information and creates a snapshot.

The snapshot is then uploaded to Oryn Cloud.

## 4. Switch Devices

Install Oryn on another supported machine and log into the same account.

## 5. Restore

Select the snapshot and restore it.

Oryn reconstructs the supported workspace state on the new device.

---

# Current Limitations

Oryn is currently an MVP and has several known limitations.

### VS Code Editor Layout

Exact VS Code editor-group and layout restoration is not guaranteed.

Project files and relevant editor state are captured, but the exact arrangement of editor groups may differ after restoration.

### Windows Browser Capture

Windows Chrome capture currently uses live browser interaction to read open tabs.

This means Oryn temporarily interacts with the Chrome window during capture.

This is a current implementation limitation.

### Linux Browser Capture

Linux Chrome capture uses Chrome's stored session state.

The stored session state may not always represent every browser change immediately before capture.

### Running Processes

Oryn does not migrate or restore running processes.

It does not currently restore:

- Running terminal processes
- Running development servers
- Background processes
- Process memory/state

The current focus is workspace and application state reconstruction.

### Operating System State

Oryn does not clone or migrate the operating system.

It does not attempt to reproduce:

- Installed system packages
- System services
- Hardware configuration
- Operating-system processes
- Complete machine state

---

# Project Structure

```text
oryn/
|
+-- oryn/
|   |
|   +-- core/
|   |   +-- snapshot.py
|   |
|   +-- applications/
|   |   |
|   |   +-- browsers/
|   |   |   +-- adapter.py
|   |   |
|   |   +-- vscode/
|   |       +-- adapter.py
|   |
|   +-- cloud/
|       |
|       +-- client.py
|       +-- session.py
|
+-- gui/
|   +-- ...
|
+-- server/
|   +-- app/
|       +-- models/
|       +-- routes/
|
+-- installer/
|   +-- Oryn.iss
|
+-- requirements.txt
+-- pyproject.toml
+-- .env.example
+-- README.md
```

---

# Development Setup

## Requirements

- Python 3.11+
- Git
- Google Chrome
- VS Code

Clone the repository:

```bash
git clone <repository-url>
cd oryn
```

---

## Linux

Create a virtual environment:

```bash
python3 -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run Oryn:

```bash
python -m gui.app
```

---

## Windows

Create a virtual environment:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.venv\Scripts\activate
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Run Oryn:

```powershell
python -m gui.app
```

---

# Building Oryn

## Windows

Oryn uses PyInstaller to package the desktop application and Inno Setup 7 to create the Windows installer.

Build the application:

```powershell
python -m PyInstaller `
    --clean `
    --noconfirm `
    --windowed `
    --name Oryn `
    gui\app.py
```

The packaged application is generated under:

```text
dist/Oryn/
```

Build the installer using Inno Setup 7:

```powershell
"C:\Program Files\Inno Setup 7\ISCC.exe" installer\Oryn.iss
```

The resulting installer is:

```text
dist/installer/Oryn-Setup.exe
```

---

## Linux

Build the PyInstaller application:

```bash
python -m PyInstaller \
    --clean \
    --noconfirm \
    --windowed \
    --name Oryn \
    gui/app.py
```

The packaged application is generated under:

```text
dist/Oryn/
```

The Linux release is distributed as an AppImage.

---

# Backend

The Oryn backend is deployed separately from the desktop application.

The backend provides APIs for:

- Authentication
- Users
- Workspaces
- Snapshots

The desktop application communicates with the backend over HTTPS.

Server-side secrets must never be included in the desktop application or committed to the repository.

---

# Security

Oryn currently uses:

- JWT authentication
- Argon2 password hashing
- User-scoped workspaces
- User-scoped snapshots

Environment files containing secrets should never be committed.

Use:

```text
.env.example
```

as the template for local configuration.

Never commit:

```text
.env
```

---

# Release

Oryn releases are distributed through GitHub Releases.

A release contains platform-specific artifacts.

Example:

```text
Oryn v0.1.0

+-- Oryn-Setup.exe
+-- Oryn-0.1.0-linux-x86_64.AppImage
```

Users do not need the source code, Python environment, PyInstaller, or development dependencies to run the packaged applications.

---

# Current Release

## Oryn v0.1.0

The first MVP release provides:

- User authentication
- Cloud-backed workspace snapshots
- VS Code workspace capture
- VS Code workspace restoration
- Project file capture and reconstruction
- Browser URL capture
- Browser URL restoration
- Windows support
- Linux support

---

# Roadmap

Future development may improve:

- Browser state capture
- Application state capture
- Cross-platform support
- Workspace restoration accuracy
- Automatic/background capture
- Additional application adapters

---

# License

This project is licensed under the MIT License.

See the `LICENSE` file for details.
