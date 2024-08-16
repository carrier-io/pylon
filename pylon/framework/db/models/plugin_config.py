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

""" Plugin config DB model """

from sqlalchemy import Column, Text, LargeBinary  # pylint: disable=E0401

from tools import context  # pylint: disable=E0401


class PluginConfig(context.pylon_db.Base):  # pylint: disable=C0111,R0903
    __tablename__ = "plugin_config"

    plugin = Column(Text, primary_key=True)
    config = Column(LargeBinary, unique=False, default=b"")
