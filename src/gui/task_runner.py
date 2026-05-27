from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, Signal, Slot


class BackgroundWorker(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self, task: Callable[[], Any]):
        super().__init__()
        self.task = task

    @Slot()
    def run(self) -> None:
        try:
            self.result.emit(self.task())
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()
