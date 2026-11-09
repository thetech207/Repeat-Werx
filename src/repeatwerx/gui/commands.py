"""Snapshot-based undo: every edit stores the document state before and
after, which keeps commands trivially correct for any operation."""

from __future__ import annotations

from PySide6.QtGui import QUndoCommand


class SnapshotCommand(QUndoCommand):
    MERGE_ID = 4242

    def __init__(self, win, label, before, after, sel_before, sel_after,
                 merge_key=None):
        super().__init__(label)
        self.win = win
        self.before, self.after = before, after
        self.sel_before, self.sel_after = sel_before, sel_after
        self.merge_key = merge_key
        self._first = True

    def id(self):
        return self.MERGE_ID if self.merge_key else -1

    def mergeWith(self, other):
        if not isinstance(other, SnapshotCommand) \
                or other.merge_key != self.merge_key:
            return False
        self.after = other.after
        self.sel_after = other.sel_after
        return True

    def redo(self):
        if self._first:
            self._first = False
            return
        self.win.restore_state(self.after, self.sel_after)

    def undo(self):
        self.win.restore_state(self.before, self.sel_before)
