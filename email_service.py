import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SendEmailRequest(BaseModel):
    from_email: str = Field(..., alias="from", min_length=1)
    to: List[str] = Field(..., min_length=1)
    subject: str = Field(..., min_length=1)
    html: str = Field(..., min_length=1)
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None
    reply_to: Optional[str] = None


class ResendEmailService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("RESEND_API_KEY")

    def send_email(self, request: SendEmailRequest) -> Dict[str, Any]:
        if not self.api_key:
            logger.error("RESEND_API_KEY is not configured.")
            raise HTTPException(status_code=500, detail="RESEND_API_KEY is not configured")

        try:
            import resend
        except ImportError as exc:
            logger.error("The resend package is not installed.", exc_info=True)
            raise HTTPException(status_code=500, detail="The resend package is not installed") from exc

        resend.api_key = self.api_key

        params: Dict[str, Any] = {
            "from": request.from_email,
            "to": request.to,
            "subject": request.subject,
            "html": request.html,
        }

        if request.cc:
            params["cc"] = request.cc
        if request.bcc:
            params["bcc"] = request.bcc
        if request.reply_to:
            params["reply_to"] = request.reply_to

        try:
            logger.info("Sending email through Resend; recipients=%s subject=%s", len(request.to), request.subject)
            email = resend.Emails.send(params)
            logger.info("Email sent through Resend successfully.")
            return email
        except Exception as exc:
            logger.error("Failed to send email through Resend: %s", exc, exc_info=True)
            raise HTTPException(status_code=502, detail=f"Failed to send email: {str(exc)}") from exc
