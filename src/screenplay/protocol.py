"""Public protocol. This module contains no game state or filesystem access."""
from __future__ import annotations

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


Coordinate = Annotated[int, Field(ge=0, le=8191)]
Duration = Annotated[int, Field(ge=1, le=1000)]


class Click(StrictModel):
    type: Literal["click"]
    x: Coordinate
    y: Coordinate
    button: Literal["left", "right", "middle"] = "left"
    count: Literal[1, 2] = 1


class Move(StrictModel):
    type: Literal["mouse_move"]
    x: Coordinate
    y: Coordinate


class Drag(StrictModel):
    type: Literal["drag"]
    from_: Annotated[list[Coordinate], Field(min_length=2, max_length=2)] = Field(alias="from")
    to: Annotated[list[Coordinate], Field(min_length=2, max_length=2)]
    duration_ms: Duration = 300
    button: Literal["left", "right", "middle"] = "left"


class KeyPress(StrictModel):
    type: Literal["key_press"]
    key: Literal["up", "down", "left", "right", "space", "enter", "escape", "u", "r", "z"]


class Wait(StrictModel):
    type: Literal["wait"]
    duration_ms: Annotated[int, Field(ge=1, le=5000)]


class Finish(StrictModel):
    type: Literal["finish"]


Action = Annotated[Click | Move | Drag | KeyPress | Wait | Finish, Field(discriminator="type")]
ACTION = TypeAdapter(Action)


class ActionRequest(StrictModel):
    episode_id: Annotated[str, Field(min_length=1, max_length=80)]
    action_id: Annotated[str, Field(min_length=1, max_length=100)]
    based_on_observation_id: Annotated[int, Field(ge=0)]
    action: dict


def validate_action(payload: dict, width: int, height: int):
    action = ACTION.validate_python(payload)
    coords = []
    if isinstance(action, (Click, Move)):
        coords = [(action.x, action.y)]
    if isinstance(action, Drag):
        coords = [action.from_, action.to]
    if any(x >= width or y >= height for x, y in coords):
        raise ValueError("coordinate_outside_observation")
    return action
