import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk


class HistoryTable(ctk.CTkFrame):
    """
    In-memory download history shown as a Treeview.
    Resets every time the app is relaunched — no persistence.
    Right-click a row to open its containing folder.
    """

    COLUMNS  = ("title", "size", "resolution", "status")
    HEADINGS = ("Title", "Size", "Resolution", "Status")
    WIDTHS   = (300, 80, 100, 100)

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._paths: dict[str, str] = {}  # iid → file path
        self._build_tree()

    def _build_tree(self) -> None:
        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "History.Treeview",
            background="#2b2b2b",
            foreground="#ffffff",
            fieldbackground="#2b2b2b",
            rowheight=24,
            font=("Segoe UI", 11),
        )
        style.configure(
            "History.Treeview.Heading",
            background="#1e1e1e",
            foreground="#aaaaaa",
            font=("Segoe UI", 11, "bold"),
        )
        style.map("History.Treeview", background=[("selected", "#3a3a3a")])

        self._tree = ttk.Treeview(
            self,
            style="History.Treeview",
            columns=self.COLUMNS,
            show="headings",
            selectmode="browse",
        )

        for col, heading, width in zip(self.COLUMNS, self.HEADINGS, self.WIDTHS):
            self._tree.heading(col, text=heading)
            self._tree.column(col, width=width, minwidth=40, anchor="w")

        self._tree.tag_configure("success", foreground="#4caf50")
        self._tree.tag_configure("failure", foreground="#f44336")

        scrollbar = ctk.CTkScrollbar(self, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._tree.bind("<Button-3>", self._show_context_menu)

    def add_entry(self, meta: dict) -> None:
        """Add a completed download entry. Called from the UI thread."""
        status = meta.get("status", "—")
        tag = "success" if "Success" in status else "failure"

        iid = self._tree.insert(
            "",
            "end",
            values=(
                meta.get("title", "—"),
                meta.get("size", "—"),
                meta.get("resolution", "—"),
                status,
            ),
            tags=(tag,),
        )

        path = meta.get("path", "")
        if path:
            self._paths[iid] = path

        children = self._tree.get_children()
        if children:
            self._tree.see(children[-1])

    def clear(self) -> None:
        self._tree.delete(*self._tree.get_children())
        self._paths.clear()

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_context_menu(self, event: tk.Event) -> None:
        iid = self._tree.identify_row(event.y)
        if not iid:
            return
        self._tree.selection_set(iid)

        path = self._paths.get(iid, "")
        menu = tk.Menu(self, tearoff=0, bg="#2b2b2b", fg="#ffffff",
                       activebackground="#3a3a3a", activeforeground="#ffffff")

        if path and os.path.exists(os.path.dirname(path)):
            menu.add_command(
                label="Open containing folder",
                command=lambda: self._open_folder(path),
            )
        else:
            menu.add_command(label="Open containing folder", state="disabled")

        menu.tk_popup(event.x_root, event.y_root)

    @staticmethod
    def _open_folder(path: str) -> None:
        folder = os.path.dirname(os.path.abspath(path))
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])
