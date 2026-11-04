"""Outbound outreach: the deliverability + compliance brain for emailing CRM contacts.

Pure, deterministic, tested (`app/outreach/compliance.py`). The actual SEND is a write that flows
through the action gate (ADR 0007) via the `send_outreach_email` executor + the Resend transport
(`app/integrations/email_send/`). Nothing here makes a network call.
"""
