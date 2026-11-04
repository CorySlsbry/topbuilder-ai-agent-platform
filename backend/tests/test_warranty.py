"""Unit + property tests for the deterministic warranty-registration engine.

Hand-computed oracle (4 pieces of installed equipment):
  - EQ1: Fujitsu, serial read       -> PACKET (fujitsugeneral.com/warranty)
  - EQ2: Mitsubishi, serial read    -> PACKET (mylink.mitsubishicomfort.com/register)
  - EQ3: Fujitsu, serial UNREADABLE -> NEEDS_HUMAN (unreadable serial)
  - EQ4: Whirlpool (no portal)      -> NEEDS_HUMAN (unknown vendor — not an HVAC brand we register)
=> packets_ready 2 / needs_human 2.

Also asserts the executor's hard safety rule: the agent NEVER signs in — register_warranty refuses
without a human-established vendor session, and carries no credentials.
"""
from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.agents.documents import warranty as w
from app.agents.documents.warranty_models import InstalledEquipment, WarrantyData

AS_OF = date(2026, 6, 16)
INSTALL = date(2026, 6, 10)


def _eq(eid: str, **kw) -> InstalledEquipment:
    base = {"job_ref": "JOB-9001", "customer_name": "Peter Powell", "brand": "Fujitsu",
            "model": "AOU24RLXFZH", "serial": "FJ-2026-0001", "install_date": INSTALL}
    base.update(kw)
    return InstalledEquipment(id=eid, **base)


def _scenario() -> WarrantyData:
    equipment = [
        _eq("EQ1", brand="Fujitsu", serial="FJ-2026-0001"),
        _eq("EQ2", brand="Mitsubishi", model="MSZ-FS12NA", serial="MIT-77-ABCD", customer_name="Mercer Building"),
        _eq("EQ3", brand="Fujitsu", serial=None),                  # OCR couldn't read the plate
        _eq("EQ4", brand="Whirlpool", serial="WP-1", customer_name="Santos Home"),  # no portal configured
    ]
    return WarrantyData(as_of=AS_OF, equipment=equipment)


# The full brand set a Vancouver Island heat-pump / HVAC installer actually registers. Every one
# must resolve to a configured portal (test_resolves_every_configured_brand) and every portal's
# required_fields must be fully fillable (test_every_required_field_resolves) — the two typo guards.
CONFIGURED_BRANDS = [
    "Mitsubishi", "Daikin", "Fujitsu", "LG", "Samsung", "Bosch", "Carrier", "Lennox", "Trane",
    "Goodman", "Rheem", "Gree", "Midea", "Panasonic", "Navien", "York", "Tempstar", "Heil",
    "Amana", "Gibson", "Broan",
]


class TestResolvePortal:
    def test_known_vendors(self) -> None:
        assert w.resolve_portal("Fujitsu").portal == "fujitsugeneral.com/warranty"
        assert w.resolve_portal("Mitsubishi").portal.startswith("mylink.mitsubishicomfort.com")
        assert w.resolve_portal("Daikin") is not None

    def test_case_and_suffix_insensitive(self) -> None:
        assert w.resolve_portal("FUJITSU General") is w.resolve_portal("fujitsu")

    def test_unknown_vendor(self) -> None:
        # An unknown brand has no portal -> routes to needs_human downstream (see TestAnalyze).
        assert w.resolve_portal("Whirlpool") is None
        assert w.resolve_portal("") is None

    @pytest.mark.parametrize("brand", CONFIGURED_BRANDS)
    def test_resolves_every_configured_brand(self, brand: str) -> None:
        portal = w.resolve_portal(brand)
        assert portal is not None, f"{brand} should resolve to a configured warranty portal"
        # The registry key must equal the first lowercased word of the brand (the _normalize_vendor
        # contract) — and a multi-word brand name must still resolve to the same portal.
        assert w.resolve_portal(f"{brand} ductless mini-split") is portal

    def test_registry_keys_match_normalize_vendor(self) -> None:
        # Every dict key IS what _normalize_vendor produces for that key (no stray casing/spaces).
        for key in w.VENDOR_PORTALS:
            assert w._normalize_vendor(key) == key

    def test_brand_coverage_includes_the_required_set(self) -> None:
        required = {b.lower() for b in CONFIGURED_BRANDS}
        assert required.issubset(set(w.VENDOR_PORTALS)), "missing brands from the registry"
        assert len(w.VENDOR_PORTALS) >= 21


