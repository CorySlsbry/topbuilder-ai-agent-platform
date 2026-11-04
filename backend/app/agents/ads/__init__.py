"""Ads agent package — the operator-only ad-platform write executors (ADR 0007 + ADR 0009).

The five ad-platform WRITES (create_campaign / update_budget / activate_campaign / pause_campaign /
sync_conversion) live here as :mod:`app.agents.ads.executors` and are imported + registered into the
shared action gate (``app/actions/executors.py``). Like every other agent-package executor (pricebook,
collections) they are owned + tested in this package; the gate only wires them in.
"""
