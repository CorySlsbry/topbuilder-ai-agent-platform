"""Consumable → recommended-proration-basis catalog (ADR 0003 — pure, no LLM, no randomness).

The proration engine (``proration.py``) can split a consumable lot across the jobs it served three
ways: ``even`` / ``by_usage_proxy`` (linear feet, weight, or any per-job draw) / ``by_job_count``.
Until now the caller had to pick. But the RIGHT basis is a property of the MATERIAL, not the caller:

  * A copper line set, refrigerant pipe, vent/duct, or wire is drawn by the FOOT — the fair split is
    proportional to linear feet (``by_usage_proxy``). Dumping it evenly undercosts the long runs.
  * A refrigerant charge or solder is drawn by WEIGHT — fair split is proportional to pounds
    (``by_usage_proxy`` on weight).
  * Fittings, fasteners, sealant, tape, filters, condensate whips are DISCRETE handful-per-job
    consumables — there's no meaningful linear/weight proxy, so a per-job (``by_job_count``) split is
    both fair and the most you can know without per-unit counts.

This module classifies a consumable (by its ``unit`` and name/sku keywords) into one of those three
CATEGORIES and maps each category to its recommended basis. The engine consults it to make ``auto``
smarter when not every job carries a usage proxy: discrete materials get a clean per-job split, while
linear/weight materials still fall back to ``even`` (you can't proxy without data) BUT the result
reasoning names the basis the shop SHOULD capture next time (e.g. "log linear feet").
"""
from __future__ import annotations

from app.agents.inventory.proration import METHOD_BY_JOB_COUNT, METHOD_BY_USAGE

# Material categories — a property of the consumable, independent of any single job.
CATEGORY_LINEAR = "linear"  # measured by length: line set, pipe, duct, wire — unit "ft"
CATEGORY_WEIGHT = "weight"  # measured by mass: refrigerant charge, solder — unit "lb"
CATEGORY_DISCRETE = "discrete"  # handful-per-job: fittings, fasteners, tape, filters — unit "ea"
_VALID_CATEGORIES = (CATEGORY_LINEAR, CATEGORY_WEIGHT, CATEGORY_DISCRETE)

# Category -> the recommended proration basis (an existing engine method constant). Linear and weight
# both proxy on a per-job quantity (feet / pounds); discrete materials split per job.
CONSUMABLE_BASIS: dict[str, str] = {
    CATEGORY_LINEAR: METHOD_BY_USAGE,
    CATEGORY_WEIGHT: METHOD_BY_USAGE,
    CATEGORY_DISCRETE: METHOD_BY_JOB_COUNT,
}

# Human-readable proxy unit per category — used to tell the shop WHAT to capture next time.
CATEGORY_PROXY_LABEL: dict[str, str] = {
    CATEGORY_LINEAR: "linear feet",
    CATEGORY_WEIGHT: "pounds used",
    CATEGORY_DISCRETE: "per-job count",
}

# Name/sku keyword signals. Order is intentional: a charge/solder is WEIGHT even if the catalog calls
# it "refrigerant" (which also appears on pipe), so weight keywords are matched before linear.
_WEIGHT_KEYWORDS = ("charge", "solder", "braze", "flux")
_LINEAR_KEYWORDS = (
    "line set", "lineset", "pipe", "tubing", "tube", "vent", "duct", "wire", "cable",
    "coil", "conduit", "flex", "linear",
)
_DISCRETE_KEYWORDS = (
    "fitting", "fastener", "screw", "bolt", "nut", "anchor", "sealant", "caulk", "tape",
    "filter", "whip", "strap", "clamp", "connector", "lug", "terminal", "valve", "elbow", "tee",
)


def _norm(*parts: str) -> str:
    return " ".join(p for p in parts if p).lower()


def classify_consumable(name: str, sku: str, unit: str) -> str:
    """Classify a consumable into one of CATEGORY_LINEAR / CATEGORY_WEIGHT / CATEGORY_DISCRETE.

    Deterministic, keyword + unit based. The ``unit`` is the strongest signal ("lb" -> weight,
    "ft" -> linear, "ea" -> discrete); name/sku keywords refine or override an ambiguous unit
    (e.g. a "Refrigerant Charge" sold by the pound is WEIGHT even though it ships in a cylinder).
    """
    text = _norm(name, sku)
    unit_l = (unit or "").strip().lower()

    # Keyword precedence is intentional and deterministic:
    #   1. WEIGHT first  — a "charge"/"solder" is mass even if "refrigerant" also appears on pipe.
    #   2. DISCRETE next — the discrete keywords name the consumable NOUN itself ("duct sealant",
    #      "duct tape" are a tube/roll, NOT linear duct), so they override a co-occurring linear word.
    #   3. LINEAR last   — bare line set / pipe / vent / wire with no discrete noun present.
    if any(k in text for k in _WEIGHT_KEYWORDS):
        return CATEGORY_WEIGHT
    if any(k in text for k in _DISCRETE_KEYWORDS):
        return CATEGORY_DISCRETE
    if any(k in text for k in _LINEAR_KEYWORDS):
        return CATEGORY_LINEAR

    # No decisive keyword -> trust the unit of measure.
    if unit_l in ("lb", "lbs", "kg", "oz"):
        return CATEGORY_WEIGHT
    if unit_l in ("ft", "feet", "ft.", "m", "in", "inch"):
        return CATEGORY_LINEAR
    # "ea", blanks, and anything else are treated as discrete (per-job) by default.
    return CATEGORY_DISCRETE


def recommended_basis(name: str, sku: str, unit: str, category: str | None = None) -> str:
    """The recommended proration basis (engine method constant) for a consumable. Uses an explicitly
    set ``category`` when provided (and valid), else classifies from name/sku/unit."""
    cat = category if category in _VALID_CATEGORIES else classify_consumable(name, sku, unit)
    return CONSUMABLE_BASIS[cat]


def resolve_category(name: str, sku: str, unit: str, category: str | None = None) -> str:
    """The consumable's category — explicit when set & valid, else classified from name/sku/unit."""
    if category in _VALID_CATEGORIES:
        return category
    return classify_consumable(name, sku, unit)
