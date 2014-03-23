#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" wxgame server framework
게임 서버용으로 수정, wxpython code를 제거

wxGameFramework
Copyright 2011,2013,1014 kasw <kasworld@gmail.com>
wxpython을 사용해서 게임을 만들기위한 프레임웍과 테스트용 게임 3가지
기본적인 가정은
좌표계는 0~1.0 인 정사각형 실수 좌표계
collision은 원형: 현재 프레임의 위치만을 기준으로 검출한다.
모든? action은 frame 간의 시간차에 따라 보정 된다.
문제점은 frame간에 지나가 버린 경우 이동 루트상으론 collision 이 일어나야 하지만 검출 불가.

C/S protocol
zlib compressed json : Vector2 => (x, y)
connect

client send
{
    cmd : makeTeam,
    teamname : teamname
}
Server send
{
    cmd : teamInfo
    teamname : teamname,
    teamid : teamid
}

client send
{
    cmd='reqState',
}
server send state
{
    'cmd': 'gameState',
    'frameinfo': {k: v for k, v in self.frameinfo.iteritems() if k not in ['stat']},
    'objplayers': [og.serialize() for og in self.dispgroup['objplayers']],
    'effectObjs': self.dispgroup['effectObjs'].serialize()
}

client send
{
    cmd='act',
    team=self.myteam,
    actions=actionjson,
}
server send
{
    cmd='actACK',
}

server send to server
{
    cmd: del
}

