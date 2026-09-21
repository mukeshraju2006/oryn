"""Surface factories for cards and recessed wells.

Presentation only: a card is a raised surface, a well is a slightly deeper
recessed surface. Behaviour belongs to the screens.
"""

from tkinter import ttk


def card_frame(master, **kwargs):
    return ttk.Frame(master, style="Oryn.Card.TFrame", **kwargs)


# CHANGED: recessed surface variant used for wells and the sidebar.
def well_frame(master, **kwargs):
    return ttk.Frame(master, style="Oryn.Well.TFrame", **kwargs)


__all__ = ["card_frame", "well_frame"]
