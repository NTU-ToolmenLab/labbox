from flask import Flask, request, jsonify, abort
import docker
import ast
import os


app = Flask(__name__)
app.secret_key = "super secret string"  # Change this!
label = "labbox-user"
client = docker.from_env()


@app.errorhandler(Exception)
def AllError(error):
    """
    Catch all error here.

    This function will call if the error cannot handle by my code.

    Returns
    -------
    json
        The status code will be 500.
        There will have a key named "status" and its value is 500.
        The message will show why this happened.
    """
    message = {
        'status': 500,
        'message': "Internal Error: " + str(error)
    }
    app.logger.warning("AllError: " + str(error))
    resp = jsonify(message)
    resp.status_code = 500
    return resp


@app.errorhandler(400)
def Error(error):
    """
    Handle error here.

    Returns
    -------
    json
        The status code will be 400.
        There will have a key named "status" and its value is 400.
        The message will show why this happened.
    """
    app.logger.warning("Error: " + str(error))
    message = {
        'status': 400,
        'message': str(error)
    }
    resp = jsonify(message)
    resp.status_code = 400
    return resp


def Ok(data={}):
    """
    Handle all return data here.

    Returns
    -------
    json
        The status code will be 200.
        There will have a "status" key and its value is 200.
        All the return data will in "data" key.
    """
    return jsonify({
        'status': 200,
        'message': "OK",
        'data': data
    })


def getContainer(id):
    """Ouery the container by id"""
    if not id:
        abort(400, "Container Not Found")
    try:
        container = client.containers.get(id)
        """
        # TODO
        # for k8s label is in another containers
        if label not in container.labels:
            abort(400, "Not in the same namespace")
        """
        return container
    except docker.errors.NotFound:
        abort(400, "Container Not Found")


def parseContainer(cont):
    """Return a json object from container object"""
    return {
        'name': cont.name,
        'image': cont.attrs['Config']['Image'],
        'status': cont.status,
        'reason': cont.status,
        'start': cont.attrs['Created'],
        'id': cont.id,
        'ip': cont.attrs['NetworkSettings']['IPAddress']
    }


@app.route("/search", methods=["POST"])
def search():
    """
    Search the container by ID.

    Parameters
    ----------
    name: str
        The container ID. Empty will show all containers
    """
    query = request.form.get("name")
    output = []
    if not query:
        allcontainer = client.containers.list(filters={'label': label})
        output = [parseContainer(c) for c in allcontainer]
    else:
        container = getContainer(query)
        output = parseContainer(container)

    return Ok(output)


@app.route("/search/image", methods=["POST"])
def searchImage():
    """
    Search the images by ID.

    Parameters
    ----------
    name: str
        The tag name of image.
    """
    query = request.form.get("name")

    try:
        img = client.images.get(query)
    except docker.errors.ImageNotFound:
        abort(400, "Image Not Found")

    return Ok({
            'tag': img.tags[0],
            'date': img.attrs['Metadata']['LastTagTime']})


@app.route("/start", methods=["POST"])
def start():
    """Start the container by name=ID"""
    name = request.form.get("name")
    container = getContainer(name)
    container.start()
    return Ok()


@app.route("/stop", methods=["POST"])
def stop():
    """Stop the container by name=ID"""
    name = request.form.get("name")
    container = getContainer(name)
    container.stop()
    return Ok()


@app.route("/restart", methods=["POST"])
def restart():
    """Restart the container by name=ID"""
    name = request.form.get("name")
    container = getContainer(name)
    container.restart()
    return Ok()


@app.route("/passwd", methods=["POST"])
def passwd():
    """
    Change the password of user(ubuntu).

    Parameters
    ----------
    name: str
        The container ID.
    pw: str
        The sha512 encrypted password
    """
    name = request.form.get("name")
    container = getContainer(name)
    if not container.attrs['State']['Running']:
        abort(400, "Not Running")
    pw = request.form.get("pw")
    rest = container.exec_run('usermod -p "' + pw + '" ubuntu')
    return Ok()


