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

""" MetadataProvider """

import requests  # pylint: disable=E0401

from . import MetadataProviderModel


class Provider(MetadataProviderModel):
    """ Provider model """

    def __init__(self, context, settings):
        self.context = context
        self.settings = settings
        #
        self.username = self.settings.get("username", None)
        self.password = self.settings.get("password", None)
        self.verify = self.settings.get("verify", True)

    def init(self):
        """ Initialize provider """

    def deinit(self):
        """ De-initialize provider """

    def get_metadata(self, target):
        """ Get plugin metadata """
        auth = None
        if self.username is not None and self.password is not None:
            auth = (self.username, self.password)
        #
        response = requests.get(
            target.get("source"),
            auth=auth,
            verify=self.verify,
        )
        #
        return response.json()

    def get_multiple_metadata(self, targets):
        """ Get plugins metadata """
        result = list()
        #
        for target in targets:
            result.append(self.get_metadata(target))
        #
        return result
