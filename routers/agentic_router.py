"""
routers/agentic_router.py
Admin-only agentic automation flows.
Currently implemented: Email automation, Google Calendar events.
Future: WhatsApp broadcasts, CRM sync, order workflows.

All routes require role="admin" and permission "agent:email" / "agent:calendar".
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
import smtplib, os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

from auth.models import APIKey
from auth.dependencies import require_role

router = APIRouter(prefix="/admin/agent", tags=["Admin — Agentic Flows"])

_ADMIN = Depends(require_role("admin"))


# ════════════════════════════════════════════════════════════════
# EMAIL AUTOMATION
# ════════════════════════════════════════════════════════════════

class EmailRequest(BaseModel):
    to:       list[str]        = Field(..., description="Recipient email addresses")
    subject:  str
    body:     str              = Field(..., description="Plain text or HTML body")
    is_html:  bool             = Field(False)
    cc:       Optional[list[str]] = None
    reply_to: Optional[str]   = None


class EmailResponse(BaseModel):
    status:     str
    recipients: int
    message:    str


@router.post("/email/send", response_model=EmailResponse)
async def send_email(
    req:    EmailRequest,
    caller: APIKey = _ADMIN,
):
    """
    Send an email via SMTP.
    Configure SMTP credentials in .env:
      SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
    """
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)

    if not smtp_user or not smtp_pass:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "SMTP credentials not configured. Set SMTP_USER and SMTP_PASSWORD in .env"
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = req.subject
    msg["From"]    = smtp_from
    msg["To"]      = ", ".join(req.to)
    if req.cc:
        msg["Cc"] = ", ".join(req.cc)
    if req.reply_to:
        msg["Reply-To"] = req.reply_to

    mime_type = "html" if req.is_html else "plain"
    msg.attach(MIMEText(req.body, mime_type))

    all_recipients = req.to + (req.cc or [])

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_from, all_recipients, msg.as_string())
    except Exception as e:
        raise HTTPException(500, f"Email send failed: {e}")

    return EmailResponse(
        status     = "sent",
        recipients = len(all_recipients),
        message    = f"Email sent to {len(all_recipients)} recipient(s)",
    )


# ── Email Template endpoint ───────────────────────────────────────

class TemplatedEmailRequest(BaseModel):
    template:    str            = Field(..., description="order_confirm | welcome | promotional")
    to:          list[str]
    variables:   dict           = Field(default_factory=dict)


TEMPLATES = {
    "welcome": {
        "subject": "Welcome to VaseegrahVeda! 🌿",
        "body": (
            "<h2>Welcome to VaseegrahVeda!</h2>"
            "<p>Dear {name},</p>"
            "<p>Thank you for joining our herbal wellness community. "
            "Explore our products at <a href='https://www.vaseegrahveda.com'>www.vaseegrahveda.com</a></p>"
            "<p>– Team VaseegrahVeda</p>"
        ),
    },
    "order_confirm": {
        "subject": "Your VaseegrahVeda Order #{order_id} is Confirmed! 🌿",
        "body": (
            "<h2>Order Confirmed!</h2>"
            "<p>Dear {name},</p>"
            "<p>Your order <strong>#{order_id}</strong> for <strong>{product}</strong> "
            "has been confirmed. We will dispatch within 24 hours.</p>"
            "<p>Track your order at www.vaseegrahveda.com</p>"
        ),
    },
    "promotional": {
        "subject": "{subject}",
        "body": "{body}",
    },
}


@router.post("/email/templated")
async def send_templated_email(
    req:    TemplatedEmailRequest,
    caller: APIKey = _ADMIN,
):
    tmpl = TEMPLATES.get(req.template)
    if not tmpl:
        raise HTTPException(400, f"Unknown template '{req.template}'. Available: {list(TEMPLATES)}")

    subject = tmpl["subject"].format(**req.variables)
    body    = tmpl["body"].format(**req.variables)

    email_req = EmailRequest(
        to=req.to, subject=subject, body=body, is_html=True
    )
    return await send_email(email_req, caller)


# ════════════════════════════════════════════════════════════════
# GOOGLE CALENDAR AUTOMATION
# ════════════════════════════════════════════════════════════════

class CalendarEventRequest(BaseModel):
    title:        str
    description:  Optional[str]  = None
    start:        datetime        = Field(..., description="ISO datetime  e.g. 2025-06-01T10:00:00")
    end:          datetime        = Field(..., description="ISO datetime")
    attendees:    Optional[list[str]] = Field(None, description="Email addresses of attendees")
    location:     Optional[str]   = None
    timezone:     str             = Field("Asia/Kolkata")


class CalendarEventResponse(BaseModel):
    status:    str
    event_id:  Optional[str]
    event_link: Optional[str]
    message:   str


@router.post("/calendar/create", response_model=CalendarEventResponse)
async def create_calendar_event(
    req:    CalendarEventRequest,
    caller: APIKey = _ADMIN,
):
    """
    Create a Google Calendar event.
    Requires Google OAuth2 credentials in .env:
      GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN, GOOGLE_CALENDAR_ID
    """
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        raise HTTPException(
            503,
            "Google API libraries not installed. "
            "Run: pip install google-api-python-client google-auth"
        )

    client_id     = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
    calendar_id   = os.getenv("GOOGLE_CALENDAR_ID", "primary")

    if not all([client_id, client_secret, refresh_token]):
        raise HTTPException(
            503,
            "Google Calendar credentials not configured. "
            "Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN in .env"
        )

    creds = Credentials(
        token         = None,
        refresh_token = refresh_token,
        client_id     = client_id,
        client_secret = client_secret,
        token_uri     = "https://oauth2.googleapis.com/token",
    )

    try:
        service = build("calendar", "v3", credentials=creds)

        event_body: dict = {
            "summary":     req.title,
            "description": req.description or "",
            "location":    req.location or "",
            "start": {
                "dateTime": req.start.isoformat(),
                "timeZone": req.timezone,
            },
            "end": {
                "dateTime": req.end.isoformat(),
                "timeZone": req.timezone,
            },
        }

        if req.attendees:
            event_body["attendees"] = [{"email": e} for e in req.attendees]

        created = (
            service.events()
            .insert(calendarId=calendar_id, body=event_body, sendUpdates="all")
            .execute()
        )

        return CalendarEventResponse(
            status     = "created",
            event_id   = created.get("id"),
            event_link = created.get("htmlLink"),
            message    = f"Event '{req.title}' created successfully",
        )

    except Exception as e:
        raise HTTPException(500, f"Google Calendar error: {e}")


@router.patch("/calendar/{event_id}")
async def update_calendar_event(
    event_id: str,
    req:      CalendarEventRequest,
    caller:   APIKey = _ADMIN,
):
    """Update an existing Google Calendar event."""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        raise HTTPException(503, "Google API libraries not installed")

    client_id     = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
    calendar_id   = os.getenv("GOOGLE_CALENDAR_ID", "primary")

    creds   = Credentials(None, refresh_token=refresh_token,
                          client_id=client_id, client_secret=client_secret,
                          token_uri="https://oauth2.googleapis.com/token")
    service = build("calendar", "v3", credentials=creds)

    try:
        updated = service.events().patch(
            calendarId = calendar_id,
            eventId    = event_id,
            body       = {
                "summary":     req.title,
                "description": req.description,
                "start": {"dateTime": req.start.isoformat(), "timeZone": req.timezone},
                "end":   {"dateTime": req.end.isoformat(),   "timeZone": req.timezone},
            },
        ).execute()

        return {
            "status":     "updated",
            "event_id":   updated.get("id"),
            "event_link": updated.get("htmlLink"),
        }
    except Exception as e:
        raise HTTPException(500, f"Calendar update failed: {e}")