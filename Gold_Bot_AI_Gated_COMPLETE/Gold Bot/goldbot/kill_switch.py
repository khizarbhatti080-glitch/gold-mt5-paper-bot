from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path


@dataclass
class KillSwitchState:
    engaged: bool = False
    close_all_requested: bool = False
    reason: str = ""
    changed_at_utc: str = ""


class KillSwitch:
    def __init__(self, path: str):
        self.path = Path(path)

    def read(self) -> KillSwitchState:
        if not self.path.exists():
            return KillSwitchState()
        return KillSwitchState(**json.loads(self.path.read_text(encoding="utf-8")))

    def set(self, engaged: bool, reason: str, close_all: bool = False) -> KillSwitchState:
        state = KillSwitchState(engaged, close_all, reason, datetime.now(timezone.utc).isoformat())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")
        temp.replace(self.path)
        return state

    def engage(self, reason: str, close_all: bool = False) -> KillSwitchState:
        return self.set(True, reason, close_all)

    def resume(self, reason: str) -> KillSwitchState:
        if not reason.strip():
            raise ValueError("resume requires an audit reason")
        return self.set(False, reason, False)
