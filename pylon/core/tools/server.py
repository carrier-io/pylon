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

from gevent.pywsgi import WSGIServer  # pylint: disable=E0401,C0412

from pylon.core import constants
from pylon.core.tools import log


def run_server(context):
    """ Run WSGI or Flask server """
    if not context.debug:
        log.info("Starting WSGI server")
        http_server = WSGIServer(
            (
                context.settings.get("server", dict()).get("host", constants.SERVER_DEFAULT_HOST),
                context.settings.get("server", dict()).get("port", constants.SERVER_DEFAULT_PORT)
            ),
            context.app
        )
        http_server.serve_forever()
    else:
        log.info("Starting Flask server")
        context.app.run(
            host=context.settings.get("server", dict()).get("host", constants.SERVER_DEFAULT_HOST),
            port=context.settings.get("server", dict()).get("port", constants.SERVER_DEFAULT_PORT),
            debug=context.debug, use_reloader=context.debug,
        )
