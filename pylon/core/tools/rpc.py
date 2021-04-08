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
        if rpc_rabbitmq:
            try:
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
                )
                event_node.start()
            except:  # pylint: disable=W0702
                log.exception("Cannot make EventNode instance, using local RPC only")
                event_node = arbiter.MockEventNode()
        else:
            event_node = arbiter.MockEventNode()
        #
        self.node = arbiter.RpcNode(
            event_node,
            id_prefix=rpc_config.get("id_prefix", f"{self.context.node_name}_")
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