class TestEveryPortalFieldResolves:
    """Typo guard: no required field of any portal may map to '' for a fully-populated record."""

    def test_every_required_field_resolves(self) -> None:
        eq = _eq("EQ-FULL", serial="SER-123")  # a fully-populated equipment record
        for brand, portal in w.VENDOR_PORTALS.items():
            fields = w.build_fields(eq, portal)
            assert set(fields) == set(portal.required_fields)
            blanks = [f for f, v in fields.items() if v == ""]
            assert not blanks, f"{brand} portal left these fields blank-by-typo: {blanks}"

    def test_required_fields_are_canonical_names(self) -> None:
        # Defends against adding a field name build_fields can't resolve (it would blank silently).
        from app.agents.documents.warranty_vendors import CANONICAL_FIELDS

        for brand, portal in w.VENDOR_PORTALS.items():
            unknown = set(portal.required_fields) - CANONICAL_FIELDS
            assert not unknown, f"{brand} uses non-canonical field names: {unknown}"


class TestBuildFields:
    def test_fujitsu_fields_filled_from_equipment(self) -> None:
        portal = w.resolve_portal("Fujitsu")
        fields = w.build_fields(_eq("EQ1", serial="FJ-9"), portal)
        assert set(fields) == set(portal.required_fields)
        assert fields["serial_number"] == "FJ-9"
        assert fields["model_number"] == "AOU24RLXFZH"
        assert fields["install_date"] == INSTALL.isoformat()
        assert fields["customer_name"] == "Peter Powell"

    def test_mitsubishi_uses_its_own_field_names(self) -> None:
        portal = w.resolve_portal("Mitsubishi")
        fields = w.build_fields(_eq("EQ2", brand="Mitsubishi", serial="M-1", customer_name="Mercer Building"), portal)
        assert fields["installation_date"] == INSTALL.isoformat()
        assert fields["owner_name"] == "Mercer Building"
        assert "dealer_id" in fields


class TestAnalyze:
    def test_totals(self) -> None:
        t = w.analyze(_scenario()).totals
        assert (t.equipment_processed, t.packets_ready, t.needs_human) == (4, 2, 2)

    def test_packets_are_the_known_vendors_with_serials(self) -> None:
        packets = {p.equipment_id: p for p in w.analyze(_scenario()).packets}
        assert set(packets) == {"EQ1", "EQ2"}
        assert packets["EQ1"].portal == "fujitsugeneral.com/warranty"
        assert packets["EQ1"].serial == "FJ-2026-0001"
        assert packets["EQ1"].fields["serial_number"] == "FJ-2026-0001"

    def test_needs_human_reasons(self) -> None:
        nh = {x.equipment_id: x.reason.lower() for x in w.analyze(_scenario()).needs_human}
        assert "serial" in nh["EQ3"]          # unreadable serial
        assert "portal" in nh["EQ4"]          # unknown vendor

    def test_inputs_hash_stable_and_hex(self) -> None:
        h1, h2 = w.analyze(_scenario()).inputs_hash, w.analyze(_scenario()).inputs_hash
        assert h1 == h2 and len(h1) == 64 and all(c in "0123456789abcdef" for c in h1)

    @given(st.lists(st.sampled_from(["Fujitsu", "Mitsubishi", "Daikin", "Goodman", "Unknown"]), max_size=8))
    def test_every_piece_lands_in_one_bucket(self, brands: list[str]) -> None:
        equip = [_eq(f"E{i}", brand=b, serial=f"S{i}") for i, b in enumerate(brands)]
        res = w.analyze(WarrantyData(as_of=AS_OF, equipment=equip))
        assert res.totals.packets_ready + res.totals.needs_human == len(equip)


class TestNeverSignInRule:
    """The hard safety rule (Alex): the agent NEVER logs into a vendor site itself."""

    @pytest.mark.asyncio
    async def test_register_warranty_refuses_without_human_session(self) -> None:
        from app.actions.executors import ActionError, _register_warranty
        from app.config import Settings

        params = {"equipment_id": "EQ1", "portal": "fujitsugeneral.com/warranty",
                  "fields": {"serial_number": "FJ-1"}}  # NO human_login_token
        with pytest.raises(ActionError) as exc:
            await _register_warranty(params, Settings())
        assert "human" in str(exc.value).lower() and "sign" in str(exc.value).lower()

    @pytest.mark.asyncio
    async def test_register_warranty_proceeds_with_human_session(self) -> None:
        from app.actions.executors import _register_warranty
        from app.config import Settings

        params = {"equipment_id": "EQ1", "job_ref": "JOB-9001",
                  "portal": "fujitsugeneral.com/warranty", "fields": {"serial_number": "FJ-1"},
                  "human_login_token": "hhuman-session-abc"}
        out = await _register_warranty(params, Settings())  # fixture mode by default
        assert out["status"] == "registered"
        assert out["equipment_id"] == "EQ1"

    @pytest.mark.asyncio
    async def test_executor_carries_no_credentials(self) -> None:
        """A human session handle is accepted; raw credentials must never be a parameter."""
        from app.actions.executors import ActionError, _register_warranty
        from app.config import Settings

        params = {"equipment_id": "EQ1", "portal": "x", "fields": {},
                  "username": "sam", "password": "secret"}  # creds but no human session
        with pytest.raises(ActionError):
            await _register_warranty(params, Settings())
