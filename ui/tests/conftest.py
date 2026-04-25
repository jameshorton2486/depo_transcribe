"""
Shared pytest fixtures for the ui/ test suite.

Multiple test modules need a CTk root to construct widgets against. Each
module previously declared its own module-scoped fixture, which left
pytest creating/destroying several Tk interpreters in a single session.
Tcl gets unhappy after enough teardowns ("invalid command name
tcl_findLibrary", "tk.tcl not found"). One session-scoped root sidesteps
that — every UI test inherits the same root.

Tests that mutate widget state must clean up after themselves; the root
is shared, not reset between tests.
"""

import customtkinter as ctk
import pytest


@pytest.fixture(scope="session")
def root():
    r = ctk.CTk()
    r.withdraw()
    yield r
    r.destroy()
