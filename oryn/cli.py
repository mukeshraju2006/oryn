from oryn.applications.vscode.adapter import VSCodeAdapter


def main():

    adapter = VSCodeAdapter()

    snapshot = adapter.capture()

    if not snapshot:
        print("Could not capture current VS Code session.")
        return

    data = snapshot.to_dict()

    print("Oryn Snapshot")
    print("=" * 40)

    print(f"Version:      {data['version']}")
    print(f"Application:  {data['application']}")
    print(f"Active file:  {data['active_file']}")

    print("\nWorkspace:")
    print(f"  ID:          {data['workspace']['id']}")
    print(f"  Path:        {data['workspace']['path']}")
    
    # CHANGED: Display captured unsaved changes.
    print("\nUnsaved changes:")

    if not data["unsaved_changes"]:
        print("  None")

    else:
        for path, content in data["unsaved_changes"].items():

            print(f"\n  {path}")
            print("  " + "-" * 36)

            for line in content.splitlines():
                print(f"    {line}")

    print("\nOpen editors:")

    for editor in data["editors"]:

        print(f"\n  {editor['path']}")

        if "group" in editor:
            print(
                f"    Group:      "
                f"{editor['group']}"
            )

        if "cursor" in editor:
            print(
                f"    Cursor:     "
                f"line {editor['cursor']['line']}, "
                f"column {editor['cursor']['column']}"
            )

        if "selection_start" in editor:
            print(
                f"    Selection:  "
                f"line {editor['selection_start']['line']}, "
                f"column {editor['selection_start']['column']}"
            )

        if "scroll" in editor:
            print(
                f"    Scroll:     "
                f"line {editor['scroll']['line']}, "
                f"column {editor['scroll']['column']}"
            )

        if "scroll_left" in editor:
            print(
                f"    Scroll left: "
                f"{editor['scroll_left']}"
            )

        if "first_position_delta_top" in editor:
            print(
                f"    Delta top:  "
                f"{editor['first_position_delta_top']}"
            )


if __name__ == "__main__":
    main()