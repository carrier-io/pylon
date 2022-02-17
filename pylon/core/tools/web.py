#!/usr/bin/python
# coding=utf-8
# pylint: disable=I0011

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

"""
    Web tools
"""

# from pylon.core.tools import log

routes_registry = dict()  # module -> [routes]  # pylint: disable=C0103
slots_registry = dict()  # module -> [slots]  # pylint: disable=C0103
rpcs_registry = dict()  # module -> [rpcs]  # pylint: disable=C0103
sios_registry = dict()  # module -> [sio]  # pylint: disable=C0103


def route(rule, **options):
    """ (Pre-)Register route """
    #
    def _decorator(obj):
        module = ".".join(obj.__module__.split(".")[:2])
        endpoint = options.pop("endpoint", None)
        #
        if module not in routes_registry:
            routes_registry[module] = list()
        #
        route_item = (rule, endpoint, obj, options)
        routes_registry[module].append(route_item)
        #
        return obj
    #
    return _decorator

def slot(name):
    """ (Pre-)Register slot """
    #
    def _decorator(obj):
        module = ".".join(obj.__module__.split(".")[:2])
        #
        if module not in slots_registry:
            slots_registry[module] = list()
        #
        slot_item = (name, obj)
        slots_registry[module].append(slot_item)
        #
        return obj
    #
    return _decorator

def rpc(name=None, proxy_name=None):
    """ (Pre-)Register RPC """
    #
    def _decorator(obj):
        module = ".".join(obj.__module__.split(".")[:2])
        #
        if module not in rpcs_registry:
            rpcs_registry[module] = list()
        #
        rpc_item = (name, proxy_name, obj)
        rpcs_registry[module].append(rpc_item)
        #
        return obj
    #
    return _decorator

def sio(name):
    """ (Pre-)Register SocketIO event listener """
    #
    def _decorator(obj):
        module = ".".join(obj.__module__.split(".")[:2])
        #
        if module not in sios_registry:
            sios_registry[module] = list()
        #
        sio_item = (name, obj)
        sios_registry[module].append(sio_item)
        #
        return obj
    #
    return _decorator
