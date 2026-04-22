"""
SafeSight CCTV - Email Alert Service

Sends violation alerts via Gmail SMTP with snapshot images embedded inline.
Supports multiple recipients.

Improvements over original email_sender.py:
  - Class-based (injectable, testable)
  - Config from Settings object
  - Inline image embedding via CID (nicer than attachment)
  - Multiple recipients from comma-separated SMTP_TO
  - Better error handling and logging
"""

import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime
from typing import Optional

from app.config import Settings

logger = logging.getLogger(__name__)


class AlertService:
    """Gmail SMTP alert service with inline image support."""

    def __init__(self, config: Optional[Settings] = None):
        self.config = config or Settings()

    def is_configured(self) -> bool:
        """Check if SMTP credentials are properly configured."""
        return bool(
            self.config.SMTP_ENABLED
            and self.config.SMTP_EMAIL
            and self.config.SMTP_PASSWORD
            and self.config.smtp_to_list
        )

    def send_violation_alert(
        self,
        camera_name: str,
        detection_type: str,
        confidence: float,
        snapshot_path: Optional[str] = None,
    ) -> bool:
        """Send a violation alert email with optional inline snapshot.

        Args:
            camera_name: Name/ID of the camera.
            detection_type: Type of violation (e.g., "no_helmet").
            confidence: Detection confidence score.
            snapshot_path: Optional path to snapshot image to embed.

        Returns:
            True if email was sent successfully.
        """
        if not self.config.SMTP_ENABLED:
            return False

        if not self.is_configured():
            logger.warning(
                "SMTP not fully configured — skipping alert. "
                "Set SMTP_EMAIL, SMTP_PASSWORD, and SMTP_TO in .env"
            )
            return False

        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conf_pct = f"{confidence * 100:.0f}%"

            msg = MIMEMultipart("related")
            msg["Subject"] = (
                f"[SafeSight Alert] {detection_type} detected on {camera_name}"
            )
            msg["From"] = self.config.SMTP_EMAIL
            msg["To"] = ", ".join(self.config.smtp_to_list)

            # HTML body with styled violation card
            html_body = f"""
            <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
                <div style="background:#1a1a2e;border-radius:12px;padding:24px;color:#fff;">
                    <h2 style="margin:0 0 16px 0;color:#ff4444;font-size:20px;">
                        &#9888; Safety Violation Detected
                    </h2>
                    <table style="width:100%;border-collapse:collapse;font-size:14px;">
                        <tr>
                            <td style="padding:8px 0;color:#aaa;">Camera</td>
                            <td style="padding:8px 0;font-weight:600;text-align:right;">{camera_name}</td>
                        </tr>
                        <tr>
                            <td style="padding:8px 0;color:#aaa;">Type</td>
                            <td style="padding:8px 0;font-weight:600;text-align:right;color:#ff4444;">{detection_type}</td>
                        </tr>
                        <tr>
                            <td style="padding:8px 0;color:#aaa;">Confidence</td>
                            <td style="padding:8px 0;font-weight:600;text-align:right;">{conf_pct}</td>
                        </tr>
                        <tr>
                            <td style="padding:8px 0;color:#aaa;">Time</td>
                            <td style="padding:8px 0;font-weight:600;text-align:right;">{now}</td>
                        </tr>
                    </table>
                </div>
                <p style="color:#666;font-size:12px;text-align:center;margin-top:16px;">
                    SafeSight AI — Real-time construction site safety monitoring
                </p>
            </div>
            """

            # Embed snapshot as inline image (if available)
            if snapshot_path and os.path.exists(snapshot_path):
                try:
                    with open(snapshot_path, "rb") as img_file:
                        img_data = img_file.read()
                    img_mime = MIMEImage(img_data, "jpeg")
                    cid = "violationsnapshot"
                    img_mime.add_header("Content-ID", f"<{cid}>")
                    img_mime.add_header(
                        "Content-Disposition",
                        "inline",
                        filename=os.path.basename(snapshot_path),
                    )
                    msg.attach(img_mime)

                    # Add image reference to HTML
                    img_html = f"""
                    <div style="margin-top:16px;text-align:center;">
                        <img src="cid:{cid}" alt="Violation Snapshot"
                             style="max-width:100%;border-radius:8px;border:1px solid #333;">
                    </div>
                    """
                    html_body = html_body.replace("</div></p>", f"</div>{img_html}</p>")
                    logger.debug("Embedded snapshot in email: {}", snapshot_path)
                except Exception as e:
                    logger.error("Failed to embed snapshot: {}", e)

            msg.attach(MIMEText(html_body, "html"))

            # Send via TLS-encrypted SMTP
            server = smtplib.SMTP(self.config.SMTP_SERVER, self.config.SMTP_PORT)
            server.starttls()
            server.login(self.config.SMTP_EMAIL, self.config.SMTP_PASSWORD)
            server.sendmail(
                self.config.SMTP_EMAIL,
                self.config.smtp_to_list,
                msg.as_string(),
            )
            server.quit()

            logger.info(
                "Alert sent to {} recipient(s): {} on {}",
                len(self.config.smtp_to_list),
                detection_type,
                camera_name,
            )
            return True

        except Exception as e:
            logger.error("Failed to send alert: {}", e)
            return False