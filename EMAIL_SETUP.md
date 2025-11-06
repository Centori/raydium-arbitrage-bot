# Email Notifications Setup

The KOL Copy Trader sends email alerts for important events. Gmail requires an **App Password** for SMTP access.

## ✅ Quick Fix (5 minutes)

### 1. Generate Gmail App Password

Visit: https://myaccount.google.com/apppasswords

1. Sign in to your Google Account (centori1@gmail.com)
2. Click "Create app" 
3. Name it: "KOL Copy Trader"
4. Copy the 16-character password (no spaces)

### 2. Update `.env` File

Replace line 73 in `.env`:

```bash
SMTP_PASSWORD=your_new_app_password_here
```

### 3. Remove Duplicate Lines

Delete lines 79-83 (duplicate email config):

```bash
# Remove these lines:
# Email Notifications
EMAIL_NOTIFICATIONS=true
SMTP_EMAIL=your_email@gmail.com
SMTP_PASSWORD=your_app_password
NOTIFICATION_EMAIL=your_email@gmail.com
```

## 🔒 Security Notes

- App Passwords are specific to your app
- They bypass 2FA for that app only
- You can revoke them anytime
- Never share your app password

## ⚡ Test Email

After updating, restart the bot:

```bash
python3 kol_copy_trader.py
```

You should see:
```
✉️  Email sent: System Started
```

## 🚫 Disable Email (Optional)

If you don't want email alerts, set in `.env`:

```bash
EMAIL_NOTIFICATIONS=false
```

The bot will work fine without email—you'll just see alerts in the console.
