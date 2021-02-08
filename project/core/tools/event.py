#!/usr/bin/python
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

""" Core events """

import functools

import arbiter  # pylint: disable=E0401

from core.tools import log


class EventManager:
    """ Simple event manager """

    def __init__(self, context):
        self.context = context
        #
        events_rabbitmq = self.context.settings.get("events", dict()).get("rabbitmq", dict())
        if events_rabbitmq:
            try:
                self.node = arbiter.EventNode(
                    host=events_rabbitmq.get("host"),
                    port=events_rabbitmq.get("port", 5672),
                    user=events_rabbitmq.get("user", ""),
                    password=events_rabbitmq.get("password", ""),
                    vhost=events_rabbitmq.get("vhost", "carrier"),
                    event_queue=events_rabbitmq.get("queue", "events"),
                    hmac_key=events_rabbitmq.get("hmac_key", None),
                    hmac_digest=events_rabbitmq.get("hmac_digest", "sha512"),
                )
                self.node.start()
                self.partials = dict()
            except:  # pylint: disable=W0702
                log.exception("Cannot make EventNode instance, using local events only")
                self.node = None
        else:
            self.node = None
        #
        self.listeners = dict()

    def register_listener(self, event, listener):
        """ Register event listener """
        if self.node is not None:
            if listener not in self.partials:
                self.partials[listener] = functools.partial(listener, self.context)
            self.node.subscribe(event, self.partials[listener])
        else:
            if event not in self.listeners:
                self.listeners[event] = list()
            if listener not in self.listeners[event]:
                self.listeners[event].append(listener)

    def unregister_listener(self, event, listener):
        """ Unregister event listener """
        if self.node is not None:
            if listener not in self.partials:
                return
            self.node.unsubscribe(event, self.partials[listener])
        else:
            if event not in self.listeners:
                return
            if listener not in self.listeners[event]:
                return
            self.listeners[event].remove(listener)

    def fire_event(self, event, payload=None):
        """ Run listeners for event """
        if self.node is not None:
            self.node.emit(event, payload)
        else:
            if event not in self.listeners:
                return
            for listener in self.listeners[event]:
                try:
                    listener(self.context, event, payload)
                except:  # pylint: disable=W0702
                    log.exception("Event listener exception")
