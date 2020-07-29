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
    command: str
        The commnad want to run of this task
    status: str
        Determine the task is waiting(True)
    create_date: date
        The date the task created
    """
    __tablename__ = "boxqueue"
    id          = db.Column(db.Integer, primary_key=True)
    user        = db.Column(db.String(32), nullable=False)
    image       = db.Column(db.String(64), nullable=False)
    command     = db.Column(db.String(128))
    status      = db.Column(db.String(32), default="InQueue")
    create_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    # status
    # * InQueue
    # * Running
    # * Done
    # * Error

    def __str__(self):
        return "queue-" + str(self.id)

    def getData(self):
        """Return all information of the task"""
        return {'name':    str(self),
                'user':    self.user,
                'date':    self.create_date.strftime("%Y/%m/%d %X"),
                'image':   self.image.split(":")[-1],
                'status':  self.status,
                'command': self.command}

    def changeStatus(self, st):
        """ Change the status text """
        self.status = st
        logger.debug(f"[Queue] {self} -> {st}")
        db.session.commit()

    def checkStatus(self):
        """ Check and change the status of boxqueue """
        rep = baseAPI("search", name=str(self))
        if self.status == "Running":
            if rep["status"] == "Succeeded":
                self.changeStatus("Complete")
            if rep["status"] == "Failed":
                self.changeStatus("Error")
        return {
            'node': rep['node'],
            'start_time': rep['start']
        }

    def getLog(self):
        """Get the log of the task even it's still running"""
        if self.status == "InQueue":
            abort(400, "Not yet created")
        log = baseAPI("log", name=str(self), check=False)
        if log.get('times'):
            log['running_time(s)'] = log['times'][1] - log['times'][0]
            del log['times']
        return {**self.checkStatus(),
                **log}

    def run(self, node, gpu):
        """
        Run the task at specific gpu on specific node

        After started, it will mark used in redis.

        Parameters
        ----------
        node: str

        gpu_index: str
        """
        if self.status != "InQueue":
            abort(400, "Double creation")
        self.changeStatus("Running")

        user = User.query.filter_by(name=self.user).first()

        # parameters
        now_dict = {
            'name': str(self),
            'node': node,
            'gpu': gpu,
            'image': self.image,
            'command': self.command,
            'pull': True,
            'homepath': user.name}
        now_dict.update(user.getGroupData())
        if not bp.repo_url:
            now_dict['pull'] = False
        logger.debug(f"[Queue] Run {self} {now_dict}")

        # run
        rep = baseAPI("create", check=False, **now_dict)
        if rep is None:
            self.changeStatus("Error")
            return

        # save
        bp.redis.set(str((node, gpu)), time.time())
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
            The pod name you want to find,
            it should be queue-{i}.
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
        if user.groupid == 0:  # admin
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
        return render_template("boxqueue.html",
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
        abort(400, "You have too many tasks in queue")

    # Validate Image
    image = data.get('image')
    parent = None
    if Image.query.filter_by(user="*", name=image).first():
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


@bp.route("/queue/status")
@flask_login.login_required
def queue_status():
    """ An api endpoint for queue status """
    user = flask_login.current_user
    queue = []
    for box in BoxQueue.query.all():
        q = box.getData()
        q['permit'] = user.groupid == 0 or box.user == user.name
        queue.append(q)
    return jsonify({'data': queue})


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
    bq = BoxQueue.find(user, request.form.get('name'))
    logger.debug(f"[Queue] log {bq}")
    return jsonify(bq.getLog())


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
    bq = BoxQueue.find(user, request.form.get('name'))
    logger.debug(f"[Queue] delete {bp}")
    bq.delete()
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
            id = (met['metric']['node_name'], str(met['metric']['minor_number']))
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
def boxRun(bid, node, gpu):
    bq = BoxQueue.query.get(bid)
    logger.debug(f"[Queue] {bq} use {node} {gpu}")
    bq.run(node, gpu)


@celery.task()
def scheduleGPU():
    """Checking task and gpu status"""
    for _ in range(60):
        if bp.gpu_url:
            avail_gpus = getAvailableGPUs()
        else:
            avail_gpus = [('', 0)] * 10

        # Run to Complete
        boxqueue = BoxQueue.query.filter_by(status="Running")\
                                 .all()
        for bq in boxqueue:
            bq.checkStatus()

        # Queue to run
        boxqueue = BoxQueue.query.filter_by(status="InQueue")\
                                 .limit(len(avail_gpus))\
                                 .all()
        for i, bq in enumerate(boxqueue):
            boxRun.delay(bq.id, *avail_gpus[i])

        time.sleep(1)
