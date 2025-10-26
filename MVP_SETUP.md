# MVP Setup Guide

## 🎯 Pre-Launch Checklist

### 1. Analytics Security (CRITICAL)
Add to your `.env` file:
```bash
ADMIN_API_KEY=your-random-secure-key-here
```

**Generate a secure key:**
```bash
# On Mac/Linux:
openssl rand -hex 32

# Or use any password generator
```

**Access analytics:**
```bash
curl -H "X-Admin-Key: your-key" http://localhost:8000/api/analytics/stats?days=7
```

---

### 2. Slack Notifications (Optional but Recommended)

**Get Slack Webhook URL:**
1. Go to https://api.slack.com/messaging/webhooks
2. Click "Create your Slack app"
3. Choose "From scratch"
4. Name it "Doc Intelligence Feedback"
5. Choose your workspace
6. Click "Incoming Webhooks" → Activate
7. Click "Add New Webhook to Workspace"
8. Choose a channel (e.g., #feedback)
9. Copy the webhook URL

**Add to `.env`:**
```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

**Test it:**
Upload a doc, submit feedback, check Slack!

---

### 3. Environment Variables Checklist

**Backend `.env` file should have:**
```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Security (MVP)
ADMIN_API_KEY=<generate-random-32-char-string>
CORS_ORIGINS=["http://localhost:5173","https://your-production-domain.com"]

# Notifications (Optional)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# Limits
MAX_PAGES=100
RATE_LIMIT_UPLOADS=10
RATE_LIMIT_WINDOW_HOURS=24

# Timeouts
LLM_TIMEOUT_SECONDS=300
```

**Frontend `.env` file should have:**
```bash
VITE_API_URL=http://localhost:8000
# For production: VITE_API_URL=https://your-backend.com
```

---

## 🚀 What's New (MVP Essentials)

### ✅ Completed:

1. **Analytics Endpoint Protected**
   - `/api/analytics/stats` now requires `X-Admin-Key` header
   - Returns 403 Forbidden without valid key
   - Prevents anyone from seeing your usage stats

2. **Slack Notifications for Feedback**
   - Get instant notification when users submit feedback
   - Shows rating, comment, email, and request ID
   - Silent fail if webhook not configured (won't break app)

3. **Dark Mode for Feedback**
   - FeedbackForm fully supports dark mode
   - FeedbackBanner supports dark mode
   - All inputs, buttons, and text adapt to theme

4. **Fixed Currency/Number Formatting**
   - Negative numbers now show as `-$75.00M` instead of `-$75000000`
   - Currency/Fiscal Year labels work in dark mode

---

## 📊 Monitoring Your MVP

### View Analytics

```bash
# Last 7 days
curl -H "X-Admin-Key: YOUR_KEY" http://localhost:8000/api/analytics/stats

# Last 30 days
curl -H "X-Admin-Key: YOUR_KEY" http://localhost:8000/api/analytics/stats?days=30
```

**Example response:**
```json
{
  "period_days": 7,
  "stats": {
    "total_events": 45,
    "events_by_type": {
      "upload_success": 12,
      "upload_error": 2,
      "cache_hit": 31
    },
    "unique_ips": 5,
    "daily_uploads": {
      "2025-10-24": 3,
      "2025-10-25": 9
    }
  }
}
```

### View Feedback Files

```bash
# List all feedback
ls -lt backend/logs/feedback/

# Read a feedback file
cat backend/logs/feedback/2025-10-25_15-30-12_abc123.json
```

---

## 🎨 What Users See

### Light Mode
- Clean white backgrounds
- Blue accents for CTAs
- Gray text hierarchy

### Dark Mode
- Dark gray backgrounds (#1f2937, #374151)
- Same blue accents (adjusted brightness)
- Light text for readability

---

## 🐛 Testing Before Launch

### Test Analytics Security
```bash
# Should fail (no key)
curl http://localhost:8000/api/analytics/stats
# Response: 403 Forbidden

# Should work
curl -H "X-Admin-Key: YOUR_KEY" http://localhost:8000/api/analytics/stats
# Response: { stats ... }
```

### Test Slack Notifications
1. Upload a test document
2. Submit feedback with 5 stars and a comment
3. Check Slack channel for notification
4. Should show rating, comment, email

### Test Dark Mode
1. Toggle dark mode in app
2. Upload document → View results
3. Click "Share your thoughts" feedback button
4. Check all form elements are visible and styled correctly

---

## 🚨 Common Issues

### "Analytics returns 403"
- Make sure `ADMIN_API_KEY` is set in backend `.env`
- Make sure you're passing `X-Admin-Key` header

### "Not getting Slack notifications"
- Check `SLACK_WEBHOOK_URL` is in backend `.env`
- Test webhook: `curl -X POST -H 'Content-type: application/json' --data '{"text":"Test"}' YOUR_WEBHOOK_URL`
- Check backend logs: `tail -f backend/logs/app.log`

### "Feedback form looks wrong in dark mode"
- Clear browser cache
- Make sure frontend rebuild: `npm run dev` (if dev) or `npm run build` (if production)

---

## 📝 Next Steps After MVP Launch

1. **First 10 Users:**
   - Monitor Slack for feedback
   - Check analytics daily
   - Note common pain points

2. **First 50 Users:**
   - Consider adding database (SQLite)
   - Add simple analytics dashboard (internal page)
   - Track conversion rate (visits → uploads → feedback)

3. **Product-Market Fit Signals:**
   - ✅ Users give 4-5 star ratings
   - ✅ "Would pay" responses are > 50%
   - ✅ Users share specific use cases in comments
   - ✅ Repeat usage (check unique IPs in analytics)

---

## 🔐 Security Reminders

- ✅ Never commit `.env` files to git
- ✅ Use strong `ADMIN_API_KEY` (32+ random characters)
- ✅ Change `ADMIN_API_KEY` before production deploy
- ✅ Keep `SLACK_WEBHOOK_URL` private
- ✅ Don't share analytics endpoint URL publicly

---

## 🎯 Ready to Launch?

**Checklist:**
- [ ] `ADMIN_API_KEY` set and secure
- [ ] `SLACK_WEBHOOK_URL` configured (optional)
- [ ] `CORS_ORIGINS` set to production domain
- [ ] Test analytics endpoint is protected
- [ ] Test feedback submission works
- [ ] Test dark mode on all pages
- [ ] Test negative numbers display correctly
- [ ] Backend running on production server
- [ ] Frontend deployed and accessible

**When ready:**
1. Push code to GitHub
2. Deploy backend (Railway/Render/DigitalOcean)
3. Deploy frontend (Vercel/Netlify)
4. Update `VITE_API_URL` in frontend
5. Update `CORS_ORIGINS` in backend
6. Post on Reddit/LinkedIn for beta users!

Good luck! 🚀
