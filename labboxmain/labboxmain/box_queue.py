from flask import request, abort, render_template, redirect, url_for, jsonify
import flask_login
import logging
import time
import datetime
import requests
from .models import User
from .box_models import db as db, Box, Image, bp, baseAPI
from labboxmain import celery
from .box import getImages, imagePush


logger = logging.getLogger("labboxmain")


class BoxQueue(db.Model):
    """
    BoxQueue is task queue system

    Entries
    ----------
    id:
        ID
    user:
        Who own this task
    command:
        The commnad want to run of this task
    queueing: bool
        Determine the task is waiting(True)
    create_date: date
        The date the task created
    """
    __tablename__ = "boxqueue"
    id          = db.Column(db.Integer, primary_key=True)
    user        = db.Column(db.String(32), nullable=False)
    image       = db.Column(db.String(64), nullable=False)
    command     = db.Column(db.String(128))
    queueing    = db.Column(db.Boolean, default=True)
    create_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def __str__(self):
        return "queue-" + str(self.id)

    def getData(self):
        """Return all information of the task"""
        return {'name':     str(self),
                'user':     self.user,
                'image':    self.image.split(":")[-1],
                'command':  self.command,
                'queueing': self.queueing,
                'date':     self.create_date.strftime("%Y/%m/%d %X")}

    def getLog(self):
        """Get the log of the task even it's still running"""
        if self.queueing:
            abort(400, "Not yet created")
        rep = baseAPI("search", name=str(self), check=False)
        log = baseAPI("log",    name=str(self), check=False)
        if log.get('result'):
            log['running_time(s)'] = log['result'][1] - log['result'][0]
            del log['result']
        return {'node': rep['node'],
                'start_time': rep['start'],
                **log}

    def run(self, nodegpu):
        """
        Run the task at specific gpu

        After started, it will mark used in redis.

        Parameters
        ----------
        nodegpu: tuple
            (node, gpu_index)
        """
        if not self.queueing:
            abort(400, "Double creation")
        user = User.query.filter_by(name=self.user).first()
        node, gpu = nodegpu

        now_dict = {
            'name': str(self),
            'node': node,
            'gpu': gpu,
            'image': self.image,
            'command': self.command,
            'pull': True,
            'homepath': user.name}
        now_dict.update(bp.create_rule(user))
        rep = baseAPI("create", **now_dict)

        self.queueing = False
        bp.redis.set(str(nodegpu), time.time())
        db.session.commit()

    def delete(self):
        baseAPI("delete", name=str(self), check=False)
        db.session.delete(self)
        db.session.commit()

    @classmethod
    def create(cls, user, image, command):
        boxqueue = BoxQueue(user=user.name,
                            image=image,
                            command=command)
        db.session.add(boxqueue)
        db.session.commit()
        return boxqueue

    @classmethod
    def find(cls, user, name):
        """
        List all boxqueue object

        Parameters
        ----------
        user: object
            The user.
        name:
            The pod name you want to find.
            Empty will list all available boxqueue.
        """
        # check name
        if not name or name.count('-') != 1:
            abort(400, "Wrong Name")
        try:
            name = int(name.split("-")[1])
        except ValueError:
            abort(400, "Wrong Name")

        # search in database
        if user.groupid == 1:  # admin
            box = BoxQueue.query.filter_by(id=name).first()
        else:
            box = BoxQueue.query.filter_by(id=name,
                                           user=user.name).first()
        if not box:
            abort(400, "Not your command")
        return box


