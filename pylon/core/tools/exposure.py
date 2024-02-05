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

import io

import flask  # pylint: disable=E0401
import arbiter  # pylint: disable=E0401

from pylon.core.tools import log
from pylon.core.tools.context import Context


def expose():
    """ Expose this pylon over pylon network """
    log.info("Exposing pylon")
    from tools import context  # pylint: disable=E0401,C0411,C0415
    #
    context.exposure = Context()
    context.exposure.id = f"pylon_{context.id}"
    context.exposure.config = context.settings.get("exposure", {})
    context.exposure.event_node = None
    context.exposure.rpc_node = None
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
    if config.get("handle", False):
        context.exposure.event_node.subscribe(
            "pylon_exposed", on_pylon_exposed
        )
        #
        context.exposure.event_node.subscribe(
            "pylon_unexposed", on_pylon_unexposed
        )
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
        context.exposure.event_node.emit(
            "pylon_exposed",
            {
                "exposure_id": context.exposure.id,
                "url_prefix": context.url_prefix,
            },
        )
    #
    # Next: periodic announce to other pylons... and handle announces
    # And: SIO, as it needs special handling
    # Later: streaming, caching and so on


def unexpose():
    """ Unexpose this pylon over pylon network """
    log.info("Unexposing pylon")
    from tools import context  # pylint: disable=E0401,C0411,C0415
    #
    if context.exposure.event_node is None:
        return
    #
    if context.exposure.config.get("expose", False):
        context.exposure.event_node.emit(
            "pylon_unexposed",
            {
                "exposure_id": context.exposure.id,
            },
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
    context.exposure.rpc_node.stop()
    #
    if context.exposure.config.get("handle", False):
        context.exposure.event_node.unsubscribe(
            "pylon_unexposed", on_pylon_unexposed
        )
        #
        context.exposure.event_node.unsubscribe(
            "pylon_exposed", on_pylon_exposed
        )
    #
    context.exposure.event_node.stop()


def on_pylon_exposed(event_name, event_payload):
    """ Event callback """
    _ = event_name
    from tools import context  # pylint: disable=E0401,C0411,C0415
    exposure_id = event_payload.get("exposure_id")
    #
    if exposure_id == context.exposure.id:
        return
    #
    base_url = f'{event_payload.get("url_prefix")}/'
    view_func = make_view_func(exposure_id)
    #
    context.app.add_url_rule(
        base_url,
        endpoint=f"pylon_exposure_{exposure_id}",
        view_func=view_func,
        defaults={"sub_path": ""},
    )
    #
    context.app.add_url_rule(
        f'{base_url}/<path:sub_path>',
        endpoint=f"pylon_exposure_{exposure_id}_sub_path",
        view_func=view_func,
    )


def on_pylon_unexposed(event_name, event_payload):
    """ Event callback """
    _ = event_name, event_payload


def make_view_func(exposure_id):
    """ Make exposure handler """
    #
    def on_request(sub_path):
        """ Exposure handler """
        _ = sub_path
        from tools import context  # pylint: disable=E0401,C0411,C0415
        #
        log.info("Target: %s", exposure_id)
        #
        wsgi_environ = flask.request.environ
        log.info("WSGI env [input]: %s", wsgi_environ)
        #
        call_environ = prepare_rpc_environ(wsgi_environ)
        log.info("WSGI env [prepared]: %s", call_environ)
        #
        wsgi_result = context.exposure.rpc_node.call(
            f"{exposure_id}_wsgi_call", call_environ,
        )
        #
        view_rv = (
            wsgi_result["body"],
            wsgi_result["status"],
            wsgi_result["headers"],
        )
        #
        return flask.make_response(view_rv)
    #
    return on_request


def prepare_rpc_environ(wsgi_environ):
    """ Prepare environ for wsgi_call """
    result = dict(wsgi_environ)
    #
    drop_keys = [
        "wsgi.input",
        "wsgi.errors",
        "werkzeug.socket",
        "werkzeug.request",
    ]
    #
    for key in drop_keys:
        result.pop(key, None)
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
        data = context.app.wsgi_app(environ, start_response)
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
