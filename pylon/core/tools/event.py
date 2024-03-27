#!/usr/bin/python
# coding=utf-8

#   Copyright 2021 getcarrier.io
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

""" Core events """

import ssl
import functools

import arbiter  # pylint: disable=E0401

from pylon.core.tools import log


class EventManager:
    """ Simple event manager """

    def __init__(self, context):
        self.context = context
        #
        events_rabbitmq = self.context.settings.get("events", dict()).get("rabbitmq", dict())
        events_redis = self.context.settings.get("events", dict()).get("redis", dict())
        events_socketio = self.context.settings.get("events", dict()).get("socketio", dict())
        #
        if events_rabbitmq:
            try:
                ssl_context=None
                ssl_server_hostname=None
                #
                if events_rabbitmq.get("use_ssl", False):
                    ssl_context = ssl.create_default_context()
                    if events_rabbitmq.get("ssl_verify", False) is True:
                        ssl_context.verify_mode = ssl.CERT_REQUIRED
                        ssl_context.check_hostname = True
                        ssl_context.load_default_certs()
                    else:
                        ssl_context.check_hostname = False
                        ssl_context.verify_mode = ssl.CERT_NONE
                    ssl_server_hostname = events_rabbitmq.get("host")
                #
                self.node = arbiter.EventNode(
                    host=events_rabbitmq.get("host"),
                    port=events_rabbitmq.get("port", 5672),
                    user=events_rabbitmq.get("user", ""),
                    password=events_rabbitmq.get("password", ""),
                    vhost=events_rabbitmq.get("vhost", "carrier"),
                    event_queue=events_rabbitmq.get("queue", "events"),
                    hmac_key=events_rabbitmq.get("hmac_key", None),
                    hmac_digest=events_rabbitmq.get("hmac_digest", "sha512"),
                    callback_workers=events_rabbitmq.get("callback_workers", 1),
                    ssl_context=ssl_context,
                    ssl_server_hostname=ssl_server_hostname,
                    mute_first_failed_connections=events_rabbitmq.get("mute_first_failed_connections", 10),  # pylint: disable=C0301
                )
                self.node.start()
            except:  # pylint: disable=W0702
                log.exception("Cannot make EventNode instance, using local events only")
                self.node = arbiter.MockEventNode()
                self.node.start()
        elif events_redis:
            try:
                self.node = arbiter.RedisEventNode(
                    host=events_redis.get("host"),
                    port=events_redis.get("port", 6379),
                    password=events_redis.get("password", ""),
                    event_queue=events_redis.get("queue", "events"),
                    hmac_key=events_redis.get("hmac_key", None),
                    hmac_digest=events_redis.get("hmac_digest", "sha512"),
                    callback_workers=events_redis.get("callback_workers", 1),
                    mute_first_failed_connections=events_redis.get("mute_first_failed_connections", 10),  # pylint: disable=C0301
                    use_ssl=events_redis.get("use_ssl", False),
                )
                self.node.start()
            except:  # pylint: disable=W0702
                log.exception("Cannot make EventNode instance, using local events only")
                self.node = arbiter.MockEventNode()
                self.node.start()
        elif events_socketio:
            try:
                self.node = arbiter.SocketIOEventNode(
                    url=events_socketio.get("url"),
                    password=events_socketio.get("password", ""),
                    room=events_socketio.get("room", "events"),
                    hmac_key=events_socketio.get("hmac_key", None),
                    hmac_digest=events_socketio.get("hmac_digest", "sha512"),
                    callback_workers=events_socketio.get("callback_workers", 1),
                    mute_first_failed_connections=events_socketio.get("mute_first_failed_connections", 10),  # pylint: disable=C0301
                    ssl_verify=events_socketio.get("ssl_verify", False),
                )
                self.node.start()
            except:  # pylint: disable=W0702
                log.exception("Cannot make EventNode instance, using local events only")
                self.node = arbiter.MockEventNode()
                self.node.start()
        else:
            self.node = arbiter.MockEventNode()
            self.node.start()
        #
        self.partials = dict()

    def register_listener(self, event, listener):
        """ Register event listener """
        if listener not in self.partials:
            self.partials[listener] = functools.partial(listener, self.context)
        self.node.subscribe(event, self.partials[listener])

    def unregister_listener(self, event, listener):
        """ Unregister event listener """
        if listener not in self.partials:
            return
        self.node.unsubscribe(event, self.partials[listener])

    def fire_event(self, event, payload=None):
        """ Run listeners for event """
        self.node.emit(event, payload)
