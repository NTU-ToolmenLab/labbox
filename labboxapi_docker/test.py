import unittest
import docker
from requests import get, post
import os
import time


client = docker.from_env()
url = "http://localhost:3476"
name = "unit_test"
default_image = "alpine"
reg = {  # used in push_cycle
    'registry': "harbor.default.svc.cluster.local",
    'username': "",
    'password': "",
}


class TestDocker(unittest.TestCase):
    def test_basic(self):
        envs = client.containers.list()
        self.assertGreater(len(envs), 0)


class TestAPI_unit(unittest.TestCase):
    def setUp(self):
        self.url = url

    def errorCatch(self, rep):
        self.assertEqual(rep.status_code, 400)
        rep = rep.json()
        self.assertEqual(rep['status'], 400)

    def noErrorCatch(self, rep):
        self.assertEqual(rep.status_code, 500)
        rep = rep.json()
        self.assertEqual(rep['status'], 500)

    def checkOK(self, rep):
        self.assertEqual(rep.status_code, 200)
        rep = rep.json()
        self.assertEqual(rep['status'], 200)

    def test_url0(self):
        rep = get(self.url)
        self.noErrorCatch(rep)

    def test_url1(self):
        rep = get(self.url + "/hi")
        self.noErrorCatch(rep)

    def test_search(self):
        rep = get(self.url + "/search")
        self.noErrorCatch(rep)

    def test_search_fail(self):
        rep = post(self.url + "/search", data={'name': name})
        self.errorCatch(rep)

    def test_search_fail_image(self):
        rep = post(self.url + "/search/image", data={'name': name})
        self.errorCatch(rep)

    def test_prune(self):
        rep = post(self.url + "/prune")
        self.checkOK(rep)

    def test_delete_empty(self):
        rep = post(self.url + "/delete", data={'name': name})
        self.errorCatch(rep)

    def test_delete_empty_image(self):
        rep = post(self.url + "/delete/image", data={'name': name})
        self.errorCatch(rep)


class TestAPI_cycle(unittest.TestCase):
    def setUp(self):
        self.url = url

    def checkOK(self, rep):
        self.assertEqual(rep.status_code, 200)
        rep = rep.json()
        self.assertEqual(rep['status'], 200)
        self.assertEqual(rep['message'], "OK")

    def errorCatch(self, rep):
        self.assertEqual(rep.status_code, 400)
        rep = rep.json()
        self.assertEqual(rep['status'], 400)

    def checkRunning(self):
        rep = post(self.url + "/search", data={'name': name})
        self.checkOK(rep)
        rep = rep.json()
        self.assertIsInstance(rep['data'], dict)
        self.assertEqual(rep['data']['status'], "running")

    def test_container_cycle(self):
        """
        # this should run on local mechine
        mkdir -p /home/nas/test/tmp0
        mkdir -p /nashome/guest/test/tmp1
        # os.makedirs("/home/nas/test/tmp0", exist_ok=True)
        # os.makedirs("/nashome/guest/test/tmp1", exist_ok=True)
        """
        # Before Create
        print("Create")
        rep = post(self.url + "/search", data={'name': name})
        self.errorCatch(rep)

        # Create
        rep = post(self.url + "/create", data={
            'image': default_image,
            'homepath': "/nashome/guest/test",
            'naspath': "/home/nas/test",
            'command': "tail -f /dev/null",
            'name': name})
        self.checkRunning()

        # Double create
        rep = post(self.url + "/create", data={
            'image': default_image,
            'homepath': "/nashome/guest/test",
            'naspath': "/home/nas/test",
            'command': "tail -f /dev/null",
            'name': name})
        self.errorCatch(rep)

        # Check by api
        con = client.containers.get(name)
        self.assertIn("tmp0", con.exec_run("ls /home/nas").output.decode())
        self.assertIn("tmp1", con.exec_run("ls /home/ubuntu").output.decode())
        self.assertEqual(con.status, "running")

        # Stop
        con.exec_run("touch /opt/tmp2").output.decode()
        print("Stop")
        rep = post(self.url + "/stop", data={'name': name})
        self.checkOK(rep)

        # check stop
        rep = post(self.url + "/search", data={'name': name})
        self.checkOK(rep)
        rep = rep.json()
        self.assertIsInstance(rep["data"], dict)
        self.assertEqual(rep['data']['status'], "exited")

        # start
        print("Resume")
        rep = post(self.url + "/start", data={'name': name})
        self.checkOK(rep)
        self.checkRunning()
        con = client.containers.get(name)
        self.assertIn("tmp2", con.exec_run("ls /opt").output.decode())

        # change pw
        print("Change Password")
        con.exec_run("adduser ubuntu")
        rep = post(self.url + "/passwd", data={'name': name,
                                               'pw': "tmpPW"})
        self.checkOK(rep)
        self.assertIn("tmpPW", con.exec_run("cat /etc/shadow").output.decode())

        # commit
        print("Commit")
        rep = post(self.url + "/commit", data={'name': name,
                                               'newname': name})
        self.checkOK(rep)

        # search image
        rep = post(self.url + "/search/image", data={'name': name})
        rep = rep.json()
        self.assertIsInstance(rep['data'], dict)

        # delete
        print("Delete")
        rep = post(self.url + "/delete", data={'name': name})
        self.checkOK(rep)

        # check delete
        rep = post(self.url + "/search", data={'name': name})
        self.errorCatch(rep)

        # Delete Image
        print("Delete Image")
        rep = post(self.url + "/delete/image", data={'name': name})
        self.checkOK(rep)

        # Check if delete it
        rep = post(self.url + "/search/image", data={'name': name})
        self.errorCatch(rep)

    def test_push_cycle(self):
        # Create
        print("Create")
        rep = post(self.url + "/create", data={
            'image': default_image,
            'homepath': "/nashome/guest/test",
            'naspath': "/home/nas/test",
            'command': "tail -f /dev/null",
            'name': name})
        self.checkRunning()
        t = str(time.time())
        con = client.containers.get(name)
        con.exec_run("touch /opt/" + t).output.decode()

        # commit
        print("Commit")
        reg_name = reg['registry'] + "/" + reg['username'] + '/' + name
        rep = post(self.url + "/commit", data={'name': name,
                                               'newname': reg_name})
        self.checkOK(rep)

        # push
        print("Push")
        rep = post(self.url + "/push", data={
                   **reg,
                   'name': reg_name})

        # delete
        print("Delete")
        rep = post(self.url + "/delete", data={'name': name})
        self.checkOK(rep)

        # Delete Image
        print("Delete Image")
        rep = post(self.url + "/delete/image", data={'name': reg_name})
        self.checkOK(rep)
        rep = post(self.url + "/search/image", data={'name': reg_name})
        self.errorCatch(rep)

        # pull
        print("Pull Image")
        client.images.pull(reg_name)

        # start
        print("Create")
        rep = post(self.url + "/create", data={
            'image': reg_name,
            'homepath': "/nashome/guest/test",
            'naspath': "/home/nas/test",
            'command': "tail -f /dev/null",
            'name': name})
        self.checkRunning()
        con = client.containers.get(name)
        self.assertIn(t, con.exec_run("ls /opt").output.decode())

        # delete
        print("Delete")
        rep = post(self.url + "/delete", data={'name': name})
        self.checkOK(rep)
        print("Delete Image")
        rep = post(self.url + "/delete/image", data={'name': reg_name})
        self.checkOK(rep)


if __name__ == "__main__":
    unittest.main()
