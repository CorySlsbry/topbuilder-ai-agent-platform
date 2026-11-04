"""Operator reporting: push new signups, chatbot/assistant requests, and user-submitted
bug / feature / question reports to Slack + email.

Everything here is BEST-EFFORT and FAIL-CLOSED: reporting must never break the thing being reported
on, and an unconfigured deployment (no Slack webhook, no operator emails) silently skips (logged).
"""
