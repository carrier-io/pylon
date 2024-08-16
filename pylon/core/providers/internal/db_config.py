#!/usr/bin/python3
# coding=utf-8

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

""" DBConfigProvider """

# from pylon.core.tools import log

from pylon.core.providers.config import ConfigProviderModel
from pylon.framework.db.models.plugin_config import PluginConfig


class Provider(ConfigProviderModel):
    """ DB-based internal ConfigProvider """

    def __init__(self, context, backend):
        self.context = context
        self.backend = backend

    def init(self):
        """ Initialize provider """
        self.backend.init()

    def deinit(self):
        """ De-initialize provider """
        self.backend.deinit()

    def config_data_exists(self, plugin_name, backend=False):
        """ Check if custom plugin config exists """
        if backend:
            return self.backend.config_data_exists(plugin_name)
        #
        with self.context.pylon_db.make_session() as db_session:
            config_obj = db_session.query(PluginConfig).get(plugin_name)
            #
            if config_obj is None:
                return self.backend.config_data_exists(plugin_name)
            #
            return True

    def get_config_data(self, plugin_name, backend=False):
        """ Get custom plugin config """
        if backend:
            return self.backend.get_config_data(plugin_name)
        #
        with self.context.pylon_db.make_session() as db_session:
            config_obj = db_session.query(PluginConfig).get(plugin_name)
            #
            if config_obj is None:
                return self.backend.get_config_data(plugin_name)
            #
            return config_obj.config

    def add_config_data(self, plugin_name, config, backend=False):
        """ Add custom plugin config """
        if backend:
            return self.backend.add_config_data(plugin_name, config)
        #
        with self.context.pylon_db.make_session() as db_session:
            config_obj = db_session.query(PluginConfig).get(plugin_name)
            #
            if config_obj is None:
                config_obj = PluginConfig(
                    plugin=plugin_name,
                    config=config,
                )
                #
                db_session.add(config_obj)
            else:
                config_obj.config = config
            #
            try:
                db_session.commit()
            except:  # pylint: disable=W0702
                db_session.rollback()
                raise
            #
            return None

    def delete_config_data(self, plugin_name, backend=False):
        """ Delete custom plugin config """
        if backend:
            return self.backend.delete_config_data(plugin_name)
        #
        with self.context.pylon_db.make_session() as db_session:
            config_obj = db_session.query(PluginConfig).get(plugin_name)
            #
            if config_obj is not None:
                db_session.delete(config_obj)
                #
                try:
                    db_session.commit()
                except:  # pylint: disable=W0702
                    db_session.rollback()
                    raise
            #
            return None
