import docker
import time
import logging

logger = logging.getLogger('GUIKILL')
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('/app/guikill.log')
ch = logging.StreamHandler()
fh.setLevel(logging.DEBUG)
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)-12s - %(name)-12s - %(levelname)-8s - %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
logger.addHandler(fh)
logger.addHandler(ch)

def killandAdd(name, what):
    shstr = ''
    if name.startswith("2018summer_"):
        shstr = 'su ubuntu '
    shstr += 'sh -c "'

    if what == 'gnome-panel':
        tar = 'gnome-panel'
    elif what == 'nemo' or what == 'nautilus':
        if name.startswith("dockercompose_"):
            tar = 'nemo'
        else:
            tar = 'pcmanfm'
    else:
        raise TypeError

    return [shstr + 'pkill ' + what + '"',
            shstr + 'DISPLAY=:0 ' + tar + ' > /dev/null 2>&1 &"']

def getconts():
    conts = docker.from_env().containers.list()
    newconts = []
    for cont in conts:
        if cont.name.startswith("dockercompose_") or \
           cont.name.startswith("2018summer_"):
            newconts.append(cont)
    return newconts

def main():
    conts = getconts()
    for cont in conts:
        if cont.status != 'running':
            continue
        name = cont.name
        top = cont.top(ps_args='-A -o pid,pcpu,rss,time,command')
        scripts = []
        for p in top['Processes']:
            if float(p[1]) < 2:
                continue
            for cmd in ['gnome-panel', 'nemo', 'nautilus']:
                if cmd  in p[-1]:
                    logger.debug(p)
                    scripts.extend(killandAdd(name, cmd))

        if scripts:
            logger.info(name)
            logger.info(scripts)
            for s in scripts:
                cont.exec_run(s)

while True:
    logger.info("Check")
    main()
    time.sleep(3600)


# real code
"""
b.exec_run('sh -c "pkill nemo"')
b.exec_run('sh -c "DISPLAY=:0  nemo > /dev/null 2>&1 &"')
b.exec_run('sh -c "pkill gnome-panel"')
b.exec_run('sh -c "DISPLAY=:0  gnome-panel > /dev/null 2>&1 &"')

b.exec_run('su ubuntu sh -c "pkill gnome-panel"')
b.exec_run('su ubuntu sh -c "DISPLAY=:0  gnome-panel > /dev/null 2>&1 &"')
b.exec_run('su ubuntu sh -c "pkill pcmanfm"')
b.exec_run('su ubuntu sh -c "DISPLAY=:0  pcmanfm . > /dev/null 2>&1 &"')
"""
