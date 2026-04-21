"""
SafeSight CCTV - Email Alert Sender
Sends violation alerts via Gmail SMTP with snapshot images attached.
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime

from config import Config


def send_violation_alert(
    camera_name: str,
    detection_type: str,
    confidence: float,
    snapshot_path: str = None,
):
    """Send a violation alert email with optional snapshot attachment."""
    if not Config.SMTP_ENABLED:
        return False

    if not Config.SMTP_EMAIL or not Config.SMTP_PASSWORD:
        print("[Email] SMTP_EMAIL and SMTP_PASSWORD not configured — skipping alert")
        return False

    if not Config.SMTP_TO_LIST:
        print("[Email] SMTP_TO not configured — skipping alert")
        return False

    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conf_pct = f"{confidence * 100:.0f}%"

        msg = MIMEMultipart("related")
        msg["Subject"] = f"[SafeSight Alert] {detection_type} detected on {camera_name}"
        msg["From"] = Config.SMTP_EMAIL
        msg["To"] = ", ".join(Config.SMTP_TO_LIST)

        # HTML body
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

        # If snapshot exists, embed it as inline image
        cid = None
        if snapshot_path and os.path.exists(snapshot_path):
            try:
                with open(snapshot_path, "rb") as img_file:
                    img_data = img_file.read()
                img_mime = MIMEImage(img_data, "jpeg")
                cid = "violationsnapshot"
                img_mime.add_header("Content-ID", f"<{cid}>")
                img_mime.add_header(
                    "Content-Disposition", "inline", filename=os.path.basename(snapshot_path)
                )
                msg.attach(img_mime)

                # Add image to HTML
                img_html = f"""
                <div style="margin-top:16px;text-align:center;">
                    <img src="cid:{cid}" alt="Violation Snapshot" 
                         style="max-width:100%;border-radius:8px;border:1px solid #333;">
                </div>
                """
                html_body = html_body.replace("</div></p>", f"</div>{img_html}</p>")
            except Exception as e:
                print(f"[Email] Failed to attach snapshot: {e}")

        # Attach HTML body
        msg.attach(MIMEText(html_body, "html"))

        # Send via SMTP
        server = smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT)
        server.starttls()
        server.login(Config.SMTP_EMAIL, Config.SMTP_PASSWORD)
        server.sendmail(Config.SMTP_EMAIL, Config.SMTP_TO_LIST, msg.as_string())
        server.quit()

        print(f"[Email] Alert sent to {len(Config.SMTP_TO_LIST)} recipient(s)")
        return True

    except Exception as e:
        print(f"[Email] Failed to send alert: {e}")
        return False