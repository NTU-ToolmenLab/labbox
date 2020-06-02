from config import config
from jinja2 import Template
import logging
import requests

logger = logging.getLogger('labboxmain')
email_sender = config['email_sender']
email_title = config['email_title']


def sendMail(address, template, **kwargs):
    """ Send email """
    # check
    if "//None:" in email_sender:
        return None

    # send it
    text = ""
    try:
        if email_title.get(template):
            template = email_title[template]
            text = Template(open("labboxmain/mail_templates/" + template + ".j2", 'r').read()).render(kwargs)
        resp = requests.post(email_sender, json={
                'title': template,
                'text': text,
                'address': address})
        logger.debug(resp.json())
    except:
        logger.error("[Email] send Error" + str(resp))

    return True
