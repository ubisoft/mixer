import logging
import socket
import time

# https://stackoverflow.com/questions/1833563/simple-way-to-simulate-a-slow-network-in-python

# slice, latency, jitter, bandwidth

logger = logging.getLogger(__name__)


class Socket:
    """Simple wrapper around a socket to simulate bandwidth limitation

    Would be obsoleted by twisted
    (https://stackoverflow.com/questions/13047458/bandwidth-throttling-using-twisted/13647506)
    """

    def __init__(self, sock: socket.socket):
        self._socket: socket.socket = sock
        self._upstream_Bps: float = 0.0
        self._downstream_Bps: float = 0.0

    def __getattr__(self, name):
        return getattr(self._socket, name)

    def set_bandwidth(self, upstream_mbps: float = 0.0, downstream_mbps: float = 0.0):
        mbps_to_bytes_per_sec = 1024 * 1024 / 8.0
        self._upstream_Bps = upstream_mbps * mbps_to_bytes_per_sec
        self._downstream_Bps = downstream_mbps * mbps_to_bytes_per_sec

    def sendall(self, buffer, flags: int = 0):
        if self._downstream_Bps > 0.0:
            delay = len(buffer) / self._downstream_Bps
            logger.warning(f"send {self._downstream_Bps} Bps, buffer {len(buffer)} bytes, delay {delay}")
            time.sleep(delay)
        return self._socket.sendall(buffer, flags)

    def recv(self, size):
        buffer = self._socket.recv(size)
        if self._upstream_Bps > 0.0:
            delay = len(buffer) / self._upstream_Bps
            logger.warning(f"recv {self._upstream_Bps} Bps, buffer {len(buffer)} bytes, delay {delay}")
            time.sleep(delay)
        return buffer
