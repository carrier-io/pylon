#!/usr/bin/python
# coding=utf-8
# pylint: disable=I0011

#   Copyright 2023 getcarrier.io
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

import os
import signal
import logging
import datetime
import urllib.parse

import socketio  # pylint: disable=E0401

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
    #
    # SIO in WSGI mode
    #
    if context.web_runtime != "uvicorn":
        context.app.wsgi_app = socketio.WSGIApp(
            context.sio, context.app.wsgi_app,
        )
        #
        if context.web_runtime == "waitress":
            context.app.wsgi_app = WaitressSocket(context.app.wsgi_app)
    #
    # Health
    #
    health_config = context.settings.get("server", {}).get("health", {})
    health_endpoints = {}
    health_filters = []
    #
    if health_config.get("healthz", False):
        log.info("Adding healthz endpoint")
        health_endpoints["/healthz"] = ok_app
        health_filters.append("GET /healthz")
    #
    if health_config.get("livez", False):
        log.info("Adding livez endpoint")
        health_endpoints["/livez"] = ok_app
        health_filters.append("GET /livez")
    #
    if health_config.get("readyz", False):
        log.info("Adding readyz endpoint")
        health_endpoints["/readyz"] = ok_app
        health_filters.append("GET /readyz")
    #
    if health_filters and not health_config.get("log", False):
        log.info("Adding logging filter")
        health_filter = log.Filter(health_filters)
        logging.getLogger("server").addFilter(health_filter)
        logging.getLogger("werkzeug").addFilter(health_filter)
        logging.getLogger("geventwebsocket.handler").addFilter(health_filter)
    #
    # Dispatcher
    #
    if context.url_prefix:
        context.app.wsgi_app = DispatcherMiddleware(
            noop_app, {
                context.url_prefix: context.app.wsgi_app,
                **health_endpoints
            },
        )
    elif health_endpoints:
        context.app.wsgi_app = DispatcherMiddleware(
            context.app.wsgi_app, health_endpoints,
        )
    #
    # Logging
    #
    if context.web_runtime in ["waitress", "hypercorn"]:
        context.app.wsgi_app = LoggingMiddleware(context.app.wsgi_app)
    #
    # Proxy
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
    #
    # ASGI
    #
    if context.web_runtime == "uvicorn":
        import asgiref.wsgi  # pylint: disable=E0401,C0412,C0415
        context.app.wsgi_app = asgiref.wsgi.WsgiToAsgi(context.app.wsgi_app)
        #
        context.app.wsgi_app = socketio.ASGIApp(
            context.sio, context.app.wsgi_app,
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


def ok_app(environ, start_response):
    """ Dummy app that always returns 200 """
    _ = environ
    #
    start_response("200 OK", [
        ("Content-type", "text/plain")
    ])
    #
    return [b"OK\n"]


class LoggingMiddleware:  # pylint: disable=R0903
    """ Log requests """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        #
        def log_and_start_response(status, headers, *args, **kwargs):
            request_uri = urllib.parse.quote(
                f'{environ.get("SCRIPT_NAME", "")}{environ.get("PATH_INFO", "")}'
            )
            if "QUERY_STRING" in environ and environ["QUERY_STRING"]:
                request_uri = f'{request_uri}?{environ["QUERY_STRING"]}'
            #
            response_size = "-"
            for key, value in headers:
                if key.lower() == "content-length":
                    response_size = str(value)
                    break
            #
            logger = logging.getLogger("server")
            logger.info(
                '%s - - [%s] "%s %s %s" %s %s',
                environ.get("REMOTE_ADDR", "-"),
                datetime.datetime.now().strftime("%d/%b/%Y %H:%M:%S"),
                environ.get("REQUEST_METHOD", "-"),
                request_uri,
                environ.get("SERVER_PROTOCOL", "-"),
                status.split(None, 1)[0],
                response_size,
            )
            #
            return start_response(status, headers, *args, **kwargs)
        #
        return self.app(environ, log_and_start_response)


class WaitressSocket:  # pylint: disable=R0903
    """ Get socket from waitress channel """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        channel = None
        #
        if "waitress.client_disconnected" in environ:
            channel = environ["waitress.client_disconnected"].__self__
        #
        if channel is not None:
            environ["werkzeug.socket"] = WaitressSocketWrapper(channel)
        #
        return self.app(environ, start_response)


class WaitressSocketWrapper:  # pylint: disable=R0903
    """ Get socket from waitress channel: wrapper """

    def __init__(self, channel):
        self.channel = channel
        self.socket = None

    def __getattr__(self, name):
        if self.socket is None:
            self.socket = self.channel.socket
            #
            self.channel.socket = None
            self.channel.del_channel()
            self.channel.cancel()
            #
            self.socket.setblocking(1)
        #
        return getattr(self.socket, name)


def create_socketio_instance(context):  # pylint: disable=R0914
    """ Create SocketIO instance """
    client_manager = None
    #
    socketio_config = context.settings.get("socketio", dict())
    socketio_rabbitmq = socketio_config.get("rabbitmq", dict())
    socketio_redis = socketio_config.get("redis", dict())
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
    if socketio_redis:
        try:
            host = socketio_redis.get("host")
            port = socketio_redis.get("port", 6379)
            password = socketio_redis.get("password", "")
            database = socketio_redis.get("database", 0)
            queue = socketio_redis.get("queue", "socketio")
            use_ssl = socketio_redis.get("use_ssl", False)
            #
            scheme = "rediss" if use_ssl else "redis"
            url = f'{scheme}://:{password}@{host}:{port}/{database}'
            client_manager = socketio.RedisManager(
                url=url, channel=queue,
            )
        except:  # pylint: disable=W0702
            log.exception("Cannot make RedisManager instance, SocketIO is in standalone mode")
    #
    if not context.debug and context.web_runtime == "gevent":
        sio = socketio.Server(
            async_mode="gevent",
            client_manager=client_manager,
            cors_allowed_origins=socketio_config.get("cors_allowed_origins", "*"),
        )
    elif context.web_runtime == "uvicorn":
        sio = socketio.AsyncServer(
            async_mode="asgi",
            client_manager=client_manager,
            cors_allowed_origins=socketio_config.get("cors_allowed_origins", "*"),
        )
    elif context.web_runtime == "hypercorn":
        sio = socketio.Server(
            allow_upgrades=False,
            async_mode="threading",
            client_manager=client_manager,
            cors_allowed_origins=socketio_config.get("cors_allowed_origins", "*"),
        )
    elif context.web_runtime == "waitress":
        sio = socketio.Server(
            allow_upgrades=True,
            async_mode="threading",
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
    # TODO: patch sio to lock emits (and also allow to use catch-all handler for exposure)
    #
    return sio


def run_server(context):
    """ Run WSGI or Flask server """
    if not context.debug and context.web_runtime == "gevent":
        log.info("Starting gevent WSGI server")
        from gevent.pywsgi import WSGIServer  # pylint: disable=E0401,C0412,C0415
        from geventwebsocket.handler import WebSocketHandler  # pylint: disable=E0401,C0412,C0415
        http_server = WSGIServer(
            (
                context.settings.get("server", dict()).get("host", constants.SERVER_DEFAULT_HOST),
                context.settings.get("server", dict()).get("port", constants.SERVER_DEFAULT_PORT)
            ),
            context.app,
            handler_class=WebSocketHandler,
        )
        http_server.serve_forever()
    elif not context.debug and context.web_runtime == "uvicorn":
        log.info("Starting Uvicorn server")
        import uvicorn  # pylint: disable=E0401,C0412,C0415
        #
        uvicorn.run(
            context.app.wsgi_app,
            host=context.settings.get("server", dict()).get("host", constants.SERVER_DEFAULT_HOST),
            port=context.settings.get("server", dict()).get("port", constants.SERVER_DEFAULT_PORT),
        )
    elif not context.debug and context.web_runtime == "hypercorn":
        log.info("Starting Hypercorn server")
        import asyncio  # pylint: disable=E0401,C0412,C0415
        import hypercorn.config  # pylint: disable=E0401,C0412,C0415
        import hypercorn.asyncio  # pylint: disable=E0401,C0412,C0415
        import hypercorn.middleware  # pylint: disable=E0401,C0412,C0415
        #
        host = context.settings.get("server", {}).get("host", constants.SERVER_DEFAULT_HOST)
        port = context.settings.get("server", {}).get("port", constants.SERVER_DEFAULT_PORT)
        #
        config = hypercorn.config.Config()
        config.bind = [f"{host}:{port}"]
        #
        app = hypercorn.middleware.AsyncioWSGIMiddleware(
            context.app,
        )
        asyncio.run(
            hypercorn.asyncio.serve(
                app,
                config,
            ),
        )
    elif not context.debug and context.web_runtime == "waitress":
        log.info("Starting Waitress server")
        import waitress  # pylint: disable=E0401,C0412,C0415
        waitress.serve(
            context.app,
            host=context.settings.get("server", dict()).get("host", constants.SERVER_DEFAULT_HOST),
            port=context.settings.get("server", dict()).get("port", constants.SERVER_DEFAULT_PORT),
            threads=context.settings.get("server", {}).get(
                "threads", constants.SERVER_DEFAULT_THREADS
            ),
            clear_untrusted_proxy_headers=False,
            ident="Pylon",
        )
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
    os.kill(os.getpid(), signal.SIGTERM)
