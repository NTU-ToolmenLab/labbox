# LABBOX

An very easy interface for every user to create and run job in their instance on k8s.

Some features are added into this project.
* labboxmain: A web interface to control instance
* noVNC: Allow user to access their instance by vnc
* sshpiper: Allow user to access their instance by ssh
* simple_email_sender: A simple REST api to send email
* gpu_monitor: Monitor the gpus usage by user
* gpu_notify: Send email to user if gpu is occupied

## Architecture
* Labboxapi_docker
    * The REST api to control docker on each node(DaemonSet).
* Labboxapi_k8s
    * The REST api to control k8s instance.
    * Some operations (e.g. commit push) will pass to labboxapi_docker.
* Labboxmain
    * The interface that every user to login and control their instance.
    * Query everything from labboxapi_k8s
    * Use database(db.sqlite) to store user and apps data.
    * SSH tunnels passing through sshpiper are handled by labboxmain.
    * noVNC query for permission from labboxmain.
    * Oauth server
    * Framework: Vue + flask

## USAGE

0. Build dockerfile
```
./build_docker.sh
```

1. Edit configuartion
* `labboxmain/config.py`
* `./values.yaml` You can copy from `labbox/values.yaml`

2. Run it

You can try this meta configuration before creating
```
cd test
helm install lab-traefik stable/traefik -f traefik.yml
kubectl create -f pv.yml pv_user.yml
cd ..
```

Using helm to install this package
```
helm install labbox ./labbox -f values.yaml
```

3. Where is your Data

Logs and database are put in `data_subpath`(Deafult: `data/`)


### Add user
Note: groupid=0 is admin
```
docker run -it --rm -v $PWD/data:/app/ linnil1/labboxmain flask std-add-user
```

### Add user in batch
You can change the code in `labboxmain/labboxmain/__init__.py`.

Then run `kubectl exec -it $(kubectl get pods -l name=labbox-main -o name) flask add-user-batch`

### Add user's storage in Nextcloud
```
kubectl exec -it $(kubectl get pods -l name=labbox-main -o name) -- flask nextcloud-share-storage --name=linnil1
cp data/nextcloud_storage_setting.json ../Nextcloud/nextcloud/tmp.json
kubectl exec -it -n user $(kubectl get pods -l name=nextcloud-fpm -o name -n user) -- sudo -u www-data php occ files_external:import tmp.json
```

### Add node
Add labboxgroup=0-1-2 for allowing group 0,1,2 access this node.
```
kubectl label nodes lab304-server2 labboxgroup=0-1-2 --overwrite
```

And check it:
`kubectl get nodes --show-labels`


### Configure on web after started
Go to `your.domain/admin/`


### Add help.html
You can add `help.html` in `labboxmain/labboxmain/templates/`

### Change email
You can add and change `*.j2` in `labboxmain/labboxmain/email_templates/`


### Add images and enviorment files for user
It is recommand to use the docker image built in
https://github.com/NTU-ToolmenLab/LabDockerFile

and put `all.tar` under the root of `nfs-homenas`(PV)


### If any emergency happened
```
kubectl exec -it $(kubectl get pods -l name=labbox-main -o name) -- flask stop --server=all
```
or using web interface

`https://your.domain:443/box/stop/`


### VNC
If you want to do more fancy things, like auto login for vnc password.
you can add `novnc/noVNC/app/ui.js` with
```
var xmlHttp = new XMLHttpRequest();
xmlHttp.onreadystatechange = function() {
    if (xmlHttp.readyState == 4 && xmlHttp.status == 200) {
        password = xmlHttp.responseText;
        // do somethings
    }
}
var tokenname = window.location.search;
tokenname = tokenname.substr(17);
xmlHttp.open("POST", "/box/vnctoken, true);  // true for asynchronous
xmlHttp.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
xmlHttp.send("token=" + tokenname);
```

## Demo Image
![](https://raw.githubusercontent.com/NTU-ToolmenLab/labbox/master/test/demo1.jpg)
![](https://raw.githubusercontent.com/NTU-ToolmenLab/labbox/master/test/demo2.jpg)


## TODO
* [ ] Separte config file from source code
* [ ] Separte help.html from source code
* [ ] Separte mail_template/ from source code
