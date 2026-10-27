"""Step 2: define exactly four required, strict action fields. See reading.md."""
from typing import Literal
from pydantic import BaseModel, ConfigDict


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    # TODO: action, item, target and focus. Use Literal for action and focus.
    # The current room schema, not this type, decides which object IDs are known.
