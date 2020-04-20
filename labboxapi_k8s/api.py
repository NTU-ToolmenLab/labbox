from kubernetes import client, config
from flask import Flask, jsonify, redirect, request, abort
import yaml
import re


config.load_incluster_config()
v1 = client.CoreV1Api()
v1beta = client.ExtensionsV1beta1Api()

app = Flask(__name__)
ns = "user"
label = "labbox-user"


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
    app.logger.debug("Error: " + str(error))
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
    app.logger.debug("Error: " + str(error))
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


def listDockerServer():
    """List all available labboxapi_docker"""
    allpods = v1.list_pod_for_all_namespaces(label_selector="app=labbox")
    pods = []
    for pod in list(allpods.items):
        # check labboxapi-docker is alive
        if pod.spec.containers[0].name != "labboxapi-docker" or \
           pod.status.phase != "Running":
            continue

        # check node is alive
        node = pod.spec.node_name
        node_info = v1.list_node(label_selector="kubernetes.io/hostname=" + node).items
        if not node_info or not node_info[0].metadata.labels.get("labboxgroup"):
            continue
        group = node_info[0].metadata.labels.get("labboxgroup")
        try:
            group = [int(g) for g in group.split("-")]
        except ValueError:
            continue

        # add to list
        pods.append({'name': node,
                     'ip': pod.status.pod_ip,
                     'group': group})
    return pods


@app.route("/search/node", methods=["POST"])
def getDockerServer():
    """Return all available labboxapi_docker's node"""
    return Ok(listDockerServer())


def getPod(name):
    """Get pod by name."""
    try:
        pod = v1.read_namespaced_pod(name, ns)
        if pod.metadata.labels[label] != 'true':
            abort(400, "Not in the same namespace")
        if pod.metadata.namespace != ns:
            abort(400, "Not in the same namespace")
    except client.rest.ApiException:
        abort(400, "Pod cannot found")
    return pod


def parsePod(pod):
    """Return a json object from pod object"""
    dockerid = ""
    # container_id has prefix docker://
    if pod.status.container_statuses[0].container_id:
        dockerid = re.findall(r"\w+$", pod.status.container_statuses[0].container_id)[0]
    return {
        'name': pod.metadata.name,
        'image': pod.spec.containers[0].image,
        'status': pod.status.phase,
        'reason': pod.status.reason,
        'start': pod.status.start_time,
        'id': dockerid,
        'ip': pod.status.pod_ip,
        'node': pod.spec.node_name,
    }


