#!/usr/bin/python3
# coding=utf-8

#   Copyright 2022 getcarrier.io
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

""" DB migrations """

import sqlalchemy
import sqlalchemy.pool

import alembic  # pylint: disable=E0401
import alembic.util  # pylint: disable=E0401
import alembic.config  # pylint: disable=E0401
import alembic.script  # pylint: disable=E0401
import alembic.migration  # pylint: disable=E0401
import alembic.runtime.environment  # pylint: disable=E0401

from pylon.core.tools import log  # pylint: disable=E0611,E0401


def run_db_migrations(  # pylint: disable=R0913
        module, db_url, payload=None,
        migrations_path=None, version_table=None,
        revision="head",
    ):
    """ Perform DB migrations """
    log.info(
        "Running DB migrations for %s up to revision %s",
        module.descriptor.name, revision,
    )
    #
    if migrations_path is None:
        migrations_path = f"plugins.{module.descriptor.name}:db/migrations"
    #
    if version_table is None:
        version_table = f"db_version__{module.descriptor.name}"
    #
    config = alembic.config.Config()
    script = alembic.script.ScriptDirectory(
        alembic.util.coerce_resource_to_filename(migrations_path),
        version_locations=[migrations_path],
    )
    #
    with alembic.runtime.environment.EnvironmentContext(
        config, script,
        fn=lambda rev, context: script._upgrade_revs(revision, rev),  # pylint: disable=W0212
    ) as alembic_context:
        engine = sqlalchemy.create_engine(
            db_url,
            poolclass=sqlalchemy.pool.NullPool,
        )
        with engine.connect() as connection:
            alembic_context.configure(
                target_metadata=None,
                connection=connection,
                version_table=version_table,
            )
            with alembic_context.begin_transaction():
                alembic_context.run_migrations(module=module, payload=payload)


def get_db_revision(module, db_url, version_table=None):
    """ Get current DB revision """
    #
    if version_table is None:
        version_table = f"db_version__{module.descriptor.name}"
    #
    engine = sqlalchemy.create_engine(
        db_url,
        poolclass=sqlalchemy.pool.NullPool,
    )
    with engine.connect() as connection:
        alembic_context = alembic.migration.MigrationContext.configure(
            connection,
            opts={"version_table": version_table},
        )
        #
        return alembic_context.get_current_revision()


def get_db_head(module, migrations_path=None):
    """ Get migrations head revision """
    #
    if migrations_path is None:
        migrations_path = f"plugins.{module.descriptor.name}:db/migrations"
    #
    script = alembic.script.ScriptDirectory(
        alembic.util.coerce_resource_to_filename(migrations_path),
        version_locations=[migrations_path],
    )
    #
    return script.get_current_head()
