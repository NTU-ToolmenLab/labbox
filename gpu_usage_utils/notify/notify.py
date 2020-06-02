import time
import logging
import sqlite3
import os
from datetime import datetime, timedelta
from pprint import pprint
import requests
from jinja2 import Template


# general setting
threshold_time = 3  # 3 days
timezone_offset = 8
db_path = "/data/db.sqlite"
db_query = 'SELECT email FROM user where name = ?'

# email setting
email_url = "http://{}:5870/mail".format(os.environ.get("NAME_EMAIL_SENDER"))
template_name = "GPU usage notified from Toolmen Lab"

# query setting to prometheus
url = "http://{}/api/v1/".format(os.environ.get("NAME_PROMETHEUS"))
query = 'gpuprocesses_memory'
params = {
    'query': query,
    'start': str(time.time() - 60),
    'end': str(time.time()),
    'step': 5
}

# set logger
logger = logging.getLogger("gpu_notify")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)


def gpuQuery():
    """Query to prometheus"""
    rep = requests.get(url + "query_range", params=params).json()
    data = rep['data']['result']
    now = datetime.utcnow()
    consumer = {}
    for d in data:
        created_time = datetime.utcfromtimestamp(float(d['metric']['create_time']))
        interval = now - created_time
        if interval.days >= threshold_time:
            m = d['metric']
            # insert
            if m['user'] == 'None':
                continue
            if not consumer.get(m['user']):
                consumer[m['user']] = []
            consumer[m['user']].append({
                'name': m['user'],
                'cmd': m['cmd'],
                'gpuid': m['gpuid'],
                'box_name': m['id'],
                'node_name': m['node_name'],
                'memory': str(d['values'][0][1]) + "MB",
                'interval': f"{interval.days} days and {interval.seconds / 3600:.0f} hours",
                'created_time': (created_time + timedelta(hours=timezone_offset)).isoformat()
            })
    return consumer


def mailRender(consumer):
    """ Write the mail """
    db = sqlite3.connect(db_path)
    mails = []
    for user, processes in consumer.items():
        logger.debug(f"Notify {user}")
        text = Template(open(template_name + ".j2", 'r').read()).render({
            'name': user,
            'processes': processes
        })
        mails.append({
            # 'name': user,
            'title': template_name,
            'text': text,
            'address': db.execute(db_query, [user]).fetchone()[0]
        })
    return mails


def sendEmail(mails):
    """ send email """
    for mail in mails:
        if not mail['address']:
            continue
        a = requests.post(email_url, json=mail)
        logger.debug(f"Send to {mail['address']} {a}")


if __name__ == "__main__":
    consumer = gpuQuery()
    mails = mailRender(consumer)
    sendEmail(mails)
