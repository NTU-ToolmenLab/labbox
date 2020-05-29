from config import config
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jinja2 import Template
import logging

logger = logging.getLogger('labboxmain')
email_host = config['email_host']
email_port = config['email_port']
admin_email = config['admin_email']
email_title = config['email_title']
admin_password = config['email_password']


def sendMail(email, template, **kwargs):
    # init
    s = smtplib.SMTP(host=email_host, port=email_port)
    s.starttls()
    s.login(admin_email, admin_password)

    # prepare for mail
    template = email_title[template]
    msg = MIMEMultipart()
    msg['From']    = admin_email
    msg['To']      = email
    msg['Subject'] = template
    text = Template(open("labboxmain/mail_templates/" + template + ".j2", 'r').read()).render(kwargs)
    msg.attach(MIMEText(text))

    # send
    logger.warning("[Email] send " + msg)
    try:
        s.send_message(msg)
    except smtplib.SMTPException as e:
        logger.warning("[Email] send Error" + e)
    return

