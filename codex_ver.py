"""Daily QQ-mail briefing for GitHub Actions.

This version always sends a report, including when there are no unread emails.
Any failed connection, LLM call, or send raises an exception so the Actions run
is marked failed instead of silently showing a green check.
"""

import os
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText

from imbox import Imbox
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI


def required_env(name: str) -> str:
    """Return a required environment variable or fail with a clear message."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required GitHub Actions secret: {name}")
    return value


EMAIL_ACCOUNT = required_env("QQ_EMAIL_ACCOUNT")
RECEIVER_EMAIL = required_env("REPORT_RECEIVER_EMAIL")
EMAIL_PASSWORD = required_env("QQ_EMAIL_PASSWORD")
DEEPSEEK_API_KEY = required_env("DEEPSEEK_API_KEY")


def fetch_recent_unread_emails(days: int = 1) -> list[dict[str, str]]:
    """Fetch unread QQ Mail received in the preceding number of days."""
    start_date = datetime.now() - timedelta(days=days)
    print(f"Fetching unread mail received after {start_date:%Y-%m-%d %H:%M:%S} ...")
    emails: list[dict[str, str]] = []

    # Do not catch exceptions here: an IMAP issue must fail the workflow.
    with Imbox("imap.qq.com", username=EMAIL_ACCOUNT, password=EMAIL_PASSWORD, ssl=True) as imbox:
        for uid, message in imbox.messages(unread=True, date__gt=start_date):
            plain_body = message.body.get("plain", [""])[0]
            html_body = message.body.get("html", [""])[0]
            body = plain_body or html_body
            sender = message.sent_from[0]["email"] if message.sent_from else "Unknown sender"
            emails.append(
                {
                    "sender": sender,
                    "subject": message.subject or "(No subject)",
                    "body": body.strip()[:500],
                }
            )
            # Enable this only after you are happy with the summaries:
            # imbox.mark_seen(uid)

    print(f"Fetched {len(emails)} unread email(s).")
    return emails


def make_summary(emails: list[dict[str, str]]) -> str:
    """Produce a daily briefing; even an empty inbox gets a report."""
    if not emails:
        return "🧸 All clear today! 过去 24 小时没有新的未读邮件。"

    formatted = "\n".join(
        f"[Email {index}]\nFrom: {mail['sender']}\nSubject: {mail['subject']}\n"
        f"Content: {mail['body']}"
        for index, mail in enumerate(emails, start=1)
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a concise personal email assistant. Keep only important "
                "HKUST, coursework, exams, iPlan, and academic updates. Write in "
                "Simplified Chinese; preserve important dates, times, links, and actions.",
            ),
            (
                "user",
                "Summarize these unread emails. Use headings '🎀 Action Required' "
                "and '🫐 Key Updates'. State briefly what was filtered out.\n\n{emails}",
            ),
        ]
    )
    llm = ChatOpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        temperature=0.3,
    )
    print("Generating summary with DeepSeek ...")
    return (prompt | llm | StrOutputParser()).invoke({"emails": formatted})


def send_email(summary: str) -> None:
    """Send the report through QQ SMTP; errors deliberately propagate."""
    message = MIMEText(summary, "plain", "utf-8")
    message["Subject"] = f"🦞 Lobster Daily Briefing — {datetime.now():%Y-%m-%d}"
    message["From"] = EMAIL_ACCOUNT
    message["To"] = RECEIVER_EMAIL

    print(f"Sending report to {RECEIVER_EMAIL} ...")
    with smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=30) as server:
        server.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ACCOUNT, [RECEIVER_EMAIL], message.as_string())
    print("Report sent successfully.")


def main() -> None:
    emails = fetch_recent_unread_emails()
    send_email(make_summary(emails))


if __name__ == "__main__":
    main()
