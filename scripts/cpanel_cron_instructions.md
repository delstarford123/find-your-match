# How to Set Up the Campus Manager Email Cron Job in cPanel (HostPinnacle)

This guide explains how to set up the automated monthly email script in your HostPinnacle cPanel.

## Step 1: Configure SMTP Settings

Before the script can send emails, it needs your actual email credentials.
1. Open `scripts/send_campus_managers_report.py` in the cPanel File Manager (or locally before uploading).
2. Look at the top of the file and replace the default credentials with your actual HostPinnacle Webmail credentials.
   ```python
   SMTP_SERVER = 'mail.yourdomain.com'
   SMTP_PORT = 465
   SMTP_USERNAME = 'admin@yourdomain.com'
   SMTP_PASSWORD = 'your_real_email_password'
   ```

## Step 2: Ensure Dependencies are Installed

Since this script uses `firebase_admin`, it must be run using the Python environment where your app dependencies are installed. If you are using cPanel's "Setup Python App", you have a virtual environment.
To find the virtual environment path, it usually looks something like this:
`/home/yourusername/virtualenv/your_app_folder/3.9/bin/python`

## Step 3: Set up the Cron Job

1. Log in to your HostPinnacle cPanel.
2. Scroll down to the **Advanced** section and click on **Cron Jobs**.
3. Under **Add New Cron Job**:
   - **Common Settings**: Select `Once Per Month (0 0 1 * *)`. This runs the script on the 1st of every month at midnight.
   - **Command**: You need to provide the absolute path to your Python executable and the absolute path to the script.
     It should look something like this:
     ```bash
     /home/username/virtualenv/mmust-dating-ai/3.9/bin/python /home/username/mmust-dating-ai/scripts/send_campus_managers_report.py >> /home/username/mmust-dating-ai/logs/cron.log 2>&1
     ```
     *(Make sure to replace `username` with your actual cPanel username, and adjust the paths depending on where you uploaded the files).*
4. Click **Add New Cron Job**.

## Verifying it Works
To test it immediately, you can run the command directly in the cPanel Terminal, or set the cron job to run "Once Per Minute" just to see if the email arrives, and then change it back to "Once Per Month".
