helm install lab-traefik stable/traefik -f traefik.yml
# Update
# helm upgrade lab-traefik -f traefik.yml stable/traefik 
# kubectl rollout restart deployment lab-traefik

kubectl create -f pv.yml pv_user.yml
kubectl label nodes $(hostname) labboxgroup=0-1 --overwrite

