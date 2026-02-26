"""
Downstream email notification service (Step 14).
Sends automated email to downstream teams upon successful classification.
No raw PII is included in the notification.
"""

import logging
from datetime import datetime

from config import settings
from services.graph_client import GraphClient

logger = logging.getLogger(__name__)

NOTIFICATION_EMAIL_TEMPLATE = """
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
  <h2 style="color: #1a365d;">IAT Insurance - New Case Classified</h2>
  <hr style="border-color: #e2e8f0;">

  <table style="width: 100%; border-collapse: collapse;">
    <tr>
      <td style="padding: 8px; font-weight: bold; color: #4a5568; width: 40%;">Case ID</td>
      <td style="padding: 8px;">{case_id}</td>
    </tr>
    <tr style="background: #f7fafc;">
      <td style="padding: 8px; font-weight: bold; color: #4a5568;">Classification</td>
      <td style="padding: 8px;">{category}</td>
    </tr>
    <tr>
      <td style="padding: 8px; font-weight: bold; color: #4a5568;">Confidence Score</td>
      <td style="padding: 8px;">{confidence}%</td>
    </tr>
    <tr style="background: #f7fafc;">
      <td style="padding: 8px; font-weight: bold; color: #4a5568;">Routing</td>
      <td style="padding: 8px;">{routing}</td>
    </tr>
    <tr>
      <td style="padding: 8px; font-weight: bold; color: #4a5568;">Requires Human Review</td>
      <td style="padding: 8px;">{review}</td>
    </tr>
  </table>

  <h3 style="color: #2d3748;">AI Summary</h3>
  <p style="color: #4a5568; background: #f7fafc; padding: 12px; border-radius: 4px;">
    {summary}
  </p>

  <p style="font-size: 12px; color: #718096; margin-top: 24px;">
    This is an automated notification from the IAT Insurance Email Automation Platform.
    No personal information is included in this notification.
    <br>View full case details at: {portal_url}
  </p>
</body>
</html>
"""


class Notifier:
    """Sends downstream email notifications via Microsoft Graph API."""

    def __init__(self, graph: GraphClient):
        self._graph = graph

    async def send_notification(self, case_id: str, classification_result: dict) -> None:
        """
        Send a downstream notification email for a classified case.

        Args:
            case_id: The case identifier.
            classification_result: The classification result dictionary from GPT.
        """
        try:
            category = classification_result.get("classification_category", "Unknown")
            confidence = int(float(classification_result.get("confidence_score", 0)) * 100)
            routing = classification_result.get("routing_recommendation", "")
            summary = classification_result.get("summary", "")
            requires_review = classification_result.get("requires_human_review", False)
            portal_url = f"{settings.webhook_url.rstrip('/webhook/email')}/cases/{case_id}"

            subject = f"[IAT Insurance] New Case Classified: {case_id} — {category}"
            body = NOTIFICATION_EMAIL_TEMPLATE.format(
                case_id=case_id,
                category=category,
                confidence=confidence,
                routing=routing,
                review="Yes — Human review required" if requires_review else "No",
                summary=summary,
                portal_url=portal_url,
            )

            await self._graph.send_email(
                to=settings.downstream_email,
                subject=subject,
                body_html=body,
            )
            logger.info(f"Downstream notification sent for case {case_id} to {settings.downstream_email}")

        except Exception as e:
            logger.error(f"Failed to send downstream notification for case {case_id}: {e}", exc_info=True)
            raise