@app.route("/commit", methods=["POST"])
def commit():
    """
    Commit the container to image.

    Parameters
    ----------
    name: str
        The container ID.
    newname: str
        The tag name.
    """
    name = request.form.get("name")
    newname = request.form.get("newname", name)
    container = getContainer(name)
    container.commit(newname)
    return Ok()


@app.route("/push", methods=["POST"])
def push():
    """
    Push the image to somewhere(Harbor).

    Parameters
    ----------
    name: str
        The container ID.
    username: str
        The user name of somewhere
    password: str
        The password of the user
    registry: url
        The url of somewhere
    """
    # check image
    name = request.form.get("name")
    try:
        client.images.get(name)
    except docker.errors.ImageNotFound:
        abort(400, "Not Find Image")

    # check registry
    username = request.form.get("username")
    password = request.form.get("password")
    registry = request.form.get("registry")
    try:
        client.login(username, password=password, registry=registry)
    except docker.errors.APIError:
        abort(400, "Cannot login to registry")

    # push and wait
    rep = client.images.push(name)
    for r in rep.split('\n'):
        if r and ast.literal_eval(r).get("error"):
            abort(400, ast.literal_eval(r).get("error"))
    return Ok()


@app.route("/create", methods=["POST"])
def create():
    """
    Create the container

    Parameters
    ----------
    name: str
        The container name.
    image: str
        The base image you want to start.
    homepath: str
        The path you want to mount "homepath" to /home/ubuntu.
        Default homepath = name
    naspath: str
        The path you want to mount "naspath" to /home/nas.
        You can use more than one nas, use "," to split it.
    command: str
        Commands to execute.

    Returns
    ----------
    Nothing will return.
    You should check by "search".
    """
    # check container exist
    name = request.form.get("name")
    if not name:
        abort(400, "No Name")
    try:
        container = client.containers.get(name)
        abort(400, "Container Already Exist")
    except docker.errors.NotFound:
        pass

    # check image exist
    image = request.form.get("image")
    try:
        client.images.get(image)
    except docker.errors.ImageNotFound:
        abort(400, "Image Not Found")

    # TODO: check path is valid
    mounts = []

    # Path to mount home dir
    homepath = request.form.get("homepath")
    if homepath:
        mounts.append(docker.types.Mount("/home/ubuntu",
                      homepath, type="bind"))

    # Path to mount nas dir
    naspath = request.form.get("naspath")
    if naspath:
        naspath = naspath.split(',')
        if len(naspath) == 1:
            mounts.append(docker.types.Mount("/home/nas",
                          naspath[0], type="bind"))
        else:
            for p in naspath.split(','):
                mounts.append(docker.types.Mount(
                              "/home/nas/" + os.path.basename(p),
                              p,
                              type="bind"))

    # create
    cont = client.containers.run(image,
                                 name=name,
                                 mounts=mounts,
                                 command=request.form.get("command"),
                                 labels={label: "True"},
                                 detach=True,
                                 restart_policy={'Name': "always"})
    return Ok()


@app.route("/delete", methods=["POST"])
def delete():
    """Delete the container by name=ID"""
    name = request.form.get("name")
    container = getContainer(name)
    container.stop()
    container.remove()
    return Ok()


@app.route("/delete/image", methods=["POST"])
def deleteImage():
    """Delete the image by name=ID"""
    name = request.form.get("name")
    try:
        client.images.remove(name, force=True)
    except docker.errors.ImageNotFound:
        abort(400, "Not found Image")
    return Ok()


@app.route("/prune", methods=["POST"])
def prune():
    """Clean staging images"""
    client.images.prune()
    return Ok()


@app.route("/log", methods=["POST"])
def log():
    """Log the container by name=ID"""
    name = request.form.get("name")
    container = getContainer(name)
    return Ok(container.logs().decode())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3476)
