docker tag linnil1/labboxmain harbor.default.svc.cluster.local/linnil1/labboxmain
docker tag linnil1/labboxapi-docker harbor.default.svc.cluster.local/linnil1/labboxapi-docker
docker tag linnil1/labboxapi-k8s harbor.default.svc.cluster.local/linnil1/labboxapi-k8s
docker tag linnil1/novnc harbor.default.svc.cluster.local/linnil1/novnc
docker tag linnil1/gpu-notify harbor.default.svc.cluster.local/linnil1/gpu-notify
docker tag linnil1/gpu-monitor harbor.default.svc.cluster.local/linnil1/gpu-monitor
docker push harbor.default.svc.cluster.local/linnil1/labboxmain
docker push harbor.default.svc.cluster.local/linnil1/labboxapi-docker
docker push harbor.default.svc.cluster.local/linnil1/labboxapi-k8s
docker push harbor.default.svc.cluster.local/linnil1/novnc
docker push harbor.default.svc.cluster.local/linnil1/gpu-notify
docker push harbor.default.svc.cluster.local/linnil1/gpu-monitor
helm install labbox -f test/k8s_values.yaml labbox
