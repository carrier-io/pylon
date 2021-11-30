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

import socketio  # pylint: disable=E0401

from gevent.pywsgi import WSGIServer  # pylint: disable=E0401,C0412
from geventwebsocket.handler import WebSocketHandler  # pylint: disable=E0401,C0412

from werkzeug.middleware.dispatcher import DispatcherMiddleware  # pylint: disable=E0401
from werkzeug.middleware.proxy_fix import ProxyFix  # pylint: disable=E0401

from pylon.core import constants
from pylon.core.tools import log


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
    if context.settings.get("server", dict()).get("proxy", False):
        context.app.wsgi_app = ProxyFix(
            context.app.wsgi_app, x_proto=1, x_host=1,
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
    if not context.debug:
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
    if not context.debug:
        log.info("Starting WSGI server")
        http_server = WSGIServer(
            (
                context.settings.get("server", dict()).get("host", constants.SERVER_DEFAULT_HOST),
                context.settings.get("server", dict()).get("port", constants.SERVER_DEFAULT_PORT)
            ),
            context.app, handler_class=WebSocketHandler,
        )
        http_server.serve_forever()
    else:
        log.info("Starting Flask server")
        context.app.run(
            host=context.settings.get("server", dict()).get("host", constants.SERVER_DEFAULT_HOST),
            port=context.settings.get("server", dict()).get("port", constants.SERVER_DEFAULT_PORT),
            debug=context.debug, use_reloader=context.debug,
        )