@bp.route("/queue", methods=["GET", "POST"])
@flask_login.login_required
def queue():
    """
    Main function of the queue system

    Methods
    ----------
    GET
        Show all the task.
        Everyone can see all the task, but the detail(
        log, command, delete) will show if "permit" is on.
    POST
        Add more tasks.
        The parameters show below.

    Parameters
    ----------
    command:
        The command want to do.
    image:
        The image where the task run on.
    """
    user = flask_login.current_user
    # list task
    if request.method == "GET":
        queue = []
        for box in BoxQueue.query.all():
            q = box.getData()
            q['permit'] = user.groupid == 1 or box.user == user.name
            queue.append(q)
        return render_template("boxqueue.html",
                               queue=queue,
                               create_images=[i['name'] for i in getImages()])

    # Insert task
    data = request.form
    logger.debug("[Queue] " + user.name + ": " + str(data))

    # validate
    if not data.get('command'):
        abort(400, "What is your command")
    if len(data['command']) >= 128:
        abort(400, "Command Too Long")
    if len(BoxQueue.query.filter_by(user=user.name).all()) > bp.queue_quota:
        abort(400, "You have too mnay in queue")

    # Validate Image
    image = data.get('image')
    parent = None
    if Image.query.filter_by(user="user", name=image).first():
        image = bp.repo_default + data.get('image')
    elif Box.query.filter_by(user=user.name, box_name=image).first():
        # TODO
        abort(400, "No implement yet")
        box = Box.query.filter_by(user=user.name, box_name=image).first()
        image = box.getImageName()
        box.commit(check=False)
        imagePush(parent)
    else:
        abort(400, "No such environment")

    # Add into queue
    BoxQueue.create(user=user, image=image, command=data['command'])
    return redirect(url_for("labboxmain.box_models.queue"))


@bp.route("/log", methods=["POST"])
@flask_login.login_required
def log():
    """
    Query the log of the task

    Parameters
    ----------
    name:
        The task name
    """
    user = flask_login.current_user
    box = BoxQueue.find(user, request.form.get('name'))
    logger.debug("[Queue] log " + str(box))
    return jsonify(box.getLog())


@bp.route("/queueDelete", methods=["POST"])
@flask_login.login_required
def queueDelete():
    """
    Delete the task

    Parameters
    ----------
    name:
        The task name
    """
    user = flask_login.current_user
    box = BoxQueue.find(user, request.form.get('name'))
    logger.debug("[Queue] delete " + str(box))
    box.delete()
    return redirect(url_for("labboxmain.box_models.queue"))


def getGPUStatus():
    """
    This function will query gpu status from prometheus.

    The promethus url is defined in "gpu_url"
    The querying metrics are defined in "gpu_query_metrics".
    The interval between queries is defined in "gpu_query_interval".

    Returns
    ----------
    dict
        key = (server, gpu_index)
        value = A array of time series array of each metrics.
                e.g. [A metrics time series, B metrics time series]
    """
    gpu_st = {}
    for query_metric in bp.gpu_query_metrics:
        params = {
            'query': query_metric,
            'start': str(time.time() - bp.gpu_query_interval),
            'end': str(time.time()),
            'step': 5
        }
        rep = requests.get(bp.gpu_url + "query_range", params=params).json()
        metrics = rep['data']['result']

        for met in metrics:
            id = (met['metric']['node_name'], met['metric']['minor_number'])
            value = [float(i[1]) for i in met['values']]
            gpu_st[id] = gpu_st.get(id, []) + [value]
    return gpu_st


def getAvailableGPUs():
    """
    Find the available gpu by filtering the gpu status with decision function.

    The decision function is define in "gpu_decision_func", also
    it will filter gpus if it's assigned in some specific time interval
    (gpu_exe_interval).

    After started, it will mark used in redis.

    Returns
    ----------
    array
        Array item = (server, gpu_index)
    """
    gpu_st = getGPUStatus()
    avail_gpu = []
    for gpu in gpu_st.items():
        a = bp.redis.get(str(gpu[0]))
        if not a or time.time() - float(a) > bp.gpu_exe_interval \
                and bp.gpu_decision_func(gpu[1]):
            avail_gpu.append(gpu[0])
    return avail_gpu


@celery.task()
def scheduleGPU():
    """Checking task and gpu status"""
    if not BoxQueue.query.filter_by(queueing=True).count():
        return
    avail_gpus = getAvailableGPUs()
    boxqueue = BoxQueue.query.filter_by(queueing=True)\
                             .limit(len(avail_gpus))\
                             .all()
    for i, box in enumerate(boxqueue):
        logger.debug("[Queue] " + str(box) + " use " + str(avail_gpus[i]))
        box.run(avail_gpus[i])
