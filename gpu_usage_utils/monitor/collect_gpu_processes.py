import subprocess
import psutil
import re
import sqlite3
from prometheus_client import start_http_server, Summary, Gauge
import time

# Get process
db_file = '/data/db.sqlite'
query_str = 'SELECT user, box_name FROM box where docker_id = ?'


def getGPU():
    process = subprocess.run('nvidia-smi pmon -c 1 -o DT -s um -d 1'.split(),
                             stdout=subprocess.PIPE)
    ori_data = process.stdout.decode().split('\n')

    header = ori_data[0][1:].split()
    data = ori_data[2:]
    value_arr = [dict(zip(header, data_str.split())) for data_str in data]
    value_arr = list(filter(lambda a: a and a.get('fb') != '-', value_arr))
    return value_arr


def getProcess(pid):
    now_p = psutil.Process(pid)
    container_p = now_p
    while container_p.name() != 'containerd-shim' and \
          container_p.name() != 'docker-containerd-shim':
        container_p = container_p.parent()

    container_name = ' '.join(container_p.cmdline())
    container_name = re.findall(r'moby/(\w+)', container_name)[0]
    return {
        'container': container_name,
        'cmd': ' '.join(now_p.cmdline()),
        'cpu_usage': now_p.cpu_times().user / 3600,
        'create_time': now_p.create_time()
    }


def setMetrics():
    """ exmaple metrics
{
    'time': 123
    'create_time': 1555399054.08,
    'cmd': 'python3 train.py',
    'container': 'dcf',
    'user': 'username',
    'cpu_usage': 3.350138888888889,
    'create_time': 1555399054.08,
    'gpuid': 1,
    'memory': 5453,
    'pid': 15716,
    'gpu_usage': 30
}
    """
    db = sqlite3.connect(db_file)
    mapping = {
        'gpu': ('gpuid', int),
        'pid': ('pid', int),
        'sm': ('gpu_usage', int),
        'fb': ('memory', int)}
    objs = []
    for m in getGPU():
        obj = {}
        # from gpu data
        for i in mapping:
            obj[mapping[i][0]] = mapping[i][1](m[i])
        obj['read_time'] = time.strptime(m['Date'] + ' ' + m['Time'],
                                         "%Y%m%d %H:%M:%S")
        obj['read_time'] = time.mktime(obj['read_time'])

        # from process data
        obj.update(getProcess(int(m['pid'])))

        # from database
        db_result = db.execute(query_str, [obj['container']]).fetchone()
        if not db_result: db_result = (None, None)
        obj['user'] = db_result[0]
        obj['boxname'] = db_result[1]

        objs.append(obj)

    return objs


metrics = {
    # 'container': 'dcf',
    # 'cmd': 'python3 train.py',
    # 'user': 'username',
    # 'boxname': 'linnil1_123',
    'create_time': 1555399054.08,
    'read_time': 123,
    'cpu_usage': 3.350138888888889,
    'gpuid': 1,
    'memory': 5453,
    # 'pid': 15716,
    'gpu_usage': 30
}

def pushInit():
    for i in metrics:
        if type(metrics[i]) is float or \
           type(metrics[i]) is int:
            g = Gauge('gpuprocesses_' + i, '',
                      ['id', 'create_time', 'user', 'cmd', 'gpuid'])
            # ID is for find out container
            # user is the username for container
            # create_time is for process
            # gpuid  is which gpu it run on
            metrics[i] = g


def push():
    # remove old
    # why cannot clean it more easily?
    for i in metrics:
        g = metrics[i]
        for sample in g.collect()[0].samples:
            obj = sample.labels
            g.remove(obj['id'],
                     obj['create_time'],
                     obj['user'],
                     obj['cmd'],
                     obj['gpuid'])

    # add
    objs = setMetrics()
    for obj in objs:
        for i in metrics:
            g = metrics[i]
            g.labels(id=obj['boxname'],
                     create_time=obj['create_time'],
                     user=obj['user'],
                     cmd=obj['cmd'],
                     gpuid=obj['gpuid']).set(obj[i])



if __name__ == '__main__':
    from pprint import pprint
    pprint(setMetrics())
    start_http_server(8000)
    pushInit()
    while True:
        push()
        time.sleep(3)
