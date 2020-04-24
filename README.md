# LABBOX

An very easy interface for every user to control their instance on k8s.

Some features are added into this project.
* noVNC
* sshpiper

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

## USAGE

0. Build dockerfile
```
./build_docker.sh
```

1. Modify `labboxmain/config.py`
* [ ] Separte config file from source code

2.  Add user
Note: groupid=0 is admin
```
docker run -it --rm -v $PWD/data:/app/ linnil1/labboxmain flask std-add-user
```

3. Configure on web after started

go to your.domain/admin/

4. Add help.html

You can add `help.html` in `labboxmain/labboxmain/templates/`
* [ ] TODO: Separte help.html from source code

5. Add more node
Add labboxgroup=0-1-2 for allowing group 0,1,2 access this node.
```
kubectl label nodes lab304-server2 labboxgroup=0-1-2 --overwrite
```

And check it:
`kubectl get nodes --show-labels`

7. It is recommand to use the docker image built in
https://github.com/NTU-ToolmenLab/LabDockerFile

and put `all.tar` under the root of `nfs-homenas`(PV)

8. All the output or database are put in `./data`

9. You can try this configuration before creating
```
cd test
helm install lab-traefik stable/traefik -f traefik.yml
kubectl create -f pv.yml pv_user.yml
cd ..
```

10. Using helm to install this package
```
helm install labbox ./labbox
```

11. If any emergency happened
```
kubectl exec -it labboxmain-6599f4b74c-z5jcx flask stop --server=all
```


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
