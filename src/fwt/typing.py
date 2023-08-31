"""Custom types for FWT."""
from __future__ import annotations

import re
from os import PathLike
from pathlib import Path
from typing import Union

from typing_extensions import TypeAlias, TypedDict


StrOrBytesPath: TypeAlias = Union[str, bytes, PathLike]
StrPath: TypeAlias = Union[Path, str]

StrPattern: TypeAlias = Union[str, re.Pattern]


class FoundryDesc(TypedDict):
    """Foundry item description."""

    value: str


class FoundryItemSystemData(TypedDict):
    """Foundry item data.

    V9 and below: ``item.data``
    V10+: ``item.system``
    """

    description: FoundryDesc


class FoundryItem(TypedDict):
    """Foundry item, as stored in the database."""

    name: str
    img: str
    system: FoundryItemSystemData
    # ! V9 Compat
    data: FoundryItemSystemData


class FoundryPrototypeTokenTexture(TypedDict):
    """Foudnry prototype token texture (V10+)."""

    src: str


class FoundryPrototypeToken(TypedDict):
    """Foudnry prototype token data (V10+)."""

    texture: FoundryPrototypeTokenTexture


class FoundryToken(TypedDict):
    """Foundry token data (V9 and below)."""

    img: str


class FoundryActorBiography(TypedDict):
    """Foundry actor biography."""

    value: str


class FoundryActorDetails(TypedDict):
    """Foundry actor details."""

    biography: FoundryActorBiography


class FoundryActorSystemData(TypedDict):
    """Foundry actor data.

    V9 and below: ``actor.data``
    V10+: ``actor.system``
    """

    details: FoundryActorDetails


class FoundryActor(TypedDict):
    """Foundry actor, as stored in the database."""

    name: str
    img: str
    prototypeToken: FoundryPrototypeToken
    system: FoundryActorSystemData
    # ! V9 Compat
    token: FoundryToken
    data: FoundryActorSystemData
