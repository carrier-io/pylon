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

""" SourceProvider """

import os

from . import SourceProviderModel


class Provider(SourceProviderModel):
    """ Provider model """

    def __init__(self, context, settings):
        self.context = context
        self.settings = settings
        #
        self.path = self.settings["path"]

    def init(self):
        """ Initialize provider """
        os.makedirs(self.path, exist_ok=True)

    def deinit(self):
        """ De-initialize provider """

    def get_source(self, target):
        """ Get plugin source """
        target_path = os.path.join(self.path, target["name"])
        #
        if not os.path.exists(target_path):
            raise RuntimeError(f"Source not found: {target}")
        #
        return target_path

    def get_multiple_source(self, targets):
        """ Get plugins source """
        result = list()
        #
        for target in targets:
            result.append(self.get_source(target))
        #
        return result
