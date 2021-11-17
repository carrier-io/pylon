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

from pylon.core.tools import log

routes_registry = dict()  # module -> [routes]  # pylint: disable=C0103


def route(rule, **options):
    """ (Pre-)Register route """
    #
    def _decorator(obj):
        module = ".".join(obj.__module__.split(".")[:2])
        endpoint = options.pop("endpoint", None)
        #
        log.info("module = %s -> %s", obj.__module__, module)
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
