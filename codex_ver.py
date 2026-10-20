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

import imaplib
import re
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime

import imbox.parser


def safe_str_encode(value="", encoding=None, errors="strict"):
    try:
        return str(value, encoding, errors)
    except UnicodeDecodeError:
        charset = (encoding or "").lower().replace("-", "")
        fallback = "gb18030" if charset in {"gb2312", "gbk"} else encoding
        return str(value, fallback, "replace")


imbox.parser.str_encode = safe_str_encode


def secret(name: str) -> str:
    """Read a value injected by GitHub Actions; never store it in this file."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required GitHub Secret is missing: {name}")
    return value


def get_unread_mail(mailbox: str, password: str) -> list[dict[str, str]]:
    hk_tz = ZoneInfo("Asia/Hong_Kong")
    now = datetime.now(hk_tz)

    end = datetime.combine(now.date(), time(20, 0), tzinfo=hk_tz)
    start = end - timedelta(days=1)
    reports = []

    with imaplib.IMAP4_SSL("imap.qq.com", timeout=30) as inbox:
        inbox.login(mailbox, password)
        inbox.select("INBOX", readonly=True)

        # Search broadly: IMAP date searches cannot filter by hour.
        since = (start - timedelta(days=1)).strftime("%d-%b-%Y")
        before = (end + timedelta(days=1)).strftime("%d-%b-%Y")
        status, data = inbox.uid(
            "search", None,
            f'(UNSEEN SINCE "{since}" BEFORE "{before}")',
        )
        if status != "OK":
            raise RuntimeError("Mailbox search failed")

        for uid in data[0].split():
            status, parts = inbox.uid(
                "fetch", uid, "(INTERNALDATE BODY.PEEK[])"
            )
            if status != "OK":
                raise RuntimeError(f"Failed to fetch email {uid!r}")

            for part in parts:
                if not isinstance(part, tuple):
                    continue

                metadata, raw_email = part
                match = re.search(
                    rb'INTERNALDATE "([^"]+)"', metadata
                )
                if not match:
                    raise RuntimeError("Email has no received timestamp")

                received = parsedate_to_datetime(
                    match.group(1).decode("ascii").replace("-", " ")
                )
                if not start <= received.astimezone(hk_tz) < end:
                    continue

                message = BytesParser(policy=policy.default).parsebytes(
                    raw_email
                )
                body_part = message.get_body(
                    preferencelist=("plain", "html")
                )
                body = ""
                if body_part is not None:
                    payload = body_part.get_payload(decode=True) or b""
                    charset = body_part.get_content_charset() or "utf-8"
                    if charset.lower().replace("-", "") in {"gb2312", "gbk"}:
                        charset = "gb18030"
                    try:
                        body = payload.decode(charset, errors="replace")
                    except LookupError:
                        body = payload.decode("utf-8", errors="replace")

                reports.append({
                    "sender": str(message.get("From", "Unknown")),
                    "subject": str(message.get("Subject", "(No subject)")),
                    "body": body.strip()[:500],
                })

    print(f"Found {len(reports)} unread emails in the daily window.")
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
    """你是可爱的个人邮件小助手。以下邮件已经由程序按香港时间筛选，
    范围为昨天晚上八点（含）至今天晚上八点（不含）。
    只总结其中真正重要的邮件，尽量控制陈列的事情越少越好：
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
