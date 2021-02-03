#!/usr/bin/python3
# coding=utf-8

#   Copyright 2020 getcarrier.io
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
        # Make Blueprint
        bp = flask.Blueprint(  # pylint: disable=C0103
            "base", "pylon_base",
            root_path=self.root_path,
            url_prefix="/",
            template_folder="templates",
            static_url_path="/",
            static_folder="static",
        )
        # Add routes
        bp.add_url_rule("/", "index", self.index)
        # Register in app
        self.context.app.register_blueprint(bp)

    def deinit(self):  # pylint: disable=R0201
        """ De-init module """
        log.info("De-initializing module")

    def index(self):  # pylint: disable=R0201
        """ Index """
        self.context.event_manager.fire_event("base.index")
        return flask.render_template("index.html")
