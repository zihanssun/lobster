"""A daily email briefing that obtains all personal settings from GitHub Secrets."""

import os
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText

from imbox import Imbox
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI


def secret(name: str) -> str:
    """Read a value injected by GitHub Actions; never store it in this file."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required GitHub Secret is missing: {name}")
    return value


def get_unread_mail(mailbox: str, password: str) -> list[dict[str, str]]:
    since = datetime.now() - timedelta(days=1)
    reports: list[dict[str, str]] = []

    # Deliberately allow connection errors to fail the Actions run.
    with Imbox("imap.qq.com", username=mailbox, password=password, ssl=True) as inbox:
        for _, message in inbox.messages(unread=True, date__gt=since):
            plain_parts = message.body.get("plain") or []
            html_parts = message.body.get("html") or []

            plain = plain_parts[0] if plain_parts else ""
            html = html_parts[0] if html_parts else ""
            body = (plain or html).strip()
            reports.append(
                {
                    "sender": message.sent_from[0]["email"] if message.sent_from else "Unknown",
                    "subject": message.subject or "(No subject)",
                    "body": (plain or html).strip()[:500],
                }
            )
    print(f"Found {len(reports)} unread email(s).")
    return reports


def summarize(messages: list[dict[str, str]], api_key: str) -> str:
    if not messages:
        return "🧸 All clear today! 过去 24 小时没有新的未读邮件。"

    source = "\n\n".join(
        f"From: {item['sender']}\nSubject: {item['subject']}\nContent: {item['body']}"
        for item in messages
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Summarize important personal, HKUST, coursework, exam, iPlan, and academic "
                "emails in concise Simplified Chinese. Keep deadlines and required actions. "
                "Ignore promotions and say briefly what was ignored.",
            ),
            ("user", "Emails to process:\n{source}"),
        ]
    )
    model = ChatOpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        temperature=0.3,
    )
    return (prompt | model | StrOutputParser()).invoke({"source": source})


def send_report(mailbox: str, password: str, recipient: str, report: str) -> None:
    message = MIMEText(report, "plain", "utf-8")
    message["Subject"] = f"🦞 Lobster Daily Briefing — {datetime.now():%Y-%m-%d}"
    message["From"] = mailbox
    message["To"] = recipient

    with smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=30) as smtp:
        smtp.login(mailbox, password)
        smtp.sendmail(mailbox, [recipient], message.as_string())
    print("Daily report sent.")


def main() -> None:
    # Values are injected at runtime from GitHub Secrets, never hard-coded.
    mailbox = secret("LOBSTER_MAILBOX")
    password = secret("LOBSTER_MAIL_PASSWORD")
    recipient = secret("LOBSTER_REPORT_RECIPIENT")
    api_key = secret("DEEPSEEK_API_KEY")

    messages = get_unread_mail(mailbox, password)
    report = summarize(messages, api_key)
    send_report(mailbox, password, recipient, report)


if __name__ == "__main__":
    main()
