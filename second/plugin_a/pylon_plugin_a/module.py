#!/usr/bin/python3
# coding=utf-8

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

""" Module """

import flask  # pylint: disable=E0401
import jinja2  # pylint: disable=E0401

from core.tools import log  # pylint: disable=E0611,E0401
from core.tools import module  # pylint: disable=E0611,E0401


class Module(module.ModuleModel):
    """ Galloper module """

    def __init__(self, settings, root_path, context):
        self.settings = settings
        self.root_path = root_path
        self.context = context

    def init(self):
        """ Init module """
        log.info("Initializing module")
        bp = flask.Blueprint(  # pylint: disable=C0103
            "plugin_a", "pylon_plugin_a",
            root_path=self.root_path,
            url_prefix=f"{self.context.url_prefix}/plugin_a",
        )
        bp.jinja_loader = jinja2.loaders.PackageLoader("pylon_plugin_a", "templates")
        # Register in app
        self.context.app.register_blueprint(bp)
        # Register template slot callback
        self.context.slot_manager.register_callback("base", self.base_slot)
        # Register event listener
        self.context.event_manager.register_listener("base.index", self.base_event)

    def deinit(self):  # pylint: disable=R0201
        """ De-init module """
        log.info("De-initializing module")

    def base_slot(self, context, slot, payload):  # pylint: disable=R0201,W0613
        """ Base template slot """
        with context.app.app_context():
            return flask.render_template(
                "a-slot-base.html", data=self.context.rpc_manager.call.test_rpc()
            )

    def base_event(self, context, event, payload):  # pylint: disable=R0201,W0613
        """ Base event listener """
        log.info("Got event: %s", event)
