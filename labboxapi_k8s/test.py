import unittest
from kubernetes import client, config, stream
from requests import get, post
import os
import time
import yaml


config.load_incluster_config()
v1 = client.CoreV1Api()
v1beta = client.ExtensionsV1beta1Api()
url = "http://localhost:3476"
name = "unit-test"
test_node = "lab304-server1"
ns = "user"
image_name = "alpine"
# remember to add
# """
# command: [tail]
# args: ["-f", "/dev/null"]
# """
# in pod.yml


class Test_K8s(unittest.TestCase):
    """Test the api is accessible"""
    def test_basic(self):
        pods = v1.list_pod_for_all_namespaces(watch=False)
        self.assertGreater(len(pods.items), 0)


class TestAPI_unit(unittest.TestCase):
    """Try some easy error input to api"""
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

    def checkOk(self, rep):
        self.assertEqual(rep.status_code, 200)
        rep = rep.json()
        self.assertEqual(rep['status'], 200)

    def test_basic0(self):
        rep = get(self.url)
        self.noErrorCatch(rep)

    def test_basic1(self):
        rep = get(self.url + "/hi")
        self.noErrorCatch(rep)

    def test_basic2(self):
        rep = get(self.url + "/search")
        self.noErrorCatch(rep)

    def test_basic_search(self):
        rep = post(self.url + "/search")
        self.checkOk(rep)
        rep = rep.json()['data']
        self.assertIsInstance(rep, list)

    def test_listnode(self):
        rep = post(self.url + "/search/node")
        self.checkOk(rep)
        rep = rep.json()['data']
        self.assertIsInstance(rep, list)
        self.assertIsInstance(rep[0], dict)
        self.assertIn("ip", rep[0])
        self.assertIn("name", rep[0])
        return rep

    def test_basic_search_fail(self):
        rep = post(self.url + "/search", data={'name': name})
        self.errorCatch(rep)

    def test_send_node(self):
        rep = self.test_listnode()
        for node in rep:
            rep = post(self.url + "/" + node['name'] + "/search")
            self.assertEqual(rep.status_code, 200)
            rep = rep.json()['data']
            self.assertIsInstance(rep, list)

    def test_redir_node_error(self):
        rep = post(self.url + "/123123/search")
        self.errorCatch(rep)

    def test_delete_empty(self):
        rep = post(self.url + "/delete", data={'name': name})
        self.errorCatch(rep)


