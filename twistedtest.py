#!/usr/bin/env python
# -*- coding: utf-8 -*-

import struct
import Queue
import multiprocessing
import sys
import time

if __name__ == '__main__' and sys.platform == 'linux2':
    print 'running by epollreactor'
    from twisted.internet import epollreactor
    epollreactor.install()
from twisted.internet import reactor

from twisted.internet import protocol
from twisted.protocols.basic import Int32StringReceiver
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.internet import task


class StringTooLongError(AssertionError):

    """
    Raised when trying to send a string too long for a length prefixed
    protocol.
    """


i32proto = Int32StringReceiver


class Echo(i32proto):

    def connectionMade(self):
        self.factory.clientCount += 1

    def stringReceived(self, string):
        self.factory.recvcount += 1
        self.factory.sendcount += 1
        self.sendString(string)

    def connectionLost(self, reason):
        self.factory.clientCount -= 1


class EchoFactory(protocol.Factory):
    protocol = Echo

    def startFactory(self):
        self.recvcount, self.sendcount, self.initedTime = 0, 0, time.time()
        self.clientCount = 0
        task.LoopingCall(self.printStat).start(1.0)

    def buildProtocol(self, addr):
        return protocol.Factory.buildProtocol(self, addr)

    def printStat(self):
        print self.getStatInfo()
        self.recvcount, self.sendcount, self.initedTime = 0, 0, time.time()

    def getStatInfo(self):
        t = time.time() - self.initedTime
        return 'clients:{} recv:{} {}/s send:{} {}/s'.format(
            self.clientCount,
            self.recvcount, self.recvcount / t,
            self.sendcount, self.sendcount / t
        )


class EchoClient(i32proto):

    def connectionMade(self):
        self.recvcount, self.sendcount, self.initedTime = 0, 0, time.time()
        self.sendString("Hello, world!")

    def stringReceived(self, string):
        self.recvcount += 1
        self.sendcount += 1
        self.sendString(string)

    def getStatInfo(self):
        t = time.time() - self.initedTime
        return 'recv:{} {}/s send:{} {}/s'.format(
            self.recvcount, self.recvcount / t,
            self.sendcount, self.sendcount / t
        )


class EchoClientFactory(ReconnectingClientFactory):
    protocol = EchoClient


def makeServer():
    reactor.listenTCP(22517, EchoFactory())
    reactor.run()


def makeClients(cn):
    for i in xrange(cn):
        reactor.connectTCP('localhost', 22517, EchoClientFactory())
    reactor.run()


if __name__ == "__main__":
    if sys.argv[1] == 's':
        print 'makeserver'
        makeServer()
    else:
        print 'makeclient'
        makeClients(int(sys.argv[1]))
