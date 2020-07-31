from flask import Blueprint, abort, render_template
from flask_sqlalchemy import SQLAlchemy
import logging
from requests import post
import datetime
from dateutil.parser import parse as dateParse
import redis


db = SQLAlchemy()
logger = logging.getLogger("labboxmain")
bp = Blueprint(__name__, "box")
method_k8s = ["create", "delete", "search", "search/node", "log"]


@bp.record
def record_params(setup_state):
    """Copy config data to blueprint"""
    config = setup_state.app.config
    # api settings
    if config.get('labboxapi-k8s'):
        bp.apiurl = config.get('labboxapi-k8s')
        bp.usek8s = True
    else:
        bp.apiurl = config.get('labboxapi-docker')
        bp.usek8s = False

    # other component
    bp.vncpw = config.get('vnc_password')
    bp.sshpiper = config.get('sshpiper')

    # registry settings
    url = ""
    if config.get('registry_url'):
        url = config.get('registry_url') + "/"
    bp.repo_url = url
    bp.repo_default = url + config.get('registry_repo_default') + ':'
    bp.repo_backup = url + config.get('registry_repo_backup') + ':'

    if config.get('registry_url'):
        bp.registry = dict(
            username=config.get('registry_user'),
            password=config.get('registry_password'),
            registry=config.get('registry_url'))
    else:
        bp.registry = None

    # queue & gpu setting
    bp.queue_quota = config.get('queue_quota')
    bp.gpu_url = config.get('gpu_monitor_url')
    bp.gpu_query_metrics = config.get('gpu_query_metrics')
    bp.gpu_query_interval = config.get('gpu_query_interval')
    bp.gpu_exe_interval = config.get('gpu_exe_interval')
    bp.gpu_decision_func = config.get('gpu_is_free')

    # setup redis
    redis_url = config.get('celery_broker_url')
    u = redis_url.rfind(':')
    head = redis_url.find("://")
    bp.redis = redis.Redis(host=redis_url[head + 3:u], port=int(redis_url[u + 1:]), db=0)


@bp.errorhandler(400)
def errorCatch(e):
    """Return known error"""
    return render_template("error.html", code=400, text=str(e)), 400


@bp.errorhandler(Exception)
def errorCatchAll(e):
    """Return unknown error"""
    return render_template("error.html", code=500, text=str(e)), 500


def baseAPI(method, node=None, check=True, **kwargs):
    """Called upstream API: labboxapi-k8s or labboxapi-docker"""
    # prepare url
    url = bp.apiurl
    if method not in method_k8s and bp.usek8s:
        url += "/" + node
    url += "/" + method

    # post and check
    kwargs['node'] = node
    rep = post(url, data=kwargs).json()
    if check and rep['status'] != 200:
        logger.warning("[labboxapi] " + node + " : " + str(kwargs) + "->" + str(rep))
        abort(400, rep['message'])
    return rep.get('data')


