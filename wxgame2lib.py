#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" wxgame framework common lib
wxGameFramework
Copyright 2011,2013,1014 kasw <kasworld@gmail.com>
wxpython을 사용해서 게임을 만들기위한 프레임웍과 테스트용 게임 3가지
기본적인 가정은
좌표계는 0~1.0 인 정사각형 실수 좌표계
collision은 원형: 현재 프레임의 위치만을 기준으로 검출한다.
모든? action은 frame 간의 시간차에 따라 보정 된다.
문제점은 frame간에 지나가 버린 경우 이동 루트상으론 collision 이 일어나야 하지만 검출 불가.
"""
Version = '2.5.0'
import time
import math
import random
import itertools
import zlib
try:
    import simplejson as json
except:
    import json
import sys
import Queue
import select
import multiprocessing
import cProfile as Profile
import pstats
import socket
import logging
import struct

from euclid import Vector2
# ======== general lib ============


def getLogger(level=logging.DEBUG, appname='noname'):
    # create logger
    logger = logging.getLogger(appname)
    logger.setLevel(level)
    # create console handler and set level to debug
    ch = logging.StreamHandler()
    ch.setLevel(level)
    # create formatter
    #formatter = logging.Formatter("%(asctime)s:%(levelname)s: %(message)s")
    formatter = logging.Formatter("%(levelname)s: %(message)s")
    # add formatter to ch
    ch.setFormatter(formatter)
    # add ch to logger
    logger.addHandler(ch)
    return logger

Log = getLogger(level=logging.ERROR, appname='wxgame2lib')
# Log.critical('current loglevel is %s',
#              logging.getLevelName(Log.getEffectiveLevel()))

if sys.version_info < (2, 7, 0):
    Log.critical('python version 2.7.x or more need')

getSerial = itertools.count().next


def getFrameTime():
    return time.time()


def random2pi(m=2):
    return math.pi * m * (random.random() - 0.5)


def putParams2Queue(qobj, **kwds):
    qobj.put(toGzJson(kwds))


def toGzJson(obj):
    return zlib.compress(json.dumps(obj))


def toGzJsonParams(**kwds):
    return zlib.compress(json.dumps(kwds))


def fromGzJson(data):
    return json.loads(zlib.decompress(data))


class Storage(dict):

    """from gluon storage.py """
    __slots__ = ()
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__
    __getitem__ = dict.get
    __getattr__ = dict.get
    __repr__ = lambda self: '<Storage %s>' % dict.__repr__(self)
    # http://stackoverflow.com/questions/5247250/why-does-pickle-getstate-accept-as-a-return-value-the-very-instance-it-requi
    __getstate__ = lambda self: None
    __copy__ = lambda self: Storage(self)

    def getlist(self, key):
        value = self.get(key, [])
        if value is None or isinstance(value, (list, tuple)):
            return value
        else:
            return [value]

    def getfirst(self, key, default=None):
        values = self.getlist(key)
        return values[0] if values else default

    def getlast(self, key, default=None):
        values = self.getlist(key)
        return values[-1] if values else default


class Statistics(object):

    def __init__(self, timeFn=None):
        self.datadict = {
            'min': None,
            'max': None,
            'avg': None,
            'sum': 0,
            'last': None,
            'count': 0,
        }
        self.formatstr = '%(last)s(%(min)s~%(max)s), %(avg)s=%(sum)s/%(count)d'

        self.timeFn = timeFn  # FPS mode
        if self.timeFn:
            self.frames = []

    def update(self, data):
        data = float(data)
        self.datadict['count'] += 1
        self.datadict['sum'] += data

        if self.datadict['last'] is not None:
            self.datadict['min'] = min(self.datadict['min'], data)
            self.datadict['max'] = max(self.datadict['max'], data)
            self.datadict['avg'] = self.datadict[
                'sum'] / self.datadict['count']
        else:
            self.datadict['min'] = data
            self.datadict['max'] = data
            self.datadict['avg'] = data
            self.formatstr = '%(last).2f(%(min).2f~%(max).2f), %(avg).2f=%(sum).2f/%(count)d'

        self.datadict['last'] = data

        return self

    def updateFPS(self):
        if not self.timeFn:
            raise AttributeError('Statistics not inited for FPS')
        thistime = self.timeFn()
        self.frames.append(thistime)
        while(self.frames[-1] - self.frames[0] > 1):
            del self.frames[0]

        if len(self.frames) > 1:
            fps = len(self.frames) / (self.frames[-1] - self.frames[0])
        else:
            fps = 0
        self.update(fps)
        return self.frames

    def getStat(self):
        return self.datadict

    def __str__(self):
        return self.formatstr % self.datadict


class FPSMixin(object):

    """ frames per second or frame pacing system
    framepacing to maxFPS

    class workClass(FPSMixin):
        def __init__(self):
            self.FPSInit(time.time, 60)
            self.registerRepeatFn( self.calledEvery1secFn , 1)
            self.registerRepeatFn( self.calledEvery2secFn , 2)
            while True:
                self.FPSRun()
                self.FPSYield()

        def FPSMain(self): # called 60 / sec
            # your code here

        def calledEvery1secFn(self):
            pass
        def calledEvery2secFn(self):
            pass
    """

    def FPSInit(self, frameTimeFn, maxFPS):
        self.repeatingcalldict = {}
        self.frameinfo = Storage(
            stat=Statistics(timeFn=frameTimeFn),
            pause=False,
            maxFPS=maxFPS,
            frameTimeFn=frameTimeFn,
            thisFrameTime=frameTimeFn(),
            last_ms=0.1,
            lastFPS=10.0,
            remain_ms=1,
        )

    def registerRepeatFn(self, fn, dursec):
        """
            function signature
            def repeatFn(self,repeatinfo):
            repeatinfo is {
            "dursec" : dursec ,
            "oldtime" : time.time() ,
            "starttime" : time.time(),
            "repeatcount":0 }
        """
        self.repeatingcalldict[fn] = {
            "dursec": dursec,
            "oldtime": self.frameinfo.frameTimeFn(),
            "starttime": self.frameinfo.frameTimeFn(),
            "repeatcount": 0}
        return self

    def unRegisterRepeatFn(self, fn):
        return self.repeatingcalldict.pop(fn, [])

    def FPSRun(self):
        self.frameinfo.thisFrameTime = self.frameinfo.frameTimeFn()
        frames = self.frameinfo.stat.updateFPS()

        self.frameinfo.last_ms = frames[
            -1] - frames[-2] if len(frames) > 1 else 0.1
        self.frameinfo.lastFPS = 1 / self.frameinfo.last_ms

        if not self.frameinfo.pause:
            self.FPSMain()

        for fn, d in self.repeatingcalldict.iteritems():
            if self.frameinfo.thisFrameTime - d["oldtime"] > d["dursec"]:
                self.repeatingcalldict[fn][
                    "oldtime"] = self.frameinfo.thisFrameTime
                self.repeatingcalldict[fn]["repeatcount"] += 1
                fn(d)

        nexttime = (self.frameinfo.frameTimeFn()
                    - self.frameinfo.thisFrameTime) * 1000

        remain_ms = min(1000, 1000 / self.frameinfo.maxFPS - nexttime)
        # remain_ms = min(
        # 1000, max(self.frameinfo.last_ms * 800, 1000 / self.frameinfo.maxFPS)
        # - nexttime)
        if remain_ms < 1:
            remain_ms = 0
        self.frameinfo.remain_ms = remain_ms

    def isFPSRunNeed(self):
        return (self.frameinfo.frameTimeFn() - self.frameinfo.thisFrameTime) > 1.0 / self.frameinfo.maxFPS

    def FPSYield(self):
        if self.frameinfo.remain_ms > 0:
            time.sleep(self.frameinfo.remain_ms / 1000.0)

    def FPSMain(self):
        """ overide this """
        pass


class ProfileMixin(object):

    def __init__(self, profile):
        if profile:
            self.begin = self._begin
            self.end = self._end
        else:
            self.begin = self._dummy
            self.end = self._dummy

    def _dummy(self):
        pass

    def _begin(self):
        self.profile = Profile.Profile()
        self.profile.enable()

    def _end(self):
        self.profile.disable()
        pstats.Stats(self.profile).strip_dirs().sort_stats(
            'time').print_stats(20)


class SendRecvStatMixin(object):

    def __init__(self):
        self.sendstat = Statistics(timeFn=getFrameTime)
        self.recvstat = Statistics(timeFn=getFrameTime)

    def getStatInfo(self):
        return 'send:{} recv:{}'.format(
            self.sendstat, self.recvstat
        )

    def updateSendStat(self):
        self.sendstat.updateFPS()

    def updateRecvStat(self):
        self.recvstat.updateFPS()


class I32sendrecv(SendRecvStatMixin):

    """
    recv 32bit len packet to recvQueue
    send 32bit len packet from sendQueue
    """
    headerStruct = struct.Struct('!I')
    headerLen = struct.calcsize('!I')

    def __init__(self, sock):
        self.recvQueue = Queue.Queue()
        self.sendQueue = Queue.Queue()
        self.sock = sock
        self.readbuf = []  # memorybuf, toreadlen , buf state
        self.writebuf = []  # memorybuf, towritelen
        SendRecvStatMixin.__init__(self)

    def __str__(self):
        return '[{}:{}:{}:{}]'.format(
            self.__class__.__name__,
            self.sock,
            self.readbuf,
            self.writebuf,
        )

    def getStatInfo(self):
        return 'send:{}:{} | recv:{}:{}'.format(
            self.sendQueue.qsize(), self.sendstat,
            self.recvQueue.qsize(), self.recvstat
        )

    def recv(self):
        """ async recv
        recv completed packet is put to recv packet
        """
        if self.recvQueue.full():
            return 'sleep'  # recv queue full
        if self.readbuf == []:  # read header
            self.readbuf = [
                memoryview(bytearray(self.headerLen)),
                self.headerLen,
                'header'
            ]

        nbytes = self.sock.recv_into(
            self.readbuf[0][-self.readbuf[1]:], self.readbuf[1])
        if nbytes == 0:
            raise RuntimeError("socket connection broken")
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
                self.recvQueue.put(self.readbuf[0].tobytes())
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

    def sendrecv(self):
        recvlist = [self]
        sendlist = [self] if self.canSend() else []
        inputready, outputready, exceptready = select.select(
            recvlist, sendlist, [], 1.0 / 120)
        for s in inputready:
            if self.recv() == 'complete':
                self.recvstat.updateFPS()
        for s in outputready:
            if self.send() == 'complete':
                self.sendstat.updateFPS()

    def fileno(self):
        # for select
        return self.sock.fileno()


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


class ChannelPipe(object):

    def __init__(self, reader, writer):
        self.initedTime = time.time()
        self.recvcount, self.sendcount = 0, 0
        self.sendQueue = Queue.Queue()

        self.reader, self.writer = reader, writer
        self.canreadfn = self.reader.poll
        self.readfn = self.reader.recv
        self.writefn = self.writer.send

    def __str__(self):
        return '[{}:{}:{}:{}]'.format(
            self.__class__.__name__,
            self.reader,
            self.writer,
            self.getStatInfo(),
        )

    def getStatInfo(self):
        t = time.time() - self.initedTime
        return 'recv:{} {}/s send:{} {}/s'.format(
            self.recvcount, self.recvcount / t,
            self.sendcount, self.sendcount / t
        )

    def canReadFrom(self):
        return self.canreadfn()

    def readFrom(self):
        self.recvcount += 1
        return self.readfn()

    def canSend(self):
        return not self.sendQueue.empty()

    def writeFromQueue(self):
        if self.sendQueue.empty():
            return 'sleep'  # send queue empty
        self.writeTo(self.sendQueue.get())

    def writeTo(self, obj):
        self.sendcount += 1
        return self.writefn(obj)


def makeChannel():
    reader1, writer1 = multiprocessing.Pipe(duplex=False)
    reader2, writer2 = multiprocessing.Pipe(duplex=False)
    return ChannelPipe(reader1, writer2), ChannelPipe(reader2, writer1)

# ================================
# for game


def updateDict(dest, src):
    for k, v in src.iteritems():
        if isinstance(v, dict) and not isinstance(v, Storage):
            if k not in dest:
                dest[k] = {}
            updateDict(dest[k], v)
        elif isinstance(v, Vector2):
            dest[k] = v.copy()
        elif isinstance(v, list) and not isinstance(v, GameObjectGroup):
            dest[k] = v[:]
        else:
            dest[k] = v


class SpriteObj(Storage):
    validFields = {
        'ID': 0,
        "enabled": True,
        "visible": True,
        "pos": Vector2(0.5, 0.5),
        "objtype": None,
        "collisionCricle": 0.01,
        "secToLifeEnd": 10.0,
        "createdTime": 0,
        "expireFn": None,

        "movefn": None,
        "movevector": Vector2(0, 0),
        "movelimit": 1.0,
        "movefnargs": {
            "accelvector": Vector2(0, 0),
            "handstype": 0,
            "targetobj": None,
            "diffvector": Vector2(0, 0),
            "anglespeed": 0.0,
        },
        "wallactionfn": None,
        "bounceDamping": 1.,
        "weight": 1,
        "afterremovefn": None,
        "afterremovefnarg": [],

        "level": 0,
        "group": None,

        'lastAutoMoveTick': 0,
        'autoMoveFns': [],
        'fireTimeDict': {},
        'difftick': 0,
        'thistick': 0,
    }

    def __init__(self):
        """ create obj
        """
        Storage.__init__(self)

        # initailize default field, value
        # self.update(copy.deepcopy(self.validFields))
        updateDict(self, self.validFields)
        self.ID = getSerial()
        self.createdTime = getFrameTime()
        self.lastAutoMoveTick = self.createdTime

    def __str__(self):
        return '[{}:{}:{}: pos:{} mv:{}|{}]'.format(
            self.__class__.__name__,
            self.objtype,
            self.ID,
            self.pos,
            self.movevector,
            self.group
        )

    def __hash__(self):
        return self.ID

    """
    moving, bouncing sprite
    모든 move fn은 movevector를 통해서 pos를 바꾼다.
    movevector의 속도는 /sec 임.
    즉 abs(movevector) == 1 이면 1초에 화면 왼쪽끝에서 오른쪽 끝가지 가는 속도임.
    여러 개의 mvfn을 등록할수 있고 각 펑션은 mvector를 수정한다.
    그 마직막 결과를 pos에 더한다.
    movefn, move, check wall 순으로 일어남.
    """

    def initialize(self, params={}):
        updateDict(
            self,
            self.typeDefaultDict.get(params.get('objtype'), {})
        )
        updateDict(self, params)
        self.registerAutoMoveFn(self.movefn, [])
        self.registerAutoMoveFn(SpriteObj.Move_byMoveVector, [])
        self.registerAutoMoveFn(self.wallactionfn, [])
        return self

    def registerAutoMoveFn(self, fn, args=[]):
        if fn is not None:
            self.autoMoveFns.append([fn, args])
        return self

    def lento(self, target):
        return abs(target.pos - self.pos)

    def lentopos(self, targetpos):
        return abs(targetpos - self.pos)

    def lentocenter(self):
        return abs(Vector2(.5, .5) - self.pos)

    def isCollision(self, target):
        return self != target and self.lento(target) < target.collisionCricle + self.collisionCricle

    def CheckWallCollision(self, collisionRange):
        collisionWall = []
        collisionLen = {
            "Center": 0,
            "Outer": self.collisionCricle,
            "Inner": -self.collisionCricle
        }[collisionRange]
        if self.pos.x + collisionLen > 1.0:
            collisionWall.append("Right")
        elif self.pos.x - collisionLen < 0.0:
            collisionWall.append("Left")
        if self.pos.y + collisionLen > 1.0:
            collisionWall.append("Bottom")
        elif self.pos.y - collisionLen < 0.0:
            collisionWall.append("Top")
        return collisionWall

    def getAge(self, tick):
        return tick - self.createdTime

    def AutoMoveByTime(self, thistick):
        if not self.enabled:
            return
        self.difftick = (thistick - self.lastAutoMoveTick)
        if self.difftick == 0:
            return
        self.thistick = thistick
        if self.secToLifeEnd > 0 and self.createdTime + self.secToLifeEnd < thistick:
            if self.expireFn:
                self.expireFn(self)
            self.enabled = False
            return  # to old too move

        for fn, args in self.autoMoveFns:
            fn(self)
        self.lastAutoMoveTick = thistick

    def Move_byMoveVector(self):
        """실제로 pos를 변경하는 함수."""
        if abs(self.movevector) > self.movelimit:
            self.movevector = self.movevector.normalized() * self.movelimit
        self.pos += self.movevector * self.difftick

    def WallAction_Bounce(self):
        movevector = self.movevector
        rtn = self.CheckWallCollision("Outer")
        while rtn:
            if "Right" in rtn:
                self.pos = Vector2(
                    2.0 - self.collisionCricle * 2 - self.pos.x, self.pos.y)
                movevector = movevector.negX()
            elif "Left" in rtn:
                self.pos = Vector2(
                    0.0 + self.collisionCricle * 2 - self.pos.x, self.pos.y)
                movevector = movevector.negX()

            if "Bottom" in rtn:
                self.pos = Vector2(
                    self.pos.x, 2.0 - self.collisionCricle * 2 - self.pos.y)
                movevector = movevector.negY()
            elif "Top" in rtn:
                self.pos = Vector2(
                    self.pos.x, 0.0 + self.collisionCricle * 2 - self.pos.y)
                movevector = movevector.negY()
            if rtn:
                movevector *= self.bounceDamping
                movevector = movevector.addAngle(random.random() - 0.5)
                if abs(movevector) > 0.5:
                    movevector = movevector.normalized() / 0.5
                self.movevector = movevector
            rtn = self.CheckWallCollision("Outer")

    def WallAction_Remove(self):
        if self.CheckWallCollision("Inner"):
            self.enabled = False

    def WallAction_Wrap(self):
        rtn = self.CheckWallCollision("Center")
        if "Right" in rtn:
            self.pos = Vector2(0.0, self.pos.y)
        elif "Left" in rtn:
            self.pos = Vector2(1.0, self.pos.y)
        elif "Bottom" in rtn:
            self.pos = Vector2(self.pos.x, 0.0)
        elif "Top" in rtn:
            self.pos = Vector2(self.pos.x, 1.0)

    def WallAction_Wrap_Outer(self):
        rtn = self.CheckWallCollision("Outer")
        if "Right" in rtn:
            self.pos = Vector2(0.0, self.pos.y)
        elif "Left" in rtn:
            self.pos = Vector2(1.0, self.pos.y)
        elif "Bottom" in rtn:
            self.pos = Vector2(self.pos.x, 0.0)
        elif "Top" in rtn:
            self.pos = Vector2(self.pos.x, 1.0)

    def WallAction_Wrap_Inner(self):
        rtn = self.CheckWallCollision("Inner")
        if "Right" in rtn:
            self.pos = Vector2(0.0, self.pos.y)
        elif "Left" in rtn:
            self.pos = Vector2(1.0, self.pos.y)
        elif "Bottom" in rtn:
            self.pos = Vector2(self.pos.x, 0.0)
        elif "Top" in rtn:
            self.pos = Vector2(self.pos.x, 1.0)

    def WallAction_Stop(self):
        if self.CheckWallCollision("Outer"):
            self.movefn = SpriteObj.Move_NoAccel

    def WallAction_None(self):
        pass

    def Move_Sin(self):
        self.movevector = Vector2.rect(0.005, self.difftick * 10)

    def Move_NoAccel(self):
        pass

    def Move_Circle(self):
        self.movevector = (
            self.pos.rotate(Vector2(0.5, 0.5), - self.difftick * self.movefnargs["anglespeed"]
                            ) - self.pos) / self.difftick

    def Move_Vector(self):
        self.movevector += self.movefnargs["accelvector"]

    def Move_SyncTarget(self):
        if self.movefnargs["targetobj"] is None:
            return
        self.enabled = self.movefnargs["targetobj"].enabled
        if not self.enabled:
            return

        self.movefnargs["diffvector"] = self.movefnargs["diffvector"].rotate(
            Vector2(0, 0), self.movefnargs["anglespeed"] * self.difftick)
        self.movevector = (self.movefnargs[
                           "targetobj"].pos - self.pos + self.movefnargs["diffvector"]) / self.difftick

    def Move_FollowTarget(self):
        if self.movefnargs["targetobj"] is None:
            return
        self.enabled = self.movefnargs["targetobj"].enabled
        if not self.enabled:
            return
        self.accelToPos(self.movefnargs["targetobj"].pos)
        mvlen = abs(self.movevector)
        self.movevector += self.movefnargs["accelvector"] * self.difftick
        self.movevector = self.movevector.normalized() * mvlen

    def bounceToObj(self, target):
        self.movevector = Vector2.rect(
            abs(self.movevector) * self.bounceDamping,
            (self.movevector.normalized() * self.collisionCricle +
                (self.pos - target.pos).normalized() * target.collisionCricle).phase())
        return self

    def accelToPos(self, pos):
        self.movefnargs["accelvector"] = Vector2.rect(abs(
            self.movefnargs["accelvector"]), (pos - self.pos).phase())

    def setAccelVector(self, vt):
        self.movefnargs["accelvector"] = vt
        return self

    def clearAccelVector(self):
        self.movefnargs["accelvector"] = Vector2(0, 0)
        return self

    def getAccelVector(self):
        return self.movefnargs["accelvector"]

    """
    obj type, level, groupingingo
    check collsion and scrore object
    """

    def getDelScore(self, factor=1):
        " 피격 타격시 점수 계산 로직 "
        " (1-math.sqrt(2)/2) ~ 1.0 사이의 값 * factor 를 리턴, 중앙으로 갈수록 점수가 작다. "
        # return (self.lentopos(Vector2(0.5,0.5))  + (1-math.sqrt(2)/2))*factor
        # return math.sqrt(1.0/(1-self.lentocenter()) -1)*factor
        return (self.lentocenter() + 0.5) * factor
        # return factor

    def checkCollisionAppend(self, target, rtnobjs):
        """
        두 object간에 collision(interaction) 하고
        objtype이 collisionTarget에 속하면
        rtnobjs에 append 한다.
        """
        if self.isCollision(target):
            if target.objtype in self.collisionTarget:
                rtnobjs.setdefault(self, set()).add(target)
            if self.objtype in target.collisionTarget:
                rtnobjs.setdefault(target, set()).add(self)

    typeDefaultDict = {
        "circularbullet": {
            "objtype": 'circularbullet',
            'secToLifeEnd': 10.0,
            'movelimit': 0.4,
            'collisionCricle': 0.004,
            'collisionTarget': ['bounceball', 'shield', 'supershield', 'bullet', 'circularbullet', 'superbullet', 'hommingbullet'],
            'movefnargs': {"accelvector": Vector2(0, 0)},
            'movefn': Move_Vector,
            'wallactionfn': WallAction_Remove,
            'shapefnargs': {'animationfps': 30},
        },
        "superbullet": {
            "objtype": 'superbullet',
            'secToLifeEnd': 10.0,
            'movelimit': 0.6,
            'collisionCricle': 0.032,
            'collisionTarget': ['supershield', 'superbullet', 'hommingbullet'],
            'movefnargs': {"accelvector": Vector2(0, 0)},
            'movefn': Move_Vector,
            'wallactionfn': WallAction_Remove,
            'shapefnargs': {'animationfps': 30},
        },
        "hommingbullet": {
            "objtype": 'hommingbullet',
            'secToLifeEnd': 10.0,
            'movelimit': 0.3,
            'collisionCricle': 0.016,
            'collisionTarget': ['supershield', 'superbullet', 'hommingbullet'],
            'movefn': Move_FollowTarget,
            'movefnargs': {"accelvector": Vector2(0.0, 0.0)},
            'wallactionfn': WallAction_None,
            'shapefnargs': {'animationfps': 30},
        },
        "bullet": {
            "objtype": 'bullet',
            'secToLifeEnd': 10.0,
            'movelimit': 0.5,
            'collisionCricle': 0.008,
            'collisionTarget': ['bounceball', 'shield', 'supershield', 'bullet', 'circularbullet', 'superbullet', 'hommingbullet'],
            'movefnargs': {"accelvector": Vector2(0, 0)},
            'movefn': Move_Vector,
            'wallactionfn': WallAction_Remove,
            'shapefnargs': {'animationfps': 30},
        },
        "bounceball": {
            "objtype": 'bounceball',
            'secToLifeEnd': -1.0,
            'movelimit': 0.3,
            'collisionCricle': 0.016,
            'collisionTarget': ['bounceball', 'shield', 'supershield', 'bullet', 'circularbullet', 'superbullet', 'hommingbullet'],
            'bounceDamping': 1.0,
            "level": 1,
            'pos': Vector2(0.5, 0.5),
            'movevector': Vector2(0, 0),
            'movefn': Move_Vector,
            'wallactionfn': WallAction_Bounce,
            'movefnargs': {"accelvector": Vector2(0, 0)},
            'fireTimeDict': {},
            'shapefnargs': {'animationfps': 30},
        },
        "shield": {
            "objtype": 'shield',
            'secToLifeEnd': -1.0,
            'collisionCricle': 0.008,
            'collisionTarget': ['bounceball', 'shield', 'supershield', 'bullet', 'circularbullet', 'superbullet', 'hommingbullet'],
            'movefn': Move_SyncTarget,
            'wallactionfn': WallAction_None,
            'shapefnargs': {'animationfps': 30},
        },
        "supershield": {
            "objtype": 'supershield',
            'secToLifeEnd': 10.0,
            'collisionCricle': 0.011,
            'collisionTarget': ['bounceball', 'shield', 'supershield', 'bullet', 'circularbullet', 'superbullet', 'hommingbullet'],
            'movefn': Move_SyncTarget,
            'wallactionfn': WallAction_None,
            'shapefnargs': {'animationfps': 30},
        },
        "spriteexplosioneffect": {
            "objtype": 'spriteexplosioneffect',
            'secToLifeEnd': .25,
            'collisionCricle': 0,
            'collisionTarget': [],
            'movefn': Move_Vector,
            'wallactionfn': WallAction_Remove,
            'movefnargs': {"accelvector": Vector2(0, 0)},
            'shapefnargs': {'animationfps': 30},
        },
        "ballexplosioneffect": {
            "objtype": 'ballexplosioneffect',
            'secToLifeEnd': 0.5,
            'collisionCricle': 0,
            'collisionTarget': [],
            'movefn': Move_Vector,
            'wallactionfn': WallAction_Remove,
            'movefnargs': {"accelvector": Vector2(0, 0)},
            'shapefnargs': {'animationfps': 30},
        },
        "spawneffect": {
            "objtype": 'spawneffect',
            'secToLifeEnd': 0.5,
            'collisionCricle': 0,
            'collisionTarget': [],
            'movevector': Vector2(0, 0),
            'movefn': Move_Vector,
            'wallactionfn': WallAction_Remove,
            'movefnargs': {"accelvector": Vector2(0, 0)},
            'shapefnargs': {'animationfps': 30},
        },
        "cloud": {
            "objtype": 'cloud',
            'movelimit': 0.2,
            'secToLifeEnd': -1.0,
            'collisionCricle': 0.05,
            'collisionTarget': [],
            'movevector': Vector2(0, 0),
            'movefn': Move_Vector,
            'wallactionfn': WallAction_Wrap_Inner,
            'movefnargs': {"accelvector": Vector2(1, 0)},
            'shapefnargs': {'animationfps': 0},
        },
        "background": {
            "objtype": 'background',
            'pos': Vector2(500, 500),
            'secToLifeEnd': -1.0,
            'collisionCricle': 0,
            'collisionTarget': [],
            'movelimit': 100,
            'movefnargs': {"accelvector": Vector2(1, 0)},
            'wallactionfn': WallAction_None,
            'movefn': Move_Vector,
            'shapefnargs': {'animationfps': 0},
        },
    }


class GameObjectGroup(list):

    """
    moving, interacting, displaying object 의 group
    collision check 의 단위가 된다.
    (inter, in)
    object type: bullet, superbullet, bounceball, None

    독립 버전과 달리 member count는 1만 지원, 이외는 에러임.
    """

    def __str__(self):
        return '[{}:{}:{}:{}:{}]'.format(
            self.__class__.__name__,
            self.teamname,
            self.ID,
            self.teamcolor,
            len(self)
        )

    def serialize(self):
        rtn = {
            'ID': self.ID,
            'teamname': self.teamname,
            'teamcolor': self.teamcolor,
            'objs': []
        }
        for o in self:
            rtn['objs'].append(
                (o.ID, o.objtype, (o.pos.x, o.pos.y),
                 (o.movevector.x, o.movevector.y))
            )
        return rtn

    def setAttrs(self, defaultdict, kwds):
        for k, v in defaultdict.iteritems():
            setattr(self, k, kwds.pop(k, v))

    def initStat(self):
        statdict = {
            'total': 0,
            'bounceball': 0,
            'shield': 0,
            'supershield': 0,
            'bullet': 0,
            'circularbullet': 0,
            'superbullet': 0,
            'hommingbullet': 0,
            'accel': 0,
            "doNothing": 0,
        }
        self.statistic = {
            'act': dict(statdict),

            "teamStartTime": getFrameTime(),
            "teamscore": 0,
        }

    # 표준 interface들 .
    def initialize(self, *args, **kwds):
        defaultdict = {
            "enableshield": True,
            "actratedict": {
                "circularbullet": 1.0 / 30 * 1,
                "superbullet": 1.0 / 10 * 1,
                "hommingbullet": 1.0 / 10 * 1,
                "bullet": 1.0 * 2,
                "accel": 1.0 * 30
            },
            "effectObjs": [],

            "teamname": None,
            "teamcolor": None,
            "servermove": True,
            'gameObj': None,
            'spriteClass': None
        }
        self.setAttrs(defaultdict, kwds)

        if self.gameObj is None:
            Log.warn('gameObj: %s', self.gameObj)
        if self.spriteClass is None:
            Log.warn('spriteClass: %s', self.spriteClass)

        self.ID = getSerial()
        self.initStat()
        return self

    def hasBounceBall(self):
        return len(self) > 1 and self[0].objtype == "bounceball"

    def findObjByID(self, ID):
        for o in self:
            if o.ID == ID:
                return o
        return None

    def makeMember(self):
        if not self.hasBounceBall():
            self.addMember(Vector2(random.random(), random.random()))

    def addMember(self, newpos):
        self.statistic['act']['bounceball'] += 1
        self.statistic['act']['total'] += 1
        target = self.AddBouncBall(newpos)
        # if self.enableshield:
        self.statistic['act']['shield'] += 1
        for i, a in enumerate(range(0, 360, 30)):
            self.AddShield(
                target=target,
                startangle=a,
                anglespeed=math.pi if i % 2 == 0 else -math.pi
            )
        return target

    # 이후는 SpriteObj를 편하게 생성하기위한 factory functions
    def AddBouncBall(self, newpos):
        o = self.spriteClass().initialize(dict(
            objtype='bounceball',
            pos=newpos,
            group=self,
        ))
        self.insert(0, o)
        return o

    def AddShield(self, target, startangle, anglespeed):
        diffvector = Vector2(0.03, 0).addAngle(
            2 * math.pi * startangle / 360.0)
        o = self.spriteClass().initialize(dict(
            pos=target.pos + diffvector,
            movefnargs={
                "targetobj": target,
                "anglespeed": anglespeed,
                'diffvector': diffvector,
            },
            objtype="shield",
            group=self,
        ))
        self.append(o)
        return self

    def AddSuperShield(self, target, expireFn):
        diffvector = Vector2(0.06, 0).addAngle(random2pi())
        o = self.spriteClass().initialize(dict(
            expireFn=expireFn,
            pos=target.pos + diffvector,
            movefnargs={
                "targetobj": target,
                "diffvector": diffvector,
                "anglespeed": random2pi()
            },
            objtype="supershield",
            group=self,
        ))
        self.append(o)
        return self

    def AddCircularBullet2(self, centerpos):
        for a in range(0, 360, 5):
            o = self.spriteClass().initialize(dict(
                pos=centerpos + Vector2.rect(0.03, math.radians(a)),
                movevector=Vector2.rect(1, math.radians(a)),
                objtype="circularbullet",
                group=self,
            ))
            self.append(o)
        return self

    def AddTargetFiredBullet(self, startpos, tagetpos):
        o = self.spriteClass().initialize(dict(
            pos=startpos,
            movevector=Vector2.rect(1, (tagetpos - startpos).phase()),
            objtype="bullet",
            group=self,
        ))
        self.append(o)
        return self

    def AddHommingBullet(self, startpos, target, expireFn=None):
        o = self.spriteClass().initialize(dict(
            expireFn=expireFn,
            pos=startpos,
            movevector=Vector2.rect(1, Vector2.phase(target.pos - startpos)),
            movefnargs={
                "accelvector": Vector2(0.5, 0.5),
                "targetobj": target
            },
            objtype="hommingbullet",
            group=self,
        ))
        self.append(o)
        return self

    def AddTargetSuperBullet(self, startpos, tagetpos):
        o = self.spriteClass().initialize(dict(
            pos=startpos,
            movevector=Vector2.rect(1, Vector2.phase(tagetpos - startpos)),
            objtype="superbullet",
            group=self,
        ))
        self.append(o)
        return self

    def addSpriteExplosionEffect(self, src):
        self.append(
            self.spriteClass().initialize(dict(
                pos=src.pos,
                movevector=src.movevector / 4,
                afterremovefn=None,
                afterremovefnarg=(),
                objtype="spriteexplosioneffect"
            )))

    def addBallExplosionEffect(self, effectObjs, g1, b):
        self.append(
            self.spriteClass().initialize(dict(
                pos=b.pos,
                movevector=b.movevector / 4,
                afterremovefn=self.addSpawnEffect,
                afterremovefnarg=(effectObjs, g1),
                objtype="ballexplosioneffect"
            )))

    def addSpawnEffect(self, effectObjs, g1):
        newpos = Vector2(random.random(), random.random())
        self.append(
            self.spriteClass().initialize(dict(
                pos=newpos,
                afterremovefn=g1.addMember,
                afterremovefnarg=(newpos,),
                objtype="spawneffect"
            )))

    # game logics

    def RemoveDisabled(self):
        rmlist = [a for a in self if not a.enabled]
        for a in rmlist:
            self.remove(a)
            if a.afterremovefn:
                a.afterremovefn(*a.afterremovefnarg)
        return self

    def makeCollisionBucket(self, objtypes, xunit=0.05, yunit=0.05):
        """
        return { (x,y): [], ... }
        """
        def getBucketPos(o):
            assert xunit > o.collisionCricle, yunit > o.collisionCricle
            return set((
                (int((o.pos.x + o.collisionCricle) / xunit), int(
                    (o.pos.y + o.collisionCricle) / yunit)),
                (int((o.pos.x - o.collisionCricle) / xunit), int(
                    (o.pos.y + o.collisionCricle) / yunit)),
                (int((o.pos.x + o.collisionCricle) / xunit), int(
                    (o.pos.y - o.collisionCricle) / yunit)),
                (int((o.pos.x - o.collisionCricle) / xunit), int(
                    (o.pos.y - o.collisionCricle) / yunit))
            ))
        bucketlist = {}
        for o in self:
            if o.objtype not in objtypes:
                continue
            buk = getBucketPos(o)
            for b in buk:
                bucketlist.setdefault(b, []).append(o)
        return bucketlist

    # AI start funcion
    # call
    # prepareActions
    # SelectAction from AI or get actions from client
    # applyActions
    # AutoMoveByTime
    def prepareActions(self, enemyTeamList, thisFPS, thistick):
        self.thistick = thistick
        self.tdur = self.thistick - self.statistic["teamStartTime"]
        self.thisFPS = thisFPS

        # 최대 사용 가능 action 제한
        self.usableBulletCountDict = {}
        for act in ["circularbullet", "superbullet", "hommingbullet", "bullet", "accel"]:
            self.usableBulletCountDict[act] = self.tdur * self.actRatePerSec(
                act) - self.statistic['act'][act]

        if self.hasBounceBall():
            self[0].clearAccelVector()

    def applyActions(self, actions):
        # don't change pos , movevector
        # fire and change accelvector
        if actions is None:
            return
        if not self.hasBounceBall():
            Log.debug('No bounceBall')
            return
        src = self[0]
        for act, actargs in actions:
            if self.usableBulletCountDict.get(act, 0) > 0:
                self.statistic['act'][act] += 1
                if not actargs and act in ["superbullet", "hommingbullet", "bullet", "accel"]:
                    Log.debug("no target %s %s %s", act, src, actargs)
                    pass
                elif act == "circularbullet":
                    self.AddCircularBullet2(src.pos)
                elif act == "superbullet":
                    self.AddTargetSuperBullet(src.pos, actargs)
                elif act == "hommingbullet":
                    self.AddHommingBullet(
                        src.pos,
                        actargs,
                        expireFn=self.effectObjs.addSpriteExplosionEffect
                    )
                elif act == "bullet":
                    self.AddTargetFiredBullet(src.pos, actargs)
                elif act == "accel":
                    src.setAccelVector(actargs)
                else:
                    Log.warn('unknown act %s', act)
                src.fireTimeDict[act] = self.thistick
            else:
                if act != 'doNothing':
                    Log.debug("%s action %s overuse fail", self.teamname, act)
                    pass

    def AutoMoveByTime(self, thistick):
        # change movevector , pos
        for a in self:
            a.AutoMoveByTime(thistick)
        return self

    # AI utility functions
    def actRatePerSec(self, act):
        return self.actratedict.get(act, 0)

    def getObjectByTypes(self, filterlist):
        return [a for a in self if a.objtype in filterlist]

    # advanced AI util functions
    def getAimPos(self, srcpos, s1, target):
        # estimate target pos by target speed
        s2 = abs(target.movevector)
        if s2 == 0:
            return target.pos
        vt = target.pos - srcpos
        try:
            a2 = target.movevector.phase() - vt.phase()
            a1 = math.asin(s2 / s1 * math.sin(a2))
        except:
            a1 = 0
        dirvect = vt.addAngle(a1).normalized()
        return srcpos + dirvect

    def getFireTarget(self, src, act, target, lslist):
        # return target else None
        # lslist list of (len, sec)
        if not target or not src or act not in ["hommingbullet", "superbullet", "bullet"]:
            return None
        tlen = src.lento(target)
        fsec = self.thistick - src.fireTimeDict.get(act, 0)
        for l, s in lslist:
            if tlen < l and fsec > s:
                return target
        return None

    def selectByLenRate(self, lento, oldtime, datalist):
        # data list: ((max len, min sec, select object ), ...)
        fsec = self.thistick - oldtime  # src.fireTimeDict.get(act, 0)
        for l, s, o in datalist:
            if lento < l and fsec > s:
                return o
        return None

    # 실제 각 AI 별로 다르게 만들어야 하는 함수
    def SelectAction(self, enemyTeamList, src):
        """
        returns
        [ (action, acttionargs), ... ]
        """
        return [
            #("accel",Vector2.rect(random.random()/14.0,random2pi())),
            #("superbullet",Vector2(.5,.5)),
            #("bullet",Vector2(.5,.5)),
        ]

    def mapPro2Act(self, actionprobabilitylist, applyactcount=False):
        rtn = []
        for act, p, obj in actionprobabilitylist:
            if applyactcount:
                cando = random.random() < p * \
                    self.usableBulletCountDict.get(act, 0)
            else:
                cando = self.usableBulletCountDict.get(
                    act, 0) > 0 and random.random() < p
            if cando:
                if act in ["hommingbullet", "superbullet", "bullet", "accel"] and not obj:
                    continue
                rtn.append([act, obj])
        return rtn


class AI1(GameObjectGroup):

    def SelectAction(self, enemyTeamList, src):
        randomtarget = self.gameObj.selectRandomBall(enemyTeamList)
        #randomtargetlen = randomtarget.lento(src) if randomtarget else 1

        supertargetpos = randomtarget.pos if randomtarget else None
        bullettargetpos = randomtarget.pos if randomtarget else None

        accelvector = Vector2.rect(.2, random2pi())
        accelvector = self.selectByLenRate(
            1, src.fireTimeDict.get('accel', 0),
            ((2, .4, accelvector),)
        )

        fps = self.thisFPS
        actions = (
            # action, probability, object
            ("circularbullet", self.actRatePerSec(
                "circularbullet") / fps, None),
            ("hommingbullet", self.actRatePerSec(
                "hommingbullet") / fps, randomtarget),
            ("superbullet", self.actRatePerSec(
                "superbullet") / fps, supertargetpos),
            ("bullet", self.actRatePerSec("bullet") / fps, bullettargetpos),
            ("accel", self.actRatePerSec("accel") / fps, accelvector),
        )

        return self.mapPro2Act(actions, True)


class AI2(GameObjectGroup):

    def SelectAction(self, enemyTeamList, src):
        fps = self.thisFPS

        # calc fire target
        neartarget, nearlen = self.gameObj.findTarget(
            src,
            ['bounceball'],
            src.lento,
            enemyTeamList
        )
        randomtarget = self.gameObj.selectRandomBall(enemyTeamList)

        hommingtarget = self.getFireTarget(
            src, "hommingbullet", neartarget, ((0.5, 0.1),))
        supertarget = self.getFireTarget(
            src, "superbullet", neartarget, ((0.3, 0.1),))
        supertargetpos = self.getAimPos(
            src.pos,
            self.spriteClass.typeDefaultDict['superbullet']['movelimit'],
            supertarget
        ) if supertarget else None

        bullettarget = self.selectByLenRate(
            nearlen, src.fireTimeDict.get("bullet", 0),
            (
                (0.3, 1 / self.actRatePerSec("bullet") / 4, neartarget),
                (2, 1 / self.actRatePerSec("bullet") / 1.5, randomtarget),
            )
        )
        bullettargetpos = self.getAimPos(
            src.pos,
            self.spriteClass.typeDefaultDict['bullet']['movelimit'],
            bullettarget
        ) if bullettarget else None

        # find evasion action
        # 가장 단시간내에 나와 충돌할 target을 찾아야 한다. 어떻게?
        # 현재 거리 - 다음 프레임거리  클수록 : 즉 서로 접근중.
        # 현재 거리가 작을수록 (충돌 크기를 추가해야 함.)
        def getDangerLevel(x):
            curlen = abs(src.pos - x.pos)
            nextlen = abs(src.pos + src.movevector / fps - (
                x.pos + x.movevector / fps))
            relSpeed = curlen - nextlen
            if relSpeed > 0:
                return curlen - src.collisionCricle - x.collisionCricle
            else:
                return 2
        dangertarget, dangerlen = self.gameObj.findTarget(
            src,
            ['bounceball', 'superbullet', 'hommingbullet',
                'bullet', "circularbullet"],
            getDangerLevel,
            enemyTeamList
        )
        # 찾은 위험 object로 부터 회피한다.
        # target to src vector 의 방향으로 이동한다. (즉 뒤로 이동.)
        if dangertarget:
            mvvt = (src.pos - dangertarget.pos).normalized() * abs(
                src.collisionCricle + dangertarget.collisionCricle) * 2
            dangle = random2pi(1)  # 뒤로 이동시 random angle을 추가 한다.

            if src.pos.lentocenter() > 0.5 and \
                    (src.pos + mvvt.addAngle(dangle)).lentocenter() > (src.pos + mvvt.addAngle(-dangle)).lentocenter():  # 중앙쪽 으로 이동
                dangle = - dangle
            mvvt = mvvt.addAngle(dangle)
            acvt = mvvt - src.movevector / fps
            dangerrange = src.collisionCricle * 10 + abs(src.movevector / fps)
            accelvector = self.selectByLenRate(
                dangerlen, src.fireTimeDict.get('accel', 0),
                ((dangerrange, 0.0, acvt), (
                    2, 1.0, Vector2.rect(.2, random2pi())))
            )
        else:
            accelvector = None

        # make action and args
        actions = (
            # action, probability, object
            ("circularbullet", self.actRatePerSec(
                "circularbullet") / fps / src.getAge(self.thistick) / 2, None),
            ("circularbullet", self.actRatePerSec(
                "circularbullet") / fps / src.lentopos(Vector2(0.5, 0.5)) / 2, None),
            ("hommingbullet", self.actRatePerSec(
                "hommingbullet") / fps / nearlen / 2, hommingtarget),
            ("superbullet", self.actRatePerSec(
                "superbullet") / fps / nearlen / 2, supertargetpos),
            ("bullet", self.actRatePerSec("bullet") / fps, bullettargetpos),
            ("accel", 1, accelvector),
            #("accel"         , self.actRatePerSec("accel")/fps         , accelvector),
        )
        return self.mapPro2Act(actions, True)


class ShootingGameMixin(object):

    def getTeamByID(self, ID):
        return self.getTeamByIDfromList(self.dispgroup['objplayers'], ID)

    def getTeamByIDfromList(self, goglist, ID):
        findteam = None
        for t in goglist:
            if t.ID == ID:
                findteam = t
                break
        return findteam

    def getBallByID(self, ID):
        findball = None
        for t in self.dispgroup['objplayers']:
            if t.hasBounceBall() and t[0].ID == ID:
                findball = t[0]
                break
        return findball

    def delTeamByID(self, ID):
        findteam = self.getTeamByID(ID)
        if findteam is not None:
            self.dispgroup['objplayers'].remove(findteam)

    def serializeActions(self, actions):
        if actions is None:
            return None
        actionsjson = []
        try:
            for oname, args in actions:
                if isinstance(args, Vector2):
                    actionsjson.append((oname, (args.x, args.y)))
                elif oname == 'hommingbullet':
                    actionsjson.append((oname, args.ID))
                else:
                    actionsjson.append((oname, args))
            return actionsjson
        except:
            Log.exception('%s %s', actionsjson, actions)
            return None

    def deserializeActions(self, actionjson):
        if actionjson is None:
            return None
        actions = []
        try:
            for oname, args in actionjson:
                if oname == 'hommingbullet':
                    actions.append((oname, self.getBallByID(args)))
                elif args and len(args) == 2:
                    actions.append((oname, Vector2(*args)))
                else:
                    actions.append((oname, args))
            return actions
        except:
            Log.exception('%s %s', actionjson, actions)
            return None

    def makeCollisionDict(self):
        # 현재 위치를 기준으로 collision / interaction 검사하고
        # get all collision list { src: [ t1, t1.. ], .. }
        buckets = []
        for aa in self.dispgroup['objplayers']:
            bk = aa.makeCollisionBucket(
                ['bounceball', 'shield', 'supershield', 'bullet',
                    'circularbullet', 'superbullet', 'hommingbullet'],
                0.05, 0.05)
            buckets.append((aa, bk))

        resultdict = {}
        cmpsum = 0
        for ob1, ob2 in itertools.combinations(buckets, 2):
            g1, b1 = ob1
            g2, b2 = ob2
            if g1.teamname == g2.teamname:
                continue
            toiter = set(b1.keys()) & set(b2.keys())
            for i in toiter:
                cmpsum += len(b1[i]) * len(b2[i])
                for o1 in b1[i]:
                    for o2 in b2[i]:
                        o1.checkCollisionAppend(o2, resultdict)
        return resultdict, cmpsum

    # game AI support functions
    def getEnemyTeamList(self, myTeam):
        # 자신과 같은 팀을 제외한 teamList를 만든다.
        return [tt for tt in self.dispgroup[
            'objplayers'] if tt.teamname != myTeam.teamname]

    def selectRandomBall(self, teamList):
        targetobjs = [a[0] for a in teamList if a.hasBounceBall()]
        return random.choice(targetobjs) if targetobjs else None

    def getFilterdObjects(self, teamList, filterlist):
        return sum([a.getObjectByTypes(filterlist) for a in teamList], [])

    def findTarget(self, src, objtypes, filterfn, teamList):
        # select target filtered by objtypelist and filterfn
        target = None
        olist = self.getFilterdObjects(teamList, objtypes)
        if olist:
            target = min(olist, key=filterfn)
        targetlen = target.lento(src) if target else 1.5
        return target, targetlen

    # deserialize functions
    def findObjByID(self, objlist, id):
        for o in objlist:
            if o.ID == id:
                return o
        return None

    def addNewObj2Team(self, team, objdef):
        objid, objtype, objpos, objmovevector = objdef[:4]

        argsdict = dict(
            objtype=objtype,
            pos=Vector2(*objpos),
            movevector=Vector2(*objmovevector),
            group=team
        )
        newobj = team.spriteClass().initialize(argsdict)
        newobj.ID = objid
        team.append(newobj)

    def makeNewTeam(self, groupClass, spriteClass, groupdict):
        newteam = groupClass(
        ).initialize(
            teamcolor=groupdict['teamcolor'],
            teamname=groupdict['teamname'],
            gameObj=self,
            spriteClass=spriteClass,
        )
        newteam.ID = groupdict['ID']
        for objdef in groupdict['objs']:
            self.addNewObj2Team(newteam, objdef)
        return newteam

    def migrateExistTeamObj(self, aliveteam, groupdict):
        oldobjs = aliveteam[:]
        aliveteam[:] = []
        for objdef in groupdict['objs']:
            objid, objtype, objpos, objmovevector = objdef[:4]
            aliveobj = self.findObjByID(oldobjs, objid)
            if aliveobj is not None:  # obj alive
                aliveteam.append(aliveobj)
                aliveobj.pos = Vector2(*objpos)
                aliveobj.movevector = Vector2(*objmovevector)
            else:  # new obj
                self.addNewObj2Team(aliveteam, objdef)

    def applyState(self, groupClass, spriteClass, loadlist):
        self.frameinfo.update(loadlist['frameinfo'])
        self.migrateExistTeamObj(
            self.dispgroup['effectObjs'], loadlist['effectObjs'])

        oldgog = self.dispgroup['objplayers']
        self.dispgroup['objplayers'] = []
        for groupdict in loadlist['objplayers']:
            aliveteam = self.getTeamByIDfromList(oldgog, groupdict['ID'])
            if aliveteam is not None:  # copy oldteam to new team
                self.dispgroup['objplayers'].append(aliveteam)
                # now copy members
                self.migrateExistTeamObj(aliveteam, groupdict)
            else:  # make new team
                self.dispgroup['objplayers'].append(
                    self.makeNewTeam(groupClass, spriteClass, groupdict)
                )
