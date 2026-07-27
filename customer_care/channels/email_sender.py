"""
Email Sender for Customer Care
===============================
Handles sending actual emails to customers.
Supports booking confirmations, support responses, and promotional emails.
"""

import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class EmailSender:
    """Sends emails to customers."""

    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_email = os.getenv("EMAIL_FROM", "your-email@example.com")
        self.from_name = "Pointours - Rome Tours"

    def _send_email(self, to_email: str, subject: str, html_body: str,
                    text_body: str = "") -> bool:
        """Send an email."""
        if not self.smtp_user or not self.smtp_password:
            logger.warning("SMTP not configured — email not sent")
            logger.info(f"Would send to {to_email}: {subject}")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = to_email

            if text_body:
                msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, to_email, msg.as_string())

            logger.info(f"Email sent to {to_email}: {subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False

    def send_booking_confirmation(self, to_email: str, customer_name: str,
                                   booking_details: Dict) -> bool:
        """Send booking confirmation email."""
        subject = f"🎫 Booking Confirmation - {booking_details.get('product', 'Your Rome Tour')}"

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #1a5276; color: white; padding: 20px; text-align: center;">
                <h1>🏛️ Pointours</h1>
                <p>Your Rome & Vatican Tour Booking</p>
            </div>
            <div style="padding: 20px;">
                <h2>Hello {customer_name}!</h2>
                <p>Thank you for booking with Pointours. Here are your booking details:</p>

                <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 15px 0;">
                    <h3 style="margin-top: 0;">{booking_details.get('product', 'Tour')}</h3>
                    <p>📅 <strong>Date:</strong> {booking_details.get('date', 'TBD')}</p>
                    <p>⏰ <strong>Time:</strong> {booking_details.get('time', 'TBD')}</p>
                    <p>👥 <strong>Participants:</strong> {booking_details.get('participants', 'TBD')}</p>
                    <p>🎫 <strong>Confirmation:</strong> {booking_details.get('confirmation', 'TBD')}</p>
                    <p>📍 <strong>Meeting Point:</strong> {booking_details.get('meeting_point', 'See booking details')}</p>
                </div>

                <div style="background: #fff3cd; padding: 15px; border-radius: 8px; margin: 15px 0;">
                    <h3>📋 Important Reminders</h3>
                    <ul>
                        <li>Arrive 15 minutes before your tour time</li>
                        <li>Bring a valid ID/passport</li>
                        <li>Vatican dress code: shoulders and knees must be covered</li>
                        <li>Comfortable walking shoes recommended</li>
                    </ul>
                </div>

                <p>Need help? Reply to this email or message us on Telegram: @RomaAssistantBot</p>

                <p>Have a wonderful time in Rome! 🇮🇹</p>
            </div>
            <div style="background: #f8f9fa; padding: 15px; text-align: center; font-size: 12px; color: #666;">
                <p>Pointours | Rome, Italy | your-email@example.com</p>
            </div>
        </body>
        </html>
        """
        return self._send_email(to_email, subject, html)

    def send_support_response(self, to_email: str, customer_name: str,
                               ticket_id: str, response: str) -> bool:
        """Send support ticket response."""
        subject = f"🎫 Support Response - Ticket #{ticket_id}"

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #1a5276; color: white; padding: 20px; text-align: center;">
                <h1>🏛️ Pointours Support</h1>
            </div>
            <div style="padding: 20px;">
                <h2>Hello {customer_name},</h2>
                <p>We've responded to your support request <strong>#{ticket_id}</strong>:</p>

                <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 15px 0;">
                    <p>{response}</p>
                </div>

                <p>If you need further assistance, reply to this email or contact us on Telegram.</p>
            </div>
        </body>
        </html>
        """
        return self._send_email(to_email, subject, html)

    def send_cancellation_confirmation(self, to_email: str, customer_name: str,
                                        booking_details: Dict) -> bool:
        """Send cancellation confirmation."""
        subject = f"❌ Booking Cancelled - {booking_details.get('confirmation', '')}"

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #c0392b; color: white; padding: 20px; text-align: center;">
                <h1>🏛️ Pointours - Booking Cancelled</h1>
            </div>
            <div style="padding: 20px;">
                <h2>Hello {customer_name},</h2>
                <p>Your booking has been cancelled as requested:</p>

                <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 15px 0;">
                    <p>🎫 <strong>Confirmation:</strong> {booking_details.get('confirmation', 'N/A')}</p>
                    <p>📅 <strong>Date:</strong> {booking_details.get('date', 'N/A')}</p>
                    <p>⏰ <strong>Time:</strong> {booking_details.get('time', 'N/A')}</p>
                </div>

                <p>Refund will be processed within 5-10 business days.</p>
                <p>We hope to see you again in Rome! 🇮🇹</p>
            </div>
        </body>
        </html>
        """
        return self._send_email(to_email, subject, html)

    def send_promotional_email(self, to_email: str, customer_name: str,
                                products: List[Dict]) -> bool:
        """Send promotional email with tour recommendations."""
        subject = "🏛️ Special Offers for Your Rome Visit!"

        products_html = ""
        for p in products[:3]:
            products_html += f"""
            <div style="border: 1px solid #ddd; border-radius: 8px; padding: 15px; margin: 10px 0;">
                <h3>{p.get('title', 'Tour')}</h3>
                <p>{p.get('summary', '')[:150]}...</p>
                <p><strong>From €{p.get('price', '0')}</strong></p>
            </div>
            """

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #1a5276; color: white; padding: 20px; text-align: center;">
                <h1>🏛️ Pointours Special Offers</h1>
            </div>
            <div style="padding: 20px;">
                <h2>Ciao {customer_name}!</h2>
                <p>Based on your interests, we thought you might love these experiences:</p>
                {products_html}
                <p>Book now at pointours.com or reply to this email!</p>
            </div>
        </body>
        </html>
        """
        return self._send_email(to_email, subject, html)
