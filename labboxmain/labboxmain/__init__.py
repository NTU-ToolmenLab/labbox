from .app import create_app
from config import config
import logging
import click

app, celery = create_app(config)

# Before create box model, it need to create celery first
from .box_queue import bp as boxbp, db as boxdb
from .adminpage import admin
from .oauth2 import config_oauth
app.register_blueprint(boxbp, url_prefix='/box')
boxdb.init_app(app)
admin.init_app(app)
config_oauth(app, url_prefix="/oauth")

logger = logging.getLogger('labboxmain')
logger.info('[All] Start')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')


@app.cli.command()
def initdb():
    from labboxmain.models import db, add_user
    from labboxmain.box_models import db as boxdb
    logger.warning('[Database] Recreate DataBase')
    # db.drop_all()
    # boxdb.drop_all()
    db.create_all()
    boxdb.create_all()
    db.session.commit()
    boxdb.session.commit()
    # add_user('linnil1', 'test123', groupid=0, quota=2)
    # add_image('*', 'learn3.0', 'cuda9.0 cudnn7 python3')


@app.cli.command()
def std_add_user():
    from labboxmain.models import add_user
    from getpass import getpass
    import time
    name = input('Username ')
    passwd = getpass().strip()
    passwd1 = getpass('Password Again: ').strip()
    assert(passwd == passwd1 and len(passwd) >= 8)
    groupid = int(input('Group: (Interger)'))
    quota = int(input('Quota: '))
    email = input("Email: ")
    return add_user(name, passwd, groupid, quota, email)


@app.cli.command()
def add_user_by_email():
    from labboxmain.models import add_user_by_email
    name = input('Username ')
    groupid = int(input('Group: (Interger)'))
    quota = int(input('Quota: '))
    email = input("Email: ")
    return add_user_by_email(name, email, groupid, quota)


@app.cli.command()
@click.option('--server', default='all', help='Server hostname. `--server=all` for all nodes')
def stop(server):
    from labboxmain.box import boxesStop
    boxesStop(node=server)


@app.cli.command()
def run_test():
    from pprint import pprint
    from labboxmain.box import Box
    import time
    for box in Box.query.all():
        print(box.box_name)
