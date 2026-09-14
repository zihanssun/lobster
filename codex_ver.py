"""A daily email briefing that obtains all personal settings from GitHub Secrets."""

import os
import smtplib
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
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
    hk_tz = ZoneInfo("Asia/Hong_Kong")
    today = datetime.now(hk_tz).date()
    day_start = datetime.combine(today, time.min)
    next_day_start = day_start + timedelta(days=1)
    reports: list[dict[str, str]] = []

    with Imbox("imap.qq.com", username=mailbox, password=password, ssl=True) as inbox:
        for _, message in inbox.messages(
            unread=True,
            date__gt=day_start,
            date__lt=next_day_start,
        ):
            plain_parts = message.body.get("plain") or []
            html_parts = message.body.get("html") or []
            plain = plain_parts[0] if plain_parts else ""
            html = html_parts[0] if html_parts else ""

            reports.append(
                {
                    "sender": message.sent_from[0]["email"] if message.sent_from else "Unknown",
                    "subject": message.subject or "(No subject)",
                    "body": (plain or html).strip()[:500],
                }
            )

    print(f"Found {len(reports)} unread email(s) received today.")
    return reports


def summarize(messages: list[dict[str, str]], api_key: str) -> str:
    if not messages:
        return "🦞 今日邮件小报\n\n🧸 今天没有需要关注的新邮件，安心休息吧～"

    source = "\n\n".join(
        f"From: {item['sender']}\nSubject: {item['subject']}\nContent: {item['body']}"
        for item in messages
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
    """你是可爱的个人邮件小助手。只总结今天收到的、真正重要的邮件：
    HKUST、课程、作业、考试、项目、iPlan、会议和必须处理的事项。
    
    输出必须是纯文本，绝对不要使用 Markdown。
    禁止出现 **、#、-、*、反引号或 HTML 标签。
    
    严格按以下格式输出：
    
    🦞 今日邮件小报
    
    🚨 要处理
    • 💻 主题：一句话说明要做什么；如有截止时间，写“截止：…”
    • 📅 主题：一句话说明
    
    ✨ 重要更新
    • 📚 主题：一句话摘要
    • 📍 主题：一句话摘要
    
    🗑️ 已忽略
    • 简短列出被忽略的广告、验证码或推广邮件类型
    
    每封重要邮件最多一条，总共最多 6 条；使用简体中文和合适 Emoji。"""
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
