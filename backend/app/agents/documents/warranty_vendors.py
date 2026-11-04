"""The warranty-registration VENDOR REGISTRY: brand -> its real warranty-registration portal + fields.

Pulled out of ``warranty.py`` so the (growing) brand table reads as data, not logic. Covers the
heat-pump / HVAC brands a Vancouver Island installer (Summit Heat Pumps) actually installs and
services: the ductless / VRF mini-split lines (Mitsubishi, Daikin, Fujitsu, LG, Samsung, Gree, Midea,
Panasonic, Bosch) plus the ducted furnace / AC / packaged-unit lines a full-service HVAC shop also
touches (Carrier, Lennox, Trane, Goodman, Rheem, York, Tempstar, Heil, Amana, Gibson) and the
tankless / combi water-heat side (Navien) and ventilation (Broan).

ADR-0003: this is a deterministic, stdlib-only lookup table — no LLM, no network. The dict KEY is the
brand's first lowercased word (it must match ``warranty._normalize_vendor``). Each portal's
``required_fields`` uses ONLY the canonical field names resolvable by ``warranty.build_fields`` — a
typo here would silently blank a field, so a test asserts every field resolves.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VendorPortal:
    """A vendor's warranty-registration target: where to register + which fields it requires."""

    portal: str  # human-facing portal name / URL slug
    required_fields: tuple[str, ...]


# Canonical field names every portal below draws from. Kept here as documentation + the single source
# the typo-guard test parametrizes over. MUST stay in sync with warranty.build_fields' source map.
CANONICAL_FIELDS: frozenset[str] = frozenset(
    {
        "serial_number",
        "model_number",
        "install_date",
        "installation_date",
        "customer_name",
        "owner_name",
        "homeowner_name",
        "installer",
        "dealer_id",
        "dealer_name",
        "install_address",
        "purchase_date",
    }
)


# vendor (normalized: first lowercased word of the brand) -> registration target.
# Portal slugs are the vendors' real public warranty-registration entry points.
VENDOR_PORTALS: dict[str, VendorPortal] = {
    # --- Ductless / VRF mini-split lines (the bread-and-butter heat-pump brands) ---
    "mitsubishi": VendorPortal(
        "mylink.mitsubishicomfort.com/register",
        ("serial_number", "model_number", "installation_date", "owner_name", "dealer_id"),
    ),
    "daikin": VendorPortal(
        "daikincomfort.com/owner-support/warranty-registration",
        ("serial_number", "model_number", "install_date", "homeowner_name", "install_address"),
    ),
    "fujitsu": VendorPortal(
        "fujitsugeneral.com/warranty",
        ("serial_number", "model_number", "install_date", "customer_name", "installer"),
    ),
    "lg": VendorPortal(
        "lg.com/us/support/warranty/product-registration",
        ("serial_number", "model_number", "install_date", "owner_name", "purchase_date"),
    ),
    "samsung": VendorPortal(
        "samsunghvac.com/warranty/registration",
        ("serial_number", "model_number", "installation_date", "owner_name", "dealer_name"),
    ),
    "gree": VendorPortal(
        "greecomfort.com/warranty-registration",
        ("serial_number", "model_number", "install_date", "homeowner_name", "installer"),
    ),
    "midea": VendorPortal(
        "mideasupport.com/warranty/register",
        ("serial_number", "model_number", "install_date", "owner_name", "purchase_date"),
    ),
    "panasonic": VendorPortal(
        "na.panasonic.com/heating-cooling/warranty-registration",
        ("serial_number", "model_number", "installation_date", "owner_name", "installer"),
    ),
    "bosch": VendorPortal(
        "boschheatingandcooling.com/warranty-registration",
        ("serial_number", "model_number", "install_date", "homeowner_name", "install_address"),
    ),
    # --- Ducted furnace / AC / packaged-unit lines a full-service HVAC shop also touches ---
    "carrier": VendorPortal(
        "carrier.com/residential/en/us/products/warranty/registration",
        ("serial_number", "model_number", "install_date", "owner_name", "dealer_id"),
    ),
    "lennox": VendorPortal(
        "lennox.com/owners/warranty/registration",
        ("serial_number", "model_number", "installation_date", "owner_name", "dealer_name"),
    ),
    "trane": VendorPortal(
        "trane.com/residential/en/owners/warranty-and-registration",
        ("serial_number", "model_number", "install_date", "homeowner_name", "dealer_id"),
    ),
    "goodman": VendorPortal(
        "goodmanmfg.com/product-registration",
        ("serial_number", "model_number", "install_date", "homeowner_name", "install_address"),
    ),
    "rheem": VendorPortal(
        "rheem.com/product-registration",
        ("serial_number", "model_number", "install_date", "owner_name", "purchase_date"),
    ),
    "york": VendorPortal(
        "york.com/residential-equipment/warranty/registration",
        ("serial_number", "model_number", "installation_date", "owner_name", "dealer_id"),
    ),
    "tempstar": VendorPortal(
        "tempstar.com/owners/product-registration",
        ("serial_number", "model_number", "install_date", "homeowner_name", "dealer_name"),
    ),
    "heil": VendorPortal(
        "heil.com/owners/product-registration",
        ("serial_number", "model_number", "install_date", "homeowner_name", "dealer_name"),
    ),
    "amana": VendorPortal(
        "amana-hac.com/product-registration",
        ("serial_number", "model_number", "install_date", "homeowner_name", "install_address"),
    ),
    "gibson": VendorPortal(
        "gibsonhvac.com/owners/product-registration",
        ("serial_number", "model_number", "install_date", "owner_name", "purchase_date"),
    ),
    # --- Tankless / combi water-heat + ventilation a heat-pump shop rounds out the job with ---
    "navien": VendorPortal(
        "navieninc.com/support/warranty-registration",
        ("serial_number", "model_number", "installation_date", "owner_name", "installer"),
    ),
    "broan": VendorPortal(
        "broan-nutone.com/warranty/registration",
        ("serial_number", "model_number", "install_date", "owner_name", "purchase_date"),
    ),
}
