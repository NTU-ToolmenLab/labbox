from flask import request, abort, render_template, redirect, url_for
import flask_login
import logging
import time
import re
from .models import db as user_db, User
from .box_models import db as db, Box, Image, bp, baseAPI
from labboxmain import celery
import shutil
import os


logger = logging.getLogger("labboxmain")


@bp.route("/")
@flask_login.login_required
def List():
    """Render available pods on UI"""
    return render_template("boxlist.html",
                           container_list=getPods(),
                           create_param=getCreateParams(),
                           image_list=getImages())


# Some function for rendering web
def getPods():
    """Get user's pods"""
    user = flask_login.current_user
    if user.groupid == 1:  # admin
        boxes_ori = Box.query.all()
    else:
        boxes_ori = Box.query.filter_by(user=user.name).all()
    boxes = [box.getStatus() for box in boxes_ori]
    return boxes


def getCreateParams():
    """User create options"""
    user = flask_login.current_user
    return {'quota': user.quota,
            'use_quota': user.use_quota,
            'image': [i['name'] for i in getImages()],
            'node': getNodes(user)}


def getImages():
    """Available images"""
    images = Image.query.filter_by(user="user").order_by(Image.id.desc()).all()
    images = [{'name': i.name, 'description': i.description} for i in images]

    # TODO
    # user = flask_login.current_user
    # box_images = Box.query.filter_by(user=user.name).all()
    # images.extend([{'name': i.box_name} for i in box_images])
    return images


def getNodes(user=None):
    """Return available nodes"""
    # if not bp.usek8s:
    req = baseAPI("search/node")
    if user:
        nodes = [i['name'] for i in req if user.groupid in i['group']]
    else:
        nodes = [i['name'] for i in req]
    return nodes


@bp.route("/vnctoken", methods=["POST"])
@flask_login.login_required
def vncToken():
    """Return vnc password to novnc by token=docker_name"""
    user = flask_login.current_user
    docker_name = request.form.get('token')
    logger.debug("[VNC] " + user.name + " " + str(docker_name))
    if not docker_name:
        abort(400, "VNC Token Error")
    if user.groupid == 1:  # admin
        box = Box.query.filter_by(docker_name=docker_name).first()
    else:
        box = Box.query.filter_by(user=user.name,
                                  docker_name=docker_name).first()
    if not box:
        abort(400, "Environment Not Found")
    return bp.vncpw


@bp.route("/api", methods=["POST"])
@flask_login.login_required
def api():
    """Call pod operations related api"""
    # validation
    user = flask_login.current_user
    data = request.form
    logger.debug("[API] " + user.name + ": " + str(data))

    name = data.get('name')
    if not name:
        abort(400, "What is your environment name")
    if user.groupid == 1:  # admin
        box = Box.query.filter_by(docker_name=name).first()
    else:
        box = Box.query.filter_by(user=user.name,
                                  docker_name=name).first()
    if not box:
        abort(400, "Cannot find your environment")

    # Redirect
    if data.get('method') == "Desktop":
        return redirect("/vnc/?path=vnc/?token=" + box.docker_name)

    elif data.get('method') == "Jupyter":
        return redirect("/jupyter/" + box.docker_name)

    # Methods
    elif data.get('method') == "Restart":
        box.api("restart")

    elif data.get('method') == "Stop":
        boxStop.delay(box.id)

    elif data.get('method') == "Delete":
        boxDelete.delay(box.id)

    elif data.get('method') == "node":
        node = data.get('node')
        if not node or node not in getNodes(user):
            abort(400, "No such server")
        if node == box.node:
            abort(400, "Same server")
        boxChangeNode.delay(box.id, node)

    elif data.get('method') == "Rescue":
        if box.node not in getNodes(user):
            abort(400, "The server is gone")
        boxRescue.delay(box.id)

    elif data.get('method') == "Sync":
        # TODO
        abort(400, "No Implement")

    else:
        abort(400, "How can you show this error")

    return redirect(url_for("labboxmain.box_models.List"))


@bp.route("/create", methods=["POST"])
@flask_login.login_required
def create():
    """Create the pod from web query"""
    user = flask_login.current_user
    data = request.form
    logger.debug("[API Create] " + user.name + ": " + str(data))

    # Validation
    if user.use_quota >= user.quota:
        abort(400, "Quota = 0")
    if not data.get('node') or data.get('node') not in getNodes(user):
        abort(400, "No such server")

    # Validation for name
    realname = user.name + "{:.3f}".format(time.time()).replace(".", "")
    name = realname
    if data.get('name'):
        name = user.name + "_" + data['name']
        # https://github.com/tg123/sshpiper/blob/3243906a19e2e63f7a363050843109aa5caf6b91/sshpiperd/upstream/workingdir/workingdir.go#L36
        if not re.match(r"^[a-z_][-a-z0-9_]{0,31}$", name):
            abort(400, "Your name does not follow the rule")
    if Box.query.filter_by(box_name=name).first():
        abort(400, "Already have the environment")
    if Box.query.filter_by(docker_name=realname).first():
        abort(400, "Already have the environment")

    # Validation for image. Will find the possible image name.
    image = data.get('image')
    parent = None
    if Image.query.filter_by(user="user", name=image).first():
        image = bp.repo_default + data.get('image')
    elif Box.query.filter_by(user=user.name, box_name=image).first():
        parent = Box.query.filter_by(user=user.name, box_name=image).first()
        image = parent.getImageName()
        # TODO
        abort(400, "Not implement method")
    else:
        abort(400, "No such environment")

    boxCreate.delay(user.id, name, realname, data['node'], image, True, parent)
    return redirect(url_for("labboxmain.box_models.List"))


