# Main program
echo "BUILD labboxmain"
docker build labboxmain -t linnil1/labboxmain

# Control docker to start or stop
echo "BUILD labboxapi-docker"
docker build labboxapi_docker -t linnil1/labboxapi-docker

# Control k8s to create or delete
echo "BUILD labboxapi-k8s"
docker build labboxapi_k8s -t linnil1/labboxapi-k8s

echo "BUILD gpu notifier"
docker build gpu_usage_utils/notify linnil1/gpu-notify

echo "BUILD gpu monitoring"
docker build gpu_usage_utils/monitor linnil1/gpu-monitor

# VNC
echo "BUILD VNC"
cd novnc
git clone https://github.com/novnc/websockify
git clone https://github.com/novnc/noVNC.git
docker run -it --rm -v $PWD/noVNC:/app node:alpine sh -c 'cd /app && npm install . && ./utils/use_require.js --with-app --as commonjs' 
cp -r noVNC/build ./
cp build/vnc.html build/index.html
cat token_plugin.py >> websockify/websockify/token_plugins.py
docker build . -t linnil1/novnc
cd ..
