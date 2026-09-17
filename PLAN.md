# Oryn Project Plan

## 1. What Is Oryn?

Oryn is a cross-device workspace and application/session restoration platform.

The goal is to allow a user to continue their work on another computer without manually rebuilding their development environment and workspace state.

Example:

1. User works on Laptop A.
2. Oryn captures the current workspace.
3. The snapshot is stored in Oryn Cloud.
4. User moves to Laptop B.
5. User logs into Oryn.
6. Oryn restores the workspace.
7. The user continues working from approximately the same state.

Oryn does NOT migrate running processes between machines.

Oryn captures and reconstructs application/workspace state.

---

# 2. Product Goal

The long-term goal is:

> Capture a user's working environment and restore it on another device.

The restored environment should preserve as much useful workspace state as possible.

For VS Code this includes:

- Project/workspace directory
- Open files
- Active file
- Cursor positions
- Selection state
- Scroll positions
- Editor groups/layout
- Unsaved file contents
- Project files
- Other relevant VS Code workspace state

The system should eventually support multiple applications.

VS Code is the first application being implemented.

Chrome and multi-application workspaces come later.

---

# 3. Core Architecture

Oryn is a desktop application.

It is NOT a website.

The intended production architecture is:

    GitHub Repository
           |
           v
    Oryn Desktop App
      /          \
 Laptop A       Laptop B
      \          /
       \        /
        HTTPS
          |
          v
    Public FastAPI Backend
          |
          v
    Managed PostgreSQL

The desktop application communicates with the backend over HTTPS.

The desktop application must NOT connect directly to PostgreSQL.

PostgreSQL is the cloud source of truth for metadata and snapshot JSON.

Object storage may be introduced later for large snapshot payloads.

---

# 4. Current Technology

## Desktop Application

- Python
- Tkinter for the initial GUI
- Existing Oryn Python modules
- VS Code adapter

## Backend

- FastAPI
- SQLAlchemy
- PostgreSQL
- psycopg
- JWT authentication
- Argon2 password hashing

## Snapshot

- JSON-based snapshot representation
- Current snapshot version: 4

---

# 5. Repository Structure

Current important structure:

    oryn/
    ├── oryn/
    │   ├── __init__.py
    │   ├── __main__.py
    │   ├── cli.py
    │   ├── core/
    │   │   └── snapshot.py
    │   ├── applications/
    │   │   └── vscode/
    │   │       └── adapter.py
    │   └── cloud/
    │       ├── client.py
    │       └── session.py
    │
    ├── gui/
    │   ├── __init__.py
    │   └── app.py
    │
    ├── server/
    │   └── app/
    │       ├── main.py
    │       ├── database.py
    │       ├── models/
    │       └── routes/
    │
    └── test_cloud.py

Do not restructure the project without a specific reason and explicit approval.

---

# 6. Completed Milestones

The following functionality has already been implemented and tested.

## 6.1 Cloud Backend

Completed:

- FastAPI backend
- PostgreSQL database
- SQLAlchemy models
- User model
- Workspace model
- Snapshot model
- JWT authentication
- User registration
- User login
- Password hashing
- Authenticated workspace operations
- Authenticated snapshot operations
- Ownership checks

---

## 6.2 Environment Configuration

Completed:

- Database configuration through environment variables
- JWT secret through environment variables
- `.env` for local secrets
- `.env.example` for repository documentation
- `.env` excluded from Git

Never commit secrets.

---

# 7. VS Code Snapshot System

VS Code is currently the primary application supported by Oryn.

The snapshot system currently uses snapshot version 4.

The snapshot contains information including:

- Application
- Workspace
- Workspace path
- Workspace ID
- Open files
- Active file
- Editor groups
- Editor layout
- Active editor group
- Most recently active groups
- Cursor state
- Selection state
- Scroll state
- Raw VS Code editor state
- Raw VS Code text editor state
- Project data

