"""Deterministic warranty-registration engine: equipment -> vendor target + required fields -> packet.

No LLM, no randomness. For each piece of installed equipment on a completed job the engine resolves the
vendor's registration target (the portal + the fields that vendor requires) and assembles a ready-to-
submit registration packet. Equipment with no readable serial (the OCR couldn't read the serial-plate
photo) or an unknown vendor routes to a human. Submitting the registration is a WRITE through the
action gate (ADR 0007), and the agent NEVER signs in — submission requires a HUMAN-established vendor
session (enforced in the executor, not here). The reasoning layer narrates; it never decides (ADR 0003).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date

from app.agents.documents.warranty_models import InstalledEquipment, WarrantyData
# The brand table is data, not logic — it lives in its own registry module (re-exported here so
# existing callers of `warranty.VendorPortal` / `warranty.VENDOR_PORTALS` keep working unchanged).
from app.agents.documents.warranty_vendors import VENDOR_PORTALS, VendorPortal

__all__ = ["VENDOR_PORTALS", "VendorPortal"]


@dataclass(frozen=True)
class WarrantyPacket:
    """A ready-to-submit registration packet for one piece of equipment (auto-fills the vendor form)."""

    equipment_id: str
    job_ref: str
    customer_name: str
    brand: str
    model: str
    serial: str
    portal: str
    fields: dict[str, str]   # the vendor's required_fields, filled from the equipment record
    confidence: float
    reasoning: str


@dataclass(frozen=True)
class WarrantyException:
    """Equipment we can't register unattended — unreadable serial or an unknown vendor."""

    equipment_id: str
    job_ref: str
    brand: str
    reason: str


@dataclass(frozen=True)
class WarrantyTotals:
    equipment_processed: int
    packets_ready: int
    needs_human: int


@dataclass(frozen=True)
class WarrantyAnalysis:
    as_of: date
    packets: list[WarrantyPacket]
    needs_human: list[WarrantyException]
    totals: WarrantyTotals
    inputs_hash: str


def _normalize_vendor(brand: str) -> str:
    return brand.strip().lower().split()[0] if brand.strip() else ""


def resolve_portal(brand: str) -> VendorPortal | None:
    """Resolve a brand to its warranty-registration target. None if the vendor is not configured."""
    return VENDOR_PORTALS.get(_normalize_vendor(brand))


INSTALLER_NAME = "Summit Heat Pumps"


def build_fields(eq: InstalledEquipment, portal: VendorPortal) -> dict[str, str]:
    """Fill a vendor's required fields from the equipment record (ADR-0003: a deterministic mapping).

    Every name in any portal's ``required_fields`` MUST be a key in ``source`` — an unmapped name
    would silently resolve to ``""`` (a blank-by-typo). ``test_warranty`` asserts this can't happen.
    ``install_address`` / ``purchase_date`` are resolved off the equipment record via ``getattr`` so
    the mapping degrades gracefully if the upstream model hasn't been extended yet (purchase date for
    a contractor-supplied unit is the install date — the proof-of-purchase a vendor portal expects).
    """
    # Map our canonical equipment record onto whatever the vendor calls each field.
    install_iso = eq.install_date.isoformat()
    source: dict[str, str] = {
        "serial_number": eq.serial or "",
        "model_number": eq.model,
        "install_date": install_iso,
        "installation_date": install_iso,
        "customer_name": eq.customer_name,
        "owner_name": eq.customer_name,
        "homeowner_name": eq.customer_name,
        "installer": INSTALLER_NAME,
        "dealer_id": INSTALLER_NAME,
        "dealer_name": INSTALLER_NAME,
        "install_address": getattr(eq, "install_address", "") or eq.customer_name,
        "purchase_date": getattr(eq, "purchase_date", "") or install_iso,
    }
    return {f: source.get(f, "") for f in portal.required_fields}


def analyze(data: WarrantyData) -> WarrantyAnalysis:
    packets: list[WarrantyPacket] = []
    needs_human: list[WarrantyException] = []

    for eq in data.equipment:
        portal = resolve_portal(eq.brand)
        if portal is None:
            needs_human.append(
                WarrantyException(eq.id, eq.job_ref, eq.brand,
                                  f"no warranty portal configured for vendor '{eq.brand}'")
            )
            continue
        if not eq.serial:
            needs_human.append(
                WarrantyException(eq.id, eq.job_ref, eq.brand,
                                  "serial number unreadable from the photo — needs a human to read it")
            )
            continue

        fields = build_fields(eq, portal)
        packets.append(
            WarrantyPacket(
                equipment_id=eq.id, job_ref=eq.job_ref, customer_name=eq.customer_name,
                brand=eq.brand, model=eq.model, serial=eq.serial, portal=portal.portal, fields=fields,
                confidence=0.9,
                reasoning=(
                    f"{eq.brand} {eq.model} (serial {eq.serial}) on job {eq.job_ref}: register at "
                    f"{portal.portal}; packet ready — submit after a human signs into the vendor portal."
                ),
            )
        )

    totals = WarrantyTotals(
        equipment_processed=len(data.equipment),
        packets_ready=len(packets),
        needs_human=len(needs_human),
    )
    return WarrantyAnalysis(data.as_of, packets, needs_human, totals, _hash_inputs(data))


def _hash_inputs(data: WarrantyData) -> str:
    payload = {
        "as_of": data.as_of.isoformat(),
        "equipment": sorted((asdict(e) for e in data.equipment), key=lambda r: r["id"]),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
