"""Oryn Desktop Application Entry Point.

This module is executed when running `python -m oryn` and launches the GUI.
"""

import sys
import os

# When running as `python -m oryn`, add the project root to the path so we can import gui
if __name__ == "oryn.__main__":
    # __file__ is .../oryn/__main__.py
    # Project root is two levels up: .../oryn/
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the main function from gui.app
try:
    from gui.app import main
except ImportError:
    # Fallback for when the package is installed differently
    from oryn.gui.app import main

if __name__ == "__main__":
    main()