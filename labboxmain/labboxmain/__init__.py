from .app import create_app
from config import config
import logging
import click

app, celery = create_app(config)

# Before create box model, it need to create celery first
from .box_queue import bp as boxbp, db as boxdb
app.register_blueprint(boxbp, url_prefix='/box/')
boxdb.init_app(app)

logger = logging.getLogger('labboxmain')
logger.info('[All] Start')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')


@app.cli.command()
def initdb():
    from labboxmain.models import db, add_user
    from labboxmain.box_models import db as boxdb, add_image
    logger.warning('[Database] Recreate DataBase')
    # db.drop_all()
    # boxdb.drop_all()
    db.create_all()
    boxdb.create_all()
    db.session.commit()
    boxdb.session.commit()
    # testing
    # add_user('linnil1', 'test123', groupid=1, quota=2)
    # add_image('user', 'learn3.0', 'cuda9.0 cudnn7 python3')
    # add_image('user', 'learn3.1', 'cuda9.0 cudnn7 python3 caffe2')


@app.cli.command()
def std_add_user():
    from labboxmain.models import add_user
    from getpass import getpass
    import time
    name = input('Username ')
    passwd = getpass()
    passwd1 = getpass('Password Again: ')
    groupid = int(input('Group: (Interger)'))
    quota = int(input('Quota: '))
    assert(passwd == passwd1 and len(passwd) >= 8)
    return add_user(name, passwd, time.time(), groupid, quota)


@app.cli.command()
def std_add_image():
    from labboxmain.box_models import Image
    user = input('Username ')
    name = input('Imagename ')
    description = input('description ')
    Image.create(user, name, description)


@app.cli.command()
@click.option('--server', default='all', help='Server hostname. `--server=all` for all nodes')
def stop(server):
    from labboxmain.box import boxesStop 
    boxesStop(node=server)


@app.cli.command()
def run_test():
    from pprint import pprint
    from labboxmain.models import db as user_db, User
    from labboxmain.box import Box, boxCreate, boxDelete, boxRescue, boxStop, boxChangeNode
    import time
    image = "harbor.default.svc.cluster.local/linnil1/serverbox:learn3.6"
    user = User.query.filter_by(name="linnil1").first()
    for box in Box.query.all()[-3:]:
        print(box.getStatus())

    print("RUN")
    boxCreate(user.id, "test", "test123", "lab304-server1", image, pull=True, parent='')

    box = Box.query.filter_by(box_name="test").first()
    print(box.getStatus())

    # boxRescue(box.id)
    # boxChangeNode(box.id, "lab304-server2")
    # boxDelete(box.id)
    # boxStop(box.id)

    box = Box.query.filter_by(box_name="test").first()
    print(box.getStatus())
    """
    from labboxmain.box_queue import BoxQueue
    box = BoxQueue.create(user, image, "echo 123")
    box = BoxQueue.find(user, "queue-1")
    box.run(("lab304-server1", 1))
    print(box.getData())
    print(box.getLog())
    time.sleep(10)
    print(box.getData())
    print(box.getLog())
    box.delete()
    """
