import os
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from imbox import Imbox
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

import os

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
    """大模型进行垃圾过滤与核心特征提取（动态Emoji + 极简下划线排版）"""
    if not email_list:
        return "🧸 All clear today! 今天没有未读邮件，好好休息哦~ ✨"

    formatted_emails = ""
    for i, email in enumerate(email_list, 1):
        formatted_emails += f"\n[Email {i}]\nSender: {email['sender']}\nSubject: {email['subject']}\nContent: {email['body']}...\n"

    # 初始化 DeepSeek 模型，温度调到 0.3 让 Emoji 选择更灵活
    llm = ChatOpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"), 
        base_url="https://api.deepseek.com", 
        model="deepseek-chat",               
        temperature=0.3 
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a super cute, highly efficient personal assistant.
        Your task is to filter out junk emails and ONLY extract important updates (pay special attention to HKUST affairs, Data Science, iPlan startup, exams, and academic news).
        
        Strict Output Requirements:
        1. Dynamic Emojis: Select highly relevant emojis based on the specific content of each email (e.g., 💻 for coding/Lab, 📈 for startup/iPlan, 📍 for location, 📅 for meetings). 
        2. Formatting: STRICTLY follow the template. DO NOT use bullet points (no '-' or '*'). Use the HTML <u> tag to underline the English topics. 
        3. Language & Tone: Topics MUST be in English. Content MUST be in lively, cute Simplified Chinese (简体普通话), ending with a tilde '~' or cute particles (e.g., 哦, 呀). NO Traditional Chinese.
        4. Filtered Summary: Briefly mention the categories of junk emails you ignored at the very bottom.
        """),
        ("user", """
        Here are today's unread emails:
        {emails}
        
        Please generate the daily briefing STRICTLY using this format (pay attention to the <u> tags and dynamic emojis):
        
        🎀 **Action Required** 🎀
        [Dynamic Emoji] <u>[English Topic]</u>: [Cute Chinese Content] (Deadline: xxx) [End Emoji]
        
        🫐 **Key Updates** 🫐
        [Dynamic Emoji] <u>[English Topic]</u>: [Cute Chinese Content] [End Emoji]
        
        (Skip a line)
        🗑️ **Filtered out today**: [1-sentence summary of what you skipped, e.g., 已过滤Follett书店promo、Instagram code等junk~]
        
        (If all emails are junk, just reply "🧸 All clear today! 今天没有重要邮件，已被我全部清空啦，早点休息哦~ ✨")
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
    print("🦞 赛博龙虾定时系统已启动。等待晚上 18:00 投喂...")
    daily_job()
