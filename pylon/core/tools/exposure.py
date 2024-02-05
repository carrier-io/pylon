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

from pylon.core.tools import log

from tools import context  # pylint: disable=E0401,C0411


def expose():
    """ Expose this pylon over pylon network """
    log.info("Exposing pylon")
    rpc_id = f"pylon_{context.id}"
    #
    context.rpc_manager.register_function(
        ping, name=f"{rpc_id}_ping"
    )
    #
    context.rpc_manager.register_function(
        wsgi_call, name=f"{rpc_id}_wsgi_call"
    )
    #
    # Need: use separate RpcNode (use arbiter.make_event_node)
    # Next: SIO, as it needs special handling
    # Also: streaming, caching and so on
    # And: announce to other pylons... and handle announces


def unexpose():
    """ Unexpose this pylon over pylon network """
    log.info("Unexposing pylon")
    rpc_id = f"pylon_{context.id}"
    #
    context.rpc_manager.unregister_function(
        wsgi_call, name=f"{rpc_id}_wsgi_call"
    )
    #
    context.rpc_manager.unregister_function(
        ping, name=f"{rpc_id}_ping"
    )


def ping():
    """ Check if this pylon is alive """
    return True


def wsgi_call(environ):
    """ Call this pylon WSGI app """
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
