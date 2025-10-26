# Gmail Notification Setup (5 minutes)

## Why Email > Slack for MVP?
- ✅ You already have Gmail
- ✅ Instant push notifications on phone
- ✅ Free forever
- ✅ No extra accounts to manage
- ✅ Searchable history

---

## Step 1: Enable 2-Factor Authentication on Gmail

1. Go to https://myaccount.google.com/security
2. Scroll to "How you sign in to Google"
3. Click "2-Step Verification"
4. Follow setup (use your phone for codes)

**Why?** You need 2FA enabled to create App Passwords.

---

## Step 2: Create Gmail App Password

1. Go to https://myaccount.google.com/apppasswords
   - Or: Google Account → Security → App passwords
2. **App name:** Doc Intelligence Notifications
3. Click "Create"
4. **Copy the 16-character password** (looks like: `abcd efgh ijkl mnop`)
   - ⚠️ You won't see this again!

---

## Step 3: Add to Your `.env` File

Open `backend/.env` and add:

```bash
# Email Notifications (Gmail)
NOTIFICATION_EMAIL=your.email@gmail.com
GMAIL_APP_PASSWORD=abcdefghijklmnop  # The 16-char password from Step 2 (no spaces)
```

**Example:**
```bash
NOTIFICATION_EMAIL=saransh@gmail.com
GMAIL_APP_PASSWORD=xyzw abcd efgh ijkl  # Copy exactly as shown
```

---

## Step 4: Test It!

1. **Restart your backend server:**
   ```bash
   # Stop if running, then:
   uvicorn app.main:app --reload
   ```

2. **Upload a test document**
3. **Submit feedback** with 5 stars and a comment
4. **Check your email inbox!**

You should receive:
- **Subject:** 🎉 New Feedback: ⭐⭐⭐⭐⭐ (5/5)
- **Pretty HTML email** with all feedback details

---

## Troubleshooting

### "Authentication failed" error
- ❌ Did you use your regular Gmail password? (won't work)
- ✅ Must use the 16-character **App Password** from Step 2
- ✅ Remove any spaces from the password in `.env`

### "2-Step Verification required"
- You must enable 2FA on your Google account first (Step 1)

### Email not arriving
- Check spam folder
- Verify `NOTIFICATION_EMAIL` is correct in `.env`
- Check backend logs: `tail -f backend/logs/app.log`

### Still not working?
```bash
# Test SMTP connection:
python3 -c "
import smtplib
email = 'your@gmail.com'
password = 'your-app-password'
with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
    server.login(email, password)
    print('✓ Gmail SMTP connection successful!')
"
```

---

## Security Notes

- ✅ App Passwords are safer than your real password
- ✅ You can revoke them anytime at https://myaccount.google.com/apppasswords
- ✅ Never commit `.env` to git (already in `.gitignore`)
- ✅ Use different App Password for each app/service

---

## What the Email Looks Like

**Subject:** 🎉 New Feedback: ⭐⭐⭐⭐⭐ (5/5)

**Body:**
```
🎉 New Feedback Received!

Overall Rating: ⭐⭐⭐⭐⭐ (5/5)
Accuracy Rating: 5/5
Would Pay: ✅ Yes

Comment:
This tool saved me hours! Love it.

User Email: user@company.com
Request ID: abc123...
Feedback ID: def456...
```

Pretty formatted HTML with colors and styling!

---

## Alternative: Use Your Own Domain Email

If you have a custom domain (e.g., `you@yourdomain.com`), you can use that too!

**Common SMTP providers:**
- **Gmail:** `smtp.gmail.com:465` (SSL)
- **Outlook:** `smtp-mail.outlook.com:587` (TLS)
- **Yahoo:** `smtp.mail.yahoo.com:465` (SSL)
- **Custom domain:** Check your hosting provider docs

Just update the SMTP settings in `notifications.py` if needed.

---

## Done! 🎉

Now every time someone submits feedback, you'll get an instant email notification on your phone!

**Next:** Test it, then move on to deployment.
