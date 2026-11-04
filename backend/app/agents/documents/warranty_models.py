"""Domain models for the warranty-registration lane of the Documents agent (stdlib only).

From a completed job's installed equipment (brand/model/serial — serial read off a photo by OCR —
plus the install date), the engine determines the vendor's registration target + the required fields
and assembles a registration packet. Submitting it is a WRITE that goes through the action gate, and
the agent NEVER logs in: registration requires a HUMAN-established vendor session (a person signs into
the vendor portal first; the agent only fills the form). ADR-0003: deterministic compute here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class InstalledEquipment:
    """A piece of equipment installed on a completed job (serial typically OCR'd from a photo)."""

    id: str
    job_ref: str
    customer_name: str
    brand: str
    model: str
    serial: str | None       # read off the serial-plate photo; None if the photo was unreadable
    install_date: date
    serial_source: str = "photo_ocr"  # how the serial was obtained (audit/confidence)


@dataclass(frozen=True)
class WarrantyData:
    as_of: date
    equipment: list[InstalledEquipment] = field(default_factory=list)
