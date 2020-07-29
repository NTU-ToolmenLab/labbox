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
    """ Init the database """
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
    """ Add user using std input """
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
def add_user_batch():
    """ Add user using std input without password """
    from labboxmain.models import add_user_by_email
    users = []
    for user in "linnil1 linnil2".split():
        users.append({'name': user,
                 'email': f"{user}@ntu.edu.tw",
                 'groupid': 1,
                 'quota': 4})
        print(users[-1])

    for user in users:
        add_user_by_email(**user)


@app.cli.command()
@click.option('--server', default='all', help='Server hostname. `--server=all` for all nodes')
def stop(server):
    """ Stop all instances """
    from labboxmain.box import boxesStop
    boxesStop(node=server)


@app.cli.command()
def add_user_by_email():
    """ Add user using std input without password """
    from labboxmain.models import add_user_by_email
    name = input('Username ')
    groupid = int(input('Group: (Interger)'))
    quota = int(input('Quota: '))
    email = input("Email: ")
    return add_user_by_email(name, email, groupid, quota)


@app.cli.command()
@click.option("--name", default=None, help="The target user for nextcloud stroage setting")
def nextcloud_share_storage(name=None):
    """ Create nextcloud share_storage setting """
    from labboxmain.models import User
    import json
    if not name:
        name = input("Enter the username")
    path = "/external_data/"
    names = [name]
    datas = []
    for name in names:
        user = User.query.filter_by(name=name).first()
        if not user:
            print("No such user")
            exit()

        datas.append({
            # "mount_id": 56 + i,
            "mount_point": f"/share_{name}",
            "storage": "\\OC\\Files\\Storage\\Local",
            "configuration": {
                "datadir": f"{path}" + user.getGroupData()['homepath']
            },
            "authentication_type": "null::null",
            "options": {
                "encrypt": True,
                "previews": True,
                "enable_sharing": True,
                "filesystem_check_changes": 1,
                "encoding_compatibility": False,
                "readonly": False,
            },
            "applicable_users": [name],
        })
    json.dump(datas, open("/data/nextcloud_storage_setting.json", "w"))


@app.cli.command()
def run_test():
    from pprint import pprint
    from labboxmain.box import Box
    import time
    for box in Box.query.all():
        print(box.box_name)
