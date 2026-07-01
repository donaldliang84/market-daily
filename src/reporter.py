"""Generate HTML email report and send via SMTP."""

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header

logger = logging.getLogger(__name__)

_IMPACT_LABELS = {
    "positive": '<span style="color:#28a745;">📈 积极</span>',
    "negative": '<span style="color:#dc3545;">📉 消极</span>',
    "neutral": '<span style="color:#6c757d;">➡️ 中性</span>',
}

_IMPORTANCE_LABELS = {
    "major": '<span style="background:#dc3545;color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;">重要</span>',
    "normal": '<span style="background:#6c757d;color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;">一般</span>',
}


def generate_html_report(direction_groups, date_str=None, edition_label="午间"):
    """Generate a styled HTML report string."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    sections = []

    for group in direction_groups:
        direction = group["direction"]
        news_list = group.get("news", [])

        if not news_list:
            sections.append(f"""
            <div style="margin-bottom:24px;">
              <h2 style="font-size:18px;color:#333;border-left:4px solid #ddd;padding-left:12px;margin:0 0 12px;">{direction}
                <span style="font-size:12px;color:#999;font-weight:normal;margin-left:6px;">暂无新闻</span>
              </h2>
            </div>""")
            continue

        items = []
        for news in news_list:
            a = news.get("analysis", {})
            items.append(f"""
            <div style="padding:14px 16px;margin-bottom:10px;background:#fafafa;border-radius:8px;border:1px solid #eee;{'' if a.get('importance') != 'major' else 'border-left:3px solid #dc3545;'}">
              <div style="margin-bottom:6px;">
                <a href="{news['url']}" target="_blank" style="font-size:15px;color:#1a73e8;text-decoration:none;font-weight:600;">{news['title']}</a>
                <span style="font-size:12px;color:#999;margin-left:8px;">— {news.get('source', '')}</span>
              </div>
              <div style="margin-bottom:6px;">
                {_IMPORTANCE_LABELS.get(a.get('importance', 'normal'), '')}
                {" " + _IMPACT_LABELS.get(a.get('impact', 'neutral'), '')}
              </div>
              <div style="font-size:14px;color:#444;line-height:1.6;margin-bottom:4px;">{a.get('summary', news.get('snippet', ''))}</div>
              {f'<div style="font-size:13px;color:#666;border-top:1px dashed #eee;padding-top:6px;margin-top:6px;">{a.get("impact_detail", "")}</div>' if a.get('impact_detail') else ''}
            </div>""")

        sections.append(f"""
        <div style="margin-bottom:28px;">
          <h2 style="font-size:18px;color:#333;border-left:4px solid #1a73e8;padding-left:12px;margin:0 0 12px;">
            {direction}
            <span style="font-size:13px;color:#999;font-weight:normal;margin-left:8px;">{len(news_list)}条</span>
          </h2>
          {''.join(items)}
        </div>""")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans SC','Microsoft YaHei',sans-serif;background:#f5f5f5;margin:0;padding:0;color:#333;">
<div style="max-width:680px;margin:0 auto;padding:20px;">
  <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);border-radius:12px;padding:28px 20px;margin-bottom:24px;text-align:center;">
    <h1 style="color:#fff;margin:0;font-size:22px;">📊 每日市场新闻日报</h1>
    <p style="color:rgba(255,255,255,.65);margin:6px 0 0;font-size:13px;">{date_str} · {edition_label}</p>
  </div>
  {''.join(sections)}
  <div style="text-align:center;padding:16px 0;color:#aaa;font-size:12px;border-top:1px solid #eee;margin-top:8px;">
    <p style="margin:2px 0;">本报告仅供参考，不构成投资建议</p>
    <p style="margin:2px 0;">数据来源：公开网络搜索</p>
  </div>
</div>
</body></html>"""


def send_email(smtp_config, html_content, date_str=None, edition="午间"):
    """Send HTML email via SMTP. Returns True on success."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(f"每日市场新闻日报 ({edition}) - {date_str}", "utf-8")
    msg["From"] = smtp_config["user"]
    msg["To"] = smtp_config.get("to_addr", smtp_config["user"])

    msg.attach(MIMEText("请使用支持HTML的邮件客户端查看完整内容。", "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        if smtp_config.get("use_ssl", True):
            server = smtplib.SMTP_SSL(smtp_config["host"], smtp_config["port"])
        else:
            server = smtplib.SMTP(smtp_config["host"], smtp_config["port"])
            server.starttls()

        server.login(smtp_config["user"], smtp_config["password"])
        server.send_message(msg)
        server.quit()
        logger.info("Email sent to %s", smtp_config.get("to_addr", smtp_config["user"]))
        return True
    except Exception as e:
        logger.error("Failed to send email: %s", e)
        return False