# Method of pod operations
# All of this operations takes long time
# boxStop boxDelete boxChangeNode boxResuce boxCreate
@celery.task()
def boxStop(bid):
    """Commit and Stop the pod"""
    box = Box.query.get(bid)
    box.commit()
    # check=False for double stop
    box.api("delete", check=False)
    piperDelete(box.box_name)
    box.changeStatus("Stopped")


@celery.task()
def boxDelete(bid):
    """Delete the pod"""
    box = Box.query.get(bid)
    # delete
    box.api("delete", check=False)  # force delete
    imageDelete(box)
    piperDelete(box.box_name)
    podDelete(box)

    # quota
    box.delete()
    user = User.query.filter_by(name=box.user).first()
    # user.use_quota -= 1
    user.use_quota = Box.query.filter_by(user=user.name).count()
    user_db.session.commit()


@celery.task()
def boxChangeNode(bid, node):
    """Copy the pod and Change the node"""
    # box data
    box = Box.query.get(bid)
    user = User.query.filter_by(name=box.user).first()
    uid = user.id  # bug?
    parent = box.parent
    name = box.box_name
    docker_name = box.docker_name
    backupname = box.getImageName()

    # commit and push
    box.commit()
    imagePush(box)

    # delete and create
    boxDelete(bid)
    boxCreate(uid, name, docker_name, node, backupname, pull=True, parent=parent)


@celery.task()
def boxCreate(uid, name, realname, node, image, pull=True, parent=""):
    """Create all of pod and it's related"""
    # user
    user = User.query.get(uid)
    user.use_quota += 1
    user_db.session.commit()

    # create
    box = Box.create(user, name, realname, node, image, pull, parent)
    podCreate(box)
    piperCreate(box.box_name, box.docker_ip)

    # make sure it is running
    time.sleep(5)
    box.api("passwd", pw=user.password)


@celery.task()
def boxRescue(bid):
    """Resuce the pod from it's image"""
    box = Box.query.get(bid)
    image = box.image if not box.findImage() else box.getImageName()
    node = box.node
    name = box.box_name
    parent = box.parent
    docker_name = box.docker_name

    # delete(Note: did not delete image)
    box.api("delete", check=False)  # force delete
    piperDelete(box.box_name)
    podDelete(box)

    # quota
    user = User.query.filter_by(name=box.user).first()
    user.use_quota = Box.query.filter_by(user=user.name).count()
    user_db.session.commit()
    box.delete()

    # create
    boxCreate(user.id, name, docker_name, node, image,
              pull=False, parent=parent)


# TODO
@celery.task()
def duplicate(bid, uid, name, node, docker_name, image, delete_bid=""):
    if not Box.query.filter_by(user=user.name,
                               box_name=box.parent).first():
        abort(400, "No Parent existed")
    box.api("delete", check=False)
    parent_box = Box.query.filter_by(user=user.name,
                                     box_name=box.parent).first()
    backupname = parent_box.getImageName()
    parent = box.parent
    node = box.node
    name = box.box_name
    realname = box.docker_name
    duplicate.delay(parent_box.id, user.id, name, node,
                    realname, backupname, box.id)
    box = Box.query.get(bid)
    logger.debug("[Duplicate] push:" + box.box_name)
    box.commit(check=False)
    boxPush(bid)
    if delete_bid:
        logger.debug("[Duplicate] podDelete: " + name)
        podDelete(delete_bid)
    logger.debug("[Duplicate] create: " + name)
    createAPI(uid, name, node, docker_name, image, parent=box.box_name)


# Components Operations
# Image, sshpiper, pod, user.quota
def piperCreate(name, ip):
    """Create sshpiper path to pod"""
    logger.debug("[sshpiper] create: " + name)
    sshfolder = bp.sshpiper + name + "/"
    sshpip = sshfolder + "sshpiper_upstream"
    os.makedirs(sshfolder, exist_ok=True)
    open(sshpip, "w").write("ubuntu@" + ip)
    os.chmod(sshpip, 0o600)


