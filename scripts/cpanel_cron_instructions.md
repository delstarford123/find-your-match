# HostPinnacle (cPanel) Complete Cron Jobs Guide
**Domain**: `findyourmatch.co.ke`  
**User**: `farmerma`  
**Virtual Environment**: `/home1/farmerma/virtualenv/findyourmatch.co.ke/mmust-dating-ai/3.13/bin/activate`  
**Project Directory**: `/home1/farmerma/findyourmatch.co.ke/mmust-dating-ai`

---

## Preparation Step
Before setting up cron jobs, ensure the `logs` folder exists in your project directory so logs can be saved without errors:
```bash
mkdir -p /home1/farmerma/findyourmatch.co.ke/mmust-dating-ai/logs
```

---

## 1. Monday Match Emails ("Monday Love Sheet")
- **Frequency**: Every Monday at 08:00 AM EAT (05:00 UTC)
- **Schedule**:
  - Minute: `0`
  - Hour: `5`
  - Day: `*`
  - Month: `*`
  - Weekday: `1`
- **Command**:
  ```bash
  source /home1/farmerma/virtualenv/findyourmatch.co.ke/mmust-dating-ai/3.13/bin/activate && cd /home1/farmerma/findyourmatch.co.ke/mmust-dating-ai && python send_monday_email_job.py >> logs/monday_email.log 2>&1
  ```

---

## 2. Tuesday Match & Blessings ("Blessed Tuesday")
- **Frequency**: Every Tuesday at 09:00 AM EAT (06:00 UTC)
- **Schedule**:
  - Minute: `0`
  - Hour: `6`
  - Day: `*`
  - Month: `*`
  - Weekday: `2`
- **Command**:
  ```bash
  source /home1/farmerma/virtualenv/findyourmatch.co.ke/mmust-dating-ai/3.13/bin/activate && cd /home1/farmerma/findyourmatch.co.ke/mmust-dating-ai && python send_tuesday_email_job.py >> logs/tuesday_email.log 2>&1
  ```

---

## 3. Wednesday Sponsor Match Job
- **Frequency**: Every Wednesday at 10:00 AM EAT (07:00 UTC)
- **Schedule**:
  - Minute: `0`
  - Hour: `7`
  - Day: `*`
  - Month: `*`
  - Weekday: `3`
- **Command**:
  ```bash
  source /home1/farmerma/virtualenv/findyourmatch.co.ke/mmust-dating-ai/3.13/bin/activate && cd /home1/farmerma/findyourmatch.co.ke/mmust-dating-ai && python send_sponsor_match_email_job.py >> logs/sponsor_email.log 2>&1
  ```

---

## 4. Friday Weekend Match Emails ("Friday Perfect Match")
- **Frequency**: Every Friday at 04:00 PM EAT (13:00 UTC)
- **Schedule**:
  - Minute: `0`
  - Hour: `13`
  - Day: `*`
  - Month: `*`
  - Weekday: `5`
- **Command**:
  ```bash
  source /home1/farmerma/virtualenv/findyourmatch.co.ke/mmust-dating-ai/3.13/bin/activate && cd /home1/farmerma/findyourmatch.co.ke/mmust-dating-ai && python send_friday_email_job.py >> logs/friday_email.log 2>&1
  ```

---

## 5. Monthly Campus Managers Report
- **Frequency**: 1st day of every month at midnight (00:00 UTC / 03:00 AM EAT)
- **Schedule**:
  - Minute: `0`
  - Hour: `0`
  - Day: `1`
  - Month: `*`
  - Weekday: `*`
- **Command**:
  ```bash
  source /home1/farmerma/virtualenv/findyourmatch.co.ke/mmust-dating-ai/3.13/bin/activate && cd /home1/farmerma/findyourmatch.co.ke/mmust-dating-ai && python scripts/send_campus_managers_report.py >> logs/campus_report.log 2>&1
  ```

---

## 6. Hourly System Health & Anti-Ghosting Webhook
- **Frequency**: Every hour
- **Schedule**:
  - Minute: `0`
  - Hour: `*`
  - Day: `*`
  - Month: `*`
  - Weekday: `*`
- **Command**:
  ```bash
  curl -s "https://www.findyourmatch.co.ke/api/cron/hourly-check?cron_key=mmust_dating_cron_secret_2026" > /dev/null 2>&1
  ```
