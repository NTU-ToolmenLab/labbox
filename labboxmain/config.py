from celery.schedules import crontab
import os


# groupid=0 -> admin
# groupid=1 -> Our users
# groupid=2 -> Other users
# groupid=3 -> Our guest
def create_rule(user):
    create_param = {}
    if user.groupid <= 1:
        create_param.update({
            'homepvc': "nfs-homenas",
            'naspvc': "nfs-labnas",
        }) if user.groupid == 2:
        create_param.update({
            'homepath': 'sfc/' + user.name,
            'homepvc': "nfs-homenas",
            'naspvc': "",
        })
    elif user.groupid == 3:
        create_param.update({
            'homepath': 'summer/' + user.name,
            'homepvc': "nfs-homenas",
            'naspvc': "",
        })
    return create_param


def gpu_decision_func(value):
    """
    The decision function of finding server with available gpu.
    Parameters
    ----------
    value: array
        A array of time series array of each metrics.
        e.g. [A metrics time series, B metrics time series]
    """
    duty = sum(value[0]) / len(value[0])
    memory = sum(value[1]) / len(value[1])
    return duty < 10 and memory < 1


config = {
    # Basic
    'bullet': "",
    'name': 'Toolmen',
    'domain_name': '{{ domain_name }}',
    'SECRET_KEY': '{{ secretkey }}',

    # Sehedule
    'celery_schedule': {
        # Maintain all instances(at 2 a.m.)
        'box-routine': {
            'task': 'labboxmain.box.routineMaintain',
            'schedule': crontab(hour=2, minute=0),
        },
    },

    # Registry settigs
    'registry_url': 'harbor.default.svc.cluster.local', # empty to disable
    'registry_user': 'user',
    'registry_password': '{{ registry_password }}',
    'registry_repo_backup': 'user/backup',
    'registry_repo_default': 'linnil1/serverbox',

    # Data path
    'SQLALCHEMY_DATABASE_URI': 'sqlite:////data/db.sqlite',
    'logfile': '/data/main_log.log',

    # init
    'create_rule': create_rule,
    'OAUTH2_REFRESH_TOKEN_GENERATOR': True,
    'SQLALCHEMY_TRACK_MODIFICATIONS': False,
    'SCHEDULER_API_ENABLED': True,

    # Method for connecting to pod
    'sshpiper': '/data/sshpiper/',
    'vnc_password': '{{ vncpw }}',

    # Only use dockerapi(Not maintained now)
    # 'labboxapi-docker': 'http://dockerserver:3476', # Use without kubernetes

    # Use k8s api
    'labboxapi-k8s': "http://{}:3476".format(os.environ.get("NAME_K8SAPI")),

    # Backgroud method
    'celery_broker_url': 'redis://{}:6379'.format(os.environ.get("NAME_REDIS")),
    'celery_result_backend': 'redis://{}:6379'.format(os.environ.get("NAME_REDIS")),

    # GPU settings
    # Details see in box_queue.py
    # set gpu_monitor_url = null to disable monitor gpu
    'gpu_monitor_url': '',
    # 'gpu_monitor_url': 'http://lab-monitor-prometheus-server.monitor.svc.cluster.local/api/v1/',
    'gpu_query_metrics': ['nvidia_gpu_duty_cycle', 'nvidia_gpu_memory_used_bytes / nvidia_gpu_memory_total_bytes'],
    'gpu_decision_func': gpu_decision_func,
    'queue_quota': 6,
    'gpu_query_interval': 60,
    'gpu_exe_interval': 300,
}

# Running queue(Not need to change)
config['celery_schedule']['queue-run'] = {
    'task': 'labboxmain.box_queue.scheduleGPU',
    'schedule': crontab(minute='*'),
}
