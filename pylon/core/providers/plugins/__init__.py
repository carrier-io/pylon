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

""" PluginsProvider """


class PluginsProviderModel:
    """ Provider model """

    # def __init__(self, context, settings):

    def init(self):
        """ Initialize provider """
        raise NotImplementedError()

    def deinit(self):
        """ De-initialize provider """
        raise NotImplementedError()

    def plugin_exists(self, name):
        """ Check if plugin exists """
        raise NotImplementedError()

    def add_plugin(self, name, path):
        """ Add new plugin from path """
        raise NotImplementedError()

    def delete_plugin(self, name):
        """ Delete existing plugin """
        raise NotImplementedError()

    def list_plugins(self, exclude=None):
        """ Get existing plugin names """
        raise NotImplementedError()

    def get_plugin_loader(self, name):
        """ Get loader for plugin """
        raise NotImplementedError()
