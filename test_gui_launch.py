#!/usr/bin/env python3
# This script is used to test the GUI launch for a short time.
# We import the GUI module and then start the GUI in a separate thread and stop it after 2 seconds.
import sys
import os
import threading
import time

# Add the parent directory to the path so we can import oryn when running this script directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
from gui.app import OrynGUI

def test_gui_launch():
    root = tk.Tk()
    app = OrynGUI(root)
    # Destroy the window after 2000 milliseconds
    root.after(2000, root.destroy)
    root.mainloop()
    return True

if __name__ == "__main__":
    try:
        test_gui_launch()
        print("GUI launched and destroyed successfully after 2 seconds")
        sys.exit(0)
    except Exception as e:
        print(f"GUI launch failed: {e}")
        sys.exit(1)