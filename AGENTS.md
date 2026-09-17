# Oryn Agent Rules

This file contains mandatory instructions for coding agents working on Oryn.

Before making changes, read:

    PLAN.md
    AGENTS.md

The project plan is authoritative unless the user explicitly changes it.

---

# 1. Primary Rule

Do not change the product plan unless the user explicitly asks for a plan change.

Do not redesign Oryn because a different architecture appears more elegant.

The current architecture is intentional.

---

# 2. Current Priority

The current development priority is:

    Windows compatibility
        ->
    Cloud deployment
        ->
    Desktop packaging
        ->
    Real Linux <-> Windows testing
        ->
    Automatic capture
        ->
    Chrome
        ->
    Multi-application workspaces

Do not jump ahead.

If working on Windows compatibility, do not implement Chrome, automatic capture, multi-application support, or unrelated features.

---

# 3. Do Not Add Features Without Permission

Do not add:

- New applications
- New GUI features
- New cloud providers
- New databases
- New storage systems
- AI functionality
- Automatic background services
- New authentication mechanisms
- Large refactors

unless specifically requested.

Solve the requested problem first.

---

# 4. Inspect Before Editing

Before modifying a file:

1. Read the current file.
2. Understand how it interacts with the rest of the project.
3. Search for callers/usages when changing public behavior.
4. Check existing tests.
5. Make the smallest change that solves the problem.

Do not assume the code is still in the state described by an old prompt.

The repository is the source of truth.

---

# 5. Do Not Guess the Current State

Agents may receive stale context.

If something in the task conflicts with the current repository:

- inspect the repository
- inspect Git status
- inspect relevant files
- inspect tests
- determine the actual current implementation

Do not blindly apply changes from an old conversation.

---

# 6. Preserve Existing Architecture

Current architecture:

    GUI
      |
      v
    Oryn application/core/cloud modules
      |
      v
    FastAPI backend
      |
      v
    PostgreSQL

The GUI should remain thin.

The VS Code adapter owns VS Code-specific behavior.

The snapshot model owns snapshot representation.

The cloud client owns cloud communication.

The backend owns persistence and authentication.

Do not move responsibilities between these layers without a concrete reason.

---

# 7. No Unnecessary Dependencies

Do not install a new Python package unless it is genuinely required.

Before adding a dependency, check whether Python's standard library or an existing dependency already provides the required functionality.

Do not add packages simply because they are convenient.

Do not install packages automatically without explaining why they are necessary.

---

# 8. Do Not Modify Tests Just To Make Them Pass

Tests are evidence of expected behavior.

Do not weaken, delete, bypass, or rewrite tests merely because the implementation fails them.

If an existing test exposes a real bug, fix the implementation.

Only modify tests when the intended behavior itself has legitimately changed.

---

# 9. Do Not Break Existing Functionality

When changing cross-platform code:

Linux functionality must continue working.

When changing restore logic:

Existing-project restore must continue working.

Missing-project reconstruction must continue working.

When changing authentication:

Existing login/register behavior must continue working.

When changing snapshots:

Snapshot compatibility must be considered.

---

# 10. Cross-Platform Rules

Oryn must eventually support Linux and Windows.

Do not hardcode Linux behavior into shared code.

Avoid assumptions such as:

- `/usr/share/code/code`
- `pgrep`
- `pkill`
- `~/.config/Code`
- `/home/<username>`

Use platform-aware Python logic.

Windows paths and Linux paths must be treated correctly.

Do not use simple string replacement for filesystem path conversion when a proper path-based approach is required.

---

# 11. Path Safety

Any code that writes restored files must validate paths.

A snapshot must not be able to escape the intended project directory.

Reject or safely handle paths such as:

    ../../file
    ../../../etc/file

Also account for platform-specific path behavior.

Do not trust snapshot paths simply because they came from Oryn Cloud.

---

# 12. Snapshot Rules

Current snapshot version:

    4

Do not increment the snapshot version merely because an implementation detail changed.

Only change the snapshot version when the serialized snapshot format actually changes in a way that requires versioning.

Do not remove existing useful state without a specific reason.

Current important state includes:

- workspace path
- workspace ID
- open files
- active file
- editor groups
- editor layout
- cursor state
- selection state
- scroll state
- editor state
- text editor state
- project data
- unsaved content

---

# 13. Sensitive Data Rules

Never intentionally synchronize secrets.

Do not capture or restore:

- passwords
- API keys
- access tokens
- private keys
- secret environment variables
- authentication credentials

Be particularly careful when reading application databases.

Application state may contain information that was never intended to be portable.

Only capture state required for workspace restoration.

---

# 14. Cloud Rules

The desktop client communicates with the backend.

The desktop client must NOT connect directly to PostgreSQL.

