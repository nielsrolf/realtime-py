import json
import websockets
from channel import Channel
from collections import defaultdict
import asyncio
from messages import Message, ChannelEvents, PHOENIX_CHANNEL, HEARTBEAT_PAYLOAD
from exceptions import NotConnectedError

class Socket:

    def ensure_connection(func):
        def wrapper(*args):
            if not args[0].connected:
                raise NotConnectedError(func.__name__)

            func()

        return wrapper

    def __init__(self, url: str, params: dict = {}, hb_interval: int = 5):
        """
        `Socket` is the abstraction for an actual socket connection that receives and 'reroutes' `Message` according to its `topic` and `event`.
        Socket-Channel has a 1-many relationship.
        Socket-Topic has a 1-many relationship.
        :param url: Websocket URL of the Realtime server. starts with `ws://` or `wss://`
        :param params: Optional parameters for connection.
        :param hb_interval: WS connection is kept alive by sending a heartbeat message. Optional, defaults to 5.
        """
        self.url = url
        self.channels = defaultdict(list)
        self.connected = False
        self.params: dict = params
        self.hb_interval: int = hb_interval
        self.ws_connection: websockets.client.WebSocketClientProtocol = None
        self.kept_alive: bool = False

    @ensure_connection
    def listen(self):
        """
        Wrapper for async def _listen() to expose a non-async interface
        In most cases, this should be the last method executed as it starts an infinite listening loop.
        :return: None
        """
        loop = asyncio.get_event_loop()
        loop.run_until_complete(asyncio.gather(self._listen(), self._keep_alive()))

    async def _listen(self):
        """
        An infinite loop that keeps listening.
        :return: None
        """
        while True:
            try:
                msg = await self.ws_connection.recv()
                msg = Message(**json.loads(msg))
                if msg.event == ChannelEvents.reply:
                    continue
                for channel in self.channels.get(msg.topic, []):
                    for cl in channel.listeners:
                        if cl.event == msg.event:
                            cl.callback(msg.payload)

            except websockets.exceptions.ConnectionClosed:
                print('Connection Closed')
                break

    def connect(self):
        """
        Wrapper for async def _connect() to expose a non-async interface
        """
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._connect())
        self.connected = True

    async def _connect(self):

        ws_connection = await websockets.connect(self.url)
        if ws_connection.open:
            # TODO: Include a logger to indicate successful connection
            self.ws_connection = ws_connection
            self.connected = True

        else:
            raise Exception("Connection Failed")

    async def _keep_alive(self):
        '''
        Sending heartbeat to server every 5 seconds
        Ping - pong messages to verify connection is alive
        '''
        while True:
            try:
                data = dict(topic=PHOENIX_CHANNEL, event=ChannelEvents.heartbeat, payload=HEARTBEAT_PAYLOAD, ref=None)
                await self.ws_connection.send(json.dumps(data))
                await asyncio.sleep(self.hb_interval)
            except websockets.exceptions.ConnectionClosed:
                # TODO: use logger instead
                print('Connection with server closed')
                break

    @ensure_connection
    def set_channel(self, topic: str):
        """
        :param topic: Initializes a channel and creates a two-way association with the socket
        :return: None
        """

        chan = Channel(self, topic, self.params)
        self.channels[topic].append(chan)

        return chan


    def summary(self):
        """
        Prints a list of topics and event the socket is listening to
        :return: None
        """
        for topic, chans in self.channels.items():
            for chan in chans:
                print(f"Topic: {topic} | Events: {[e for e, _ in chan.callbacks]}]")
