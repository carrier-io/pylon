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
    Traefik tools
"""

import os
import socket

from redis import StrictRedis  # pylint: disable=E0401

from pylon.core import constants
from pylon.core.tools import log
from pylon.core.tools import env


def register_traefik_route(context):
    """ Create Traefik route for this Pylon instance """
    context.traefik_redis_keys = list()
    #
    if context.before_reloader:
        log.info("Running in development mode before reloader is started. Skipping registration")
        return
    #
    traefik_config = context.settings.get("traefik", dict())
    if not traefik_config:
        log.info("Cannot register route: no traefik config")
        return
    #
    redis_config = traefik_config.get("redis", dict())
    if not redis_config:
        log.info("Cannot register route: no redis config")
        return
    #
    local_hostname = socket.gethostname()
    local_port = context.settings.get("server", dict()).get("port", constants.SERVER_DEFAULT_PORT)
    #
    node_name = context.node_name
    #
    if "node_url" in traefik_config:
        node_url = traefik_config.get("node_url")
    elif "node_hostname" in traefik_config:
        node_url = f"http://{traefik_config.get('node_hostname')}:{local_port}"
    else:
        node_url = f"http://{local_hostname}:{local_port}"
    #
    log.info("Registering traefik route for node '%s'", node_name)
    #
    store = StrictRedis(
        host=redis_config.get("host", "localhost"),
        port=redis_config.get("port", 6379),
        password=redis_config.get("password", None),
        ssl=redis_config.get("use_ssl", False),
    )
    #
    traefik_rootkey = traefik_config.get("rootkey", "traefik")
    traefik_rule = traefik_config.get(
        "rule", f"PathPrefix(`{context.url_prefix if context.url_prefix else '/'}`)"
    )
    traefik_entrypoint = traefik_config.get("entrypoint", "http")
    #
    # 1: Services
    #
    store.set(f"{traefik_rootkey}/http/services/{node_name}/loadbalancer/servers/0/url", node_url)
    context.traefik_redis_keys.append(
        f"{traefik_rootkey}/http/services/{node_name}/loadbalancer/servers/0/url"
    )
    #
    # 2: Middlewares
    #
    if "forward_auth_address" in traefik_config and "forward_auth_headers" in traefik_config:
        traefik_forward_auth_address = traefik_config.get("forward_auth_address")
        traefik_forward_auth_headers = traefik_config.get("forward_auth_headers")
        #
        store.set(
            f"{traefik_rootkey}/http/middlewares/{node_name}/forwardauth/address",
            traefik_forward_auth_address,
        )
        context.traefik_redis_keys.append(
            f"{traefik_rootkey}/http/middlewares/{node_name}/forwardauth/address"
        )
        #
        store.set(
            f"{traefik_rootkey}/http/middlewares/{node_name}/forwardauth/authResponseHeaders",
            traefik_forward_auth_headers,
        )
        context.traefik_redis_keys.append(
            f"{traefik_rootkey}/http/middlewares/{node_name}/forwardauth/authResponseHeaders"
        )
    #
    # 3: Routers
    #
    store.set(f"{traefik_rootkey}/http/routers/{node_name}/entrypoints/0", traefik_entrypoint)
    context.traefik_redis_keys.append(f"{traefik_rootkey}/http/routers/{node_name}/entrypoints/0")
    #
    store.set(f"{traefik_rootkey}/http/routers/{node_name}/rule", traefik_rule)
    context.traefik_redis_keys.append(f"{traefik_rootkey}/http/routers/{node_name}/rule")
    #
    if "forward_auth_address" in traefik_config and "forward_auth_headers" in traefik_config:
        store.set(
            f"{traefik_rootkey}/http/routers/{node_name}/middlewares",
            f"{node_name}",
        )
        context.traefik_redis_keys.append(
            f"{traefik_rootkey}/http/routers/{node_name}/middlewares"
        )
    #
    store.set(f"{traefik_rootkey}/http/routers/{node_name}/service", f"{node_name}")
    context.traefik_redis_keys.append(f"{traefik_rootkey}/http/routers/{node_name}/service")

def unregister_traefik_route(context):
    """ Delete Traefik route for this Pylon instance """
    #
    if context.before_reloader:
        log.info("Running in development mode before reloader is started. Skipping unregistration")
        return
    #
    traefik_config = context.settings.get("traefik", dict())
    if not traefik_config:
        log.info("Cannot unregister route: no traefik config")
        return
    #
    redis_config = traefik_config.get("redis", dict())
    if not redis_config:
        log.info("Cannot unregister route: no redis config")
        return
    #
    log.info("Unregistering traefik route for node '%s'", context.node_name)
    #
    store = StrictRedis(
        host=redis_config.get("host", "localhost"),
        port=redis_config.get("port", 6379),
        password=redis_config.get("password", None),
        ssl=redis_config.get("use_ssl", False),
    )
    #
    while context.traefik_redis_keys:
        key = context.traefik_redis_keys.pop()
        store.delete(key)