PostgreSQL credentials must never be shipped inside the desktop application.

Never commit:

- `.env`
- database passwords
- JWT secrets
- API keys
- tokens

Use `.env.example` for configuration documentation.

---

# 15. GUI Rules

Keep the GUI simple.

Current GUI is Tkinter.

Do not introduce a new GUI framework unless explicitly requested.

Do not duplicate cloud or VS Code business logic inside GUI callbacks.

The GUI should call the existing application/cloud modules.

Network operations should not freeze the GUI.

---

# 16. Testing Rules

After modifying code:

1. Run syntax/compile checks.
2. Run relevant tests.
3. Run existing regression tests where practical.
4. Check Git diff.
5. Check Git status.

Do not claim something works without testing it when testing is possible.

If a test cannot be run because of an environment limitation, report the exact limitation.

Do not fake successful results.

---

# 17. Network Test Environment

Some agent environments may not allow access to:

    localhost
    127.0.0.1
    local PostgreSQL
    local Uvicorn

If a test fails because the agent environment cannot access the local server:

Do not change production code merely to bypass the environment restriction.

Report the environment limitation.

The user's machine should be used for local integration testing when required.

---

# 18. Git Rules

Do not commit changes unless the user explicitly asks for a commit.

Do not push changes unless the user explicitly asks for a push.

Do not reset or delete user work without explicit instruction.

Before making destructive Git operations, verify the requested scope carefully.

Never use Git commands that could silently destroy unrelated user changes.

---

# 19. File Modification Rules

Make focused changes.

Do not create backup files such as:

    adapter.py.backup
    file.old
    file.tmp

unless explicitly requested.

Do not leave generated junk files in the repository.

Do not modify unrelated files.

If an unrelated problem is discovered, report it instead of silently expanding scope.

---

# 20. Code Change Marking

When providing updated code to the user, mark changed sections with:

    # CHANGED:

This helps the user understand what was modified.

Do not add meaningless `# CHANGED` comments everywhere.

Only mark actual changed sections.

---

# 21. Complete Files

When the user asks for code, provide the complete file unless they explicitly request a patch or diff.

Do not provide fragments when the user needs a complete replacement file.

Preserve existing functionality in the complete file.

---

# 22. Agent Context Recovery

If an agent loses conversation context:

Read:

    PLAN.md
    AGENTS.md

Then inspect:

    git status
    git log --oneline -10

Then inspect the relevant source files and tests.

Do not ask the user to explain the entire project again before checking these files.

The repository contains the implementation.
PLAN.md contains the product direction.
AGENTS.md contains the working rules.

---

# 23. When Context Conflicts With The Repository

Use this priority:

1. Explicit current user instruction
2. Current repository implementation
3. PLAN.md
4. AGENTS.md
5. Older conversation context
6. Agent assumptions

If the user explicitly changes the plan, update PLAN.md as part of that work.

Do not silently reinterpret the plan.

---

# 24. When A Task Is Ambiguous

Do not invent major requirements.

For small implementation details, choose the simplest solution consistent with:

- PLAN.md
- AGENTS.md
- existing architecture
- existing tests

For a major architectural decision, stop and ask the user before proceeding.

---

# 25. No Scope Creep

A task such as:

    "Make VS Code work on Windows"

does NOT mean:

    redesign Oryn
    add Chrome
    redesign the GUI
    add automatic capture
    change databases
    add object storage
    package the application
    deploy the backend
    rewrite the snapshot system

Complete the requested task and stop.

---

# 26. Definition Of Done

A task is complete when:

- requested functionality is implemented
- existing functionality remains intact
- relevant tests pass
- no unnecessary dependencies were introduced
- no unrelated files were modified
- no temporary files remain
- Git diff is cleanly understandable
- the implementation matches PLAN.md

Do not continue adding features after the requested task is complete.

---

# 27. Oryn Philosophy

Keep Oryn understandable.

Prefer a simple system that works over a sophisticated system that requires an explanation longer than the code.

The objective is:

    reliable cross-device workspace restoration

not:

    maximum architectural complexity

When two solutions are technically viable, prefer the simpler one.

---

# 28. Current Task Boundary

At the beginning of the current development phase:

    DONE
    - Cloud backend
    - PostgreSQL
    - Authentication
    - Workspace API
    - Snapshot API
    - Snapshot v4
    - VS Code capture
    - VS Code restore
    - Existing project restore
    - Missing project reconstruction
    - Cross-device simulation
    - Desktop GUI

    CURRENT
    - Windows compatibility

    NEXT
    - Cloud deployment
    - Desktop packaging
    - Real Linux <-> Windows testing

    LATER
    - Automatic capture
    - Chrome support
    - Multi-application workspaces

Do not alter these priorities without explicit user instruction.