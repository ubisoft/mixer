import unittest
import threading
import time

from mixer.broadcaster.apps.server import Server
from mixer.broadcaster.client import Client
import mixer.broadcaster.common as common

from tests.process import ServerProcess


class Delegate:
    def __init__(self):
        self.clear()

    def clear(self):
        self.clients = None
        self.name_room = None

    def update_rooms_attributes(self, data):
        return None

    def update_clients_attributes(self, data):
        return None


def network_consumer(client, delegate):
    received_commands = client.fetch_commands()

    if received_commands is None:
        return

    for command in received_commands:
        if command.type == common.MessageType.LIST_ROOMS:
            delegate.update_rooms_attributes(command.data)
        elif command.type == common.MessageType.LIST_CLIENTS:
            clients_attributes, _ = common.decode_json(command.data, 0)
            delegate.update_clients_attributes(clients_attributes)


@unittest.skip("")
class TestServer(unittest.TestCase):
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

        client1 = Client()
        delay()
        self.assertTrue(client1.is_connected())
        self.assertEqual(server.client_count(), (0, 1))

        client1.disconnect()
        delay()
        self.assertFalse(client1.is_connected())
        self.assertEqual(server.client_count(), (0, 0))

        #
        client2 = Client()
        delay()
        self.assertTrue(client2.is_connected())
        self.assertEqual(server.client_count(), (0, 1))

        client3 = Client()
        delay()
        self.assertTrue(client3.is_connected())
        self.assertEqual(server.client_count(), (0, 2))

        client2.disconnect()
        delay()
        self.assertFalse(client2.is_connected())
        self.assertTrue(client3.is_connected())
        self.assertEqual(server.client_count(), (0, 1))

        client2.disconnect()
        delay()
        self.assertFalse(client2.is_connected())
        self.assertTrue(client3.is_connected())
        self.assertEqual(server.client_count(), (0, 1))

        client3.disconnect()
        delay()
        self.assertFalse(client3.is_connected())
        self.assertEqual(server.client_count(), (0, 0))

    def test_join_one_room_one_client(self):
        delay = self.delay
        server = self._server

        c0_name = "c0_name"
        c0_room = "c0_room"

        d0 = Delegate()
        c0 = Client()
        delay()
        self.assertEqual(server.client_count(), (0, 1))

        c0.set_client_attributes({common.ClientAttributes.USERNAME: c0_name})
        c0.join_room(c0_room, "ignored", "ignored", True, True)
        delay()
        network_consumer(c0, self._delegate)
        expected = (c0_name, c0_room)
        self.assertEqual(server.client_count(), (1, 0))
        self.assertEqual(len(d0.name_room), 1)
        self.assertIn(expected, d0.name_room)

    def test_join_one_room_two_clients(self):
        delay = self.delay
        server = self._server

        c0_name = "c0_name"
        c0_room = "c0_room"

        c1_name = "c1_name"
        c1_room = c0_room

        d0 = Delegate()
        c0 = Client()
        c0.join_room(c0_room, "ignored", "ignored", True, True)
        c0.set_client_attributes({common.ClientAttributes.USERNAME: c0_name})

        d1 = Delegate()
        c1 = Client()
        c1.join_room(c1_room, "ignored", "ignored", True, True)
        c1.set_client_attributes({common.ClientAttributes.USERNAME: c1_name})

        delay()

        network_consumer(c0, self._delegate)
        network_consumer(c1, self._delegate)
        expected = [(c0_name, c0_room), (c1_name, c1_room)]
        self.assertEqual(server.client_count(), (2, 0))
        self.assertEqual(len(d0.name_room), 2)
        self.assertEqual(len(d1.name_room), 2)
        self.assertCountEqual(d0.name_room, expected)
        self.assertCountEqual(d1.name_room, expected)

    def test_join_one_room_two_clients_leave(self):
        delay = self.delay
        server = self._server

        c0_name = "c0_name"
        c0_room = "c0_room"

        c1_name = "c1_name"
        c1_room = c0_room

        d0 = Delegate()
        c0 = Client()
        c0.join_room(c0_room, "ignored", "ignored", True, True)
        c0.set_client_attributes({common.ClientAttributes.USERNAME: c0_name})

        d1 = Delegate()
        c1 = Client()
        c1.join_room(c1_room, "ignored", "ignored", True, True)
        c1.set_client_attributes({common.ClientAttributes.USERNAME: c1_name})

        c1.leave_room(c1_room)

        delay()
        network_consumer(c0, self._delegate)
        network_consumer(c1, self._delegate)
        expected = [(c0_name, c0_room)]
        self.assertEqual(server.client_count(), (1, 1))
        self.assertEqual(len(d0.name_room), 1)
        self.assertCountEqual(d0.name_room, expected)
        self.assertListEqual(d0.name_room, d1.name_room)


class TestClient(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_client_is_disconnected_when_server_process_is_killed(self):
        server_process = ServerProcess()
        server_process.start()

        with Client(server_process.host, server_process.port) as client:
            self.assertTrue(client.is_connected())
            client.fetch_commands()

            server_process.kill()

            self.assertRaises(common.ClientDisconnectedException, client.fetch_commands)

            self.assertTrue(not client.is_connected())


if __name__ == "__main__":
    unittest.main()
