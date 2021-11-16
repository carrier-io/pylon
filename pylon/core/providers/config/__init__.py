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

""" ConfigProvider """


class ConfigProviderModel:
    """ Provider model """

    # def __init__(self, context, settings):

    def init(self):
        """ Initialize provider """
        raise NotImplementedError()

    def deinit(self):
        """ De-initialize provider """
        raise NotImplementedError()

    def config_data_exists(self, plugin_name):
        """ Check if custom plugin config exists """
        raise NotImplementedError()

    def get_config_data(self, plugin_name):
        """ Get custom plugin config """
        raise NotImplementedError()

    def add_config_data(self, plugin_name, config):
        """ Add custom plugin config """
        raise NotImplementedError()

    def delete_config_data(self, plugin_name):
        """ Delete custom plugin config """
        raise NotImplementedError()
