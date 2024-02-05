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
    context.exposure.registry = {}
    #
    context.app.after_request(on_after_request)
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
            )
            #
            context.app.add_url_rule(
                f'{base_url}/<path:sub_path>',
                endpoint=f"pylon_exposure_{context.id}_{idx}_sub_path",
                view_func=on_request,
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
    # And: request data + SIO, as it needs special handling
    # Later: streaming, caching and so on
    # Health: liveness checks, RPC timeouts


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
    for reg_url_prefix, reg_exposure_id in context.exposure.registry.items():
        if source_uri.startswith(reg_url_prefix):
            exposure_id = reg_exposure_id
            break
    #
    log.info("Target: %s", exposure_id)
    #
    if exposure_id is None:
        flask.abort(404)
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


def on_after_request(response):
    """ Exposure handler """
    response.headers["server"] = "Pylon"
    return response


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


def prepare_call_environ(wsgi_environ):
    """ Prepare environ for local wsgi_call """
    result = dict(wsgi_environ)
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