def piperDelete(name):
    """Remove path for sshpiper to pod"""
    logger.debug("[sshpiper] delete: " + name)
    shutil.rmtree(bp.sshpiper + name, ignore_errors=True)


def imageDelete(box):
    """Delete image"""
    logger.debug("[Delete] image: " + box.getImageName())
    box.changeStatus("Deleting ENV copy")
    box.api("delete/image", name=box.getImageName(), check=False)


def imagePush(box):
    """Push the image to registry"""
    if not bp.registry:
        return

    logger.debug("[Push] image: " + box.getImageName())
    box.changeStatus("Backuping")
    try:
        baseAPI("push", name=box.getImageName(),
                node=box.node, **bp.registry)
    except Exception as e:
        logger.error("[Push] image error: " + box.getImageName() + str(e))
        box.changeStatus("Backup Error")
        raise e

    box.changeStatus("")


def podDelete(box):
    """Wait for pod to delete"""
    box.changeStatus("Deleting ENV")
    logger.debug("[Delete] pod wait: " + box.box_name)
    for i in range(60 * 10):  # 10 min
        time.sleep(1)
        rep = box.api("search", check=False)
        if not rep:
            break
    else:
        logger.error("[Delete] pod fail: " + box.box_name)
        box.changeStatus("Delete again later or Contact Admin")
        abort(400, "Cannot Delete")
    box.changeStatus("")
    logger.debug("[Delete] pod OK " + box.box_name)


def podCreate(box):
    """Wait for pod to create"""
    box.changeStatus("Creating")
    logger.debug("[Create] pod wait: " + box.box_name)
    for i in range(60 * 10):  # 10 min
        time.sleep(1)
        rep = box.api("search", check=False)
        if rep and str(rep['status']).lower() == "running":
            break
    else:
        logger.error("[Create] pod fail: " + box.box_name)
        box.changeStatus("Cannot start your environment")
        abort(400, "Cannot start your enviroment")

    # Update data after success
    rep = box.api("search")
    logger.debug("[API Create] pod success: " + str(rep))
    box.docker_ip = rep['ip']
    box.docker_id = rep['id']
    box.changeStatus("")
    # db.session.commit()  # already


# Cross pods operations
# * Routine function: run everyday to maintain and check
# * boxesPasswd
# * boxesCommit
# * boxesStop
def boxesPasswd(user):
    """Change password for all boxes for specific user"""
    logger.debug("[Passwd] user: " + user.name)
    boxes = Box.query.filter_by(user=user.name).all()
    for box in boxes:
        if box.getStatus()['status'].lower() == "running":
            box.api("passwd", pw=user.password)


def boxesCommit(name="", node=""):
    """
    Commit for specific user and specific server.

    Parameters
    ----------
    name: str
        default: *
    node: str
        default: *
    """
    boxes = Box.query
    if name:
        boxes = boxes.filter_by(user=name)
    if node:
        boxes = boxes.filter_by(node=node)
    boxes = boxes.all()
    for box in boxes:
        if box.getStatus()['status'].lower() == "running":
            logger.debug("[Commit] " + box.box_name)
            box.commit(check=False)


def boxesStop(name="", node=""):
    """
    Stop for specific user and specific server.

    Parameters
    ----------
    name: str
        default: *
    node: str
        default: *
    """
    # Commit
    logger.warning("[Waring] Stop " + node)
    if node and node != "all":
        boxes = Box.query.filter_by(node=node).all()
    else:
        boxes = Box.query.all()
    # TODO: fix this
    boxes = [box.id for box in boxes]

    for box in boxes:
        box = Box.query.filter_by(id=box).first()
        if box.getStatus()['status'].lower() == "running":
            logger.warning("[Stop] pod " + box.box_name)
            boxStop(box.id)


# Routine
@celery.task()
def routineMaintain():
    """Run daily to maintain and check the problem"""
    # Commit
    logger.info("[Routine] Commit")
    boxesCommit()
    boxes = Box.query.all()

    # check if it is somewhat kill by kubernetes
    logger.info("[Routine] check inconsistence")
    statusTarget = "Not Consist ID"
    for box in boxes:
        if box.getStatus()['status'] == statusTarget:
            logger.warning("[Routine] inconsistence ID: " + box.box_name)
            rep = otherAPI("search", name=box.docker_name, check=False)
            box.docker_ip = rep['ip']
            box.docker_id = rep['id']
            db.session.commit()

    # run passwd
    logger.info("[Routine] passwd")
    users = User.query.all()
    for user in users:
        boxesPasswd(user)

    # Maintain sshpiper
    logger.info("[Routine] sshpiper")
    for name in os.listdir(bp.sshpiper):
        if os.path.isdir(bp.sshpiper + name):
            shutil.rmtree(bp.sshpiper + name)
    for box in boxes:
        if box.getStatus()['status'].lower() == "running":
            piperCreate(box.box_name, box.docker_ip)