class TestAPI_cycle(unittest.TestCase):
    """
    Multiple operation test together

    In the section, the tesing time will be longer. Each of the unit test
    will contain multiple operations. Such as create, delete.
    """
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

    def checkOk(self, rep):
        self.assertEqual(rep.status_code, 200)
        rep = rep.json()
        self.assertEqual(rep['status'], 200)

    def getCreateParam(self, **kwargs):
        v = {
            'image': image_name,
            'homepath': "guest/test",
            'homepvc': "nfs-homenas",
            'naspvc': "nfs-labnas",
            'node': test_node,
            'pull': "true",
            'name': name
        }
        v.update(kwargs)
        return v

    def wait(self, func):
        t = 60
        while t > 0:
            print('.')
            rep = post(self.url + "/search", data={'name': name})
            rep = rep.json()
            if func(rep):
                return
            t = t - 1
            time.sleep(3)
        self.assertTrue(False)

    def test_create_delete(self):
        # Before Create
        print("Check before Creation")
        rep = post(self.url + "/search", data={'name': name})
        self.errorCatch(rep)
        with self.assertRaises(client.rest.ApiException):
            v1.read_namespaced_service(name, ns)
        with self.assertRaises(client.rest.ApiException):
            v1beta.read_namespaced_ingress(name, ns)

        # create
        print("Create")
        rep = post(self.url + "/create", data=self.getCreateParam(naspvc=""))
        self.checkOk(rep)
        self.wait(lambda rep: rep['status'] == 200 and rep['data'].get("status") == "Running")

        # Delete
        print("Delete")
        rep = post(self.url + "/delete", data={'name': name})
        self.checkOk(rep)
        self.wait(lambda rep: rep['status'] == 400)

        # check delete
        with self.assertRaises(client.rest.ApiException):
            v1.read_namespaced_service(name, ns)
        with self.assertRaises(client.rest.ApiException):
            v1beta.read_namespaced_ingress(name, ns)

    def test_consist(self):
        """
        # You should create some data before testing
        mkdir -p /home/nas/test
        mkdir -p /nashome/guest/test/tmp1
        # os.makedirs("/home/nas/test/tmp0", exist_ok=True)
        # os.makedirs("/nashome/guest/test/tmp1", exist_ok=True)
        """
        # error creating
        rep = post(self.url + "/create", data=self.getCreateParam(node="123", naspvc=""))
        self.errorCatch(rep)

        # create
        print("Create")
        rep = post(self.url + "/create", data=self.getCreateParam())
        self.checkOk(rep)
        self.wait(lambda rep: rep['status'] == 200 and rep['data'].get("status") == "Running")

        # double create
        rep = post(self.url + "/create", data=self.getCreateParam(naspvc=""))
        self.errorCatch(rep)

        # check running
        rep = post(self.url + "/search", data={'name': name}).json()["data"]
        self.assertIn("id", rep)
        v1.read_namespaced_service(name, ns)
        v1beta.read_namespaced_ingress(name, ns)

        # Check Share Dir
        resp = stream.stream(v1.connect_get_namespaced_pod_exec, name, ns,
                             command=["ls", "/home/nas"],
                             stderr=True, stdin=True, stdout=True, tty=False)
        self.assertIn("test", resp)
        resp = stream.stream(v1.connect_get_namespaced_pod_exec, name, ns,
                             command=["ls", "/home/ubuntu"],
                             stderr=True, stdin=True, stdout=True, tty=False)
        self.assertIn("tmp1", resp)

        # Check if delete it
        print("Delete")
        rep = post(self.url + "/delete", data={'name': name})
        self.checkOk(rep)
        self.wait(lambda rep: rep['status'] == 400)

    def test_with_docker(self):
        print("Create")
        rep = post(self.url + "/create", data=self.getCreateParam(naspvc=""))
        self.checkOk(rep)
        self.wait(lambda rep: rep['status'] == 200 and rep['data'].get("status") == "Running")

        tmpname = str(time.time())
        rep = stream.stream(v1.connect_get_namespaced_pod_exec, name, ns,
                            command=["touch", "/opt/" + tmpname],
                            stderr=True, stdin=True, stdout=True, tty=False)

        print("Commit")
        id  = post(self.url + "/search", data={'name': name}).json()["data"]["id"]
        rep = post(self.url + "/" + test_node + "/commit", data={'name': id,
                                                                 'newname': name})
        self.checkOk(rep)

        print("Delete")
        rep = post(self.url + "/delete", data={'name': name})
        self.checkOk(rep)
        self.wait(lambda rep: rep['status'] == 400)

        print("Create Again")
        rep = post(self.url + "/create", data=self.getCreateParam(image=name, naspvc="", pull="false"))
        self.checkOk(rep)
        self.wait(lambda rep: rep['status'] == 200 and rep['data'].get("status") == "Running")

        # check data is exist
        rep = stream.stream(v1.connect_get_namespaced_pod_exec, name, ns,
                            command=["ls", "/opt/" + tmpname],
                            stderr=True, stdin=True, stdout=True, tty=False)
        self.assertIn(tmpname, rep)

        print("Delete Again")
        rep = post(self.url + "/delete", data={'name': name})
        self.checkOk(rep)
        self.wait(lambda rep: rep['status'] == 400)

        print("Delete image")
        rep = post(self.url + "/" + test_node + "/delete/image", data={'name': name}),
        self.checkOk(rep)

    def test_single_command(self):
        print("Create")
        rep = post(self.url + "/create", data=self.getCreateParam(
                   command="echo 123 && sleep 5 && >&2 echo error", naspvc=""))
        self.checkOk(rep)

        # Wait for command done
        self.wait(lambda rep: rep['status'] == 200 and rep['data'].get("status") in ["Succeeded", "Failed"])

        # completed
        rep = post(self.url + "/log", data={'name': name})
        self.checkOk(rep)
        rep = rep.json()['data']
        self.assertEqual(rep['log'], "123\nerror\n")

        # delete
        print("Delete")
        rep = post(self.url + "/delete", data={'name': name})
        self.checkOk(rep)
        self.wait(lambda rep: rep['status'] == 400)


if __name__ == "__main__":
    unittest.main()