@app.route("/create", methods=["POST"])
def create():
    """
    Create the Pod.

    The task will not be done when giving out response.
    Should use "search" to check.

    Parameters
    ----------
    name: str
        The pod name.
    image: str
        The base image you want to start.
    pull: bool
        Whether to pull the image automatically.(true/false)
        Default: false
    homepath: str
        The path you want to mount "homepath" to /home/ubuntu.
    homepvc: str
        The PVC for homepath.
    naspvc: str
        The PVC mount to /home/nas.
    command: str
        Commands to execute.
    inittar: str
        To initialize pod environment by extracting tar file.
        Default: server/ServerBox/all.tar
    gpu: str
        It will add NVIDIA_VISIBLE_DEVICES=gpu to pod environment.

    Returns
    ----------
    Nothing will return.
    You should check by "search".
    """
    # read and handle error
    name = request.form.get("name")
    image = request.form.get("image")
    node = request.form.get("node")
    if not name:
        abort(400, "No Name")
    if not image:
        abort(400, "No Image")
    if not node:
        abort(400, "No Node")
    if node not in [pod['name'] for pod in listDockerServer()]:
        abort(400, "Node Not Found")
    if not (request.form.get("homepvc") and request.form.get("homepath")):
        abort(400, "homepvc and homepath required")

    # fill the template
    app.logger.info("Create " + name)
    template = yaml.load(open("/app/pod.yml"), Loader=yaml.FullLoader)
    template['metadata']['name'] = name
    template['metadata']['labels']['srvname'] = name
    template['metadata']['namespace'] = ns
    template['spec']['containers'][0]['image'] = image
    template['spec']['nodeSelector']['kubernetes.io/hostname'] = request.form.get("node")
    template['spec']['containers'][0]['env'][0]['value'] = request.form.get("node")

    # inittar (Make sure it's at first in volumeMounts)
    if request.form.get("inittar"):
        template['spec']['initContainers'][0]['volumeMounts'][0]['subPath'] = request.form.get("inittar")

    # deal with home volume
    template['spec']['volumes'].append({
        'name': "homenas",
        'persistentVolumeClaim': {'claimName': request.form.get("homepvc")}})
    template['spec']['containers'][0]['volumeMounts'].append({
        'name': "homenas",
        'subPath': request.form.get("homepath"),
        'mountPath': "/home/ubuntu"
    })
    template['spec']['initContainers'][0]['volumeMounts'].append({
        'name': "homenas",
        'subPath': request.form.get("homepath"),
        'mountPath': "/home/ubuntu"
    })

    # deal with nas volume
    if request.form.get("naspvc"):
        naspvc = request.form.get("naspvc").split(",")
        for nas in naspvc:
            template['spec']['volumes'].append({
                'name': "labnas-" + nas,
                'persistentVolumeClaim': {'claimName': nas}})
            template['spec']['containers'][0]['volumeMounts'].append({
                'name': "labnas-" + nas,
                'mountPath': "/home/nas" + ("/" + nas if len(naspvc) > 1 else "")
            })

    # pull
    if request.form.get("pull").lower() == "true":
        template['spec']['containers'][0]['imagePullPolicy'] = "Always"
    if request.form.get("gpu"):
        template['spec']['containers'][0]['env'].append({
            'name': "NVIDIA_VISIBLE_DEVICES",
            'value': request.form['gpu']})

    # only run one command
    if request.form.get("command"):
        del template['spec']['containers'][0]['ports']
        env = [env['name'] + "=" + str(env['value']) for env in template['spec']['containers'][0]['env']]
        # template['spec']['containers'][0]['command'] = ["sudo"]
        # template['spec']['containers'][0]['args'] = [*env, "bash", "-c", request.form.get("command")]
        # testing
        template['spec']['containers'][0]['command'] = ["sh"]
        template['spec']['containers'][0]['args'] = ["-c", request.form.get("command")]

    # create pod
    try:
        pod = v1.read_namespaced_pod(name, ns)
        abort(400, "Double Creation")
    except client.rest.ApiException:
        v1.create_namespaced_pod(ns, template)

    # only run one command
    if request.form.get("command"):
        return Ok()

    # ingress
    template_ingress = yaml.load(open("/app/pod_ingress.yml"), Loader=yaml.FullLoader)
    template_ingress['metadata']['name'] = name
    path = template_ingress['spec']['rules'][0]['http']['paths'][0]
    path['path'] = path['path'].replace("hostname", name)
    path['backend']['serviceName'] = name

    # service
    template_service = yaml.load(open("/app/pod_service.yml"), Loader=yaml.FullLoader)
    template_service['metadata']['name'] = name
    template_service['spec']['selector']['srvname'] = name

    # create ingress and service
    try:
        v1.create_namespaced_service(ns, template_service)
    except client.rest.ApiException:
        pass
    try:
        v1beta.create_namespaced_ingress(ns, template_ingress)
    except client.rest.ApiException:
        pass

    return Ok()


@app.route("/delete", methods=["POST"])
def delete():
    """
    Delete the pod,ingress,service by name

    The task will not be done when giving out response.
    Should use "search" to check.
    """

    name = request.form.get("name")
    getPod(name)
    app.logger.info("Delete " + request.form['name'])
    # using exception bcz didn't check
    try:
        v1.delete_namespaced_pod(name, ns)
    except client.rest.ApiException:
        pass
    try:
        v1.delete_namespaced_service(name, ns)
    except client.rest.ApiException:
        pass
    try:
        v1beta.delete_namespaced_ingress(name, ns)
    except client.rest.ApiException:
        pass
    return Ok()


@app.route("/search", methods=["POST"])
def listPod():
    """
    Search the pod by name.

    Parameters
    ----------
    name: str
        The pod name. Empty will show all pods.
    """
    output = ""
    if request.form.get("name"):
        pod = getPod(request.form.get("name"))
        output = parsePod(pod)
    else:
        pod = v1.list_namespaced_pod(ns, label_selector=label)
        output = [parsePod(p) for p in pod.items]
    return Ok(output)


@app.route("/log", methods=["POST"])
def logShow():
    """Return pod log by name."""
    # find pod
    name = request.form.get("name")
    pod = getPod(name)
    app.logger.info("LOG: " + name)

    log = ""
    result = {}
    if pod.status.phase not in ["Pending", "Unknown"]:
        log = v1.read_namespaced_pod_log(name, ns),
        # why tuple
        if isinstance(log, tuple):
            log = log[0]
        if pod.status.container_statuses[0].state.terminated:
            result = pod.status.container_statuses[0].state.terminated

    # phase: Pending Running Succeeded Failed Unknown
    return Ok({
        'log': log,
        'result': [result.started_at.timestamp(), result.finished_at.timestamp()] if result else [],
        'status': pod.status.phase
    })


@app.route("/<node>/<path:subpath>", methods=["POST"])
def goRedir(node, subpath):
    """
    Transparent layer to redirect to labboxapi-docker.

    Parameters
    ----------
    node: str
        The node that labboxapi-docker in
    subpath: str
        The path send to labboxapi-docker
    """
    app.logger.info(node + " -> " + subpath)
    for dck in listDockerServer():
        if dck['name'] == node:
            return redirect("http://" + dck['ip'] + ":3476/" + subpath, code=307)
    abort(400, "Node not found")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3476)  # , debug=True)
