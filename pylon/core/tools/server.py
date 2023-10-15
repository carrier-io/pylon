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
    Server tools
"""

import sys

import socketio  # pylint: disable=E0401

from gevent.pywsgi import WSGIServer  # pylint: disable=E0401,C0412
from geventwebsocket.handler import WebSocketHandler  # pylint: disable=E0401,C0412

from werkzeug.middleware.dispatcher import DispatcherMiddleware  # pylint: disable=E0401
from werkzeug.middleware.proxy_fix import ProxyFix  # pylint: disable=E0401

from pylon.core import constants
from pylon.core.tools import log
from pylon.core.tools import env


def add_url_prefix(context):
    """ Add global URL prefix to context """
    context.url_prefix = context.settings.get("server", dict()).get("path", "/")
    while context.url_prefix.endswith("/"):
        context.url_prefix = context.url_prefix[:-1]


def add_middlewares(context):
    """ Add needed middlewares """
    if context.url_prefix:
        context.app.wsgi_app = DispatcherMiddleware(
            noop_app, {context.url_prefix: context.app.wsgi_app},
        )
    #
    proxy_settings = context.settings.get("server", dict()).get("proxy", False)
    #
    if isinstance(proxy_settings, dict):
        context.app.wsgi_app = ProxyFix(
            context.app.wsgi_app,
            x_for=proxy_settings.get("x_for", 1),
            x_proto=proxy_settings.get("x_proto", 1),
            x_host=proxy_settings.get("x_host", 0),
            x_port=proxy_settings.get("x_port", 0),
            x_prefix=proxy_settings.get("x_prefix", 0),
        )
    elif proxy_settings:
        context.app.wsgi_app = ProxyFix(
            context.app.wsgi_app, x_for=1, x_proto=1,
        )


def noop_app(environ, start_response):
    """ Dummy app that always returns 404 """
    _ = environ
    #
    start_response("404 Not Found", [
        ("Content-type", "text/plain")
    ])
    #
    return [b"Not Found\n"]


def create_socketio_instance(context):
    """ Create SocketIO instance """
    client_manager = None
    #
    socketio_config = context.settings.get("socketio", dict())
    socketio_rabbitmq = socketio_config.get("rabbitmq", dict())
    #
    if socketio_rabbitmq:
        try:
            host = socketio_rabbitmq.get("host")
            port = socketio_rabbitmq.get("port", 5672)
            user = socketio_rabbitmq.get("user", "")
            password = socketio_rabbitmq.get("password", "")
            vhost = socketio_rabbitmq.get("vhost", "carrier")
            queue = socketio_rabbitmq.get("queue", "socketio")
            #
            url = f'ampq://{user}:{password}@{host}:{port}/{vhost}'
            client_manager = socketio.KombuManager(
                url=url, channel=queue,
            )
        except:  # pylint: disable=W0702
            log.exception("Cannot make KombuManager instance, SocketIO is in standalone mode")
    #
    if not context.debug and context.web_runtime == "gevent":
        sio = socketio.Server(
            async_mode="gevent",
            client_manager=client_manager,
            cors_allowed_origins=socketio_config.get("cors_allowed_origins", "*"),
        )
    else:
        sio = socketio.Server(
            async_mode="threading",
            client_manager=client_manager,
            cors_allowed_origins=socketio_config.get("cors_allowed_origins", "*"),
        )
    #
    context.app.wsgi_app = socketio.WSGIApp(sio, context.app.wsgi_app)
    #
    return sio


def run_server(context):
    """ Run WSGI or Flask server """
    if not context.debug and context.web_runtime == "gevent":
        log.info("Starting gevent WSGI server")
        http_server = WSGIServer(
            (
                context.settings.get("server", dict()).get("host", constants.SERVER_DEFAULT_HOST),
                context.settings.get("server", dict()).get("port", constants.SERVER_DEFAULT_PORT)
            ),
            context.app,
            handler_class=WebSocketHandler,
        )
        http_server.serve_forever()
    elif not context.debug:
        log.info("Starting Flask server")
        context.app.run(
            host=context.settings.get("server", dict()).get("host", constants.SERVER_DEFAULT_HOST),
            port=context.settings.get("server", dict()).get("port", constants.SERVER_DEFAULT_PORT),
            debug=False,
            use_reloader=False,
        )
    else:
        log.info("Starting Flask server in debug mode")
        context.app.run(
            host=context.settings.get("server", dict()).get("host", constants.SERVER_DEFAULT_HOST),
            port=context.settings.get("server", dict()).get("port", constants.SERVER_DEFAULT_PORT),
            debug=True,
            use_reloader=context.settings.get("server", dict()).get(
                "use_reloader", env.get_var("USE_RELOADER", "true").lower() in ["true", "yes"],
            ),
            reloader_type=context.settings.get("server", dict()).get(
                "reloader_type", env.get_var("RELOADER_TYPE", "auto"),
            ),
            reloader_interval=context.settings.get("server", dict()).get(
                "reloader_interval", int(env.get_var("RELOADER_INTERVAL", "1")),
            ),
        )


def restart():
    """ Stop server (will be restarted by docker/runtime) """
    log.info("Stopping server for a restart")
    sys.exit()
