"""Notifications: phone push (ntfy.sh), email (Gmail SMTP), GitHub issue.

Every channel is optional and activated by environment variables / repo secrets:
  NTFY_TOPIC                        -> push to the ntfy app (subscribe to the same topic)
  SMTP_USER, SMTP_PASSWORD, ALERT_EMAIL -> email via Gmail (use an App Password)
  GITHUB_TOKEN, GITHUB_REPOSITORY   -> issue in the repo (needs Issues enabled)
"""
import os
import smtplib
from email.mime.text import MIMEText

import requests


def push(title, body, priority="default", tags="chart_with_upwards_trend", click=None):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return False
    try:
        headers = {"Title": title.encode("utf-8"), "Priority": priority, "Tags": tags}
        if click:
            headers["Click"] = click
        requests.post(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"), headers=headers, timeout=15)
        return True
    except Exception as e:
        print(f"push failed: {e}")
        return False


def email(subject, body):
    user, pwd = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD")
    to = os.environ.get("ALERT_EMAIL") or user
    if not (user and pwd and to):
        return False
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"], msg["From"], msg["To"] = subject, user, to
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as s:
            s.login(user, pwd)
            s.sendmail(user, [to], msg.as_string())
        return True
    except Exception as e:
        print(f"email failed: {e}")
        return False


def github_issue(title, body, labels):
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo) or os.environ.get("HABIBI_ISSUES") != "1":
        return False
    try:
        r = requests.post(f"https://api.github.com/repos/{repo}/issues",
                          headers={"Authorization": f"Bearer {token}",
                                   "Accept": "application/vnd.github+json"},
                          json={"title": title, "body": body, "labels": labels}, timeout=15)
        return r.status_code < 300
    except Exception:
        return False


def send_all(title, body, priority="default", tags="chart_with_upwards_trend", click=None, labels=None):
    sent = {"push": push(title, body, priority, tags, click),
            "email": email(title, body + (f"\n\nDashboard: {click}" if click else "")),
            "issue": github_issue(title, body, labels or ["habibi"])}
    print(f"notify '{title}': {sent}")
    return sent
