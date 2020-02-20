import unittest
import threading
import time
from broadcaster.dccBroadcaster import Server
from broadcaster.client import Client


class Test_Server(unittest.TestCase):
    def setUp(self):
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

        client1 = Client()
        delay()
        self.assertTrue(client1.isConnected())
        self.assertEqual(server.client_count(), (0, 1))

        client1.disconnect()
        delay()
        self.assertFalse(client1.isConnected())
        self.assertEqual(server.client_count(), (0, 0))

        #
        client2 = Client()
        delay()
        self.assertTrue(client2.isConnected())
        self.assertEqual(server.client_count(), (0, 1))

        client3 = Client()
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

    def test_join_one_room(self):
        delay = self.delay
        server = self._server

        c1 = Client()
        delay()
        self.assertEqual(server.client_count(), (0, 1))

        c1.joinRoom('room1')
        delay()
        self.assertEqual(server.client_count(), (1, 0))

        c2 = Client()
        delay()
        self.assertEqual(server.client_count(), (1, 1))

        c2.joinRoom('room1')
        delay()
        self.assertEqual(server.client_count(), (2, 0))

        c2.leaveRoom('room1')
        delay()
        self.assertEqual(server.client_count(), (1, 1))

        c2.joinRoom('room1')
        delay()
        self.assertEqual(server.client_count(), (2, 0))

        c1.leaveRoom('room1')
        delay()
        self.assertEqual(server.client_count(), (1, 1))

        c2.leaveRoom('room1')
        delay()
        self.assertEqual(server.client_count(), (0, 2))


if __name__ == '__main__':
    unittest.main()
