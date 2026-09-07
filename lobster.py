import os
import time
import schedule
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from imbox import Imbox
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

import os
from dotenv import load_dotenv

# 自动加载当前目录下的 .env 文件
load_dotenv()

# ==========================================
# 1. 配置区域 (安全读取模式)
# ==========================================
EMAIL_ACCOUNT = "3101228410@qq.com" 
RECEIVER_EMAIL = "zsunbq@connect.ust.hk"

# 通过 os.getenv 安全读取密码，代码里不再出现明文
EMAIL_PASSWORD = os.getenv("QQ_EMAIL_PASSWORD")

# LangChain 的 OpenAI 模块默认会自动从环境变量中读取 OPENAI_API_KEY
# 因此你甚至不需要在代码里写 os.environ["OPENAI_API_KEY"] = ... 这一行

# ==========================================
# 2. 数据抓取模块 (IMAP)
# ==========================================
def fetch_recent_emails(days=1):
    """抓取过去 24 小时的未读邮件"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在拉取邮箱数据...")
    email_data = []
    
    try:
        with Imbox("imap.qq.com", username=EMAIL_ACCOUNT, password=EMAIL_PASSWORD, ssl=True) as imbox:
            start_date = datetime.now() - timedelta(days=days)
            unread_messages = imbox.messages(unread=True, date__gt=start_date)
            
            for uid, message in unread_messages:
                body = message.body.get('plain', [''])[0]
                if not body:
                    body = message.body.get('html', [''])[0][:800] 
                
                email_data.append({
                    "sender": message.sent_from[0]['email'],
                    "subject": message.subject,
                    "body": body.strip()[:500] # 截断防溢出
                })
                # imbox.mark_seen(uid) # 正式运行时取消注释，将邮件标为已读
                
        print(f"成功拉取 {len(email_data)} 封邮件，准备进行 Filter 和 Summary。")
        return email_data
    except Exception as e:
        print(f"抓取失败: {e}")
        return []

# ==========================================
# 3. 核心大脑模块 (LangChain 过滤与提取)
# ==========================================
def filter_and_summarize(email_list):
    """大模型进行垃圾过滤与核心特征提取"""
    if not email_list:
        return "No new emails today. Take a rest!"

    formatted_emails = ""
    for i, email in enumerate(email_list, 1):
        formatted_emails += f"\n[Email {i}]\nSender: {email['sender']}\nSubject: {email['subject']}\nContent: {email['body']}...\n"

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)

    # 精心设计的 Prompt，要求中英夹杂、极简、高亮关键词，并进行重要性过滤
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an elite Executive Assistant. 
        Your task is to filter out junk emails (e.g., food promos, spam, useless ads) and ONLY extract important updates.
        Pay special attention to emails related to Data Science, HKUST university affairs, academic research, or startup projects (like iPlan).
        
        Output Requirements:
        1. Keep it extremely concise (字少).
        2. Use bilingual style (中英夹杂). 
        3. Use English for key business/academic terms (e.g., Deadline, Action Item, Meeting, Update, Pitch).
        4. Format with clean bullet points and emojis. Do NOT include greetings.
        """),
        ("user", """
        Here are today's unread emails:
        {emails}
        
        Please generate the daily briefing in this format:
        
        🔴 **Action Required**
        - [Sender/Topic]: Task description (Deadline: xxx)
        
        🔵 **Key Updates**
        - [Topic]: Core message in one sentence.
        
        (Skip all junk and promotional emails silently. If all emails are junk, just reply "All clear today, no Action Items.")
        """)
    ])

    chain = prompt | llm | StrOutputParser()
    print("正在调用 LLM 处理信息...")
    return chain.invoke({"emails": formatted_emails})

# ==========================================
# 4. 邮件发送模块 (SMTP)
# ==========================================
def send_summary_email(summary_content):
    """将总结好的报告发回给你的邮箱"""
    print("正在生成 Daily Report 并发送邮件...")
    msg = MIMEText(summary_content, 'plain', 'utf-8')
    msg['Subject'] = f"🦞 Lobster Daily Briefing - {datetime.now().strftime('%Y-%m-%d')}"
    msg['From'] = EMAIL_ACCOUNT
    msg['To'] = RECEIVER_EMAIL

    try:
        # QQ 邮箱的 SMTP 服务器端口为 465 (SSL)
        server = smtplib.SMTP_SSL("smtp.qq.com", 465)
        server.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ACCOUNT, [RECEIVER_EMAIL], msg.as_string())
        server.quit()
        print("✅ 总结邮件发送成功！")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

# ==========================================
# 5. 主干任务与调度 (Scheduler)
# ==========================================
def daily_job():
    """每日触发的工作流"""
    emails = fetch_recent_emails(days=1)
    if emails:
        summary = filter_and_summarize(emails)
        send_summary_email(summary)
    else:
        print("今天没有未读邮件，无需发送报告。")

if __name__ == "__main__":
    print("🦞 赛博龙虾定时系统已启动。等待晚上 20:00 投喂...")
    daily_job()