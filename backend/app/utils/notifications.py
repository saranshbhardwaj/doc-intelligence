# app/utils/notifications.py
import httpx
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import settings
from app.utils.logging import logger


async def send_feedback_notification(feedback_data: dict):
    """
    Send notification when new feedback is received.
    Supports both Email (Gmail) and Slack webhooks.
    """
    # Try email first (preferred for MVP)
    if settings.notification_email and settings.gmail_app_password:
        await _send_email_notification(feedback_data)

    # Also try Slack if configured
    if settings.slack_webhook_url:
        await _send_slack_notification(feedback_data)

    # If nothing configured, just log
    if not settings.notification_email and not settings.slack_webhook_url:
        logger.info("Feedback notification skipped - no notification method configured")
        return


async def _send_email_notification(feedback_data: dict):
    """Send email notification using Gmail SMTP"""
    try:
        rating_stars = "⭐" * feedback_data.get("rating", 0)
        accuracy = feedback_data.get("accuracy_rating")
        would_pay = feedback_data.get("would_pay")
        comment = feedback_data.get("comment", "")
        user_email = feedback_data.get("email", "Not provided")

        # Format values outside f-string to avoid syntax issues
        accuracy_display = f"{accuracy}/5" if accuracy else "Not rated"
        would_pay_display = "✅ Yes" if would_pay else "❌ No" if would_pay is False else "🤷 Not answered"
        would_pay_text = "Yes" if would_pay else "No" if would_pay is False else "Not answered"
        comment_display = comment if comment else "<em>No comment provided</em>"
        comment_text = comment if comment else "No comment provided"

        # Create email
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"🎉 New Feedback: {rating_stars} ({feedback_data.get('rating')}/5)"
        msg['From'] = settings.notification_email
        msg['To'] = settings.notification_email

        # HTML body (prettier)
        html = f"""
        <html>
          <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #2563eb;">🎉 New Feedback Received!</h2>

            <div style="background: #f3f4f6; padding: 15px; border-radius: 8px; margin: 20px 0;">
              <p><strong>Overall Rating:</strong> {rating_stars} ({feedback_data.get('rating')}/5)</p>
              <p><strong>Accuracy Rating:</strong> {accuracy_display}</p>
              <p><strong>Would Pay:</strong> {would_pay_display}</p>
            </div>

            <div style="margin: 20px 0;">
              <p><strong>Comment:</strong></p>
              <p style="background: #fff; padding: 10px; border-left: 3px solid #2563eb;">
                {comment_display}
              </p>
            </div>

            <div style="font-size: 12px; color: #666; margin-top: 20px;">
              <p><strong>User Email:</strong> {user_email}</p>
              <p><strong>Request ID:</strong> <code>{feedback_data.get('request_id', 'N/A')}</code></p>
              <p><strong>Feedback ID:</strong> <code>{feedback_data.get('feedback_id', 'N/A')[:8]}</code></p>
            </div>
          </body>
        </html>
        """

        # Plain text fallback
        text = f"""
New Feedback Received!

Overall Rating: {rating_stars} ({feedback_data.get('rating')}/5)
Accuracy Rating: {accuracy_display}
Would Pay: {would_pay_text}

Comment:
{comment_text}

User Email: {user_email}
Request ID: {feedback_data.get('request_id', 'N/A')}
Feedback ID: {feedback_data.get('feedback_id', 'N/A')[:8]}
"""

        msg.attach(MIMEText(text, 'plain'))
        msg.attach(MIMEText(html, 'html'))

        # Send via Gmail SMTP
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(settings.notification_email, settings.gmail_app_password)
            server.send_message(msg)

        logger.info("Email notification sent successfully")

    except Exception as e:
        logger.warning(f"Failed to send email notification: {e}")


async def _send_slack_notification(feedback_data: dict):
    """Send Slack notification using webhook"""
    try:
        # Format feedback for Slack
        rating_stars = "⭐" * feedback_data.get("rating", 0)
        accuracy = feedback_data.get("accuracy_rating")
        would_pay = feedback_data.get("would_pay")
        comment = feedback_data.get("comment", "")
        user_email = feedback_data.get("email", "Not provided")

        # Format values outside f-string
        accuracy_display = f"{accuracy}/5" if accuracy else "Not rated"
        would_pay_display = "✅ Yes" if would_pay else "❌ No" if would_pay is False else "🤷 Not answered"
        comment_display = comment[:500] if comment else "_No comment provided_"

        # Build message
        message = f"""
🎉 *New Feedback Received!*

*Overall Rating:* {rating_stars} ({feedback_data.get('rating')}/5)
*Accuracy Rating:* {accuracy_display}
*Would Pay:* {would_pay_display}

*Comment:*
{comment_display}

*Email:* {user_email}
*Request ID:* `{feedback_data.get('request_id', 'N/A')}`
*Feedback ID:* `{feedback_data.get('feedback_id', 'N/A')[:8]}`
"""

        # Send to Slack
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                settings.slack_webhook_url,
                json={"text": message}
            )

            if response.status_code == 200:
                logger.info("Slack notification sent successfully")
            else:
                logger.warning(f"Slack notification failed: {response.status_code}")

    except Exception as e:
        # Don't crash the feedback submission if notification fails
        logger.warning(f"Failed to send feedback notification: {e}")
