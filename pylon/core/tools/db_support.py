#!/usr/bin/python
# coding=utf-8
# pylint: disable=I0011

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

"""
    DB support tools
"""

import time

import sqlalchemy  # pylint: disable=E0401
from sqlalchemy.orm import (  # pylint: disable=E0401
    Session,
    declarative_base,
)
from sqlalchemy.schema import CreateSchema  # pylint: disable=E0401

from pylon.core.tools import log
from pylon.core.tools.context import Context


#
# API
#


def init(context):
    """ Init DB support """
    if context.before_reloader:
        log.info(
            "Running in development mode before reloader is started. Skipping DB support init"
        )
        return
    #
    log.info("Initializing DB support")
    #
    # App DB
    #
    db_config = context.settings.get("db", {})
    #
    context.db = Context()
    context.db.url = get_db_url(db_config)
    context.db.engine = make_engine(db_config)
    context.db.make_session = make_session_fn(context.db)
    #
    # Pylon DB
    #
    pylon_db_config = context.settings.get("pylon_db", {})
    #
    context.pylon_db = Context()
    context.pylon_db.url = get_db_url(pylon_db_config)
    context.pylon_db.engine = make_engine(pylon_db_config)
    context.pylon_db.make_session = make_session_fn(context.pylon_db)
    context.pylon_db.metadata = sqlalchemy.MetaData()
    context.pylon_db.Base = declarative_base()
    #
    # App hooks
    #
    context.app.before_request(db_before_request)
    context.app.teardown_appcontext(db_teardown_appcontext)


def deinit(context):
    """ De-init DB support """
    if context.before_reloader:
        log.info(
            "Running in development mode before reloader is started. Skipping DB support de-init"
        )
        return
    #
    log.info("De-initializing DB support")
    #
    # Pylon DB
    #
    try:
        context.pylon_db.engine.dispose()
    except:  # pylint: disable=W0702
        pass
    #
    # App DB
    #
    try:
        context.db.engine.dispose()
    except:  # pylint: disable=W0702
        pass


#
# Hooks
#


def db_before_request(*args, **kwargs):
    """ Setup request DB session """
    _ = args, kwargs
    #
    create_local_session()


def db_teardown_appcontext(*args, **kwargs):
    """ Close request DB session """
    _ = args, kwargs
    #
    try:
        close_local_session()
    except:  # pylint: disable=W0702
        pass  # "Teardown functions must avoid raising exceptions."


#
# Tools
#


def get_db_url(db_config):
    """ Get URL """
    return db_config.get("engine_url", "sqlite://")


def make_engine(
        db_config,
        mute_first_failed_connections=0,
        connection_retry_interval=3.0,
        max_failed_connections=None,
        log_errors=True,
):
    """ Make Engine and try to connect """
    #
    db_engine_url = get_db_url(db_config)
    db_engine_kwargs = db_config.get("engine_kwargs", {})
    default_schema = None
    #
    if "default_schema" in db_config:
        default_schema = db_config["default_schema"]
        #
        if "execution_options" not in db_engine_kwargs:
            db_engine_kwargs["execution_options"] = {}
        #
        execution_options = db_engine_kwargs["execution_options"]
        #
        if "schema_translate_map" not in execution_options:
            execution_options["schema_translate_map"] = {}
        #
        execution_options["schema_translate_map"][None] = default_schema
    #
    engine = sqlalchemy.create_engine(
        db_engine_url, **db_engine_kwargs,
    )
    #
    failed_connections = 0
    #
    while True:
        try:
            connection = engine.connect()
            connection.close()
            #
            break
        except:  # pylint: disable=W0702
            if log_errors and \
                    failed_connections >= mute_first_failed_connections:
                #
                log.exception(
                    "Failed to create DB connection. Retrying in %s seconds",
                    connection_retry_interval,
                )
            #
            failed_connections += 1
            #
            if max_failed_connections and failed_connections > max_failed_connections:
                break
            #
            time.sleep(connection_retry_interval)
    #
    if default_schema is not None:
        with engine.connect() as connection:
            connection.execute(CreateSchema(default_schema, if_not_exists=True))
            connection.commit()
    #
    return engine


def make_session_fn(target_db):
    """ Create make_session() """
    _target_db = target_db
    #
    def _make_session(schema=..., source_schema=None):
        if schema is ...:
            target_engine = _target_db.engine
        else:
            execution_options = dict(_target_db.engine.get_execution_options())
            #
            if "schema_translate_map" not in execution_options:
                execution_options["schema_translate_map"] = {}
            #
            execution_options["schema_translate_map"][source_schema] = schema
            #
            target_engine = _target_db.engine.execution_options(
                **execution_options,
            )
        #
        return Session(
            bind=target_engine,
            expire_on_commit=False,
        )
    #
    return _make_session


def create_local_session():
    """ Create and configure session, save in local """
    from tools import context  # pylint: disable=E0401,C0411,C0415
    #
    context.local.db_session = context.db.make_session()


def close_local_session():
    """ Finalize and close local session """
    from tools import context  # pylint: disable=E0401,C0411,C0415
    #
    if "session" not in context.local.__dict__:
        return
    #
    session = context.local.db_session
    #
    if session is None:
        return
    #
    try:
        if session.is_active:
            session.commit()
        else:
            session.rollback()
    finally:
        session.close()
        #
        context.local.db_session = None


def make_module_entities(context, module_name):
    """ Make module-specific entities """
    _ = context, module_name
    result = Context()
    #
    result.metadata = sqlalchemy.MetaData()
    result.Base = declarative_base()
    #
    return result
