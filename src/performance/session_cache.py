from __future__ import annotations

import json
from typing import Any

from ..db import Database


class SessionCache:
    def __init__(self, db: Database, key: str = "operator_ui_state_json"):
        self.db = db
        self.key = key

    def load(self) -> dict[str, Any]:
        raw = self.db.get_settings().get(self.key, "{}")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = {}
        return value if isinstance(value, dict) else {}

    def save(self, **state: Any) -> dict[str, Any]:
        current = self.load()
        current.update({key: value for key, value in state.items() if value is not None})
        self.db.set_settings({self.key: json.dumps(current, ensure_ascii=False)})
        return current

    def clear(self) -> None:
        self.db.set_settings({self.key: "{}"})
