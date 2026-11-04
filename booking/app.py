"""Top Builder AI — custom booking service.

A self-hosted booking calendar (no GHL, no Calendly): shows real open slots from cory.salisbury@gmail.com
and writes the booked call straight onto that calendar with a Google Meet link, inviting the prospect and
support@topbuilderai.com. Auth is a service account (booking-bot@...) that the calendar owner has shared
his calendar with ("Make changes to events").
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import logging
import os
import re
from email.mime.text import MIMEText
from email.utils import formataddr
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

log = logging.getLogger("booking")

TZ = ZoneInfo(os.environ.get("BOOKING_TZ", "America/Denver"))
CAL_ID = os.environ.get("CALENDAR_ID", "cory.salisbury@gmail.com")
SUPPORT = os.environ.get("SUPPORT_EMAIL", "support@topbuilderai.com")
SCOPES = ["https://www.googleapis.com/auth/calendar"]
MEETING_LINK = os.environ.get("MEETING_LINK", "").strip()  # permanent Meet/Zoom link (a personal calendar can't auto-create a Meet via a service account)
MEETING_MIN = 30       # the call the prospect books (shown as 30-min slots)
BOOKING_MIN = 60       # but reserve a FULL HOUR on the calendar (call + 30-min buffer between calls)
SLOT_STEP_MIN = 30     # offer a start time every 30 minutes inside each window
# Bookable windows, Mountain time as ((start_h, start_m), (end_h, end_m)); the 30-min call must fit inside.
WINDOWS = [((11, 0), (14, 0)), ((19, 0), (21, 0))]   # 11:00am–2:00pm and 7:00pm–9:00pm
N_DAYS = 8             # show the next 8 business days
LEAD_HOURS = 4         # earliest bookable slot is 4h out (Cory 2026-08-12: no bookings inside 4 hours)
HERE = os.path.dirname(__file__)

# ── Email (brand-aligned transactional): confirmations + owner notice + reminders. Sent from the
# Salisbury Workspace via a Gmail OAuth token (client id/secret/refresh in env). ALL optional and
# FAIL-CLOSED: if the creds are unset, bookings still succeed and email is silently skipped (logged).
GMAIL_CLIENT_ID = os.environ.get("GMAIL_CLIENT_ID", "").strip()
GMAIL_CLIENT_SECRET = os.environ.get("GMAIL_CLIENT_SECRET", "").strip()
GMAIL_REFRESH_TOKEN = os.environ.get("GMAIL_REFRESH_TOKEN", "").strip()
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]
# Alternative transport: Workspace SMTP with an app password (support@salisburybookkeeping.com). Used
# when SMTP_PASSWORD is set; otherwise the Gmail-API path above is used. Either one is fine.
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "support@salisburybookkeeping.com").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").strip()
FROM_EMAIL = os.environ.get("BOOKING_FROM_EMAIL", "support@topbuilderai.com").strip()   # brand send-as alias
FROM_NAME = os.environ.get("BOOKING_FROM_NAME", "Top Builder AI").strip()
OWNER_NOTIFY_EMAIL = os.environ.get("OWNER_NOTIFY_EMAIL", "cory.salisbury@gmail.com").strip()  # Cory gets a heads-up per booking
BRAND = os.environ.get("BOOKING_BRAND", "Top Builder AI").strip()
# Reminder cron: a shared-secret endpoint Cloud Scheduler hits every ~2 min. Thresholds in minutes.
REMINDER_CRON_SECRET = os.environ.get("REMINDER_CRON_SECRET", "").strip()
REMINDER_THRESHOLDS = (1440, 60, 10)   # 24 hours, 1 hour, 10 minutes before the call
CAL_SCOPES_RW = ["https://www.googleapis.com/auth/calendar"]

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _parse_guests(raw: str | None, limit: int = 6) -> list[str]:
    """Booker-supplied extra attendee emails: split on commas/semicolons/whitespace, keep valid + unique."""
    if not raw:
        return []
    out: list[str] = []
    for part in re.split(r"[,;\s]+", raw.strip()):
        e = part.strip().lower()
        if e and _EMAIL_RE.match(e) and e not in out:
            out.append(e)
    return out[:limit]


app = FastAPI(title="Top Builder AI — Booking", docs_url=None, redoc_url=None)


def _service():
    raw = os.environ.get("BOOKING_SA_JSON")
    if not raw:
        return None
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


# ── Email transport (Gmail API, OAuth user creds for the Salisbury Workspace) ───────────────────
def _gmail():
    """Build a Gmail client from the OAuth refresh token, or None if not configured. Never raises."""
    if not (GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET and GMAIL_REFRESH_TOKEN):
        return None
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None, refresh_token=GMAIL_REFRESH_TOKEN,
            client_id=GMAIL_CLIENT_ID, client_secret=GMAIL_CLIENT_SECRET,
            token_uri="https://oauth2.googleapis.com/token", scopes=GMAIL_SCOPES,
        )
        creds.refresh(Request())
        return build("gmail", "v1", credentials=creds, cache_discovery=False)
    except Exception:
        log.exception("gmail: could not build client")
        return None


def _send_email(to: str, subject: str, html: str, text: str) -> bool:
    """Send one transactional email from the brand alias. Best-effort: returns False and logs on any
    failure, NEVER raises (a mail failure must never break a booking)."""
    if not to:
        return False
    from email.mime.multipart import MIMEMultipart
    container = MIMEMultipart("alternative")
    container["To"] = to
    container["From"] = formataddr((FROM_NAME, FROM_EMAIL))
    container["Subject"] = subject
    container.attach(MIMEText(text, "plain", "utf-8"))
    container.attach(MIMEText(html, "html", "utf-8"))
    # Transport 1: Workspace SMTP with an app password.
    if SMTP_PASSWORD:
        try:
            import smtplib
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
                s.starttls()
                s.login(SMTP_USER, SMTP_PASSWORD)
                s.sendmail(FROM_EMAIL, [to], container.as_string())
            return True
        except Exception:
            log.exception("smtp send failed: to=%s subject=%s", to, subject)
            return False
    # Transport 2: Gmail API with an OAuth refresh token.
    gm = _gmail()
    if gm is None:
        log.warning("email skipped (no transport configured): to=%s subject=%s", to, subject)
        return False
    try:
        raw = base64.urlsafe_b64encode(container.as_bytes()).decode()
        gm.users().messages().send(userId="me", body={"raw": raw}).execute()
        return True
    except Exception:
        log.exception("gmail send failed: to=%s subject=%s", to, subject)
        return False


def _human_time(start: dt.datetime) -> str:
    """'Tuesday, August 12 at 11:00 AM MDT' in the booking timezone (platform-independent, no leading zeros)."""
    s = start.astimezone(TZ)
    hour12 = ((s.hour - 1) % 12) + 1
    return f"{s.strftime('%A, %B')} {s.day} at {hour12}:{s.strftime('%M %p %Z')}"


def _cal_link(start: dt.datetime, meet: str | None, guests: list[str] | None = None) -> str:
    import urllib.parse as _u
    def _g(t: dt.datetime) -> str:
        return t.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    params = {
        "action": "TEMPLATE", "text": f"{BRAND} — Fit call",
        "dates": f"{_g(start)}/{_g(start + dt.timedelta(minutes=MEETING_MIN))}",
        "details": ("Your 30-minute fit call." + (f"\nJoin: {meet}" if meet else "") + f"\nQuestions? {SUPPORT}"),
        "location": meet or "",
    }
    if guests:
        params["add"] = ",".join(guests)
    return "https://calendar.google.com/calendar/render?" + _u.urlencode(params)


_WRAP = (
    "<div style=\"font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;"
    "max-width:520px;margin:0 auto;color:#0f172a;line-height:1.55\">{body}"
    "<hr style=\"border:none;border-top:1px solid #e2e8f0;margin:28px 0 14px\">"
    "<p style=\"font-size:12px;color:#64748b;margin:0\">" + BRAND + " · Questions? "
    "<a href=\"mailto:" + SUPPORT + "\" style=\"color:#2563eb\">" + SUPPORT + "</a></p></div>"
)


def _booker_confirmation(b_name: str, start: dt.datetime, meet: str | None, cal_url: str) -> tuple[str, str]:
    when = _human_time(start)
    btn = (f"<a href=\"{meet}\" style=\"display:inline-block;background:#2563eb;color:#fff;"
           f"text-decoration:none;padding:11px 20px;border-radius:8px;font-weight:600\">Join the call</a>"
           if meet else "")
    body = (
        f"<h2 style=\"margin:0 0 6px\">You're booked in.</h2>"
        f"<p style=\"margin:0 0 16px;color:#334155\">Hi {b_name or 'there'}, your {BRAND} fit call is confirmed for:</p>"
        f"<p style=\"font-size:18px;font-weight:700;margin:0 0 4px\">{when}</p>"
        f"<p style=\"margin:0 0 18px;color:#64748b\">30 minutes{' · ' + meet if meet else ''}</p>"
        f"{btn}"
        f"<p style=\"margin:18px 0 0\"><a href=\"{cal_url}\" style=\"color:#2563eb\">Add to your calendar</a></p>"
        f"<p style=\"margin:16px 0 0;color:#334155\">We'll send you reminders 24 hours, 1 hour, and 10 minutes before. "
        f"Need to change it? Just reply to this email.</p>"
    )
    text = (f"You're booked in.\n\nYour {BRAND} fit call is confirmed for:\n{when} (30 minutes)"
            + (f"\nJoin: {meet}" if meet else "")
            + f"\nAdd to calendar: {cal_url}\n\nWe'll remind you 24h, 1h, and 10 min before. "
            f"Reply to this email to reschedule.\n\n{BRAND} · {SUPPORT}")
    return _WRAP.format(body=body), text


def _owner_notice(b: "BookingIn", start: dt.datetime, meet: str | None) -> tuple[str, str]:
    when = _human_time(start)
    body = (
        f"<h2 style=\"margin:0 0 10px\">New fit call booked</h2>"
        f"<p style=\"font-size:18px;font-weight:700;margin:0 0 12px\">{when}</p>"
        f"<table style=\"font-size:14px;color:#334155\">"
        f"<tr><td style=\"padding:2px 12px 2px 0;color:#64748b\">Name</td><td><b>{b.name}</b></td></tr>"
        f"<tr><td style=\"padding:2px 12px 2px 0;color:#64748b\">Email</td><td>{b.email}</td></tr>"
        f"<tr><td style=\"padding:2px 12px 2px 0;color:#64748b\">Company</td><td>{b.company or '—'}</td></tr>"
        f"<tr><td style=\"padding:2px 12px 2px 0;color:#64748b\">Phone</td><td>{b.phone or '—'}</td></tr>"
        f"<tr><td style=\"padding:2px 12px 2px 0;color:#64748b\">Notes</td><td>{b.notes or '—'}</td></tr>"
        f"</table>"
        + (f"<p style=\"margin:14px 0 0\"><a href=\"{meet}\" style=\"color:#2563eb\">{meet}</a></p>" if meet else "")
    )
    text = (f"New fit call booked\n\n{when}\n\nName: {b.name}\nEmail: {b.email}\nCompany: {b.company or '—'}\n"
            f"Phone: {b.phone or '—'}\nNotes: {b.notes or '—'}" + (f"\nJoin: {meet}" if meet else ""))
    return _WRAP.format(body=body), text


def _reminder_email(b_name: str, start: dt.datetime, meet: str | None, minutes: int) -> tuple[str, str]:
    when = _human_time(start)
    lead = "in 24 hours" if minutes >= 1440 else ("in 1 hour" if minutes >= 60 else "in about 10 minutes")
    btn = (f"<a href=\"{meet}\" style=\"display:inline-block;background:#2563eb;color:#fff;"
           f"text-decoration:none;padding:11px 20px;border-radius:8px;font-weight:600\">Join the call</a>"
           if meet else "")
    body = (
        f"<h2 style=\"margin:0 0 6px\">Your {BRAND} call is {lead}.</h2>"
        f"<p style=\"font-size:18px;font-weight:700;margin:0 0 4px\">{when}</p>"
        f"<p style=\"margin:0 0 18px;color:#64748b\">30 minutes</p>{btn}"
        f"<p style=\"margin:18px 0 0;color:#334155\">See you soon. Reply here if anything's changed.</p>"
    )
    text = (f"Your {BRAND} call is {lead}.\n\n{when} (30 minutes)"
            + (f"\nJoin: {meet}" if meet else "") + f"\n\nReply to this email if anything's changed.\n\n{BRAND} · {SUPPORT}")
    return _WRAP.format(body=body), text


def _candidate_slots() -> list[dt.datetime]:
    now = dt.datetime.now(TZ)
    cutoff = now + dt.timedelta(hours=LEAD_HOURS)
    slots: list[dt.datetime] = []
    day = now.date()
    business_days = 0
    probed = 0
    while business_days < N_DAYS and probed < 21:
        probed += 1
        if day.weekday() < 5:  # Mon–Fri
            business_days += 1
            for (sh, sm), (eh, em) in WINDOWS:
                wstart = dt.datetime(day.year, day.month, day.day, sh, sm, tzinfo=TZ)
                wend = dt.datetime(day.year, day.month, day.day, eh, em, tzinfo=TZ)
                s = wstart
                while s + dt.timedelta(minutes=MEETING_MIN) <= wend:  # the 30-min call must fit the window
                    if s > cutoff:
                        slots.append(s)
                    s += dt.timedelta(minutes=SLOT_STEP_MIN)
        day = day + dt.timedelta(days=1)
    return slots


def _busy_starts(svc, slots: list[dt.datetime]) -> set[str]:
    if not svc or not slots:
        return set()
    tmin, tmax = min(slots), max(slots) + dt.timedelta(minutes=BOOKING_MIN)
    fb = svc.freebusy().query(body={
        "timeMin": tmin.isoformat(), "timeMax": tmax.isoformat(), "items": [{"id": CAL_ID}],
    }).execute()
    ranges = [
        (dt.datetime.fromisoformat(b["start"]), dt.datetime.fromisoformat(b["end"]))
        for b in fb["calendars"][CAL_ID]["busy"]
    ]
    taken: set[str] = set()
    for s in slots:
        e = s + dt.timedelta(minutes=BOOKING_MIN)  # the FULL hour we'd hold must be free
        if any(s < be and e > bs for bs, be in ranges):
            taken.add(s.isoformat())
    return taken


@app.get("/api/availability")
def availability() -> dict:
    slots = _candidate_slots()
    svc = _service()
    connected = False
    taken: set[str] = set()
    try:
        if svc is not None:
            taken = _busy_starts(svc, slots)
            connected = True
    except Exception:
        connected = False  # calendar not shared yet → show all candidate slots, still bookable attempt
    days: dict[str, list[str]] = {}
    for s in slots:
        iso = s.isoformat()
        if iso in taken:
            continue
        days.setdefault(s.strftime("%Y-%m-%d"), []).append(iso)  # client formats the time label
    return {
        "timezone": str(TZ), "connected": connected, "support": SUPPORT,
        "days": [{"date": k, "slots": v} for k, v in days.items()],
    }


class BookingIn(BaseModel):
    name: str
    email: str
    company: str | None = None
    phone: str | None = None
    slot: str
    notes: str | None = None
    guests: str | None = None  # booker-supplied extra attendee emails (comma/space separated)


@app.post("/api/book")
def book(b: BookingIn) -> dict:
    svc = _service()
    if svc is None:
        raise HTTPException(503, "Booking is not configured yet.")
    try:
        start = dt.datetime.fromisoformat(b.slot)
    except Exception:
        raise HTTPException(400, "Invalid time slot.")
    # Enforce the rules server-side (never trust the client): the slot must be a real candidate
    # (inside a window, weekday, >= 4h lead) AND still free for the full hour.
    if start.isoformat() not in {s.isoformat() for s in _candidate_slots()}:
        raise HTTPException(409, "That time isn't available — please pick another slot.")
    if start.isoformat() in _busy_starts(svc, [start]):
        raise HTTPException(409, "That time was just taken — please pick another slot.")
    end = start + dt.timedelta(minutes=BOOKING_MIN)
    guest_list = _parse_guests(b.guests)
    title = f"Top Builder AI — Fit call · {b.name}" + (f" ({b.company})" if b.company else "")
    meet = MEETING_LINK or None   # static link if configured; otherwise we try to auto-create a Meet below
    desc = (
        "Fit call (Top Builder AI).\n\n"
        f"Name: {b.name}\nEmail: {b.email}\nCompany: {b.company or '—'}\nPhone: {b.phone or '—'}\n"
        f"Notes: {b.notes or '—'}\n"
        f"Guests (added by the booker): {', '.join(guest_list) if guest_list else '—'}\n"
        + (f"\nJoin: {meet}\n" if meet else "")
        + f"\nQuestions? {SUPPORT}"
    )
    # A service account on a personal (non-Workspace) calendar CANNOT invite attendees (that needs
    # domain-wide delegation), so we do NOT add attendees. The event lands on the owner's calendar with
    # the prospect's details in the description; the prospect gets their Meet link + an add-to-calendar
    # link in the confirmation. (When support@ is on Workspace, switch to real attendee invites.)
    # Thresholds already in the past at booking time are pre-marked so the cron never fires a stale
    # reminder (e.g. a call booked 5h out never gets a "24 hours" reminder). With the 4h lead, the 1h
    # and 10m reminders always apply; the 24h one applies only when booked more than a day out.
    mins_until = (start - dt.datetime.now(TZ)).total_seconds() / 60.0
    pre_sent = ",".join(str(t) for t in REMINDER_THRESHOLDS if t >= mins_until)
    base = {
        "summary": title, "description": desc,
        "start": {"dateTime": start.isoformat(), "timeZone": str(TZ)},
        "end": {"dateTime": end.isoformat(), "timeZone": str(TZ)},
        # Native Google reminders notify the calendar OWNER (Cory) with NO extra credential — this is
        # what fixes "I didn't get notified ahead of time." The booker's reminders are sent separately
        # by /api/cron/reminders (Cory 2026-08-12).
        "reminders": {"useDefault": False, "overrides": [
            {"method": "email", "minutes": 1440},
            {"method": "email", "minutes": 60},
            {"method": "popup", "minutes": 10},
        ]},
        # The cron's state store: which reminders the BOOKER has been sent, plus who/where to send.
        "extendedProperties": {"private": {
            "tba_booking": "1", "booker_email": b.email, "booker_name": b.name,
            "company": b.company or "", "rem_sent": pre_sent, "meet_url": meet or "",
        }},
    }
    if meet:
        base["location"] = meet
    try:
        if meet:
            created = svc.events().insert(calendarId=CAL_ID, body=base, sendUpdates="none").execute()
        else:
            created = svc.events().insert(
                calendarId=CAL_ID,
                body={**base, "conferenceData": {"createRequest": {
                    "requestId": f"tba-{int(start.timestamp())}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"}}}},
                sendUpdates="none", conferenceDataVersion=1,
            ).execute()
            meet = created.get("hangoutLink")
    except Exception:
        try:  # retry without conferencing if it isn't permitted on this calendar
            created = svc.events().insert(calendarId=CAL_ID, body=base, sendUpdates="none").execute()
        except Exception as exc:
            raise HTTPException(502, f"Could not create the calendar event: {exc}")

    # If a Meet was auto-created during insert, persist it so the reminder cron can include the link.
    if meet and (base.get("extendedProperties", {}).get("private", {}).get("meet_url") or "") != meet:
        try:
            svc.events().patch(calendarId=CAL_ID, eventId=created["id"],
                               body={"extendedProperties": {"private": {"meet_url": meet}}},
                               sendUpdates="none").execute()
        except Exception:
            log.exception("could not patch meet_url onto the event")

    add_to_cal = _cal_link(start, meet, guest_list)
    # Confirmation to the booker + a heads-up to Cory. Best-effort: booking already succeeded above,
    # so an email failure only degrades notification, never the booking itself.
    b_html, b_text = _booker_confirmation(b.name, start, meet, add_to_cal)
    _send_email(b.email, f"Confirmed: your {BRAND} fit call", b_html, b_text)
    o_html, o_text = _owner_notice(b, start, meet)
    _send_email(OWNER_NOTIFY_EMAIL, f"New {BRAND} booking — {b.name} · {_human_time(start)}", o_html, o_text)

    return {
        "ok": True, "when": start.isoformat(), "meet": meet, "addToCalendar": add_to_cal,
        "link": created.get("htmlLink"), "support": SUPPORT, "guests": guest_list,
    }


@app.post("/api/cron/reminders")
@app.get("/api/cron/reminders")
def cron_reminders(x_cron_key: str | None = Header(default=None)) -> dict:
    """Cloud Scheduler hits this every ~2 min. For each upcoming booked call it sends the BOOKER the
    24h / 1h / 10m reminder as each threshold is crossed, using the event's extendedProperties as the
    once-only state store (the calendar OWNER's reminders come from native overrides). Shared-secret
    gated: 404 while unconfigured (dark), 403 on a bad key."""
    if not REMINDER_CRON_SECRET:
        raise HTTPException(404, "not found")
    if x_cron_key != REMINDER_CRON_SECRET:
        raise HTTPException(403, "forbidden")
    svc = _service()
    if svc is None:
        raise HTTPException(503, "calendar not configured")
    now = dt.datetime.now(TZ)
    tmax = now + dt.timedelta(minutes=max(REMINDER_THRESHOLDS) + 5)
    try:
        items = svc.events().list(
            calendarId=CAL_ID, timeMin=now.isoformat(), timeMax=tmax.isoformat(),
            singleEvents=True, orderBy="startTime", maxResults=250,
            privateExtendedProperty="tba_booking=1",
        ).execute().get("items", [])
    except Exception as exc:
        log.exception("cron: list failed")
        raise HTTPException(502, f"calendar list failed: {exc}")

    scanned = sent = 0
    for ev in items:
        priv = (ev.get("extendedProperties") or {}).get("private") or {}
        to = priv.get("booker_email")
        start_raw = (ev.get("start") or {}).get("dateTime")
        if not to or not start_raw:
            continue
        scanned += 1
        start = dt.datetime.fromisoformat(start_raw)
        mins_until = (start - now).total_seconds() / 60.0
        already = {t.strip() for t in (priv.get("rem_sent") or "").split(",") if t.strip()}
        newly: list[int] = []
        for T in REMINDER_THRESHOLDS:
            if str(T) not in already and 0 < mins_until <= T:
                html, text = _reminder_email(priv.get("booker_name", ""), start, priv.get("meet_url") or None, T)
                if _send_email(to, f"Reminder: your {BRAND} call {'in 24 hours' if T >= 1440 else ('in 1 hour' if T >= 60 else 'is starting soon')}", html, text):
                    newly.append(T)
        if newly:
            merged = ",".join(sorted(already | {str(t) for t in newly}, key=int))
            try:
                svc.events().patch(calendarId=CAL_ID, eventId=ev["id"],
                                   body={"extendedProperties": {"private": {"rem_sent": merged}}},
                                   sendUpdates="none").execute()
                sent += len(newly)
            except Exception:
                log.exception("cron: could not patch rem_sent for %s", ev.get("id"))
    return {"ok": True, "scanned": scanned, "reminders_sent": sent}


@app.get("/health")
def health() -> dict:
    email_ok = bool(SMTP_PASSWORD) or bool(GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET and GMAIL_REFRESH_TOKEN)
    return {"status": "ok", "calendar": CAL_ID, "support": SUPPORT, "credentials": _service() is not None,
            "email_configured": email_ok, "email_transport": ("smtp" if SMTP_PASSWORD else ("gmail" if email_ok else "none")),
            "from": FROM_EMAIL, "reminder_cron": bool(REMINDER_CRON_SECRET)}


@app.get("/")
def root():
    return FileResponse(os.path.join(HERE, "book.html"))
