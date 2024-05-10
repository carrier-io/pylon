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
    Seed tools
"""

import os
import importlib

import yaml  # pylint: disable=E0401

from pylon.core.tools import log
from pylon.core.tools import env
from pylon.core.tools import config


def load_settings():
    """ Load settings from seed from env """
    settings_data = None
    settings_seed = env.get_var("CONFIG_SEED", None)
    #
    if not settings_seed or ":" not in settings_seed:
        return None
    #
    settings_seed_tag = settings_seed[:settings_seed.find(":")]
    settings_seed_data = settings_seed[len(settings_seed_tag) + 1:]
    try:
        seed = importlib.import_module(f"pylon.core.seeds.{settings_seed_tag}")
        settings_data = seed.unseed(settings_seed_data)
    except:  # pylint: disable=W0702
        log.exception("Failed to unseed settings")
    #
    if not settings_data:
        return None
    #
    try:
        settings = yaml.load(os.path.expandvars(settings_data), Loader=yaml.SafeLoader)
        settings = config.config_substitution(settings, config.vault_secrets(settings))
    except:  # pylint: disable=W0702
        log.exception("Failed to parse settings")
        return None
    #
    return settings
