#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" wxgame server
게임 서버용으로 수정, wxpython code를 제거
"""
import time
import multiprocessing
import random
import socket
import select
try:
    import simplejson as json
except:
    import json
import logging
import argparse
import multiprocessing.queues
import cPickle as pickle
import struct
import Queue

from wxgame2lib import FPSMixin, ProfileMixin
from wxgame2lib import makeChannel
from wxgame2lib import getFrameTime, getSerial
from wxgame2lib import fromGzJson, toGzJsonParams, putParams2Queue


def getLogger(level=logging.DEBUG):
    logger = multiprocessing.log_to_stderr()
    logger.setLevel(level)
    return logger


Log = getLogger(level=logging.WARN)
Log.critical('current loglevel is %s',
             logging.getLevelName(Log.getEffectiveLevel()))

g_profile = False


class ServerType:
    Any = 0
    Npc = 1
    Tcp = 2
    Game = 3
    Main = 4
    RemoteNpc = 5
    Unknown = 0xfffe
    All = 0xffff


class I32ClientProtocol(object):

    headerStruct = struct.Struct('!I')
    headerLen = struct.calcsize('!I')

    def __init__(self, sock, recvcallback):
        self.recvcallback = recvcallback
        self.sendQueue = Queue.Queue()
        self.sock = sock
        self.safefileno = sock.fileno()
        self.readbuf = []  # memorybuf, toreadlen , buf state
        self.writebuf = []  # memorybuf, towritelen

    def __str__(self):
        return '[{}:{}:{}:{}]'.format(
            self.__class__.__name__,
            self.sock,
            self.readbuf,
            self.writebuf,
        )

    def setRecvCallback(self, recvcallback):
        self.recvcallback = recvcallback

    def recv(self):
        """ async recv
        recv completed packet is put to recv packet
        """
        if self.readbuf == []:  # read header
            self.readbuf = [
                memoryview(bytearray(self.headerLen)),
                self.headerLen,
                'header'
            ]

        nbytes = self.sock.recv_into(
            self.readbuf[0][-self.readbuf[1]:], self.readbuf[1])
        if nbytes == 0:
            return 'disconnected'
        self.readbuf[1] -= nbytes

        if self.readbuf[1] == 0:  # complete recv
            if self.readbuf[2] == 'header':
                bodylen = self.headerStruct.unpack(
                    self.readbuf[0].tobytes())[0]
                self.readbuf = [
                    memoryview(bytearray(bodylen)),
                    bodylen,
                    'body'
                ]
            elif self.readbuf[2] == 'body':
                self.recvcallback(self.readbuf[0].tobytes())
                self.readbuf = []
                return 'complete'
            else:
                Log.error('invalid recv state %s', self.readbuf[2])
                return 'unknown'
        return 'cont'

    def canSend(self):
        return not self.sendQueue.empty() or len(self.writebuf) != 0

    def send(self):
        if self.sendQueue.empty() and len(self.writebuf) == 0:
            return 'sleep'  # send queue empty
        if len(self.writebuf) == 0:  # send new packet
            tosenddata = self.sendQueue.get()
            headerdata = self.headerStruct.pack(len(tosenddata))
            self.writebuf = [
                [memoryview(headerdata), 0],
                [memoryview(tosenddata), 0]
            ]
        wdata = self.writebuf[0]
        sentlen = self.sock.send(wdata[0][wdata[1]:])
        if sentlen == 0:
            raise RuntimeError("socket connection broken")
        wdata[1] += sentlen
        if len(wdata[0]) == wdata[1]:  # complete send
            del self.writebuf[0]
            if len(self.writebuf) == 0:
                return 'complete'
        return 'cont'

    def fileno(self):
        return self.sock.fileno()


class BaseServer(multiprocessing.Process, FPSMixin):

    def getStatInfo(self):
        t = time.time() - self.initedTime
        return 'recv:{} {}/s send:{} {}/s'.format(
            self.recvcount, self.recvcount / t,
            self.sendcount, self.sendcount / t
        )

    def getChannel(self):
        return self.returnChannel

    def printState(self, repeatinfo):
        Log.critical('fps: %s', self.frameinfo.stat)
        Log.critical('packets: %s', self.getStatInfo())
        Log.critical('Ch stat %s', self.mainChannel.getStatInfo())

    def __init__(self, servertype, profileopt):
        multiprocessing.Process.__init__(self)
        self.returnChannel, self.mainChannel = makeChannel()
        self.serverType = servertype
        self.profileopt = profileopt
        self.maxFPS = 60

    def run(self):
        pass

    def runSelect(self):
        self.profile = ProfileMixin(self.profileopt)
        self.profile.begin()
        self.recvcount, self.sendcount, self.initedTime = 0, 0, time.time()
        self.quit = False
        self.FPSInit(time.time, self.maxFPS)
        self.registerRepeatFn(self.printState, 1)

        Log.critical('initing pid:%s', self.pid)
        self.beforeLoop()
        Log.info('serverLoop start')
        selectwait = 0
        while not self.quit:
            ril, rol, rel = self.makeSelectArg()[:3]
            ilist, olist, elist = select.select(
                ril, rol, rel, selectwait
            )
            selectwait = 0
            for i in ilist:
                if self.inputSelected(i) == 'break':
                    break
            for o in olist:
                if self.outputSelected(o) == 'break':
                    break

            if len(ilist) == 0 and len(olist) == 0 and len(elist) == 0:
                self.nothingSelected()
                selectwait = 0.1 / self.maxFPS

                if self.isFPSRunNeed():
                    self.FPSRun()  # call FPSMain
                    selectwait = self.frameinfo.remain_ms / 1000.0

        Log.info('end serverLoop')
        self.afterLoop()
        Log.info('end server')
        self.printState(0)
        self.profile.end()

    def addRecv(self, obj):
        pass
    def addSend(self, obj):
        pass
    def delRecv(self, obj):
        pass
    def delSend(self, obj):
        pass

    def runEpoll(self):
        self.profile = ProfileMixin(self.profileopt)
        self.profile.begin()
        self.recvcount, self.sendcount, self.initedTime = 0, 0, time.time()
        self.quit = False
        self.FPSInit(time.time, self.maxFPS)
        self.registerRepeatFn(self.printState, 1)

        Log.critical('initing pid:%s', self.pid)
        self.epoll = select.epoll()
        selectwait = 0
        self.beforeLoop()
        Log.info('serverLoop start')
        while not self.quit:
            events = epoll.poll(selectwait)
            for fileno, event in events:
                if event & select.EPOLLIN:
                    self.inputSelected(fileno)
                elif event & select.EPOLLOUT:
                    self.outputSelected(fileno)

            if self.isFPSRunNeed():
                self.FPSRun()  # call FPSMain
                selectwait = self.frameinfo.remain_ms / 1000.0

        Log.info('end serverLoop')
        self.afterLoop()
        Log.info('end server')
        self.printState(0)
        self.profile.end()


    # overide fns
    def beforeLoop(self):
        # init service
        pass

    def makeSelectArg(self):
        return [], [], [], 0

    def inputSelected(self, i):
        pass

    def outputSelected(self, o):
        pass

    def nothingSelected(self):
        pass

    def afterLoop(self):
        # cleanup service
        pass

    def FPSMain(self):
        return


class TCPClient(I32ClientProtocol):

    def __init__(self, connectTo, recvcallback):
        def callback(packet):
            return recvcallback(self, packet)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, True)
        sock.connect(connectTo)
        I32ClientProtocol.__init__(self, sock, callback)
        Log.info('client inited %s', self)

    def disconnect(self):
        self.sock.close()
        Log.info('disconnect %s', self)


class MultiClientSimServer(BaseServer):

    def __init__(self, servertype, profileopt, connectTo, aicount):
        BaseServer.__init__(self, servertype, profileopt)
        if connectTo[0] is None:
            self.connectTo = ('localhost', connectTo[1])
        self.aicount = aicount

    def beforeLoop(self):
        self.allInited = False
        self.clients = []
        for i in range(self.aicount):
            self.clients.append(
                TCPClient(self.connectTo, self.process1Cmd)
            )
            self.clients[-1].sendQueue.put('sayHello')
        self.sendList = []

    def makeSelectArg(self):
        self.sendList = [
            s for s in self.clients if s.canSend()]
        return self.clients, self.sendList, []

    def inputSelected(self, i):
        try:
            r = i.recv()
        except socket.error:
            self.closeClient(i)
            return
        if r == 'complete':
            self.recvcount += 1
        elif r == 'disconnected':
            self.closeClient(i)

    def outputSelected(self, o):
        try:
            if o.send() == 'complete':
                self.sendcount += 1
        except socket.error:
            self.closeClient(o)

    def afterLoop(self):
        for c in self.clients:
            c.disconnect()

    def process1Cmd(self, client, packet):
        client.sendQueue.put('sayHello')

    def closeClient(self, client):
        client.disconnect()
        try:
            self.clients.remove(client)
        except ValueError:
            pass
        if len(self.clients) == 0:
            Log.info('no more client')
            self.quit = True


class ReceptionEchoServer(BaseServer):

    def beforeLoop(self):
        # create an INET, STREAMing socket
        self.serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # reuse address
        self.serverSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.serverSocket.setsockopt(
            socket.IPPROTO_TCP, socket.TCP_NODELAY, True)
        self.serverSocket.bind(('0.0.0.0', 22517))
        # become a server socket
        self.serverSocket.listen(65535)
        self.clientDict = {}
        # wait for game is ready
        while not self.mainChannel.canReadFrom():
            time.sleep(0)
        self.mainChannel.readFrom()  # recv start packet

        self.recvList = [self.serverSocket, self.mainChannel.reader]
        self.sendList = []

    def makeSelectArg(self):
        self.sendList = [
            self.mainChannel.writer] if self.mainChannel.canSend() else []
        self.sendList += [s for s in self.recvList[2:] if s.canSend()]
        return self.recvList, self.sendList, []

    def inputSelected(self, i):
        if i == self.serverSocket:
            # handle the server socket
            sock, address = self.serverSocket.accept()
            self.addNewClient(sock, address)
        elif i == self.mainChannel.reader:
            idno, packet = self.mainChannel.readFrom()
            if idno[-1] == -1:
                self.quit = True
                return 'break'
            else:
                Log.critical('unknown client %s', idno)
        else:
            try:
                r = i.recv()
            except socket.error:
                self.closeClient(i)
            if r == 'complete':
                self.recvcount += 1
            elif r == 'disconnected':
                self.closeClient(i)

    def outputSelected(self, o):
        try:
            if o.send() == 'complete':
                self.sendcount += 1
        except socket.error:
            self.closeClient(o)

    def afterLoop(self):
        self.serverSocket.close()
        for p in self.recvList[2:]:
            self.closeClient(p)

    def addNewClient(self, sock, address):
        Log.info('client connected %s %s', sock, address)
        protocol = I32ClientProtocol(sock, None)

        def newPacketRecved(packet):
            protocol.sendQueue.put(
                packet
            )
        protocol.setRecvCallback(newPacketRecved)
        self.clientDict[(self.serverType, sock.fileno())] = protocol
        self.recvList.append(protocol)

    def closeClient(self, p):
        Log.info('client disconnected %s', p)
        try:
            self.recvList.remove(p)
        except ValueError:
            pass
        try:
            self.sendList.remove(p)
        except ValueError:
            pass

        try:
            del self.clientDict[(self.serverType, p.safefileno)]
        except KeyError:
            pass

        p.sock.close()


class ReceptionServer(BaseServer):

    def beforeLoop(self):
        # create an INET, STREAMing socket
        self.serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # reuse address
        self.serverSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.serverSocket.setsockopt(
            socket.IPPROTO_TCP, socket.TCP_NODELAY, True)
        self.serverSocket.bind(('0.0.0.0', 22517))
        # become a server socket
        self.serverSocket.listen(5)
        self.clientDict = {}
        # wait for game is ready
        while not self.mainChannel.canReadFrom():
            time.sleep(0)
        self.mainChannel.readFrom()  # recv start packet
        self.recvList = [self.serverSocket, self.mainChannel.reader]
        self.sendList = []

    def makeSelectArg(self):
        self.sendList = [
            self.mainChannel.writer] if self.mainChannel.canSend() else []
        self.sendList += [s for s in self.recvList[2:] if s.canSend()]
        return self.recvList, self.sendList, []

    def inputSelected(self, i):
        if i == self.serverSocket:
            # handle the server socket
            sock, address = self.serverSocket.accept()
            self.addNewClient(sock, address)
        elif i == self.mainChannel.reader:
            idno, packet = self.mainChannel.readFrom()
            if idno[-1] == -1:
                self.quit = True
                return 'break'
            if idno in self.clientDict:
                self.clientDict[idno].sendQueue.put(packet)
            else:
                Log.critical('unknown client %s', idno)
        else:
            try:
                r = i.recv()
            except socket.error:
                self.closeClient(i)
            if r == 'complete':
                self.recvcount += 1
            elif r == 'disconnected':
                self.closeClient(i)

    def outputSelected(self, o):
        if o == self.mainChannel.writer:
            self.mainChannel.writeFromQueue()
        else:
            try:
                if o.send() == 'complete':
                    self.sendcount += 1
            except socket.error:
                self.closeClient(o)

    def afterLoop(self):
        self.serverSocket.close()
        for p in self.recvList[2:]:
            self.closeClient(p)

    def addNewClient(self, sock, address):
        Log.info('client connected %s %s', sock, address)

        def newPacketRecved(packet):
            self.mainChannel.sendQueue.put(
                ((self.serverType, sock.fileno()), packet)
            )
        protocol = I32ClientProtocol(sock, newPacketRecved)
        self.clientDict[(self.serverType, sock.fileno())] = protocol
        self.recvList.append(protocol)

    def closeClient(self, p):
        Log.info('client disconnected %s', p)
        try:
            self.recvList.remove(p)
        except ValueError:
            pass
        try:
            self.sendList.remove(p)
        except ValueError:
            pass

        self.mainChannel.writeTo(
            ((self.serverType, p.safefileno), toGzJsonParams(cmd='del'))
        )
        try:
            del self.clientDict[(self.serverType, p.safefileno)]
        except KeyError:
            pass

        p.sock.close()


class LogicServer(BaseServer):

    def __init__(self, servertype, aicount, profileopt):
        BaseServer.__init__(self, servertype, profileopt)
        self.aicount = aicount

    def beforeLoop(self):
        self.allInited = False
        self.thistick = getFrameTime()
        self.clientDict = {}

        # wait for game is ready
        while not self.mainChannel.canReadFrom():
            time.sleep(0)
        self.mainChannel.readFrom()  # recv start packet

        for i in range(self.aicount):
            self.mainChannel.sendQueue.put(
                ((self.serverType, getSerial()),
                 toGzJsonParams(
                     cmd='sayHello',
                     teamname='AI_%08X' % random.getrandbits(32),
                     teamcolor=[random.randint(0, 255) for i in [0, 1, 2]]
                 )))

        self.recvList = [self.mainChannel.reader]
        self.sendList = []

    def makeSelectArg(self):
        self.sendList = [
            self.mainChannel.writer] if self.mainChannel.canSend() else []
        return self.recvList, self.sendList, []

    def inputSelected(self, i):
        if i == self.mainChannel.reader:
            idno, packet = self.mainChannel.readFrom()
            if idno[-1] == -1:
                self.quit = True
                return 'break'
            if packet is not None:
                self.process1Cmd(idno, packet)

    def outputSelected(self, o):
        if o == self.mainChannel.writer:
            self.mainChannel.writeFromQueue()

    def nothingSelected(self):
        pass

    def afterLoop(self):
        # cleanup service
        pass

    def FPSMain(self):
        pass

    def process1Cmd(self, idno, packet):
        # just echo
        self.mainChannel.sendQueue.put(
            (idno, packet)
        )


class HubServer(BaseServer):

    def beforeLoop(self):
        self.clients = {}  # clientid : team info
        self.r2c = {}
        self.w2c = {}
        for c in self.channels:
            self.r2c[c.reader] = c
            self.w2c[c.writer] = c
        for ch in self.channels:
            ch.writeTo(((0, 0), None))  # run server

        self.recvList = [self.mainChannel.reader] + [
            c.reader for c in self.channels]
        self.sendList = []

    def makeSelectArg(self):
        self.sendList = [o.writer for o in self.channels if o.canSend()]
        return self.recvList, self.sendList, []

    def inputSelected(self, i):
        if i == self.mainChannel.reader:
            self.quit = True
            return 'break'
        else:
            if i in self.r2c:
                clientid, packet = self.r2c[i].readFrom()
                self.do1ClientCmd(self.r2c[i], clientid, packet)
            else:
                Log.critical('invalid reader %s', i)

    def outputSelected(self, o):
        if o in self.w2c:
            self.w2c[o].writeFromQueue()
        else:
            Log.critical('invalid writer %s', o)

    def nothingSelected(self):
        pass

    def afterLoop(self):
        for ch in self.channels:
            ch.writeTo(((0, -1), None))  # quit server

    def printState(self, repeatinfo):
        BaseServer.printState(self, repeatinfo)
        Log.critical('clients %s ', len(self.clients))
        for c in self.channels:
            Log.critical('channel %s ', c.getStatInfo())

    def __init__(self, servertype, channels, profileopt):
        BaseServer.__init__(self, servertype, profileopt)
        self.channels = channels

    def do1ClientCmd(self, ch, clientid, packet):
        clientinfo = self.clients.get(clientid)
        if clientinfo is None:
            self.clients[clientid] = {}
            clientinfo = self.clients[clientid]

        # juse echo or process packet
        ch.sendQueue.put((clientid, packet))


def getArgs():
    global g_profile

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-n', '--aicount',
        type=int,
        help='server ai count'
    )
    parser.add_argument(
        '-t', '--time',
        type=int,
        help='time sec to run'
    )
    parser.add_argument(
        '-p', '--profile',
        type=bool,
        help='do profile'
    )
    args = parser.parse_args()
    aicount = args.aicount
    if aicount is None:
        aicount = 8
    timetorun = args.time
    if timetorun is None:
        timetorun = 60

    if args.profile is not None:
        g_profile = args.profile

    return aicount, timetorun


def runServer():
    aicount, timetorun = getArgs()
    Log.critical('wxgame2server starting')

    rct_process = ReceptionServer(
        servertype=ServerType.Tcp,
        profileopt=g_profile
    )
    rct_process.start()
    logic_process = LogicServer(
        aicount=aicount,
        servertype=ServerType.Npc,
        profileopt=g_profile
    )
    logic_process.start()

    game_process = HubServer(
        channels=[rct_process.getChannel(), logic_process.getChannel()],
        servertype=ServerType.Game,
        profileopt=g_profile
    )
    game_process.start()
    toGameCh = game_process.getChannel()

    remote_process = MultiClientSimServer(
        servertype=ServerType.RemoteNpc,
        profileopt=g_profile,
        aicount=aicount,
        connectTo=(None, 22517),
    )
    remote_process.start()

    time.sleep(timetorun)

    Log.critical('wxgame2server ending')
    toGameCh.writeTo(((0, -1), None))
    game_process.join(1)
    rct_process.join(1)
    logic_process.join(1)


def runServerSockets():
    aicount, timetorun = getArgs()
    Log.critical('wxgame2server starting')

    rct_process = ReceptionEchoServer(
        servertype=ServerType.Tcp,
        profileopt=g_profile
    )
    rct_process.start()
    rctCh = rct_process.getChannel()
    rctCh.writeTo(((0, 0), None))

    remote_process = MultiClientSimServer(
        servertype=ServerType.RemoteNpc,
        profileopt=g_profile,
        aicount=aicount,
        connectTo=(None, 22517),
    )
    remote_process.start()

    time.sleep(timetorun)

    Log.critical('wxgame2server ending')
    rctCh.writeTo(((0, -1), None))
    rct_process.join(1)
    remote_process.join(1)

if __name__ == "__main__":
    # runServer()
    runServerSockets()