The project portion stores portable relative paths and file contents.

This allows a project to be reconstructed on another machine when the project does not already exist there.

---

# 8. Cross-Device Path Mapping

A major requirement of Oryn is that paths must work across different machines.

Example:

Source machine:

    /home/mukesh/projects/oryn

Destination machine:

    /home/otheruser/

The source home directory should be mapped to the destination user's home directory.

Result:

    /home/mukesh/projects/oryn
        ->
    /home/otheruser/projects/oryn

The system should not require the user to manually specify the project destination during normal restore.

---

# 9. Existing Project Restore

When restoring a snapshot:

1. Determine the original workspace path.
2. Map the source user's path to the current user's path.
3. Check whether the mapped project exists.

If the project exists:

- Use the existing project.
- Restore VS Code workspace/editor state.

If the project does not exist:

- Reconstruct the project from the portable project data in the snapshot.
- Restore file contents.
- Restore unsaved file contents.
- Restore VS Code workspace/editor state.
- Open the reconstructed project.

The project reconstruction has already been tested for byte-for-byte correctness in the simulated cross-device restore tests.

---

# 10. Important VS Code Details

VS Code is a multi-process application.

The implementation must not assume that one VS Code process represents the entire application.

The current implementation uses VS Code's workspace storage and state databases to identify workspace/editor state.

Important VS Code data includes:

- `workspace.json`
- `state.vscdb`
- editor layout state
- text editor state

The adapter must distinguish actual open editors from historical/closed editor entries.

Historical entries must not accidentally become open files during restoration.

---

# 11. Sensitive Data

VS Code state may contain sensitive information.

Do NOT capture or synchronize secrets unnecessarily.

In particular, do not copy:

- Environment variables containing secrets
- API keys
- Tokens
- Passwords
- Authentication credentials
- Private keys
- Other unrelated sensitive data

The VS Code environment-variable collection state is not part of the portable workspace state.

The goal is workspace restoration, not secret synchronization.

---

# 12. Desktop GUI

The initial desktop GUI has been implemented.

Current GUI functionality:

- Login
- Registration
- Dashboard
- Workspace selection
- Snapshot selection
- Capture workspace
- Restore workspace
- Refresh
- Logout
- Status messages
- Session/token handling

The GUI should remain thin.

Business logic belongs in the existing Oryn modules.

Do not move application logic into the Tkinter GUI unnecessarily.

---

# 13. Current Development Milestone

The immediate milestone is:

## Cross-platform Windows compatibility

The current prototype was developed and tested primarily on Linux.

The next work is to make the VS Code adapter work correctly across:

- Linux
- Windows

This includes:

- VS Code process detection
- VS Code executable discovery
- VS Code process termination
- VS Code workspace storage location
- Session storage location
- Home directory handling
- Windows path handling
- Cross-platform path remapping
- Restore path safety

The Linux implementation must continue working.

Do not break Linux functionality while adding Windows support.

---

# 14. Windows Compatibility Requirements

Linux-specific assumptions must not remain in the cross-platform implementation.

Examples of Linux-specific behavior that must be replaced where appropriate:

- Hardcoded `/usr/share/code/code`
- `pgrep`
- `pkill`
- Linux-only workspace storage paths
- Linux-only path manipulation

Windows equivalents must be handled through platform-aware Python logic.

Do not add unnecessary dependencies merely to solve a problem that Python's standard library can handle.

---

# 15. Restore Safety

Restoration writes files to the destination machine.

Restoration must ensure that snapshot paths cannot escape the intended destination directory.

For example, a snapshot containing paths such as:

    ../../outside.txt

must not cause Oryn to write outside the destination project.

Path validation should happen before writing files.

The destination path must remain inside the intended project root.

---

# 16. Testing Requirements

Every major change must be tested.

At minimum:

- Python syntax/compile check
- Existing tests
- Relevant unit/integration tests
- Linux regression testing when changing cross-platform code