class Box(db.Model):
    """
    Box: The database stored pods information

    Entries
    ----------
    id:
        ID
    box_name:
        The readable name for the pod.
    status:
        The comment for pod.
    docker_name:
        The name of pod. Use this to search pod in k8s.
    docker_id:
        The id of container. Use this to search container in docker.
    docker_ip:
        The ip of container.
    user:
        Username of the pod.
    node:
        The node where the pod run on.
    image:
        The image to start pods
    image_base:
        The base image that provided by admin
    create_date: date
        The date when the pod created
    commit_date: date
        The latest date when the pod commited.
    parent:
        The image sync from.
    """
    __tablename__ = "box"
    id = db.Column(db.Integer, primary_key=True)
    box_name    = db.Column(db.String(32), nullable=False)
    status      = db.Column(db.String(64), default="")
    docker_name = db.Column(db.String(32), nullable=False)
    docker_id   = db.Column(db.String(64), default="")  # add after creation
    docker_ip   = db.Column(db.String(32), default="")  # add after creation
    user        = db.Column(db.String(32), nullable=False)
    node        = db.Column(db.String(32), nullable=False)
    image       = db.Column(db.String(64), nullable=False)
    image_base  = db.Column(db.String(64), nullable=False)
    create_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    commit_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    parent      = db.Column(db.String(64), default="")
    # relationship is not very helpful to my project
    # user = db.relationship("User")
    # user.name

    def __str__(self):
        return "<Box {}>".format(self.docker_name)

    def getStatus(self):
        """
        Get the status of each pod.

        1. The error status will be put on status and will show first.
        2. Check the ID is consistent to database.
        """
        status = self.status
        if not status:
            rep = self.api("search", check=False)
            if not rep:
                status = "Fail"
            else:
                status = rep['status']
                # TODO: remove this feature
                if status == "Running" and self.docker_id != rep['id']:
                    status = "Not Consist ID"

        return {'name':     self.box_name,
                'realname': self.docker_name,
                'status':   status,
                'image':    self.image.split(':')[-1],
                'node':     self.node,
                'date':     (self.create_date + datetime.timedelta(hours=8)).strftime("%Y/%m/%d %X"),
                'commit':   self.commit_date.strftime("%Y/%m/%d %X") if self.commit_date else None,
                'parent':   self.parent}

    def api(self, method, check=True, **kwargs):
        """
        The simplified api calling method.

        The method will handle: search, search/image,
            restart, delete, passwd, commit, prune
        """
        name = self.docker_name
        node = self.node
        if method not in method_k8s and bp.usek8s:
            name = self.docker_id
        return baseAPI(method, check=check, **{'node': node, 'name': name, **kwargs})

    def getImageName(self):
        """Return the image name"""
        return bp.repo_backup + self.docker_name

    def findImage(self):
        """Return image data"""
        return self.api("search/image", name=self.getImageName(), check=False)

    def commit(self, **kwargs):
        """Commit the pod"""
        self.api("commit", newname=self.getImageName(), **kwargs)
        self.api("prune", check=False)
        img = self.findImage()
        self.commit_date = dateParse(img['date']) if img and img.get('date') else None
        db.session.commit()

    def delete(self):
        """Delete this record in database. Not the pod."""
        db.session.delete(self)
        db.session.commit()

    def changeStatus(self, status):
        self.status = status
        db.session.commit()

    @classmethod
    def create(cls, user, name, realname, node, image, image_base="", pull=True, parent=""):
        """Create the pod"""
        # create param
        now_dict = {
            'name': realname,
            'node': node,
            'image': image,
            'pull': pull,
            'homepath': user.name}
        now_dict.update(user.getGroupData())
        if not bp.repo_url:
            now_dict['pull'] = False

        # async, wait for creation
        box = Box(box_name=name,
                  user=user.name,
                  docker_name=now_dict['name'],
                  image=now_dict['image'],
                  image_base=image_base,
                  parent=parent,
                  node=now_dict['node'],
                  status="Creating")
        db.session.add(box)
        db.session.commit()

        # call api
        rep = baseAPI("create", check=False, **now_dict)
        if rep is None:
            box.changeStatus("Create Error")
            raise abort(400, "Create error")

        return box


class Image(db.Model):
    """
    Image: The database stored available images

    Entries
    ----------
    id:
        ID
    name:
        The full name of image
    user:
        The owner of image.
        When user="*", everyone can access it.
    description:
        The comment of this image.
    """
    __tablename__ = "image"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    user = db.Column(db.String(32), default="*")
    description = db.Column(db.String)

    def __str__(self):
        return "<Image {}>".format(self.name)

    @classmethod
    def create(cls, name, user="*", description=""):
        """Create the image"""
        logger.info("[Database] Add Image: " + user + " -> " + name)
        name = name.strip()
        assert(not name)
        assert(not Image.query.filter_by(name=name,
                                         user=user).first())

        image = Image(name=name, user=user, description=description)
        db.session.add(image)
        db.session.commit()
        return image
