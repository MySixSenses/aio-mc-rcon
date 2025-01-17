import asyncio
import random
import struct

from .errors import *


class MessageType:
    LOGIN = 3
    COMMAND = 2
    RESPONSE = 0
    INVALID_AUTH = -1


class Client:
    """The base class for creating an RCON client."""

    def __init__(self, host: str, port: int, password: str) -> None:
        self.host = host
        self.port = port
        self.password = password

        self._reader = None
        self._writer = None

        self._ready = False

    async def __aenter__(self, timeout=2):
        await self.connect(timeout)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def connect(self, timeout=2):
        """Sets up the connection between the client and server."""

        if self._ready:
            return

        try:
            self._reader, self._writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), timeout)
        except (asyncio.TimeoutError, TimeoutError) as e:
            raise RCONConnectionError("A timeout occurred whilst attempting to connect to the server.", e)
        except ConnectionRefusedError as e:
            raise RCONConnectionError("The remote server refused the connection.", e)
        except Exception as e:
            raise RCONConnectionError("The connection failed for an unknown reason.", e)

        await self._send_msg(MessageType.LOGIN, self.password)

        self._ready = True

    async def _send_msg(self, type_: int, msg: str) -> tuple:
        """Sends data to the server, and returns the response."""

        # randomly generate request id
        req_id = random.randint(0, 2147483647)

        # pack request id, packet type, and the actual message
        packet_data = struct.pack("<ii", req_id, type_) + msg.encode("utf8") + b"\x00\x00"

        # pack length of packet + rest of packet data
        packet = struct.pack("<i", len(packet_data)) + packet_data

        # send the data to the server
        self._writer.write(packet)
        await self._writer.drain()

        # read + unpack length of incoming packet
        in_len = struct.unpack("<i", (await self._reader.read(4)))[0]

        # read rest of packet data
        in_data = await self._reader.read(in_len)

        if not in_data.endswith(b"\x00\x00"):
            raise ValueError("Invalid data received from server.")

        # decode the incoming request id and packet type
        in_type, in_req_id = struct.unpack("<ii", in_data[0:8])

        if in_type == MessageType.INVALID_AUTH:
            raise IncorrectPasswordError

        # decode the received message
        in_msg = in_data[8:-2].decode("utf8")

        return in_msg, in_type

    async def send_cmd(self, cmd: str, timeout=2, strip_colors = True) -> tuple:
        """Sends a command to the server."""
        if not self._ready:
            raise ClientNotConnectedError
        value = await asyncio.wait_for(self._send_msg(MessageType.COMMAND, cmd), timeout)
        if isinstance(strip_colors, bool) and strip_colors:
            value = list(value)
            value[0] = re.sub("§.", "", value[0])
            return tuple(value)
        return value

    async def close(self):
        """Closes the connection between the client and the server."""

        if self._ready:
            self._writer.close()
            await self._writer.wait_closed()

            self._reader = None
            self._writer = None

            self._ready = False
