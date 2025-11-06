#!/usr/bin/env python3
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from email_notifier import EmailNotifier

async def main():
    print("Testing email notification system...")
    print(f"From: {os.getenv('SMTP_EMAIL')}")
    print(f"To: {os.getenv('NOTIFICATION_EMAIL')}")
    print(f"Enabled: {os.getenv('EMAIL_NOTIFICATIONS')}")
    
    notifier = EmailNotifier()
    await notifier.send_trade_notification(
        strategy="TEST_TRADE",
        profit_sol=0.05,
        txn_signature="test_signature_123456"
    )
    print("✓ Test email sent! Check your inbox at centori1@gmail.com")

if __name__ == "__main__":
    asyncio.run(main())
