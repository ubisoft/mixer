import unittest
import threading
import time
from broadcaster.dccBroadcaster import Server
from broadcaster.client import Client, TestClient
import logging


class Delegate:
    def __init__(self):
        self.clear()

    def clear(self):
        self.clients = None
        self.name_room = None

    def buildListRooms(self, data):
        return None

    def buildListRoomClients(self, clients):
        logging.info('xxx %s', clients)
        self.clients = clients
        self.name_room = [(c['name'], c['room']) for c in clients]
        return None

    def clearListRoomClients(self):
        return None


class Test_Server(unittest.TestCase):

    def setUp(self):
        self._delegate = Delegate()
        self._server = Server()
        server_thread = threading.Thread(None, self._server.run)
        server_thread.start()

    def tearDown(self):
        self._server.shutdown()
        self.delay()

    def delay(self):
        time.sleep(0.2)

    def test_connect(self):
        delay = self.delay
        server = self._server

        client1 = TestClient()
        delay()
        self.assertTrue(client1.isConnected())
        self.assertEqual(server.client_count(), (0, 1))

        client1.disconnect()
        delay()
        self.assertFalse(client1.isConnected())
        self.assertEqual(server.client_count(), (0, 0))

        #
        client2 = TestClient()
        delay()
        self.assertTrue(client2.isConnected())
        self.assertEqual(server.client_count(), (0, 1))

        client3 = TestClient()
        delay()
        self.assertTrue(client3.isConnected())
        self.assertEqual(server.client_count(), (0, 2))

        client2.disconnect()
        delay()
        self.assertFalse(client2.isConnected())
        self.assertTrue(client3.isConnected())
        self.assertEqual(server.client_count(), (0, 1))

        client2.disconnect()
        delay()
        self.assertFalse(client2.isConnected())
        self.assertTrue(client3.isConnected())
        self.assertEqual(server.client_count(), (0, 1))

        client3.disconnect()
        delay()
        self.assertFalse(client3.isConnected())
        self.assertEqual(server.client_count(), (0, 0))

    def test_join_one_room_one_client(self):
        delay = self.delay
        server = self._server

        c0_name = 'c0_name'
        c0_room = 'c0_room'

        d0 = Delegate()
        c0 = TestClient(delegate=d0)
        delay()
        self.assertEqual(server.client_count(), (0, 1))

        c0.joinRoom(c0_room)
        c0.setClientName(c0_name)
        delay()
        c0.networkConsumer()
        expected = (c0_name, c0_room)
        self.assertEqual(server.client_count(), (1, 0))
        self.assertEqual(len(d0.name_room), 1)
        self.assertIn(expected, d0.name_room)

    def test_join_one_room_two_clients(self):
        delay = self.delay
        server = self._server

        c0_name = 'c0_name'
        c0_room = 'c0_room'

        c1_name = 'c1_name'
        c1_room = c0_room

        d0 = Delegate()
        c0 = TestClient(delegate=d0)
        c0.joinRoom(c0_room)
        c0.setClientName(c0_name)

        d1 = Delegate()
        c1 = TestClient(delegate=d1)
        c1.joinRoom(c1_room)
        c1.setClientName(c1_name)

        delay()

        c0.networkConsumer()
        c1.networkConsumer()
        expected = [(c0_name, c0_room), (c1_name, c1_room)]
        self.assertEqual(server.client_count(), (2, 0))
        self.assertEqual(len(d0.name_room), 2)
        self.assertEqual(len(d1.name_room), 2)
        self.assertCountEqual(d0.name_room, expected)
        self.assertCountEqual(d1.name_room, expected)


if __name__ == '__main__':
    unittest.main()
