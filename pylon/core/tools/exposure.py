#!/usr/bin/python
# coding=utf-8
# pylint: disable=I0011

#   Copyright 2024 getcarrier.io
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
    Exposure tools
"""

import os
import io
import sys
import time
import queue
import threading
import http.server

import flask  # pylint: disable=E0401
import arbiter  # pylint: disable=E0401

from pylon.core.tools import log
from pylon.core.tools import env
from pylon.core.tools.context import Context


def expose(context):
    """ Expose this pylon over pylon network """
    if context.before_reloader:
        log.info(
            "Running in development mode before reloader is started. Skipping exposure"
        )
        return
    #
    log.info("Exposing pylon")
    #
    context.exposure = Context()
    context.exposure.id = f"pylon_{context.id}"
    context.exposure.config = context.settings.get("exposure", {})
    context.exposure.debug = context.exposure.config.get("debug", False)
    context.exposure.stop_event = threading.Event()
    context.exposure.event_node = None
    context.exposure.rpc_node = None
    context.exposure.registry = {}
    context.exposure.threads = Context()
    #
    http.server.BaseHTTPRequestHandler.version_string = lambda *args, **kwargs: "Pylon"
    #
    # Config
    #
    config = context.exposure.config
    if not config or "event_node" not in config:
        return
    #
    # EventNode
    #
    context.exposure.event_node = arbiter.make_event_node(
        config=config.get("event_node"),
    )
    context.exposure.event_node.start()
    #
    handle_config = config.get("handle", {})
    #
    if handle_config.get("enabled", False):
        context.exposure.event_node.subscribe(
            "pylon_exposed", on_pylon_exposed
        )
        #
        context.exposure.event_node.subscribe(
            "pylon_unexposed", on_pylon_unexposed
        )
        #
        for idx, url_prefix in enumerate(handle_config.get("prefixes", [])):
            while url_prefix.endswith("/"):
                url_prefix = url_prefix[:-1]
            #
            base_url = f'{url_prefix}/'
            #
            context.app.add_url_rule(
                base_url,
                endpoint=f"pylon_exposure_{context.id}_{idx}",
                view_func=on_request,
                defaults={"sub_path": ""},
                methods=[
                    "HEAD", "OPTIONS", "GET", "POST", "PUT", "PATCH", "DELETE"
                ],
            )
            #
            context.app.add_url_rule(
                f'{base_url}/<path:sub_path>',
                endpoint=f"pylon_exposure_{context.id}_{idx}_sub_path",
                view_func=on_request,
                methods=[
                    "HEAD", "OPTIONS", "GET", "POST", "PUT", "PATCH", "DELETE"
                ],
            )
            #
            # (Pre-)Register public route un auth somehow?
        #
        context.sio.pylon_add_any_handler(on_sio)
        #
        context.exposure.threads.pinger = LivenessChecker(context)
        context.exposure.threads.pinger.start()
    #
    # RpcNode
    #
    context.exposure.rpc_node = arbiter.RpcNode(
        context.exposure.event_node,
        id_prefix=f"exposure_rpc_{context.id}_",
    )
    context.exposure.rpc_node.start()
    #
    if config.get("expose", False):
        context.exposure.rpc_node.register(
            ping, name=f"{context.exposure.id}_ping"
        )
        #
        context.exposure.rpc_node.register(
            wsgi_call, name=f"{context.exposure.id}_wsgi_call"
        )
        #
        context.exposure.rpc_node.register(
            sio_call, name=f"{context.exposure.id}_sio_call"
        )
        #
        context.exposure.event_node.emit(
            "pylon_exposed",
            {
                "exposure_id": context.exposure.id,
                "url_prefix": context.url_prefix,
            },
        )
        #
        context.exposure.threads.announcer = ExposureAnnoucer(context)
        context.exposure.threads.announcer.start()
    #
    # To improve:
    # - streaming, caching and so on


def unexpose(context):
    """ Unexpose this pylon over pylon network """
    if context.before_reloader:
        log.info(
            "Running in development mode before reloader is started. Skipping unexposure"
        )
        return
    #
    log.info("Unexposing pylon")
    #
    if context.exposure.event_node is None:
        return
    #
    context.exposure.stop_event.set()
    #
    # Exposed?
    #
    config = context.exposure.config
    #
    if config.get("expose", False):
        context.exposure.threads.announcer.join(timeout=5)
        #
        context.exposure.event_node.emit(
            "pylon_unexposed",
            {
                "exposure_id": context.exposure.id,
            },
        )
        #
        context.exposure.rpc_node.unregister(
            sio_call, name=f"{context.exposure.id}_sio_call"
        )
        #
        context.exposure.rpc_node.unregister(
            wsgi_call, name=f"{context.exposure.id}_wsgi_call"
        )
        #
        context.exposure.rpc_node.unregister(
            ping, name=f"{context.exposure.id}_ping"
        )
    #
    # Handling?
    #
    handle_config = config.get("handle", {})
    #
    if handle_config.get("enabled", False):
        context.exposure.threads.pinger.join(timeout=15)
        #
        context.sio.pylon_remove_any_handler(on_sio)
        #
        context.exposure.event_node.unsubscribe(
            "pylon_unexposed", on_pylon_unexposed
        )
        #
        context.exposure.event_node.unsubscribe(
            "pylon_exposed", on_pylon_exposed
        )
    #
    context.exposure.rpc_node.stop()
    context.exposure.event_node.stop()


def on_pylon_exposed(event_name, event_payload):
    """ Event callback """
    _ = event_name
    from tools import context  # pylint: disable=E0401,C0411,C0415
    #
    exposure_id = event_payload.get("exposure_id")
    url_prefix = event_payload.get("url_prefix")
    #
    if exposure_id == context.exposure.id:
        return
    #
    context.exposure.registry[url_prefix] = exposure_id


def on_pylon_unexposed(event_name, event_payload):
    """ Event callback """
    _ = event_name
    from tools import context  # pylint: disable=E0401,C0411,C0415
    #
    exposure_id = event_payload.get("exposure_id")
    drop_url_prefixes = []
    #
    for reg_prefix, reg_id in context.exposure.registry.items():
        if reg_id == exposure_id:
            drop_url_prefixes.append(reg_prefix)
    #
    while drop_url_prefixes:
        url_prefix = drop_url_prefixes.pop()
        context.exposure.registry.pop(url_prefix, None)


def on_request(sub_path):
    """ Exposure handler """
    _ = sub_path
    from tools import context  # pylint: disable=E0401,C0411,C0415
    #
    source_uri = flask.request.full_path
    if not flask.request.query_string and source_uri.endswith("?"):
        source_uri = source_uri[:-1]
    #
    exposure_id = None
    #
    for reg_url_prefix, reg_exposure_id in sorted(
            context.exposure.registry.items(),
            key=lambda item: len(item[0]),
            reverse=True,
    ):
        if source_uri.startswith(reg_url_prefix):
            exposure_id = reg_exposure_id
            break
    #
    if context.exposure.debug:
        log.info("Target: %s", exposure_id)
    #
    if exposure_id is None:
        flask.abort(404)
    #
    wsgi_environ = flask.request.environ
    #
    if context.exposure.debug:
        log.info("WSGI env [input]: %s", wsgi_environ)
    #
    call_environ = prepare_rpc_environ(wsgi_environ)
    #
    if context.exposure.debug:
        log.info("WSGI env [prepared]: %s", call_environ)
    #
    try:
        wsgi_result = context.exposure.rpc_node.call_with_timeout(
            f"{exposure_id}_wsgi_call",
            context.exposure.config.get("wsgi_call_timeout", 86400),
            call_environ,
        )
    except queue.Empty:
        if context.exposure.debug:
            log.warning("WSGI call timeout")
        #
        flask.abort(504)
    #
    view_rv = (
        wsgi_result["body"],
        wsgi_result["status"],
        wsgi_result["headers"],
    )
    #
    return flask.make_response(view_rv)


def on_sio(event, namespace, args):
    """ SIO exposure handler """
    from tools import context  # pylint: disable=E0401,C0411,C0415
    #
    if context.exposure.debug:
        log.info("SIO: %s, %s, %s", event, namespace, args)
    #
    if event == "connect":
        rpc_environ = prepare_rpc_environ(args[1])
        #
        args = list(args)
        args[1] = rpc_environ
        args = tuple(args)
    #
    for reg_id in context.exposure.registry.values():
        try:
            context.exposure.rpc_node.call_with_timeout(
                f"{reg_id}_sio_call",
                context.exposure.config.get("sio_call_timeout", 86400),
                event, namespace, args,
            )
        except:  # pylint: disable=W0702
            if not context.is_async:
                log.exception("Failed to call SIO exposure handler, skipping")


def prepare_rpc_environ(wsgi_environ):
    """ Prepare environ for wsgi_call """
    result = dict(wsgi_environ)
    #
    drop_keys = [
        "werkzeug.socket",
        "werkzeug.request",
        "waitress.client_disconnected",
        "asgi.send",
        "asgi.receive",
        "wsgi.errors",
        "wsgi.file_wrapper",
    ]
    #
    for key in drop_keys:
        result.pop(key, None)
    #
    result["wsgi.input"] = result["wsgi.input"].read()
    #
    return result


def prepare_call_environ(wsgi_environ):
    """ Prepare environ for local wsgi_call """
    result = dict(wsgi_environ)
    #
    result["wsgi.errors"] = sys.stderr
    result["wsgi.input"] = io.BytesIO(result["wsgi.input"])
    #
    return result


def ping():
    """ Check if this pylon is alive """
    return True


def wsgi_call(environ):
    """ Call this pylon WSGI app """
    from tools import context  # pylint: disable=E0401,C0411,C0415
    #
    response = {
        "status": None,
        "headers": None,
        "body": io.BytesIO(),
    }
    #
    def start_response(status, headers):
        """ WSGI: start_response """
        response["status"] = status
        response["headers"] = headers
    #
    data = None
    #
    try:
        data = context.app.wsgi_app(
            prepare_call_environ(environ), start_response,
        )
        for item in data:
            response["body"].write(item)
    except:  # pylint: disable=W0702
        log.exception("WSGI call error")
        # May add 500 status or something like that later
    finally:
        if data is not None and hasattr(data, "close"):
            try:
                data.close()
            except:  # pylint: disable=W0702
                pass
    #
    response["body"] = response["body"].getvalue()
    return response


def sio_call(event, namespace, args):
    """ Invoke this SIO handlers """
    from tools import context  # pylint: disable=E0401,C0411,C0415
    #
    if event == "connect":
        call_environ = prepare_call_environ(args[1])
        #
        args = list(args)
        args[1] = call_environ
        args = tuple(args)
    #
    try:
        context.sio.pylon_trigger_event(event, namespace, *args)
    except:  # pylint: disable=W0702
        if not context.is_async:
            log.exception("Failed to trigger SIO exposure event")


class ExposureAnnoucer(threading.Thread):  # pylint: disable=R0903
    """ Announce about exposure periodically """

    def __init__(self, context):
        super().__init__(daemon=True)
        self.context = context
        self.interval = self.context.exposure.config.get("announce_interval", 15)
        self.last_announce = time.time()

    def run(self):
        """ Run thread """
        #
        while not self.context.exposure.stop_event.is_set():
            try:
                time.sleep(1)
                now = time.time()
                if now - self.last_announce >= self.interval:
                    self.last_announce = now
                    self.context.exposure.event_node.emit(
                        "pylon_exposed",
                        {
                            "exposure_id": self.context.exposure.id,
                            "url_prefix": self.context.url_prefix,
                        },
                    )
            except:  # pylint: disable=W0702
                log.exception("Exception in announcer thread, continuing")


class LivenessChecker(threading.Thread):  # pylint: disable=R0903
    """ Ping exposed pylons periodically """

    def __init__(self, context):
        super().__init__(daemon=True)
        self.context = context
        self.state = {}  # reg_id -> {last_ping, missed_pings}

    def run(self):  # pylint: disable=R0912
        """ Run thread """
        #
        while not self.context.exposure.stop_event.is_set():
            try:
                time.sleep(1)
                # Get currently exposed pylon IDs
                exposed_reg_ids = list(self.context.exposure.registry.values())
                state_reg_ids = list(self.state.keys())
                #
                added_ids = list(set(exposed_reg_ids).difference(state_reg_ids))
                removed_ids = list(set(state_reg_ids).difference(exposed_reg_ids))
                #
                for reg_id in added_ids:
                    self.state[reg_id] = {
                        "last_ping": time.time(),
                        "missed_pings": 0,
                    }
                #
                for reg_id in removed_ids:
                    self.state.pop(reg_id, None)
                #
                to_check = []
                now = time.time()
                #
                for reg_id, state in self.state.items():
                    if now - state["last_ping"] >= \
                            self.context.exposure.config.get("ping_interval", 15):
                        to_check.append(reg_id)
                #
                if to_check:
                    reg_id = to_check.pop(0)
                    #
                    try:
                        ping_result = self.context.exposure.rpc_node.call_with_timeout(
                            f"{reg_id}_ping",
                            self.context.exposure.config.get("ping_timeout", 5),
                        )
                        #
                        if ping_result is not True:
                            raise RuntimeError("Invalid ping result")
                    except:  # pylint: disable=W0702
                        if self.context.exposure.debug:
                            log.exception("Pylon ping failed: %s", reg_id)
                        #
                        self.state[reg_id]["last_ping"] = time.time()
                        self.state[reg_id]["missed_pings"] += 1
                        #
                        if self.state[reg_id]["missed_pings"] >= \
                                self.context.exposure.config.get("max_missed_pings", 3):
                            # Do not emit, just process locally (e.g. if this pylon network failed)
                            on_pylon_unexposed("pylon_unexposed", {"exposure_id": reg_id})
                    else:
                        if self.context.exposure.debug:
                            log.info("Pylon ping done: %s", reg_id)
                        #
                        self.state[reg_id]["last_ping"] = time.time()
                        self.state[reg_id]["missed_pings"] = 0
            except:  # pylint: disable=W0702
                log.exception("Exception in pinger thread, continuing")
