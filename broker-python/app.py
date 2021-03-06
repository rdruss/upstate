#!/usr/bin/python2
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#

import collections as _collections
import os as _os
import proton as _proton
import proton.handlers as _handlers
import proton.reactor as _reactor
import sys as _sys
import uuid as _uuid

_description = "An AMQP message broker for testing"

class BrokerCommand:
    def __init__(self):
        super().__init__()

        self.container = _reactor.Container(_Handler(self))
        self.container.container_id = "test-broker"

        self.quiet = False
        self.verbose = True

    def init(self):
        try:
            self.host = _os.environ["MESSAGING_SERVICE_HOST"]
        except KeyError:
            self.host = "0.0.0.0"

        try:
            self.port = _os.environ["MESSAGING_SERVICE_PORT"]
        except KeyError:
            self.port = 5672

    def main(self):
        try:
            self.init()

            self.container.run()
        except KeyboardInterrupt:
            pass

    def info(self, message, *args):
        if self.verbose:
            self.print_message(message, *args)

    def notice(self, message, *args):
        if not self.quiet:
            self.print_message(message, *args)

    def warn(self, message, *args):
        message = "Warning! {0}".format(message)
        self.print_message(message, *args)

    def print_message(self, message, *args):
        message = message[0].upper() + message[1:]
        message = message.format(*args)
        message = "BROKER: {0}".format(message)

        _sys.stderr.write("{0}\n".format(message))
        _sys.stderr.flush()

class _Queue:
    def __init__(self, command, address):
        self.command = command
        self.address = address

        self.messages = _collections.deque()
        self.consumers = _collections.deque()

        self.command.info("Created {0}", self)

    def __repr__(self):
        return "queue '{}'".format(self.address)

    def add_consumer(self, link):
        assert link.is_sender
        assert link not in self.consumers

        self.consumers.append(link)

        self.command.info("Added consumer for {0} to {1}",
                          link.connection.remote_container, self)

    def remove_consumer(self, link):
        assert link.is_sender

        try:
            self.consumers.remove(link)
        except ValueError:
            return

        self.command.info("Removed consumer for {0} from {1}",
                          link.connection.remote_container, self)

    def store_message(self, delivery, message):
        self.messages.append(message)

        self.command.notice("Stored {0} from {1} on {2}",
                            message, delivery.connection.remote_container, self)

    def forward_messages(self):
        credit = sum([x.credit for x in self.consumers])
        sent = 0

        if credit == 0:
            return

        while sent < credit:
            for consumer in self.consumers:
                if consumer.credit == 0:
                    continue

                try:
                    message = self.messages.popleft()
                except IndexError:
                    self.consumers.rotate(sent)
                    return

                consumer.send(message)
                sent += 1

                self.command.notice("Forwarded {0} on {1} to {2}",
                                    message, self, consumer.connection.remote_container)

        self.consumers.rotate(sent)

class _Handler(_handlers.MessagingHandler):
    def __init__(self, command):
        super().__init__()

        self.command = command
        self.queues = dict()
        self.verbose = False

    def on_start(self, event):
        interface = "{0}:{1}".format(self.command.host, self.command.port)

        self.acceptor = event.container.listen(interface)

        self.command.notice("Listening on '{0}'", interface)

    def get_queue(self, address):
        try:
            queue = self.queues[address]
        except KeyError:
            queue = self.queues[address] = _Queue(self.command, address)

        return queue

    def on_link_opening(self, event):
        if event.link.is_sender:
            if event.link.remote_source.dynamic:
                address = str(_uuid.uuid4())
            else:
                address = event.link.remote_source.address

            assert address is not None

            event.link.source.address = address

            queue = self.get_queue(address)
            queue.add_consumer(event.link)

        if event.link.is_receiver:
            address = event.link.remote_target.address
            event.link.target.address = address

    def on_link_closing(self, event):
        if event.link.is_sender:
            queue = self.queues[event.link.source.address]
            queue.remove_consumer(event.link)

    def on_connection_opening(self, event):
        # XXX I think this should happen automatically
        event.connection.container = event.container.container_id

    def on_connection_opened(self, event):
        self.command.notice("Opened connection from {0}",
                            event.connection.remote_container)

    def on_connection_closing(self, event):
        self.remove_consumers(event.connection)

    def on_connection_closed(self, event):
        self.command.notice("Closed connection from {0}",
                            event.connection.remote_container)

    def on_disconnected(self, event):
        self.command.notice("Disconnected from {0}",
                            event.connection.remote_container)
        self.remove_consumers(event.connection)

    def remove_consumers(self, connection):
        link = connection.link_head(_proton.Endpoint.REMOTE_ACTIVE)

        while link is not None:
            if link.is_sender:
                queue = self.queues[link.source.address]
                queue.remove_consumer(link)

            link = link.next(_proton.Endpoint.REMOTE_ACTIVE)

    def on_sendable(self, event):
        queue = self.get_queue(event.link.source.address)
        queue.forward_messages()

    def on_settled(self, event):
        pass
        # delivery = event.delivery

        # template = "{0} {{0}} {1} to {2}"
        # template = template.format(_summarize(event.connection),
        #                            _summarize(delivery),
        #                            _summarize(event.link.source))

        # if delivery.remote_state == delivery.ACCEPTED:
        #     self.command.info(template, "accepted")
        # elif delivery.remote_state == delivery.REJECTED:
        #     self.command.warn(template, "rejected")
        # elif delivery.remote_state == delivery.RELEASED:
        #     self.command.notice(template, "released")
        # elif delivery.remote_state == delivery.MODIFIED:
        #     self.command.notice(template, "modified")

    def on_message(self, event):
        message = event.message
        delivery = event.delivery
        address = event.link.target.address

        if address is None:
            address = message.address

        queue = self.get_queue(address)
        queue.store_message(delivery, message)
        queue.forward_messages()

if __name__ == "__main__":
    command = BrokerCommand()
    command.main()
