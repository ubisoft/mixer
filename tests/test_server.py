import unittest
import threading
import time
from broadcaster.dccBroadcaster import Server
from broadcaster.client import Client
import broadcaster.common as common
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
        logging.info("xxx %s", clients)
        self.clients = clients
        if clients is None:
            self.name_room = None
        else:
            self.name_room = [(c["name"], c["room"]) for c in clients]
        return None

    def on_connection_lost(self):
        return None


def networkConsumer(client, delegate):
    client.fetchCommands()

    while True:
        command = client.getNextReceivedCommand()
        if command is None:
            return

        if command.type == common.MessageType.LIST_ROOMS:
            delegate.buildListRooms(command.data)
        elif command.type == common.MessageType.LIST_ROOM_CLIENTS:
            clients, _ = common.decodeJson(command.data, 0)
            delegate.buildListRoomClients(clients)
        elif command.type == common.MessageType.LIST_ALL_CLIENTS:
            clients, _ = common.decodeJson(command.data, 0)
            delegate.buildListAllClients(clients)
        elif command.type == common.MessageType.CONNECTION_LOST:
            delegate.on_connection_lost()


@unittest.skip("")
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

    def test_join_one_room_one_client(self):
        delay = self.delay
        server = self._server

        c0_name = "c0_name"
        c0_room = "c0_room"

        d0 = Delegate()
        c0 = Client()
        delay()
        self.assertEqual(server.client_count(), (0, 1))

        c0.setClientName(c0_name)
        c0.joinRoom(c0_room)
        delay()
        networkConsumer(c0, self._delegate)
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
        c0.joinRoom(c0_room)
        c0.setClientName(c0_name)

        d1 = Delegate()
        c1 = Client()
        c1.joinRoom(c1_room)
        c1.setClientName(c1_name)

        delay()

        networkConsumer(c0, self._delegate)
        networkConsumer(c1, self._delegate)
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
        c0.joinRoom(c0_room)
        c0.setClientName(c0_name)

        d1 = Delegate()
        c1 = Client()
        c1.joinRoom(c1_room)
        c1.setClientName(c1_name)

        c1.leaveRoom(c1_room)

        delay()
        networkConsumer(c0, self._delegate)
        networkConsumer(c1, self._delegate)
        expected = [(c0_name, c0_room)]
        self.assertEqual(server.client_count(), (1, 1))
        self.assertEqual(len(d0.name_room), 1)
        self.assertCountEqual(d0.name_room, expected)
        self.assertListEqual(d0.name_room, d1.name_room)


if __name__ == "__main__":
    unittest.main()