Windows-specific functionality must eventually be tested on an actual Windows machine.

The final cross-device test should be:

    Linux Laptop
        |
        | capture
        v
    Oryn Cloud
        |
        | restore
        v
    Windows Laptop

The reverse direction should also eventually be tested:

    Windows Laptop
        |
        | capture
        v
    Oryn Cloud
        |
        | restore
        v
    Linux Laptop

---

# 17. Deployment Plan

After Windows compatibility is working and tested:

1. Deploy FastAPI backend publicly.
2. Move PostgreSQL to managed cloud PostgreSQL.
3. Configure production API URL.
4. Keep desktop application as the client.
5. Test authentication and snapshot upload/download against production.
6. Package Oryn as a desktop application.
7. Publish releases through GitHub.
8. Test installation on clean machines.

The desktop application must never require the user to run Uvicorn or PostgreSQL locally in production.

Local Uvicorn/PostgreSQL are development infrastructure only.

---

# 18. Future Roadmap

The following are intentionally later phases.

## Phase 1

VS Code

Status:

- Capture: implemented
- Snapshot: implemented
- Cloud storage: implemented
- Existing-project restore: implemented
- Missing-project reconstruction: implemented
- Workspace state restoration: implemented
- Cross-device simulation: implemented
- Desktop GUI: implemented

Current focus:

- Windows compatibility

---

## Phase 2

Cloud deployment

- Public FastAPI backend
- Managed PostgreSQL
- Production configuration
- HTTPS
- Desktop-to-cloud testing

---

## Phase 3

Desktop packaging

- Linux release
- Windows release
- Installation flow
- Production configuration

---

## Phase 4

Real Linux <-> Windows testing

Test actual machines rather than simulated paths.

---

## Phase 5

Automatic background capture

Oryn should eventually be able to capture workspace changes automatically.

This should be introduced only after the manual capture/restore pipeline is stable.

---

## Phase 6

Chrome support

Capture and restore relevant Chrome browser workspace/session state.

Chrome is NOT part of the current VS Code milestone.

Do not implement Chrome while working on Windows compatibility unless explicitly requested.

---

## Phase 7

Multi-application workspaces

Eventually a single Oryn workspace may contain multiple applications.

Example:

    VS Code
    Chrome
    Terminal
    Other supported applications

The workspace should represent the user's working context rather than a single application.

---

# 19. Explicitly Out of Scope Right Now

Do NOT implement these unless explicitly requested:

- Chrome support
- Automatic background capture
- Multi-application workspace orchestration
- Process migration
- VM/container migration
- Remote desktop functionality
- OS-level snapshotting
- Full operating-system restoration
- macOS support
- Mobile applications
- AI features
- Unrelated UI redesign
- Unrelated dependency changes
- Large architectural rewrites

The current priority is Windows compatibility followed by deployment and packaging.

---

# 20. Important Design Principle

Oryn should restore useful user work state, not blindly copy every application database.

Capture only the state required to reconstruct the workspace.

Prefer:

    portable structured state

over:

    machine-specific application internals

When machine-specific state is necessary, isolate it inside the application adapter.

---

# 21. Development Philosophy

Keep the implementation simple.

Prefer:

- Python standard library where practical
- Existing project architecture
- Small focused changes
- Explicit platform abstraction
- Reusable adapters
- Testable logic
- Portable snapshot data

Avoid:

- unnecessary dependencies
- unnecessary abstractions
- premature optimization
- unrelated refactoring
- architectural rewrites
- feature creep

The goal is to make Oryn work reliably, not to create an elaborate framework for making Oryn work.

---

# 22. Definition of Success

The first meaningful production milestone is:

A user can install Oryn on two different computers, log into the same account, capture a VS Code workspace on one computer, and restore that workspace on the other computer without manually rebuilding the project or editor state.

That is the core Oryn MVP.

Everything else comes after this works reliably.