profile
python -m cProfile -o profile.txt  wxgame2client.py -t teama
view profile
import pstats
pstats.Stats('profile.txt').strip_dirs().sort_stats('tottime').print_stats(40)
"""
Version = '2.2.0'
import time
import math
import random
import itertools
import zlib
import copy
try:
    import simplejson as json
except:
    import json
import sys
import signal
import threading
import SocketServer
import Queue
import select
import socket
import traceback
import struct

from euclid import Vector2
# ======== game lib ============
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
            print 'ERROR - NOT FPS stat'
            return
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


class FPSlogicBase(object):

    def FPSTimerInit(self, frameTime, maxFPS=70, ):
        self.maxFPS = maxFPS
        self.repeatingcalldict = {}
        self.pause = False
        self.frameTime = frameTime
        self.statFPS = Statistics(timeFn=self.frameTime)
        self.frameinfo = {}

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
            "oldtime": self.frameTime(),
            "starttime": self.frameTime(),
            "repeatcount": 0}
        return self

    def unRegisterRepeatFn(self, fn):
        return self.repeatingcalldict.pop(fn, [])

    def FPSTimer(self, evt):
        thistime = self.frameTime()
        frames = self.statFPS.updateFPS()

        difftime = frames[-1] - frames[-2] if len(frames) > 1 else 0.1
        self.frameinfo = {
            'stat': self.statFPS,
            'thistime': thistime,
            'ThisFPS': 1 / difftime
        }

        if not self.pause:
            self.doFPSlogic()

        for fn, d in self.repeatingcalldict.iteritems():
            if thistime - d["oldtime"] > d["dursec"]:
                self.repeatingcalldict[fn]["oldtime"] = thistime
                self.repeatingcalldict[fn]["repeatcount"] += 1
                fn(d)

        nexttime = (self.frameTime() - thistime) * 1000
        newdur = min(1000, max(difftime * 800, 1000 / self.maxFPS) - nexttime)
        if newdur < 1:
            newdur = 1
        self.newdur = newdur

    def doFPSlogic(self, thisframe):
        pass


class I32sendrecv(object):

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

        self.sendstat = Statistics(timeFn=getFrameTime)
        self.recvstat = Statistics(timeFn=getFrameTime)

    def __str__(self):
        return '[{}:{}:{}:{}]'.format(
            self.__class__.__name__,
            self.sock,
            self.readbuf,
            self.writebuf,
        )

    def getStatInfo(self):
        return 'send:{}:{}\nrecv:{}:{}'.format(
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
                print 'invalid recv state', self.readbuf[2]
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


class TCPGameClient(threading.Thread):

    def __str__(self):
        return self.conn.protocol.getStatInfo()

    def __init__(self, connectTo):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(connectTo)

        protocol = I32sendrecv(sock)
        self.conn = Storage({
            'protocol': protocol,
            'recvQueue': protocol.recvQueue,
            'sendQueue': protocol.sendQueue,
            'quit': False,
        })
        print self

    def runService(self):
        client_thread = threading.Thread(target=self.clientLoop)
        client_thread.start()
        return self, client_thread

    def clientLoop(self):
        try:
            while self.conn.quit is not True:
                self.conn.protocol.sendrecv()
        except RuntimeError as e:
            if e.args[0] != "socket connection broken":
                raise RuntimeError(e)

    def shutdown(self):
        self.conn.quit = True
        self.conn.protocol.sock.close()
        print 'end connection'
        print self


# ======== game lib end ============
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

        # self.autoMoveFns = []
        self.registerAutoMoveFn(self.movefn, [])
        self.registerAutoMoveFn(SpriteObj.Move_byMoveVector, [])
        self.registerAutoMoveFn(self.wallactionfn, [])

        # print 'init obj', self
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
            print 'Warnning gameObj:', self.gameObj
        if self.spriteClass is None:
            print 'Warnning spriteClass:', self.spriteClass

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
            # print 'remove obj', a
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
            # print 'No bounceBall'
            return
        src = self[0]
        for act, actargs in actions:
            if self.usableBulletCountDict.get(act, 0) > 0:
                self.statistic['act'][act] += 1
                if not actargs and act in ["superbullet", "hommingbullet", "bullet", "accel"]:
                    print "Error %s %s %s" % (act, src, actargs)
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
                    print 'unknown act', act
                src.fireTimeDict[act] = self.thistick
            else:
                if act != 'doNothing':
                    # print "%s action %s overuse fail" % (self.teamname, act)
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
        randomtargetlen = randomtarget.lento(src) if randomtarget else 1

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
            # print dangertarget, accelvector
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
            print traceback.format_exc()
            print actionsjson, actions
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
            print traceback.format_exc()
            print actionjson, actions
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


class AIClientMixin(ShootingGameMixin):

    def __init__(self, *args, **kwds):
        self.conn = kwds.pop('conn')
        self.myteam = None

    def makeClientAIAction(self):
        # make AI action
        if self.myteam is None:
            return
        aa = self.getTeamByID(self.myteam['teamid'])
        if aa is None:
            return
        targets = [tt for tt in self.dispgroup[
            'objplayers'] if tt.teamname != aa.teamname]

        aa.prepareActions(
            targets,
            self.frameinfo['ThisFPS'],
            self.thistick
        )
        actions = aa.SelectAction(targets, aa[0])

        actionjson = self.serializeActions(actions)
        # print actions, actionjson

        putParams2Queue(
            self.conn.sendQueue,
            cmd='act',
            team=self.myteam,
            actions=actionjson,
        )

    def processCmd(self):

        while not self.conn.recvQueue.empty():
            try:
                cmdDict = self.conn.recvQueue.get_nowait()
                if cmdDict is None:
                    break
            except Queue.Empty:
                break
            except:
                print traceback.format_exc()
                break
            cmdDict = fromGzJson(cmdDict)

            cmd = cmdDict.get('cmd')

            if cmd == 'gameState':
                putParams2Queue(
                    self.conn.sendQueue,
                    cmd='reqState',
                )
                self.applyState(cmdDict)
                if self.myteam is not None:
                    self.makeClientAIAction()

            elif cmd == 'actACK':
                pass

            elif cmd == 'teamInfo':
                teamname = cmdDict.get('teamname')
                teamid = cmdDict.get('teamid')
                self.myteam = {
                    'teamname': teamname,
                    'teamid': teamid,
                    'teamStartTime': self.thistick,
                }
                print 'joined', teamname, teamid
                print self.myteam
                putParams2Queue(
                    self.conn.sendQueue,
                    cmd='reqState',
                )
            else:
                print 'unknown cmd', cmdDict


class ShootingGameServer(ShootingGameMixin, FPSlogicBase):

    def initGroups(self, groupclass, spriteClass):
        self.dispgroup = {}
        self.dispgroup['backgroup'] = groupclass().initialize(
            gameObj=self, spriteClass=spriteClass, teamcolor=(0x7f, 0x7f, 0x7f))
        self.dispgroup['effectObjs'] = groupclass().initialize(
            gameObj=self, spriteClass=spriteClass, teamcolor=(0x7f, 0x7f, 0x7f))
        self.dispgroup['frontgroup'] = groupclass().initialize(
            gameObj=self, spriteClass=spriteClass, teamcolor=(0x7f, 0x7f, 0x7f))
        self.dispgroup['objplayers'] = []

    def __init__(self, *args, **kwds):
        def setAttr(name, defaultvalue):
            self.__dict__[name] = kwds.pop(name, defaultvalue)
            return self.__dict__[name]

        self.clientCommDict = kwds.pop('clientCommDict')
        self.FPSTimerInit(getFrameTime, 60)
        self.initGroups(GameObjectGroup, SpriteObj)

        for i in range(8):
            o = self.make1TeamCustom(
                teamname='server%d' % i,
                aiclass=AI2,
                teamcolor=(
                    random.randint(0, 255),
                    random.randint(0, 255),
                    random.randint(0, 255)),
                servermove=True,
                spriteClass=SpriteObj
            )
            self.dispgroup['objplayers'].append(o)

        self.statObjN = Statistics()
        self.statCmpN = Statistics()
        self.statPacketL = Statistics()
        print 'end init'
        self.registerRepeatFn(self.prfps, 1)

    def make1TeamCustom(self, teamname, aiclass, spriteClass, teamcolor, servermove):
        o = aiclass().initialize(
            teamcolor=teamcolor,
            teamname=teamname,
            effectObjs=self.dispgroup['effectObjs'],
            servermove=servermove,
            gameObj=self,
            spriteClass=spriteClass
        )
        o.makeMember()
        return o

    def prfps(self, repeatinfo):
        self.diaplayScore()
        for conn in self.clientCommDict['clients']:
            if conn is not None:
                print conn.teamname
                print conn.protocol.getStatInfo()
        print 'objs:', self.statObjN
        print 'cmps:', self.statCmpN
        print 'packetlen:', self.statPacketL
        print 'fps:', self.frameinfo['stat']
        print

    def diaplayScore(self):
        teamscore = {}
        for j in self.dispgroup['objplayers']:
            if j.teamname in teamscore:
                teamscore[j.teamname]['teamscore'] += j.statistic['teamscore']
                teamscore[j.teamname]['member'] += 1
                teamscore[j.teamname]['objcount'] += len(j)
            else:
                teamscore[j.teamname] = dict(
                    teamscore=j.statistic['teamscore'],
                    color=j.teamcolor,
                    ai=j.__class__.__name__,
                    member=1,
                    objcount=len(j)
                )

        print "{:12} {:15} {:>16} {:>8} {:>8} {:8}".format(
            'teamname', 'color', 'AI type', 'member', 'score', 'objcount'
        )
        sortedinfo = sorted(
            teamscore.keys(), key=lambda x: -teamscore[x]['teamscore'])

        for j in sortedinfo:
            print "{:12} {:15} {:>16} {:8} {:8.4f} {:8}".format(
                j,
                teamscore[j]['color'],
                teamscore[j]['ai'],
                teamscore[j]['member'],
                teamscore[j]['teamscore'],
                teamscore[j]['objcount']
            )

    def doScore(self, resultdict):
        for src, targets in resultdict.iteritems():
            src.enabled = False
            if src.objtype != 'bounceball':
                self.dispgroup['effectObjs'].addSpriteExplosionEffect(src)
            else:
                # 충돌한 것이 bounceball 이면
                # print 'bounceball killed', src
                src.group.addBallExplosionEffect(
                    self.dispgroup['effectObjs'], src.group, src)
                srcLostScore = src.getDelScore(math.sqrt(src.level))
                src.group.statistic["teamscore"] -= srcLostScore
                uplevel = srcLostScore * 2 / len(targets)
                for target in targets:
                    if target.objtype != 'bounceball':
                        if target.group and target.group.hasBounceBall():
                            oldlevel = target.group[0].level
                            target.group[0].level += uplevel
                            inclevel = int(
                                target.group[0].level) - int(oldlevel)
                            for i in range(inclevel):
                                target.group.statistic[
                                    'act']['supershield'] += 1
                                target.group.AddSuperShield(
                                    target=target.group[0],
                                    expireFn=self.dispgroup[
                                        'effectObjs'].addSpriteExplosionEffect
                                )
                    if target.objtype not in ['bounceball', 'supershield', 'shield']:
                        target.group.statistic["teamscore"] += uplevel
        return

    def makeState(self):
        savelist = {
            'cmd': 'gameState',
            'frameinfo': {k: v for k, v in self.frameinfo.iteritems() if k not in ['stat']},
            'objplayers': [og.serialize() for og in self.dispgroup['objplayers']],
            'effectObjs': self.dispgroup['effectObjs'].serialize()
        }
        return savelist

    def saveState(self):
        try:
            savelist = toGzJson(self.makeState())
            self.clientCommDict['gameState'] = savelist
        except zlib.error:
            print 'zlib compress fail'
            return 0
        except ValueError:
            print 'encode fail'
            return 0
        except:
            print traceback.format_exc()
            return 0

        return len(savelist)

    def processClientCmd(self):
        for conn in self.clientCommDict['clients']:
            if conn is None:
                continue
            while not conn.recvQueue.empty():
                cmdDict = None
                try:
                    cmdDict = conn.recvQueue.get_nowait()
                except Queue.Empty:
                    break
                except:
                    print traceback.format_exc()
                    break
                if cmdDict is None:
                    break
                cmdDict = fromGzJson(cmdDict)
                self.do1ClientCmd(conn, cmdDict)

    def do1ClientCmd(self, conn, cmdDict):
        cmd = cmdDict.get('cmd')
        if cmd == 'makeTeam':
            tn = cmdDict.get('teamname')
            o = self.make1TeamCustom(
                teamname=tn,
                aiclass=GameObjectGroup,
                teamcolor=cmdDict.get('teamcolor'),
                servermove=False,
                spriteClass=SpriteObj
            )
            self.dispgroup['objplayers'].append(o)
            conn['teamid'] = o.ID
            conn['teamname'] = tn
            print tn, 'team made', o.ID
            putParams2Queue(
                conn.sendQueue,
                cmd='teamInfo',
                teamname=tn,
                teamid=o.ID
            )

        elif cmd == 'del':
            print 'del team', conn.teamid
            self.delTeamByID(conn.teamid)
            self.clientCommDict['clients'].remove(conn)

        elif cmd == 'reqState':
            conn.sendQueue.put(self.clientCommDict['gameState'])

        elif cmd == 'act':
            putParams2Queue(
                conn.sendQueue,
                cmd='actACK'
            )
            actions = cmdDict.get('actions')
            tid = cmdDict['team']['teamid']
            thisTeam = self.getTeamByID(tid)
            if thisTeam.servermove:
                print 'invalid team', thisTeam
                return
            actionjson = cmdDict['actions']
            actions = self.deserializeActions(actionjson)

            enemyTeamList = self.getEnemyTeamList(thisTeam)
            thisTeam.prepareActions(
                enemyTeamList,
                self.frameinfo['ThisFPS'],
                self.thistick
            )

            thisTeam.applyActions(actions)
            thisTeam.AutoMoveByTime(self.thistick)

        else:
            print 'unknown cmd', cmdDict

    def doFireAndAutoMoveByTime(self):
        # 그룹내의 bounceball 들을 AI automove 한다.
        selmov = self.dispgroup['objplayers'][:]
        random.shuffle(selmov)
        for thisTeam in selmov:
            if thisTeam.servermove is not True:
                continue

            if thisTeam.hasBounceBall():
                enemyTeamList = self.getEnemyTeamList(thisTeam)
                thisTeam.prepareActions(
                    enemyTeamList,
                    self.frameinfo['ThisFPS'],
                    self.thistick
                )
                actions = thisTeam.SelectAction(enemyTeamList, thisTeam[0])
                thisTeam.applyActions(actions)

            thisTeam.AutoMoveByTime(self.thistick)

    def doFPSlogic(self):
        self.thistick = self.frameinfo['thistime']

        self.frameinfo['objcount'] = sum(
            [len(a) for a in self.dispgroup['objplayers']])

        self.statObjN.update(self.frameinfo['objcount'])

        # server AI move mode
        self.doFireAndAutoMoveByTime()
        # process client cmds
        self.processClientCmd()

        # make collision dictionary
        resultdict, self.frameinfo['cmpcount'] = self.makeCollisionDict()
        self.statCmpN.update(self.frameinfo['cmpcount'])

        # do score
        self.doScore(resultdict)

        # 결과에 따라 삭제한다.
        for aa in self.dispgroup['objplayers']:
            aa.RemoveDisabled()

        self.dispgroup['effectObjs'].AutoMoveByTime(
            self.thistick).RemoveDisabled()

        self.statPacketL.update(self.saveState())

    def doGame(self):
        while not self.clientCommDict['quit']:
            self.FPSTimer(0)
            time.sleep(self.newdur / 1000.)

# ================ tcp server ========


class ClientConnectedThread(SocketServer.BaseRequestHandler):

    def __str__(self):
        return 'team:{}:{}\n{}'.format(
            self.conn.teamname, self.client_address,
            self.conn.protocol.getStatInfo(),
        )

    def setup(self):
        print 'client connected', self.client_address
        protocol = I32sendrecv(self.request)
        self.conn = Storage({
            'protocol': protocol,
            'recvQueue': protocol.recvQueue,
            'sendQueue': protocol.sendQueue,
            'quit': False,
            'teamname': None,
            'teamid': None
        })
        self.server.clientCommDict['clients'].append(self.conn)

    def handle(self):
        try:
            while self.conn.quit is not True:
                self.conn.protocol.sendrecv()
        except RuntimeError as e:
            if e.args[0] != "socket connection broken":
                raise RuntimeError(e)

    def finish(self):
        self.conn.quit = True
        self.request.close()

        print 'client disconnected'
        print self

        putParams2Queue(
            self.conn.recvQueue,
            cmd='del'
        )


class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    allow_reuse_address = True


def runService(listenFrom):
    clientCommDict = {
        'gameState': '',
        #'FreeTeamList': Queue.Queue(),
        'clients': [],
        'quit': False
    }
    print 'Server start, ', listenFrom

    server = ThreadedTCPServer(listenFrom, ClientConnectedThread)
    server.clientCommDict = clientCommDict
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()

    def sigstophandler(signum, frame):
        print 'User Termination'
        clientCommDict['quit'] = True
        server.shutdown()
        server_thread.join(1)
        print 'server end'
        sys.exit(0)

    signal.signal(signal.SIGINT, sigstophandler)

    ShootingGameServer(clientCommDict=clientCommDict).doGame()

# ================ tcp server end =======


if __name__ == "__main__":
    runService(("0.0.0.0", 22517))
