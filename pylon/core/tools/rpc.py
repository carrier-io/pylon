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

""" Core template RPC """

import ssl
import arbiter  # pylint: disable=E0401

try:
    from core.tools import log
except ModuleNotFoundError:
    from pylon.core.tools import log


class RpcManager:
    """ RPC manager: register, unregister, call remote functions """

    def __init__(self, context):
        self.context = context
        #
        rpc_config = self.context.settings.get("rpc", dict())
        rpc_rabbitmq = rpc_config.get("rabbitmq", dict())
        rpc_redis = rpc_config.get("redis", dict())
        #
        if rpc_rabbitmq:
            try:
                ssl_context=None
                ssl_server_hostname=None
                #
                if rpc_rabbitmq.get("use_ssl", False):
                    ssl_context = ssl.create_default_context()
                    if rpc_rabbitmq.get("ssl_verify", False) is True:
                        ssl_context.verify_mode = ssl.CERT_REQUIRED
                        ssl_context.check_hostname = True
                        ssl_context.load_default_certs()
                    else:
                        ssl_context.check_hostname = False
                        ssl_context.verify_mode = ssl.CERT_NONE
                    ssl_server_hostname = rpc_rabbitmq.get("host")
                #
                event_node = arbiter.EventNode(
                    host=rpc_rabbitmq.get("host"),
                    port=rpc_rabbitmq.get("port", 5672),
                    user=rpc_rabbitmq.get("user", ""),
                    password=rpc_rabbitmq.get("password", ""),
                    vhost=rpc_rabbitmq.get("vhost", "carrier"),
                    event_queue=rpc_rabbitmq.get("queue", "rpc"),
                    hmac_key=rpc_rabbitmq.get("hmac_key", None),
                    hmac_digest=rpc_rabbitmq.get("hmac_digest", "sha512"),
                    callback_workers=rpc_rabbitmq.get("callback_workers", 1),
                    ssl_context=ssl_context,
                    ssl_server_hostname=ssl_server_hostname,
                    mute_first_failed_connections=rpc_rabbitmq.get("mute_first_failed_connections", 10),  # pylint: disable=C0301
                )
                event_node.start()
            except:  # pylint: disable=W0702
                log.exception("Cannot make EventNode instance, using local RPC only")
                event_node = arbiter.MockEventNode()
        elif rpc_redis:
            event_node = arbiter.RedisEventNode(
                host=rpc_redis.get("host"),
                port=rpc_redis.get("port", 6379),
                password=rpc_redis.get("password", ""),
                event_queue=rpc_redis.get("queue", "events"),
                hmac_key=rpc_redis.get("hmac_key", None),
                hmac_digest=rpc_redis.get("hmac_digest", "sha512"),
                callback_workers=rpc_redis.get("callback_workers", 1),
                mute_first_failed_connections=rpc_redis.get("mute_first_failed_connections", 10),
                use_ssl=rpc_redis.get("use_ssl", False),
            )
        else:
            event_node = arbiter.MockEventNode()
        #
        self.node = arbiter.RpcNode(
            event_node,
            id_prefix=rpc_config.get("id_prefix", f"{self.context.node_name}_"),
            trace=rpc_config.get("trace", False),
        )
        self.node.start()
        #
        self.call = self.node.proxy
        self.timeout = self.node.timeout

    def register_function(self, func, name=None):
        """ Register RPC function """
        self.node.register(func, name)

    def unregister_function(self, func, name=None):
        """ Unregister RPC function """
        self.node.unregister(func, name)

    def call_function(self, func, *args, **kvargs):
        """ Run RPC function """
        return self.node.call(func, *args, **kvargs)

    def call_function_with_timeout(self, func, timeout, *args, **kvargs):
        """ Run RPC function (with timeout) """
        return self.node.call_with_timeout(func, timeout, *args, **kvargs)
