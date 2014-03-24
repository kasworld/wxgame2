#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    wxGameFramework
    Copyright 2011 kasw <kasworld@gmail.com>
    wxpython을 사용해서 게임을 만들기위한 프레임웍과 테스트용 게임 3가지
    기본적인 가정은
    좌표계는 0~1.0 인 정사각형 실수 좌표계
    collision은 원형: 현재 프레임의 위치만을 기준으로 검출한다.
    모든? action은 frame 간의 시간차에 따라 보정 된다.
    문제점은 frame간에 지나가 버린 경우 이동 루트상으론 collision 이 일어나야 하지만 검출 불가.
AI dev order
random
center circle
near bullet
birth circle
move outer
move inner
super/homming near
super/homming rate
bullet rate near,far
bullet near, random
estmate aim
evasion bullets
evasion inner
evasion outer
evasion back + rand angle
"""

Version = '1.6.10'

import sys
import os.path

from euclid import Vector2

import wx
import wx.grid
import wx.lib.colourdb
import os
import time
import math
import random
import itertools
import pprint
import cPickle as pickle
# def handler(signum, frame):
#    print 'Signal handler called with signal', signum
# signal.signal(signal.SIGTERM, handler)
# signal.signal(signal.SIGHUP, handler)
# signal.signal(signal.SIGINT, handler)

import wx
import time
import math
import os
import random
import itertools

wx.InitAllImageHandlers()

import sys
import os.path

# general util

srcdir = os.path.dirname(os.path.abspath(sys.argv[0]))

getSerial = itertools.count().next


def getFrameTime():
    return time.time()


def random2pi(m=2):
    return math.pi * m * (random.random() - 0.5)


def getHMSAngle(mst, hands):
    """ clock hands angle
    0 : hour
    1 : minute
    2 : second
    mst = time.time()"""

    lt = time.localtime(mst)
    ms = mst - int(mst)
    if hands == 0:  # hour
        return math.radians(lt[3] * 30.0 + lt[4] / 2.0 + lt[5] / 120.0 + 90)
    elif hands == 1:  # minute
        return math.radians(lt[4] * 6.0 + lt[5] / 10.0 + ms / 10 + 90)
    elif hands == 2:  # second
        return math.radians(lt[5] * 6.0 + ms * 6 + 90)
    else:
        return None


class FastStorage(dict):

    """from gluon storage.py """

    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)
        self.__dict__ = self

    def __getattr__(self, key):
        return getattr(self, key) if key in self else None

    def __getitem__(self, key):
        return dict.get(self, key, None)

    def copy(self):
        self.__dict__ = {}
        s = FastStorage(self)
        self.__dict__ = self
        return s

    def __repr__(self):
        return '<Storage %s>' % dict.__repr__(self)

    def __getstate__(self):
        return dict(self)

    def __setstate__(self, sdict):
        dict.__init__(self, sdict)
        self.__dict__ = self

    def update(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)
        self.__dict__ = self


class Statistics(object):

    def __init__(self):
        self.datadict = {
            'min': None,
            'max': None,
            'avg': None,
            'sum': 0,
            'last': None,
            'count': 0,
        }
        self.formatstr = '%(last)s(%(min)s~%(max)s), %(avg)s=%(sum)s/%(count)d'

    def update(self, data):
        data = float(data)
        self.datadict['count'] += 1
        self.datadict['sum'] += data

        if self.datadict['last'] != None:
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

    def getStat(self):
        return self.datadict

    def __str__(self):
        return self.formatstr % self.datadict


# wx specific


def loadBitmap2MemoryDCArray(bitmapfilename, xslicenum=1, yslicenum=1,
                             totalslice=10000,  yfirst=True, reverse=False, addreverse=False):
    rtn = []
    fullbitmap = wx.Bitmap(bitmapfilename)
    dcsize = fullbitmap.GetSize()
    w, h = dcsize[0] / xslicenum, dcsize[1] / yslicenum
    if yfirst:
        for x in range(xslicenum):
            for y in range(yslicenum):
                rtn.append(wx.MemoryDC(
                    fullbitmap.GetSubBitmap(wx.Rect(x * w, y * h, w, h))))
    else:
        for y in range(yslicenum):
            for x in range(xslicenum):
                rtn.append(wx.MemoryDC(
                    fullbitmap.GetSubBitmap(wx.Rect(x * w, y * h, w, h))))
    totalslice = min(xslicenum * yslicenum, totalslice)
    rtn = rtn[:totalslice]
    if reverse:
        rtn.reverse()
    if addreverse:
        rrtn = rtn[:]
        rrtn.reverse()
        rtn += rrtn
    return rtn


def loadDirfiles2MemoryDCArray(dirname, reverse=False, addreverse=False):
    rtn = []
    filenames = sorted(os.listdir(dirname), reverse=reverse)
    for a in filenames:
        rtn.append(wx.MemoryDC(wx.Bitmap(dirname + "/" + a)))
    if addreverse:
        rrtn = rtn[:]
        rrtn.reverse()
        rtn += rrtn
    return rtn


def makeRotatedImage(image, angle):
    rad = math.radians(-angle)
    xlen, ylen = image.GetWidth(), image.GetHeight()
    #offset = wx.Point()
    # ,wx.Point(xlen,ylen) )
    rimage = image.Rotate(rad, (xlen / 2, ylen / 2), True)
    # rimage =  image.Rotate( rad, (0,0) ,True) #,wx.Point() )
    xnlen, ynlen = rimage.GetWidth(), rimage.GetHeight()
    rsimage = rimage.Size(
        (xlen, ylen), (-(xnlen - xlen) / 2, -(ynlen - ylen) / 2))
    # print angle, xlen , ylen , xnlen , ynlen , rsimage.GetWidth() ,
    # rsimage.GetHeight()
    return rsimage


def loadBitmap2RotatedMemoryDCArray(imagefilename, rangearg=(0, 360, 10),
                                    reverse = False, addreverse = False):
    rtn = []
    fullimage = wx.Bitmap(imagefilename).ConvertToImage()
    for a in range(*rangearg):
        rtn.append(wx.MemoryDC(
            makeRotatedImage(fullimage, a).ConvertToBitmap()
        ))
    if reverse:
        rtn.reverse()
    if addreverse:
        rrtn = rtn[:]
        rrtn.reverse()
        rtn += rrtn
    return rtn


class GameResource(object):

    """ game resource loading with cache
    """

    def __init__(self, dirname):
        self.resourcedir = dirname
        self.rcsdict = {}

    def getcwdfilepath(self, filename):
        return os.path.join(srcdir, self.resourcedir, filename)

    def loadBitmap2MemoryDCArray(self, name, *args, **kwds):
        key = (name, args, str(kwds))
        if not self.rcsdict.get(key, None):
            self.rcsdict[key] = loadBitmap2MemoryDCArray(
                self.getcwdfilepath(name), *args, **kwds)
        return self.rcsdict[key]

    def loadDirfiles2MemoryDCArray(self, name, *args, **kwds):
        key = (name, args, str(kwds))
        if not self.rcsdict.get(key, None):
            self.rcsdict[key] = loadDirfiles2MemoryDCArray(
                self.getcwdfilepath(name), *args, **kwds)
        return self.rcsdict[key]

    def loadBitmap2RotatedMemoryDCArray(self, name, *args, **kwds):
        key = (name, args, str(kwds))
        if not self.rcsdict.get(key, None):
            self.rcsdict[key] = loadBitmap2RotatedMemoryDCArray(
                self.getcwdfilepath(name), *args, **kwds)
        return self.rcsdict[key]


class FPSlogicBase(object):

    def FPSTimerInit(self, frameTime, maxFPS=70, ):
        self.maxFPS = maxFPS
        self.repeatingcalldict = {}
        self.pause = False
        self.statFPS = Statistics()
        self.frameTime = frameTime
        self.frames = [self.frameTime()]
        self.first = True
        self.frameCount = 0

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
        self.frameCount += 1

        thistime = self.frameTime()
        self.frames.append(thistime)
        difftime = self.frames[-1] - self.frames[-2]

        while(self.frames[-1] - self.frames[0] > 1):
            del self.frames[0]

        if len(self.frames) > 1:
            fps = len(self.frames) / (self.frames[-1] - self.frames[0])
        else:
            fps = 0
        if self.first:
            self.first = False
        else:
            self.statFPS.update(fps)

        frameinfo = {
            "ThisFPS": 1 / difftime,
            "sec": difftime,
            "FPS": fps,
            'stat': self.statFPS,
            'thistime': thistime,
            'frameCount': self.frameCount
        }

        if not self.pause:
            self.doFPSlogic(frameinfo)

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


class FPSlogic(FPSlogicBase):

    def FPSTimerInit(self, frameTime, maxFPS=70):
        FPSlogicBase.FPSTimerInit(self, frameTime, maxFPS)
        self.Bind(wx.EVT_TIMER, self.FPSTimer)
        self.timer = wx.Timer(self)
        self.timer.Start(1000 / self.maxFPS, oneShot=True)

    def FPSTimer(self, evt):
        FPSlogicBase.FPSTimer(self, evt)
        self.timer.Start(self.newdur, oneShot=True)

    def FPSTimerDel(self):
        self.timer.Stop()


g_rcs = GameResource('resource')


def getFrameTime():
    return time.time()


# game에 쓸 object 관련 class 들
class Sprite(object):

    """
    base class for Game Object
    automove: by time
    enable, visible, position, type, collision, created time
    """

    def __init__(self, *args, **kwds):
        argsdict = {
            "enabled": True,
            "visible": True,
            "pos": Vector2(0.5, 0.5),
            "objtype": None,
            "collisionCricle": 0.01,
            "secToLifeEnd":  10.0,
            "createdTime": 0,
            "expireFn": None,
        }
        self.loadArgs(kwds, argsdict)
        self.ID = getSerial()
        # self.createdTime = getFrameTime()
        self.lastAutoMoveTick = self.createdTime
        self.autoMoveFns = []

    def loadArgs(self, kwds, argsdict):
        for n, v in argsdict.iteritems():
            if n in ['pos']:
                self.__dict__[n] = kwds.get(n, v).copy()
            else:
                self.__dict__[n] = kwds.get(n, v)

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

    def getLifeRate(self, tick):
        return (tick - self.createdTime) / self.secToLifeEnd

    def registerAutoMoveFn(self, fn, args=[]):
        self.autoMoveFns.append((fn, args))
        return self

    def AutoMoveByTime(self, thistick):
        if not self.enabled:
            return
        self.thistick = thistick
        if self.secToLifeEnd > 0 and self.createdTime + self.secToLifeEnd < self.thistick:
            if self.expireFn:
                self.expireFn(self)
            self.enabled = False
            return  # to old too move

        for fn, args in self.autoMoveFns:
            fn(self, args)
        self.lastAutoMoveTick = self.thistick


class MoveBounceSprite(Sprite):

    """
    moving, bouncing sprite
    모든 move fn은 movevector를 통해서 pos를 바꾼다.
    movevector의 속도는 /sec 임.
    즉 abs(movevector) == 1 이면 1초에 화면 왼쪽끝에서 오른쪽 끝가지 가는 속도임.
    여러 개의 mvfn을 등록할수 있고 각 펑션은 mvector를 수정한다.
    그 마직막 결과를 pos에 더한다.
    movefn, move, check wall 순으로 일어남.
    """

    def __init__(self, *args, **kwds):
        Sprite.__init__(self, *args, **kwds)
        argsdict = {
            "movefn": MoveBounceSprite.Move_NoAccel,
            "movevector": Vector2(0, 0),
            "movelimit": 1.0,
            "movefnargs": {
                "accelvector": Vector2(0, 0),
                "handstype": 0,
                "targetobj": None,
                "diffvector": Vector2(0, 0),
                "anglespeed": 0.0,
            },
            "wallactionfn": MoveBounceSprite.WallAction_Remove,
            "bounceDamping": 1.,
            "weight": 1
        }
        self.loadArgs(kwds, argsdict)
        self.registerAutoMoveFn(self.movefn, [])
        self.registerAutoMoveFn(MoveBounceSprite.Move_byMoveVector, [])
        self.registerAutoMoveFn(self.wallactionfn, [])

    def Move_byMoveVector(self, args):
        """실제로 pos를 변경하는 함수."""
        dur = (self.thistick - self.lastAutoMoveTick)
        if abs(self.movevector) > self.movelimit:
            self.movevector = self.movevector.normalized() * self.movelimit
        self.pos += self.movevector * dur

    def WallAction_Bounce(self, args):
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

    def WallAction_Remove(self, args):
        if self.CheckWallCollision("Inner"):
            self.enabled = False

    def WallAction_Wrap(self, args):
        rtn = self.CheckWallCollision("Center")
        if "Right" in rtn:
            self.pos = Vector2(0.0, self.pos.y)
        elif "Left" in rtn:
            self.pos = Vector2(1.0, self.pos.y)
        elif "Bottom" in rtn:
            self.pos = Vector2(self.pos.x, 0.0)
        elif "Top" in rtn:
            self.pos = Vector2(self.pos.x, 1.0)

    def WallAction_Stop(self, args):
        if self.CheckWallCollision("Outer"):
            self.movefn = MoveBounceSprite.Move_NoAccel

    def WallAction_None(self, args):
        pass

    def Move_Sin(self, args):
        dur = (self.thistick - self.lastAutoMoveTick)
        self.movevector = Vector2.rect(0.005, dur * 10)

    def Move_NoAccel(self, args):
        pass

    def Move_Circle(self, args):
        dur = (self.thistick - self.lastAutoMoveTick)
        self.movevector = (
            self.pos.rotate(Vector2(0.5, 0.5), - dur * self.movefnargs["anglespeed"]
                            ) - self.pos) / dur

    def Move_Vector(self, args):
        dur = (self.thistick - self.lastAutoMoveTick)
        self.movevector += self.movefnargs["accelvector"]

    def Move_ClockHands(self, args):
        dur = (self.thistick - self.lastAutoMoveTick)
        self.movevector = (Vector2(0.5, 0.5) +
                           Vector2.rect(self.lentopos(Vector2(0.5, 0.5)), getHMSAngle(
                                        self.thistick, self.movefnargs["handstype"]))
                           - self.pos) / dur

    def Move_SyncTarget(self, args):
        self.enabled = self.movefnargs["targetobj"].enabled
        if not self.enabled:
            return
        dur = (self.thistick - self.lastAutoMoveTick)
        self.movefnargs["diffvector"] = self.movefnargs["diffvector"].rotate(
            Vector2(0, 0), self.movefnargs["anglespeed"] * dur)
        self.movevector = (self.movefnargs[
                           "targetobj"].pos - self.pos + self.movefnargs["diffvector"]) / dur

    def Move_FollowTarget(self, args):
        self.enabled = self.movefnargs["targetobj"].enabled
        dur = (self.thistick - self.lastAutoMoveTick)
        self.accelToPos(self.movefnargs["targetobj"].pos)
        mvlen = abs(self.movevector)
        self.movevector += self.movefnargs["accelvector"] * dur
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
        # print self

    def clearAccelVector(self):
        self.movefnargs["accelvector"] = Vector2(0, 0)

    def getAccelVector(self):
        return self.movefnargs["accelvector"]


class BackGroundSplite(MoveBounceSprite):

    """
    background scroll class
    repeat to fill background
    display dc, move, change image
    """

    def __init__(self, *args, **kwds):
        MoveBounceSprite.__init__(self, *args, **kwds)
        argsdict = {
            "memorydc": None,
            "dcsize":  None,
            "drawfillfn": BackGroundSplite.DrawFill_Both,
        }
        self.loadArgs(kwds, argsdict)
        if self.memorydc and not self.dcsize:
            self.dcsize = self.memorydc.GetSizeTuple()

    def DrawFill_Both(self, pdc, clientsize):
        for x in range(int(self.pos.x) - self.dcsize[0], clientsize.x, self.dcsize[0]):
            for y in range(int(self.pos.y) - self.dcsize[1], clientsize.y, self.dcsize[1]):
                pdc.Blit(
                    x, y,
                    self.dcsize[0],
                    self.dcsize[1],
                    self.memorydc,
                    0, 0,
                    wx.COPY,
                    True
                )

    def DrawFill_H(self, pdc, clientsize):
        y = int(self.pos.y) - self.dcsize[1]
        for x in range(int(self.pos.x) - self.dcsize[0], clientsize.x, self.dcsize[0]):
            pdc.Blit(
                x, y,
                self.dcsize[0],
                self.dcsize[1],
                self.memorydc,
                0, 0,
                wx.COPY,
                True
            )

    def DrawFill_V(self, pdc, clientsize):
        x = int(self.pos.x) - self.dcsize[0]
        for y in range(int(self.pos.y) - self.dcsize[1], clientsize.y, self.dcsize[1]):
            pdc.Blit(
                x, y,
                self.dcsize[0],
                self.dcsize[1],
                self.memorydc,
                0, 0,
                wx.COPY,
                True
            )

    def DrawFill_None(self, pdc, clientsize):
        x = int(self.pos.x) - self.dcsize[0]
        y = int(self.pos.y) - self.dcsize[1]
        pdc.Blit(
            x, y,
            self.dcsize[0],
            self.dcsize[1],
            self.memorydc,
            0, 0,
            wx.COPY,
            True
        )

    def WrapBy(self, wrapsize):
        if self.pos.x < 0:
            self.pos = Vector2(
                self.pos.x + wrapsize[0],
                self.pos.y)
        if self.pos.x >= wrapsize[0]:
            self.pos = Vector2(
                self.pos.x - wrapsize[0],
                self.pos.y)
        if self.pos.y < 0:
            self.pos = Vector2(
                self.pos.x,
                self.pos.y + wrapsize[1])
        if self.pos.y >= wrapsize[1]:
            self.pos = Vector2(
                self.pos.x,
                self.pos.y - wrapsize[1])

    def DrawToWxDC(self, pdc, clientsize, sizehint):
        # make self.pos in self.clientsize
        self.WrapBy(self.dcsize)
        self.drawfillfn(self, pdc, clientsize)


class GameObject(MoveBounceSprite):

    """
    display and shape
    """

    def __init__(self, *args, **kwds):
        MoveBounceSprite.__init__(self, *args, **kwds)
        argsdict = {
            "shapefn": GameObject.ShapeChange_None,
            "shapefnargs": {
                'radiusSpeed': 0,
                "pen": None,
                "brush": None,
                "memorydcs": [],
                "dcsize": None,
                "startimagenumber": 0,
                "animationfps": 10,
            },
            "afterremovefn": None,
            "afterremovefnarg": (),
        }
        self.loadArgs(kwds, argsdict)
        self.baseCollisionCricle = self.collisionCricle
        self.shapefnargs['memorydcs'] = self.shapefnargs.get('memorydcs', None)
        if self.shapefnargs['memorydcs'] and not self.shapefnargs.get('dcsize', None):
            self.shapefnargs['dcsize'] = self.shapefnargs[
                'memorydcs'][0].GetSizeTuple()
        self.currentimagenumber = self.shapefnargs[
            'startimagenumber'] = self.shapefnargs.get('startimagenumber', 0)
        self.shapefnargs['animationfps'] = self.shapefnargs.get(
            'animationfps', 10)

        self.registerAutoMoveFn(self.shapefn, [])
        self.registerAutoMoveFn(GameObject.changeImage, [])

    def ShapeChange_Shrink(self, args):
        self.collisionCricle = self.baseCollisionCricle * \
            (1 - self.getLifeRate(self.thistick))

    def ShapeChange_Grow(self, args):
        self.collisionCricle = self.baseCollisionCricle * \
            self.getLifeRate(self.thistick)

    def ShapeChange_Glitter(self, args):
        self.collisionCricle = self.baseCollisionCricle * (
            math.sin(self.thistick - self.createdTime + self.shapefnargs[
                     'radiusSpeed']) + 1
        )

    def ShapeChange_None(self, args):
        pass

    def changeImage(self, args):
        if self.shapefnargs['memorydcs']:
            self.currentimagenumber = int(self.shapefnargs['startimagenumber'] + (
                self.thistick - self.createdTime) * self.shapefnargs['animationfps']) % len(self.shapefnargs['memorydcs'])

    def Draw_Shape(self, pdc, clientsize, sizehint):
        pdc.SetPen(self.shapefnargs['pen'])
        pdc.SetBrush(self.shapefnargs['brush'])
        pdc.DrawCircle(
            clientsize.x * self.pos.x,
            clientsize.y * self.pos.y,
            max(sizehint * self.collisionCricle, 1)
        )

    def Draw_MDC(self, pdc, clientsize, sizehint):
        pdc.Blit(
            clientsize.x * self.pos.x - self.shapefnargs['dcsize'][0] / 2,
            clientsize.y * self.pos.y - self.shapefnargs['dcsize'][1] / 2,
            self.shapefnargs['dcsize'][0],
            self.shapefnargs['dcsize'][1],
            self.shapefnargs['memorydcs'][self.currentimagenumber],
            0, 0,
            wx.COPY,
            True
        )

    def DrawToWxDC(self, pdc, clientsize, sizehint):
        # return
        if not self.enabled or not self.visible:
            return
        if self.shapefnargs['memorydcs']:
            self.Draw_MDC(pdc, clientsize, sizehint)
        else:
            self.Draw_Shape(pdc, clientsize, sizehint)


class ShootingGameObject(GameObject):

    """
    AI for shooting game,
    level
    belongs object group
    lockme object group
    lockto target
    """

    def __init__(self, *args, **kwds):
        GameObject.__init__(self, *args, **kwds)
        argsdict = {
            "objtype": None,
            "level": 0,
            "group": None
        }
        self.loadArgs(kwds, argsdict)

    def getDelScore(self, factor=1):
        " 피격 타격시 점수 계산 로직 "
        " (1-math.sqrt(2)/2) ~ 1.0 사이의 값 * factor 를 리턴, 중앙으로 갈수록 점수가 작다. "
        # return (self.lentopos(Vector2(0.5,0.5))  + (1-math.sqrt(2)/2))*factor
        # return math.sqrt(1.0/(1-self.lentocenter()) -1)*factor
        return (self.lentocenter() + 0.5) * factor
        # return factor

    def __str__(self):
        return pprint.pformat([self.objtype, self.pos, self.movevector, self.movefnargs])

    # this is sample, modify for each purpose
    # value is for source action only, if want target action, use reversed pos in matrix
    # interaction list: if in list, source can collision to target
    samplecollisionrule = {
        'bounceball': ['bounceball', 'shield', 'supershield', 'bullet', 'circularbullet', 'superbullet', 'hommingbullet', 'effect', None],
        'shield': ['bounceball', 'shield', 'supershield', 'bullet', 'circularbullet', 'superbullet', 'hommingbullet', 'effect', None],
        'supershield': ['bounceball', 'shield', 'supershield', 'bullet', 'circularbullet', 'superbullet', 'hommingbullet', 'effect', None],
        'bullet': ['bounceball', 'shield', 'supershield', 'bullet', 'circularbullet', 'superbullet', 'hommingbullet', 'effect', None],
        'circularbullet': ['bounceball', 'shield', 'supershield', 'bullet', 'circularbullet', 'superbullet', 'hommingbullet', 'effect', None],
        'superbullet': ['bounceball', 'shield', 'supershield', 'bullet', 'circularbullet', 'superbullet', 'hommingbullet', 'effect', None],
        'hommingbullet': ['bounceball', 'shield', 'supershield', 'bullet', 'circularbullet', 'superbullet', 'hommingbullet', 'effect', None],
        'effect': ['bounceball', 'shield', 'supershield', 'bullet', 'circularbullet', 'superbullet', 'hommingbullet', 'effect', None],
        None: ['bounceball', 'shield', 'supershield', 'bullet', 'circularbullet', 'superbullet', 'hommingbullet', 'effect', None],
    }

    def checkCollisionAppend(self, target, rtnobjs, rule):
        """
        두 object간에 collision(interaction) 하고
        objtype이 rule type에 속하면
        rtnobjs에 append 한다.
        """
        if self.isCollision(target):
            if target.objtype in rule[self.objtype]:
                rtnobjs.setdefault(self, set()).add(target)
            if self.objtype in rule[target.objtype]:
                rtnobjs.setdefault(target, set()).add(self)


# game object group 관련 class들
class GameObjectGroup(list):

    """
    moving, interacting, displaying object 의 group
    collision check 의 단위가 된다.
    (inter, in)
    object type: bullet, superbullet, bounceball, None
    """

    # 표준 interface들 .
    def __init__(self, *args, **kwds):
        list.__init__(self, *args, **kwds)
        self.ID = getSerial()

    def DrawToWxDC(self, pdc):
        clientsize = pdc.GetSize()
        sizehint = min(clientsize.x, clientsize.y)
        for a in self:
            a.DrawToWxDC(pdc, clientsize, sizehint)
        return self

    def AutoMoveByTime(self, thistick):
        for a in self:
            a.AutoMoveByTime(thistick)
        return self

    def RemoveDisabled(self):
        rmlist = []
        for a in self:
            if not a.enabled:
                rmlist.append(a)
        for a in rmlist:
            self.remove(a)
        for a in rmlist:
            if a.afterremovefn:
                a.afterremovefn(*a.afterremovefnarg)
        return self

    def getSpeedByType(self, objtype):
        speed = {
            "circularbullet": 0.4,
            "superbullet": 0.6,
            "hommingbullet": 0.3,
            "bullet": 0.5,
            "bounceball": 0.3,
        }
        return speed.get(objtype, 0)

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

    # 이후는 GameObject를 편하게 생성하기위한 factory functions
    def AddCircularBullet2(self, centerpos, memorydcs, thistick=None):
        if not thistick:
            thistick = getFrameTime()
        for a in range(0, 360, 5):
            o = ShootingGameObject(
                secToLifeEnd=10.0,
                createdTime=thistick,
                collisionCricle=0.004,
                pos=centerpos + Vector2.rect(0.03, math.radians(a)),
                movevector=Vector2.rect(self.getSpeedByType(
                    "circularbullet"), math.radians(a)),
                movefnargs={"accelvector": Vector2(0, 0)},
                movefn=ShootingGameObject.Move_Vector,
                bounceDamping=0.9,
                wallactionfn=ShootingGameObject.WallAction_Remove,
                shapefn=ShootingGameObject.ShapeChange_None,
                shapefnargs={
                    'memorydcs': memorydcs,
                    'startimagenumber': a % len(memorydcs)
                },
                objtype="circularbullet",
                group=self,
            )
            self.append(o)
        return self

    def AddTargetFiredBullet(self, startpos, tagetpos, memorydcs, thistick=None):
        if not thistick:
            thistick = getFrameTime()
        o = ShootingGameObject(
            secToLifeEnd=10.0,
            createdTime=thistick,
            collisionCricle=0.008,
            pos=startpos,
            movevector=Vector2.rect(self.getSpeedByType(
                "bullet"), (tagetpos - startpos).phase()),
            movefnargs={"accelvector": Vector2(0, 0)},
            movefn=ShootingGameObject.Move_Vector,
            wallactionfn=ShootingGameObject.WallAction_Remove,
            shapefn=ShootingGameObject.ShapeChange_None,
            shapefnargs={
                'memorydcs': memorydcs,
            },
            objtype="bullet",
            group=self,
        )
        self.append(o)
        return self

    def AddHommingBullet(self, startpos, target, memorydcs, thistick=None, expireFn=None):
        if not thistick:
            thistick = getFrameTime()
        o = ShootingGameObject(
            secToLifeEnd=10.0,
            expireFn=expireFn,
            createdTime=thistick,
            collisionCricle=0.016,
            pos=startpos,
            movevector=Vector2.rect(self.getSpeedByType(
                "hommingbullet"), Vector2.phase(target.pos - startpos)),
            movefnargs={"accelvector": Vector2(
                0.5, 0.5), "targetobj": target},
            movefn=ShootingGameObject.Move_FollowTarget,
            bounceDamping=.7,
            wallactionfn=ShootingGameObject.WallAction_None,
            shapefn=ShootingGameObject.ShapeChange_None,
            shapefnargs={
                'memorydcs': memorydcs,
            },
            objtype="hommingbullet",
            group=self,
        )
        self.append(o)
        return self

    def AddTargetSuperBullet(self, startpos, tagetpos, memorydcs, thistick=None):
        if not thistick:
            thistick = getFrameTime()
        o = ShootingGameObject(
            secToLifeEnd=10.0,
            createdTime=thistick,
            collisionCricle=0.032,
            pos=startpos,
            movevector=Vector2.rect(self.getSpeedByType(
                "superbullet"), Vector2.phase(tagetpos - startpos)),
            movefnargs={"accelvector": Vector2(0, 0)},
            movefn=ShootingGameObject.Move_Vector,
            wallactionfn=ShootingGameObject.WallAction_Remove,
            shapefn=ShootingGameObject.ShapeChange_None,
            shapefnargs={
                'memorydcs': memorydcs,
            },
            objtype="superbullet",
            group=self,
        )
        self.append(o)
        return self

    def AddBouncBall(self, memorydcs,
                     animationfps=30,
                     pos=Vector2(0.5, 0.5),
                     movevector=Vector2(0, 0),
                     movelimit=1.0,
                     thistick=None
                     ):
        if not thistick:
            thistick = getFrameTime()
        o = ShootingGameObject(
            secToLifeEnd=-1.0,
            createdTime=thistick,
            collisionCricle=0.016,
            pos=pos,
            movevector=movevector,
            movelimit=movelimit,
            movefnargs={"accelvector": Vector2(0, 0)},
            movefn=ShootingGameObject.Move_Vector,
            bounceDamping=1.,
            wallactionfn=ShootingGameObject.WallAction_Bounce,
            shapefn=ShootingGameObject.ShapeChange_None,
            shapefnargs={
                'memorydcs': memorydcs,
                'animationfps': animationfps
            },
            objtype="bounceball",
            group=self,
            level=1,
        )
        # print o
        self.insert(0, o)
        return self

    def AddShield(self, memorydcs,
                  animationfps=30,
                  diffvector=Vector2(0.1, 0.1),
                  target=None,
                  anglespeed=0.05,
                  thistick=None
                  ):
        if not thistick:
            thistick = getFrameTime()
        o = ShootingGameObject(
            secToLifeEnd=-1.0,
            createdTime=thistick,
            collisionCricle=0.008,
            pos=target.pos,
            movefnargs={"targetobj": target, "diffvector":
                        diffvector, "anglespeed": anglespeed},
            movefn=ShootingGameObject.Move_SyncTarget,
            bounceDamping=.7,
            wallactionfn=ShootingGameObject.WallAction_None,
            shapefn=ShootingGameObject.ShapeChange_None,
            shapefnargs={
                'memorydcs': memorydcs,
                'animationfps': animationfps
            },
            objtype="shield",
            group=self,
        )
        self.append(o)
        return self

    def AddSuperShield(self, memorydcs,
                       animationfps=30,
                       diffvector=Vector2(0.1, 0.1),
                       target=None,
                       anglespeed=0.05,
                       thistick=None,
                       expireFn=None
                       ):
        if not thistick:
            thistick = getFrameTime()
        o = ShootingGameObject(
            secToLifeEnd=10.0,
            expireFn=expireFn,
            createdTime=thistick,
            collisionCricle=0.011,
            pos=target.pos,
            movefnargs={"targetobj": target, "diffvector":
                        diffvector, "anglespeed": anglespeed},
            movefn=ShootingGameObject.Move_SyncTarget,
            bounceDamping=.7,
            wallactionfn=ShootingGameObject.WallAction_None,
            shapefn=ShootingGameObject.ShapeChange_None,
            shapefnargs={
                'memorydcs': memorydcs,
                'animationfps': animationfps
            },
            objtype="supershield",
            group=self,
        )
        self.append(o)
        return self

    def AddExplosionEffect(self,
                           pos, memorydcs, dur=0.25,
                           movevector=Vector2(0, 0),
                           movefnargs={"accelvector": Vector2(0, 0)},
                           afterremovefn=None, afterremovefnarg=(),
                           thistick = None
                           ):
        if not thistick:
            thistick = getFrameTime()
        fps = len(memorydcs) / dur
        self.append(
            ShootingGameObject(
                pos=pos,
                secToLifeEnd=dur,
                createdTime=thistick,
                collisionCricle=0.03,
                movefn=ShootingGameObject.Move_Vector,
                movevector=movevector,
                movefnargs=movefnargs,
                wallactionfn=ShootingGameObject.WallAction_Remove,
                shapefn=ShootingGameObject.ShapeChange_None,
                shapefnargs={
                    'memorydcs': memorydcs,
                    'animationfps': fps,
                },
                afterremovefn=afterremovefn,
                afterremovefnarg=afterremovefnarg,
                objtype="effect",
                group=self,
            )
        )
        return self

    def addSpriteExplosionEffect(self, src):
        self.AddExplosionEffect(
            src.pos,
            src.group.effectmemorydcs,
            .25,
            movevector=src.movevector / 4,
            movefnargs={"accelvector": Vector2(0, 0)}
        )

    def AddStarField(self, number):
        thistick = getFrameTime()
        blackbrush = wx.Brush([0, 0, 0], wx.TRANSPARENT)
        brush = wx.Brush([0xff, 0xff, 0xff], wx.SOLID)
        pen = wx.Pen([0, 0, 0])
        # bitmap = wx.Bitmap( "resource/media-record.png")
        for a in range(number):
            # pen = wx.Pen([  random.randint(0,0xff) for b in range(4) ])
            # brush = wx.Brush([  random.randint(0,0xff) for b in range(4) ],
            # wx.SOLID)
            o = ShootingGameObject(
                secToLifeEnd=-1.0,
                createdTime=thistick,
                collisionCricle=0.002,
                pos=Vector2(random.random(), random.random()),
                movefn=ShootingGameObject.Move_Vector,
                movevector=Vector2(0, random.random() / 500),
                movefnargs={"accelvector": Vector2(0, 0)},
                # bounceDamping = 0.9,
                wallactionfn=ShootingGameObject.WallAction_Wrap,
                shapefn=ShootingGameObject.ShapeChange_Glitter,
                shapefnargs={
                    'radiusSpeed':  random2pi(),
                    'pen': pen,
                    'brush': brush,
                },
                objtype=None
                # bitmap = bitmap
            )
            self.append(o)
        return self

    def AddClockHands(self, hlen, clen, handstype):
        thistick = getFrameTime()
        blackbrush = wx.Brush([0, 0, 0], wx.TRANSPARENT)
        whitebrush = wx.Brush([0xff, 0xff, 0xff], wx.SOLID)
        blackpen = wx.Pen([0, 0, 0])
        nn = 10
        for a in range(nn):
            o = ShootingGameObject(
                secToLifeEnd=-1.0,
                createdTime=thistick,
                pos=Vector2(0.5, 0.5) + Vector2.rect(
                    hlen / nn * a, getHMSAngle(time.time(), handstype)),
                wallactionfn=ShootingGameObject.WallAction_Wrap,
                movefn=ShootingGameObject.Move_ClockHands,
                movefnargs={"handstype": handstype},
                collisionCricle=clen,
                shapefn=ShootingGameObject.ShapeChange_None,
                shapefnargs={
                    'brush': whitebrush,
                    'pen': blackpen,
                },
                objtype=None
            )
            self.append(o)
        return self

    def AddClockFace(self, flen, clen, num):
        thistick = getFrameTime()
        blackbrush = wx.Brush([0, 0, 0], wx.TRANSPARENT)
        whitebrush = wx.Brush([0xff, 0xff, 0xff], wx.SOLID)
        blackpen = wx.Pen([0, 0, 0])
        for a in range(num):
            o = ShootingGameObject(
                secToLifeEnd=-1.0,
                createdTime=thistick,
                pos=Vector2(0.5, 0.5) + Vector2.rect(
                    flen, math.radians(a * 360.0 / num)),
                movefn=ShootingGameObject.Move_NoAccel,
                wallactionfn=ShootingGameObject.WallAction_Wrap,
                shapefn=ShootingGameObject.ShapeChange_None,
                collisionCricle=clen,
                shapefnargs={
                    'brush': whitebrush,
                    'pen': blackpen,
                },
                objtype=None
            )
            self.append(o)


class GameChar(GameObjectGroup):

    """
    주 오브젝트와 그에 종속되는 shield, bullet 들
    """

    def __init__(self, *args, **kwds):
        def setAttr(name, defaultvalue):
            self.__dict__[name] = kwds.pop(name, defaultvalue)
            return self.__dict__[name]
        setAttr("membercount", 1)
        setAttr("teamname", "red")
        setAttr("teamcolor", "red")
        setAttr("resource", "red")

        setAttr("balldcs", [
            g_rcs.loadBitmap2MemoryDCArray("%sball.gif" % self.resource),
            g_rcs.loadBitmap2MemoryDCArray(
                "%sball1.gif" % self.resource, reverse=True)
        ])
        setAttr("bulletdcs", g_rcs.loadBitmap2MemoryDCArray(
            "%sbullet.png" % self.resource))
        setAttr("superbulletdcs", g_rcs.loadBitmap2MemoryDCArray(
            "%ssuper.png" % self.resource))
        setAttr("curcularmemorydc", g_rcs.loadBitmap2MemoryDCArray(
            "%sbullet1.png" % self.resource))

        GameObjectGroup.__init__(self, *args, **kwds)

        self.effectmemorydcs = g_rcs.loadBitmap2MemoryDCArray(
            "EvilTrace.png", 1, 8)
        self.ringmemorydcs = g_rcs.loadBitmap2MemoryDCArray("ring.png", 4, 4)
        self.earthmemorydcs = g_rcs.loadDirfiles2MemoryDCArray("earth")
        self.earthmemorydcsr = g_rcs.loadDirfiles2MemoryDCArray(
            "earth", reverse=True)
        self.ballbombmemorydcs = g_rcs.loadBitmap2MemoryDCArray(
            "explo1e.png", 8, 1)
        self.ballspawnmemorydcs = g_rcs.loadBitmap2MemoryDCArray(
            "spawn.png", 1, 6, reverse=True)

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
            'hitby': dict(statdict),
            'hitto': dict(statdict),
            'act': dict(statdict),

            "teamStartTime": getFrameTime(),
            "teamscore": 0,
            "maxscore": 0,
            "totalAItime": 0.0,
            "maxLevel": 0,
            "maxlost": 0,
            "maxcollision": 0,
            "maxlevelup": 0,
        }
        self.makeMember()

    def makeMember(self):
        while len(self) < self.membercount or self[self.membercount - 1].objtype != "bounceball":
            self.addMember(Vector2(random.random(), random.random()))

    def addBallExplosionEffect(self, effectObjs, g1, b):
        # pprint.pprint(("addBallExplosionEffect", self, g1))
        self.AddExplosionEffect(
            b.pos,
            g1.ballbombmemorydcs[1:],
            0.5,
            movevector=b.movevector / 4,
            movefnargs={"accelvector": Vector2(0, 0)},
            afterremovefn=self.addSpawnEffect,
            afterremovefnarg=(effectObjs, g1),
        )

    def addSpawnEffect(self, effectObjs, g1):
        # pprint.pprint(("addSpawnEffect", self, g1))
        newpos = Vector2(random.random(), random.random())
        self.AddExplosionEffect(
            newpos,
            g1.ballspawnmemorydcs,
            .5,
            movevector=Vector2(0, 0),
            movefnargs={"accelvector": Vector2(0, 0)},
            afterremovefn=g1.addMember,
            afterremovefnarg=(newpos,)
        )

    def addMember(self, newpos):
        self.statistic['act']['bounceball'] += 1
        self.statistic['act']['total'] += 1
        target = self.AddBouncBall(
            random.choice(self.balldcs),
            pos=newpos,
            #movevector=Vector2.rect(0.17, random2pi()),
            movevector=Vector2(0, 0),
            movelimit=self.getSpeedByType("bounceball"),
        )[0]
        # target.level = 1
        target.fireTimeDict = {}
        if self.enableshield:
            self.statistic['act']['shield'] += 1
            for i, a in enumerate(range(0, 360, 30)):
                self.AddShield(
                    # self.earthmemorydcs if i % 2 == 0 else
                    # self.earthmemorydcsr,
                    self.curcularmemorydc,
                    diffvector=Vector2(0.03, 0).addAngle(
                        2 * math.pi * a / 360.0),
                    target=target,
                    anglespeed=math.pi if i % 2 == 0 else -math.pi)
        return target


class ShootingAI(GameChar):

    def __init__(self, *args, **kwds):
        def setAttr(name, defaultvalue):
            self.__dict__[name] = kwds.pop(name, defaultvalue)
            return self.__dict__[name]
        setAttr("enableshield", True)
        setAttr("actratedict", {
            "circularbullet": 1.0 / 30 * 1,
            "superbullet": 1.0 / 10 * 1,
            "hommingbullet": 1.0 / 10 * 1,
            "bullet": 1.0 * 2,
            "accel": 1.0 * 30
        })
        setAttr("effectObjs", [])
        GameChar.__init__(self, *args, **kwds)

    # AI start funcion
    def FireAndAutoMoveByTime(self, aimingtargetlist, thisFPS=60, thistick=0):
        self.thistick = thistick
        self.tdur = self.thistick - self.statistic["teamStartTime"]
        self.thisFPS = thisFPS

        # 최대 사용 가능 action 제한
        self.usableBulletCountDict = {}
        for act in ["circularbullet", "superbullet", "hommingbullet", "bullet", "accel"]:
            self.usableBulletCountDict[act] = self.tdur * self.actRatePerSec(
                act) * self.membercount - self.statistic['act'][act]

        srclist = self.getBounceBalls()
        while srclist:
            src = random.choice(srclist)
            srclist.remove(src)
            src.clearAccelVector()

            sttime = getFrameTime()
            actions = self.SelectAction(aimingtargetlist, src)
            self.statistic["totalAItime"] += getFrameTime() - sttime

            for act, actargs in actions:
                if self.actCount(act) > 0:
                    self.statistic['act'][act] += 1
                    if act == "circularbullet":
                        self.AddCircularBullet2(src.pos, self.curcularmemorydc)
                    elif act == "superbullet":
                        if actargs:
                            self.AddTargetSuperBullet(
                                src.pos, actargs, self.superbulletdcs)
                        else:
                            print "Error %s %s %s" % (act, src, actargs)
                    elif act == "hommingbullet":
                        if actargs:
                            self.AddHommingBullet(
                                src.pos,
                                actargs,
                                self.ringmemorydcs,
                                expireFn=self.effectObjs.addSpriteExplosionEffect
                            )
                        else:
                            print "Error %s %s %s" % (act, src, actargs)
                    elif act == "bullet":
                        if actargs:
                            self.AddTargetFiredBullet(
                                src.pos, actargs, self.bulletdcs)
                        else:
                            print "Error %s %s %s" % (act, src, actargs)
                    elif act == "accel":
                        if actargs:
                            src.setAccelVector(actargs)
                            self.statistic['hitto'][act] += abs(actargs)
                        else:
                            print "Error %s %s %s" % (act, src, actargs)
                    else:
                        pass
                    src.fireTimeDict[act] = self.thistick
                else:
                    if act != 'doNothing':
                        print "%s action %s overuse fail" % (self.teamname, act)
        self.AutoMoveByTime(thistick)
        return self
    # 최대 사용 가능 action 제한

    def actCount(self, act):
        return self.usableBulletCountDict.get(act, 0)

    def actRatePerSec(self, act):
        return self.actratedict.get(act, 0)
    # utility functions

    def getObjectByTypes(self, filterlist):
        return [a for a in self if a.objtype in filterlist]

    def getFilterdObjects(self, aimingtargetlist, filterlist):
        return sum([a.getObjectByTypes(filterlist) for a in aimingtargetlist], [])

    # advanced AI functions
    def findTarget(self, src, objtypes, filterfn, aimingtargetlist):
        # select target filtered by objtypelist and filterfn
        target = None
        olist = self.getFilterdObjects(aimingtargetlist, objtypes)
        if olist:
            target = min(olist, key=filterfn)
        targetlen = target.lento(src) if target else 1.5
        return target, targetlen

    def getAimPos(self, srcpos, s1, target):
        # estimate target pos by target speed
        vt = target.pos - srcpos
        s2 = abs(target.movevector)
        if s2 == 0:
            return target.pos
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

    def getBounceBalls(self):
        return [a for a in self[:self.membercount] if a.objtype == "bounceball"]

    def getAllBounceBalls(self, aimingtargetlist):
        return sum([a.getBounceBalls() for a in aimingtargetlist], [])

    def selectRandomBall(self, aimingtargetlist):
        targetobjs = self.getAllBounceBalls(aimingtargetlist)
        return random.choice(targetobjs) if targetobjs else None

    # 실제 각 AI 별로 다르게 만들어야 하는 함수
    def SelectAction(self, aimingtargetlist, src):
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
                cando = random.random() < p * self.actCount(act)
            else:
                cando = self.actCount(act) > 0 and random.random() < p
            if cando:
                if act in ["hommingbullet", "superbullet", "bullet", "accel"] and not obj:
                    continue
                rtn.append([act, obj])
        return rtn


class AI1(ShootingAI):

    def SelectAction(self, aimingtargetlist, src):
        randomtarget = self.selectRandomBall(aimingtargetlist)
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


class AI2(ShootingAI):

    def __init__(self, *args, **kwds):
        def setAttr(name, defaultvalue):
            self.__dict__[name] = kwds.pop(name, defaultvalue)
            return self.__dict__[name]
        setAttr("inoutrate", 0.5)
        ShootingAI.__init__(self, *args, **kwds)

    def SelectAction(self, aimingtargetlist, src):
        fps = self.thisFPS

        # calc fire target
        neartarget, nearlen = self.findTarget(src, [
                                              'bounceball'], src.lento, aimingtargetlist)
        randomtarget = self.selectRandomBall(aimingtargetlist)

        hommingtarget = self.getFireTarget(
            src, "hommingbullet", neartarget, ((0.5, 0.1),))
        supertarget = self.getFireTarget(
            src, "superbullet", neartarget, ((0.3, 0.1),))
        supertargetpos = self.getAimPos(src.pos, self.getSpeedByType(
            'superbullet'), supertarget) if supertarget else None

        bullettarget = self.selectByLenRate(
            nearlen, src.fireTimeDict.get("bullet", 0),
            ((0.3, 1 / self.actRatePerSec("bullet") / 4, neartarget),
            (2, 1 / self.actRatePerSec("bullet") / 1.5, randomtarget),)
        )
        bullettargetpos = self.getAimPos(src.pos, self.getSpeedByType(
            'bullet'), bullettarget) if bullettarget else None

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
        dangertarget, dangerlen = self.findTarget(
            src,
            ['bounceball', 'superbullet', 'hommingbullet',
                'bullet', "circularbullet"],
            getDangerLevel,
            aimingtargetlist
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


class AI0Test(ShootingAI):

    # def __init__(self, *args, **kwds):
    #     def setAttr(name, defaultvalue):
    #         self.__dict__[name] = kwds.pop(name, defaultvalue)
    #         return self.__dict__[name]
    #     setAttr("posnumber", 0)
    #     ShootingAI.__init__(self, *args, **kwds)

    def SelectAction(self, aimingtargetlist, src):
        # super 로 맞춰야햘 type
        dangertarget, dangerlen = self.findTarget(
            src, ['bounceball', 'superbullet', 'hommingbullet'], src.lento, aimingtargetlist)

        # bullet 로 맞춰야할 type
        neartarget, nearlen = self.findTarget(
            src, ['bounceball'], src.lento, aimingtargetlist)

        accelvector = Vector2.rect(random.random() / 14.0, random2pi())

        bullettarget = self.getFireTarget(
            src, "bullet", neartarget, ((0.3, 0.04), (2, 0.2),))
        supertarget = self.getFireTarget(
            src, "superbullet", neartarget, ((0.3, 0.1),))
        hommingtarget = self.getFireTarget(
            src, "hommingbullet", neartarget, ((0.5, 0.1),))

        supertargetpos = supertarget.pos if supertarget else None
        bullettargetpos = self.getAimPos(src.pos, self.getSpeedByType(
            'bullet'), bullettarget) if bullettarget else None
        actions = (
            # action, probability, object
            ("bullet", 0.2, bullettargetpos),
        )
        return self.mapPro2Act(actions, True)


class AI0Inner(ShootingAI):

    def SelectAction(self, aimingtargetlist, src):
        accelvector = (Vector2(0.5, 0.5) - src.pos).normalized() / 20.0

        actions = (
            # action, probability, object
            ("accel", 0.5, accelvector),
        )
        return self.mapPro2Act(actions, True)


class AI0Random(ShootingAI):

    def SelectAction(self, aimingtargetlist, src):
        accelvector = Vector2.rect(random.random() / 14.0, random2pi())

        actions = (
            # action, probability, object
            ("accel", 0.5, accelvector),
        )
        return self.mapPro2Act(actions, True)


# 주 canvas class 들 wxPython전용.
class wxGameContentsControl(wx.Control, FPSlogic):
    randteam = [
        {"resource": "white", "color": wx.Colour(0xff, 0xff, 0xff)},
        {"resource": "orange", "color": wx.Colour(0xff, 0x7f, 0x00)},
        {"resource": "purple", "color": wx.Colour(0xff, 0x00, 0xff)},
        {"resource": "grey", "color": wx.Colour(0x7f, 0x7f, 0x7f)},
        {"resource": "red", "color": wx.Colour(0xff, 0x00, 0x00)},
        {"resource": "yellow", "color": wx.Colour(0xff, 0xff, 0x00)},
        {"resource": "green", "color": wx.Colour(0x00, 0xff, 0x00)},
        {"resource": "blue", "color": wx.Colour(0x00, 0xff, 0xff)},
    ]

    def __init__(self, *args, **kwds):
        def setAttr(name, defaultvalue):
            self.__dict__[name] = kwds.pop(name, defaultvalue)
            return self.__dict__[name]

        wx.Control.__init__(self, *args, **kwds)
        self.Bind(wx.EVT_PAINT, self._OnPaint)
        self.Bind(wx.EVT_SIZE, self._OnSize)
        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)

        # self.SetBackgroundStyle(wx.BG_STYLE_CUSTOM)
        self.dispgroup = []
        self.FPSTimerInit(getFrameTime, 70)

    def OnKeyDown(self, evt):
        keycode = evt.GetKeyCode()
        if keycode == wx.WXK_ESCAPE:
            self.FPSTimerDel()
            self.framewindow.Close()
        else:
            # self.GetParent().noanimation = not self.GetParent().noanimation
            # self.framewindow.OnSize(None)
            self.pause = not self.pause

            evt.Skip()

    def _OnSize(self, evt):
        self.clientsize = self.GetClientSize()
        if self.clientsize.x < 1 or self.clientsize.y < 1:
            return
        self.Refresh(False)
        self.Update()

    def _OnPaint(self, evt):
        # if self.GetParent().noanimation:
        #    return
        #pdc = wx.AutoBufferedPaintDC(self)
        pdc = wx.BufferedPaintDC(self)
        self.DrawToWxDC(pdc)

    def DrawToWxDC(self, pdc):
        for a in self.dispgroup:
            a.DrawToWxDC(pdc)

    def doFPSlogic(self, frameinfo):
        bb = ["%s:%s" % aa for aa in frameinfo.items()]
        a = [len(b) for b in self.dispgroup]
        titlestr = "Frame:%s obj:%s " % (bb, a)
        # self.GetParent().SetTitle(titlestr)
        return titlestr

    def makeCollisionDict(self):
        # 현재 위치를 기준으로 collision / interaction 검사하고
        rule = {
            'bounceball': ['bounceball', 'shield', 'supershield', 'bullet', 'circularbullet', 'superbullet', 'hommingbullet'],
            'shield': ['bounceball', 'shield', 'supershield', 'bullet', 'circularbullet', 'superbullet', 'hommingbullet'],
            'supershield': ['supershield', 'superbullet', 'hommingbullet'],
            'bullet': ['bounceball', 'shield', 'supershield', 'bullet', 'circularbullet', 'superbullet', 'hommingbullet'],
            'circularbullet': ['bounceball', 'shield', 'supershield', 'bullet', 'circularbullet', 'superbullet', 'hommingbullet'],
            'superbullet': ['supershield', 'superbullet', 'hommingbullet'],
            'hommingbullet': ['supershield', 'superbullet', 'hommingbullet'],
            'effect': [],
            None: [],
        }
        # get all collision list { src: [ t1, t1.. ], .. }
        buckets = []
        for aa in self.objplayers:
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
                        o1.checkCollisionAppend(o2, resultdict, rule)
        return resultdict, cmpsum

    def doScoreSimple(self, resultdict):
        ischanagestatistic = False
        for src, targets in resultdict.iteritems():
            # 충돌한 것이 bounceball 이면
            if src.objtype == 'bounceball':
                ischanagestatistic = True
                src.group.addBallExplosionEffect(
                    self.effectObjs, src.group, src)
                src.enabled = False

                srcLostScore = src.getDelScore(math.sqrt(src.level))
                src.group.statistic["maxlost"] = max(
                    src.group.statistic["maxlost"], srcLostScore)
                src.group.statistic["teamscore"] -= srcLostScore

                src.group.statistic["hitby"]['total'] += 1

                uplevel = srcLostScore / len(targets)
                src.group.statistic["maxcollision"] = max(
                    src.group.statistic["maxcollision"], len(targets))

                for target in targets:
                    target.group.statistic["hitto"]['total'] += 1

                    target.group.statistic["hitto"][target.objtype] += 1
                    src.group.statistic["hitby"][target.objtype] += 1

                    if target.objtype != 'bounceball':

                        if target.group and target.group[0].objtype == 'bounceball':
                            oldlevel = target.group[0].level
                            target.group[0].level += uplevel
                            target.group.statistic['maxLevel'] = max(target.group[
                                                                     0].level, target.group.statistic['maxLevel'])
                            target.group.statistic["maxlevelup"] = max(
                                target.group.statistic["maxlevelup"], uplevel)

                    # if target.objtype not in [
                    # 'bounceball','supershield','shield' ]:
                    target.group.statistic["teamscore"] += uplevel
                    target.group.statistic["maxscore"] = max(target.group.statistic[
                                                             "maxscore"], target.group.statistic["teamscore"])

            else:
                src.enabled = False
                self.effectObjs.addSpriteExplosionEffect(src)
        return ischanagestatistic

    def doScore(self, resultdict):
        ischanagestatistic = False
        for src, targets in resultdict.iteritems():
            # 충돌한 것이 bounceball 이면
            if src.objtype == 'bounceball':
                ischanagestatistic = True
                src.group.addBallExplosionEffect(
                    self.effectObjs, src.group, src)
                src.enabled = False

                srcLostScore = src.getDelScore(math.sqrt(src.level))
                src.group.statistic["maxlost"] = max(
                    src.group.statistic["maxlost"], srcLostScore)
                src.group.statistic["teamscore"] -= srcLostScore

                src.group.statistic["hitby"]['total'] += 1

                uplevel = srcLostScore * 2 / len(targets)
                src.group.statistic["maxcollision"] = max(
                    src.group.statistic["maxcollision"], len(targets))

                for target in targets:
                    target.group.statistic["hitto"]['total'] += 1

                    target.group.statistic["hitto"][target.objtype] += 1
                    src.group.statistic["hitby"][target.objtype] += 1

                    if target.objtype != 'bounceball':

                        if target.group and target.group[0].objtype == 'bounceball':
                            oldlevel = target.group[0].level
                            target.group[0].level += uplevel
                            target.group.statistic['maxLevel'] = max(target.group[
                                                                     0].level, target.group.statistic['maxLevel'])
                            target.group.statistic["maxlevelup"] = max(
                                target.group.statistic["maxlevelup"], uplevel)

                            inclevel = int(target.group[
                                           0].level) - int(oldlevel)
                            for i in range(inclevel):
                                target.group.statistic[
                                    'act']['supershield'] += 1
                                target.group.AddSuperShield(
                                    random.choice((
                                        target.group.earthmemorydcs, target.group.earthmemorydcsr)),
                                    diffvector=Vector2(
                                        0.06, 0).addAngle(random2pi()),
                                    target=target.group[0],
                                    anglespeed=random2pi(),
                                    expireFn=self.effectObjs.addSpriteExplosionEffect
                                )

                    if target.objtype not in ['bounceball', 'supershield', 'shield']:
                        target.group.statistic["teamscore"] += uplevel
                        target.group.statistic["maxscore"] = max(target.group.statistic[
                                                                 "maxscore"], target.group.statistic["teamscore"])
            else:
                src.enabled = False
                self.effectObjs.addSpriteExplosionEffect(src)
        return ischanagestatistic
    fdata = [
        ["AI Class",     "%s",  "%s"],
        ["color",   "%s",  "%s"],
        ["resource", "%s",  "%s"],
        ["member", "%d",  "%s"],

        ["maxscore", "%.2f", "%s"],
        ["score",  "%.2f", "%s"],
        ["rank",   "%d",  "%s"],
        ["maxLevel", "%.2f", "%s"],
        ["maxlost", "%.2f", "%s"],
        ["maxcollision", "%d", "%s"],
        ["maxlevelup", "%.2f", "%s"],
        ["AI time", "%.2f", "%s"],
        ["Time",   "%.2f", "%s"],
        ["objs",   "%d", "%s"],
    ]
    fdata2 = [
        ["score",  "%.2f", "%s"],
        ["rank",   "%d",  "%s"],
    ]

    def initInfoGrid(self):
        if hasattr(self, 'gridinited'):
            return
        self.gridinited = True
        print "initing grid"

        # initing info grid
        fdata = self.fdata
        maxmember = 0
        for i in self.objplayers:
            maxmember = max(maxmember, i.membercount)
        if self.infogrid.GetNumberRows() < len(fdata) + maxmember:
            self.infogrid.AppendRows(len(fdata) + len(self.objplayers[
                                     0].statistic["hitby"]) + maxmember - self.infogrid.GetNumberRows())
        if self.infogrid.GetNumberCols() < len(self.objplayers):
            self.infogrid.AppendCols(len(
                self.objplayers) - self.infogrid.GetNumberCols())

        for i, d in enumerate(fdata):
            self.infogrid.SetRowLabelValue(i, d[0])

        for i, d in enumerate(self.objplayers[0].statistic["hitby"].iterkeys(), len(fdata)):
            self.infogrid.SetRowLabelValue(i, d)

        for i, d in enumerate(self.objplayers):
            # self.infogrid.SetColLabelValue(i, d.__class__.__name__)
            self.infogrid.SetColLabelValue(i, d.teamname)
        for i in range(maxmember):
            self.infogrid.SetRowLabelValue(len(fdata) + len(self.objplayers[
                                           0].statistic["hitby"]) + i, "bounceball%d" % (i + 1,))

        for x, aa in enumerate(self.objplayers):
            for y, j in enumerate([aa.__class__.__name__, aa.teamcolor, aa.resource, aa.membercount, ]):
                self.infogrid.SetCellValue(y, x, fdata[y][1] % j)
        for r in range(self.infogrid.GetNumberRows()):
            for c in range(self.infogrid.GetNumberCols()):
                self.infogrid.SetCellBackgroundColour(
                    r, c, self.objplayers[c].teamcolor)
        self.infogrid.SetRowLabelSize(-1)  # wx.GRID_AUTOSIZE)

        # initing score grid
        fdata2 = self.fdata2
        tmpdict = {}
        for i in self.objplayers:
            tmpdict.setdefault(i.teamname, []).append(i)
        self.teamscores = []
        for n, v in tmpdict.iteritems():
            self.teamscores.append({
                                   'name': n, 'chars': v, 'score': 0, 'rank': 0})

        self.teamscores.sort(key=lambda x: x["name"])

        if self.scoregrid.GetNumberCols() < len(self.teamscores):
            self.scoregrid.AppendCols(len(
                self.teamscores) - self.scoregrid.GetNumberCols())

        for i, d in enumerate(self.teamscores):
            self.scoregrid.SetColLabelValue(i, d['name'])

        if self.scoregrid.GetNumberRows() < len(fdata2):
            self.scoregrid.AppendRows(len(
                fdata2) - self.scoregrid.GetNumberRows())
        for i, d in enumerate(fdata2):
            self.scoregrid.SetRowLabelValue(i, d[0])

    def updateInfoGrid(self, repeatinfo):
        # return
        ttime = getFrameTime()
        # self.framewindow.SetTitle(str([ "%s:%.2f" % aa for aa in
        # self.frameinfo.items() ]))
        self.initInfoGrid()

        # fill info grid
        fdata = self.fdata

        for j, t in enumerate(self.objplayers):
            for i, d in enumerate(self.objplayers[j].statistic["hitby"].iterkeys(), len(fdata)):
                self.infogrid.SetCellValue(
                    i, j,
                    "%d/%d/%d" % (
                        self.objplayers[j].statistic["act"][d],
                        self.objplayers[j].statistic["hitto"][d],
                        self.objplayers[j].statistic["hitby"][d]
                    ))

        for i, t in enumerate(self.objplayers):
            bb = t.getBounceBalls()
            for j in range(t.membercount):
                if j < len(bb):
                    self.infogrid.SetCellValue(len(fdata) + len(self.objplayers[0].statistic[
                                               "hitby"]) + j, i, "%.2f,%.2f" % (bb[j].level, ttime - bb[j].createdTime))
                else:
                    self.infogrid.SetCellValue(len(fdata) + len(
                        self.objplayers[0].statistic["hitby"]) + j, i, ' ')

        ranklist = sorted(
            self.objplayers, key=lambda x: -x.statistic["teamscore"])
        for i, aa in enumerate(ranklist, 1):
            aa.statistic["teamrank"] = i

        aisum = 0
        pdata = []
        for aa in self.objplayers:
            pdata.append((
                aa.statistic["maxscore"],
                aa.statistic["teamscore"],
                aa.statistic["teamrank"],
                aa.statistic["maxLevel"],
                aa.statistic["maxlost"],
                aa.statistic["maxcollision"],
                aa.statistic["maxlevelup"],
                aa.statistic["totalAItime"],
                ttime - aa.statistic["teamStartTime"],
                len(aa),
            ))
        for i in range(len(pdata[0])):
            for j in range(len(pdata)):
                try:
                    self.infogrid.SetCellValue(
                        i + 4, j, fdata[i + 4][1] % pdata[j][i])
                except:
                    self.infogrid.SetCellValue(
                        i + 4, j, fdata[i + 4][2] % pdata[j][i])

        # fill score grid
        fdata2 = self.fdata2
        for d in self.teamscores:
            d['score'] = 0
        for d in self.teamscores:
            for j in d['chars']:
                d['score'] += j.statistic['teamscore']

        ranklist = sorted(self.teamscores, key=lambda x: -x["score"])
        for i, aa in enumerate(ranklist, 1):
            aa['rank'] = i

        for i, d in enumerate(self.teamscores):
            for j, d2 in enumerate(fdata2):
                self.scoregrid.SetCellValue(j, i, d2[1] % d[d2[0]])

    def doFireAndAutoMoveByTime(self, frameinfo):
        # 그룹내의 bounceball 들을 AI automove 한다.
        # 자신과 같은 팀을 제외한 targets을 만든다.
        selmov = self.objplayers[:]
        random.shuffle(selmov)
        for aa in selmov:
            targets = []
            for bb in self.objplayers:
                if aa.teamname != bb.teamname:
                    targets.append(bb)
            aa.FireAndAutoMoveByTime(targets, frameinfo[
                                     'ThisFPS'], self.thistick)

    def makeState(self):
        """
        savelist = [
            {
            'teamname': teamname,
            'classname': AI class name,
            'objs': [ (type, pos, mvvt)]
            }
        ]
        """
        savelist = []
        for og in self.dispgroup:
            teamname = None
            if hasattr(og, 'teamname'):
                teamname = og.teamname
            cog = {
                'id': og.ID,
                'teamname': teamname,
                'class': og.__class__.__name__,
                'objs': []
            }
            savelist.append(cog)
            for o in og:
                cog['objs'].append((o.ID, o.objtype, o.pos, o.movevector))
        # tosenddata = zlib.compress(pickle.dumps(savelist,
        # pickle.HIGHEST_PROTOCOL))
        tosenddata = pickle.dumps(savelist, pickle.HIGHEST_PROTOCOL)
        return tosenddata

    def saveState(self):
        tosenddata = self.makeState()
        with open('state.pklz', 'wb') as f:
            f.write(tosenddata)

    def loadState(self):
        with open('state.pklz', 'rb') as f:
            recvdata = f.read()
        # loadlist = pickle.loads(zlib.decompress(recvdata) )
        loadlist = pickle.loads(recvdata)
        pprint.pprint(loadlist)
        return loadlist


class ShootingGameControl(wxGameContentsControl):

    def makeBkObj(self, mdc,
                  drawfillfn,
                  movefnargs,
                  movevector,
                  ):
        return BackGroundSplite(
            secToLifeEnd=-1.0,
            createdTime=getFrameTime(),
            pos=Vector2(500, 500),
            movevector=movevector,
            movelimit=100,
            movefnargs={"accelvector": Vector2(1, 0)},
            movefn=BackGroundSplite.Move_Vector,
            bounceDamping=1.,
            wallactionfn=BackGroundSplite.WallAction_None,
            memorydc=mdc,
            drawfillfn=drawfillfn,
        )

    def __init__(self, *args, **kwds):
        wxGameContentsControl.__init__(self, *args, **kwds)
        self.SetBackgroundColour(wx.Colour(0x0, 0x0, 0x0))

        self.backgroup = GameObjectGroup()
        self.backgroup.append(
            self.makeBkObj(
                g_rcs.loadBitmap2MemoryDCArray("background.gif")[0],
                drawfillfn=BackGroundSplite.DrawFill_Both,
                movevector=Vector2.rect(100.0, random2pi()),
                movefnargs={"accelvector": Vector2(1, 0)}
            )
        )
        self.dispgroup.append(self.backgroup)

        self.effectObjs = GameObjectGroup()

        teams = [
            {"AIClass": AI2, "teamname": 'team0', 'resource': 0},
            {"AIClass": AI2, "teamname": 'team1', 'resource': 1},
            {"AIClass": AI2, "teamname": 'team2', 'resource': 2},
            {"AIClass": AI2, "teamname": 'team3', 'resource': 3},
            {"AIClass": AI2, "teamname": 'team4', 'resource': 4},
            {"AIClass": AI2, "teamname": 'team5', 'resource': 5},
            {"AIClass": AI2, "teamname": 'team6', 'resource': 6},
            {"AIClass": AI2, "teamname": 'team7', 'resource': 7},
        ] * 1
        self.objplayers = []
        for sel, d in zip(itertools.cycle(self.randteam), teams):
            selpos = d.get('resource', -1)
            if selpos >= 0 and selpos < len(self.randteam):
                sel = self.randteam[selpos]
            self.objplayers.append(
                d["AIClass"](
                    resource=sel["resource"],
                    teamcolor=sel["color"],
                    teamname=d["teamname"],
                    membercount=1,
                    # enableshield = False,
                    # inoutrate = d / 100.0,
                    effectObjs=self.effectObjs,
                ))

        self.dispgroup.extend(self.objplayers)
        self.dispgroup.append(self.effectObjs)

        self.frontgroup = GameObjectGroup()
        for i in []:  # range(4):
            self.frontgroup.append(
                ShootingGameObject(
                    secToLifeEnd=-1.0,
                    collisionCricle=0.01,
                    pos=Vector2(random.random(), random.random()),
                    movevector=Vector2.rect(0.01, random2pi()),
                    movefnargs=dict({"accelvector": Vector2(0.01, 0)}),
                    movelimit=0.1,
                    movefn=ShootingGameObject.Move_Vector,
                    bounceDamping=1.,
                    wallactionfn=ShootingGameObject.WallAction_Wrap,
                    shapefn=ShootingGameObject.ShapeChange_None,
                    shapefnargs={
                        'memorydcs': g_rcs.loadBitmap2MemoryDCArray("Clouds.png", 1, 4),
                        "startimagenumber":  i,
                        'animationfps': 0
                    },
                    objtype="background",
                    group=None,
                    level=1,
                )
            )
        #~ for i in range(4):
            #~ self.frontgroup.append(
                #~ self.makeBkObj(
                    #~ g_rcs.loadBitmap2MemoryDCArray("background2.png")[0],
                    #~ drawfillfn = BackGroundSplite.DrawFill_Both,
                    #~ movevector = Vector2.rect(100.0, random2pi()),
                    #~ movefnargs = dict({ "accelvector": Vector2(1,0) })
                    #~)
                #~)
        self.dispgroup.append(self.frontgroup)

        nowstart = getFrameTime()
        for dg in self.dispgroup:
            for o in dg:
                self.createdTime = nowstart

        self.statObjN = Statistics()
        self.statCmpN = Statistics()
        self.statPacketL = Statistics()

    def doFPSlogic(self, frameinfo):
        self.thistick = getFrameTime()
        wxGameContentsControl.doFPSlogic(self, frameinfo)
        self.frameinfo = frameinfo
        self.frameinfo['objcount'] = sum([len(a) for a in self.objplayers])

        self.statObjN.update(self.frameinfo['objcount'])

        self.doFireAndAutoMoveByTime(frameinfo)

        # make collision dictionary
        resultdict, self.frameinfo['cmpcount'] = self.makeCollisionDict()
        self.statCmpN.update(self.frameinfo['cmpcount'])
        # do score
        ischanagestatistic = self.doScore(resultdict)
        # ischanagestatistic = self.doScoreSimple(resultdict)

        # 결과에 따라 삭제한다.
        for aa in self.objplayers:
            aa.RemoveDisabled()

        self.effectObjs.AutoMoveByTime(self.thistick).RemoveDisabled()
        self.backgroup.AutoMoveByTime(self.thistick)
        for o in self.backgroup:
            if random.random() < 0.001:
                o.setAccelVector(o.getAccelVector().addAngle(random2pi()))
        self.frontgroup.AutoMoveByTime(self.thistick)
        for o in self.frontgroup:
            if random.random() < 0.001:
                o.setAccelVector(o.getAccelVector().addAngle(random2pi()))

        senddata = ' '  # self.makeState()
        self.statPacketL.update(len(senddata))

        # 화면에 표시
        if ischanagestatistic:
            self.updateInfoGrid({})
            print 'objs:', self.statObjN
            print 'cmps:', self.statCmpN
            print 'packetlen:', self.statPacketL
            print 'fps:', self.frameinfo['stat']
        self.Refresh(False)


class TestControl(wxGameContentsControl):

    def __init__(self, *args, **kwds):
        wxGameContentsControl.__init__(self, *args, **kwds)
        self.SetBackgroundColour(wx.Colour(0x0, 0x0, 0x0))

        self.effectObjs = GameObjectGroup()
        #~ self.objplayers = []
        #~ teams = [
            #~ { "AIClass": AI0Test  ,"teamname": 'team1', 'resource': 1, 'posnumber': 0 },
            #~ { "AIClass": AI0Test  ,"teamname": 'team1', 'resource': 1, 'posnumber': 1 },
            #~ { "AIClass": AI0Test  ,"teamname": 'team1', 'resource': 1, 'posnumber': 2 },
            #~ { "AIClass": AI0Test  ,"teamname": 'team1', 'resource': 1, 'posnumber': 3 },
            #~ { "AIClass": AI0Test  ,"teamname": 'team1', 'resource': 1, 'posnumber': 4 },
            #~ ]
        #~ for sel,d in zip(itertools.cycle(self.randteam),teams):
            #~ selpos = d.get('resource', -1)
            #~ if  selpos >=  0 and selpos < len(self.randteam):
                #~ sel = self.randteam[selpos]
            #~ self.objplayers.append(
                #~ d["AIClass"](
                    #~ resource = sel["resource"],
                    #~ teamcolor = sel["color"],
                    #~ teamname = d["teamname"],
                    #~ membercount = 1,
                    #~ enableshield = False,
                    #~ posnumber = d['posnumber'],
                    # ~ #inoutrate = d / 100.0,
                    #~ effectObjs = self.effectObjs,
                #~))
        teams = [
            {"AIClass": AI2},
        ] * 50
        self.objplayers = []
        i = 0
        for sel, d in zip(itertools.cycle(self.randteam), teams):
            i += 1
            selpos = d.get('resource', -1)
            if selpos >= 0 and selpos < len(self.randteam):
                sel = self.randteam[selpos]
            self.objplayers.append(
                d["AIClass"](
                    resource=sel["resource"],
                    teamcolor=sel["color"],
                    teamname=d.get("teamname", 'team%d' % i),
                    membercount=1,
                    enableshield=False,
                    # inoutrate = d / 100.0,
                    actratedict={
                        "circularbullet": 0,
                        "superbullet": 0,
                        "hommingbullet": 0.1,
                        "bullet": 0.01,
                        "accel": 1.0 * 30
                    },
                    effectObjs=self.effectObjs,
                ))

        self.dispgroup.extend(self.objplayers)
        self.dispgroup.append(self.effectObjs)

        nowstart = getFrameTime()
        for dg in self.dispgroup:
            for o in dg:
                self.createdTime = nowstart

    def doFPSlogic(self, frameinfo):
        self.thistick = getFrameTime()
        wxGameContentsControl.doFPSlogic(self, frameinfo)
        self.frameinfo = frameinfo
        self.frameinfo['objcount'] = sum([len(a) for a in self.objplayers])

        self.doFireAndAutoMoveByTime(frameinfo)

        # make collision dictionary
        resultdict, self.frameinfo['cmpcount'] = self.makeCollisionDict()

        ischanagestatistic = self.doScoreSimple(resultdict)

        # 결과에 따라 삭제한다.
        for aa in self.objplayers:
            aa.RemoveDisabled()

        self.effectObjs.AutoMoveByTime(self.thistick).RemoveDisabled()

        # 화면에 표시
        if ischanagestatistic:
            self.updateInfoGrid({})
        self.Refresh(False)


class ClockControl(wxGameContentsControl):

    def __init__(self, *args, **kwds):
        wxGameContentsControl.__init__(self, *args, **kwds)
        self.SetBackgroundColour(wx.Colour(0x0, 0x0, 0x0))
        blackbrush = wx.Brush([0, 0, 0], wx.TRANSPARENT)
        whitebrush = wx.Brush([0xff, 0xff, 0xff], wx.SOLID)
        blackpen = wx.Pen([0, 0, 0])
        self.objs = GameObjectGroup()
        o = ShootingGameObject(
            secToLifeEnd=-1.0,
            pos=Vector2(0.5, 0.5),
            movefn=ShootingGameObject.Move_NoAccel,
            wallactionfn=ShootingGameObject.WallAction_Wrap,
            shapefn=ShootingGameObject.ShapeChange_None,
            collisionCricle=0.01,
            shapefnargs={
                'brush': whitebrush,
                'pen': blackpen,
            },
        )
        self.objs.append(o)

        self.objs.AddClockFace(0.4, 0.005, 60)
        self.objs.AddClockFace(0.4, 0.01, 12)
        self.objs.AddStarField(100)

        self.objs.AddClockHands(0.37, 0.005, 2)
        self.objs.AddClockHands(0.33, 0.005, 1)
        self.objs.AddClockHands(0.3, 0.005, 0)

        self.objs.AddBouncBall(g_rcs.loadDirfiles2MemoryDCArray("earth"))

        o = ShootingGameObject(
            secToLifeEnd=-1.0,
            collisionCricle=0.016,
            pos=Vector2(0.5, 0.5),
            movevector=Vector2.rect(0.17, random2pi()),
            movefn=ShootingGameObject.Move_FollowTarget,
            movefnargs={"accelvector": Vector2(
                0.1, 0.1), "targetobj": self.objs[0]},
            bounceDamping=.7,
            wallactionfn=ShootingGameObject.WallAction_Bounce,
            shapefn=ShootingGameObject.ShapeChange_None,
            shapefnargs={
                'memorydcs': g_rcs.loadBitmap2MemoryDCArray("media-record.png"),
                'animationfps': 30
            },
            objtype="bounceball",
        )
        self.objs.append(o)

        self.dispgroup.extend([self.objs])

    def doFPSlogic(self, frameinfo):
        self.thistick = getFrameTime()
        wxGameContentsControl.doFPSlogic(self, frameinfo)
        self.objs.AutoMoveByTime(self.thistick)
        self.Refresh(False)


class MyFrame(wx.Frame):

    def __init__(self, *args, **kwds):
        kwds["style"] = wx.DEFAULT_FRAME_STYLE
        wx.Frame.__init__(self, *args, **kwds)
        self.panel_1 = ShootingGameControl(self, -1, size=(1000, 1000))
        # self.panel_1 = TestControl(self, -1, size=(1000, 1000))
        # self.panel_1 = ClockControl(self, -1, size=(1000, 1000))
        self.panel_1.framewindow = self

        self.button_1 = wx.Button(self, -1, "pause")
        self.button_2 = wx.Button(self, -1, "quit")
        self.button_3 = wx.Button(self, -1, "save")
        self.button_4 = wx.Button(self, -1, "load")

        self.grid_1 = wx.grid.Grid(self, -1, size=(1, 1))
        self.panel_1.infogrid = self.grid_1

        self.grid_2 = wx.grid.Grid(self, -1, size=(1, 1))
        self.panel_1.scoregrid = self.grid_2

        self.__set_properties()
        self.__do_layout()

        self.Bind(wx.EVT_BUTTON, self.evt_btn_pause, self.button_1)
        self.Bind(wx.EVT_BUTTON, self.evt_btn_quit, self.button_2)
        self.Bind(wx.EVT_BUTTON, self.evt_btn_save, self.button_3)
        self.Bind(wx.EVT_BUTTON, self.evt_btn_load, self.button_4)

    def __set_properties(self):
        self.SetTitle("wxGameFramework %s by kasworld" % Version)
        self.panel_1.SetMinSize((1000, 1000))
        self.grid_1.CreateGrid(1, 1)
        self.grid_2.CreateGrid(1, 1)

    def __do_layout(self):
        sizer_1 = wx.BoxSizer(wx.VERTICAL)
        sizer_2 = wx.BoxSizer(wx.HORIZONTAL)
        sizer_3 = wx.BoxSizer(wx.VERTICAL)
        sizer_4 = wx.BoxSizer(wx.HORIZONTAL)
        sizer_2.Add(self.panel_1, 0, wx.FIXED_MINSIZE, 0)
        sizer_4.Add(self.button_1, 0, 0, 0)
        sizer_4.Add(self.button_2, 0, 0, 0)
        sizer_4.Add(self.button_3, 0, 0, 0)
        sizer_4.Add(self.button_4, 0, 0, 0)
        sizer_3.Add(sizer_4, 1, wx.EXPAND, 0)
        sizer_3.Add(self.grid_1, 24, wx.EXPAND, 0)
        sizer_3.Add(self.grid_2, 10, wx.EXPAND, 0)
        sizer_2.Add(sizer_3, 1, wx.EXPAND, 0)
        sizer_1.Add(sizer_2, 1, wx.EXPAND, 0)
        self.SetSizer(sizer_1)
        sizer_1.Fit(self)
        self.Layout()
        self.panel_1.SetFocus()

    def evt_btn_pause(self, event):
        self.panel_1.pause = not self.panel_1.pause
        event.Skip()

    def evt_btn_quit(self, event):
        self.Close()
        event.Skip()

    def evt_btn_save(self, event):
        self.panel_1.saveState()
        event.Skip()

    def evt_btn_load(self, event):
        self.panel_1.loadState()
        event.Skip()


def runtest():
    app = wx.App()
    # app = wx.PySimpleApp(0)
    # wx.InitAllImageHandlers()
    frame_1 = MyFrame(None, -1, "", size=(1400, 1000))
    app.SetTopWindow(frame_1)
    frame_1.Show()
    app.MainLoop()

if __name__ == "__main__":
    runtest()
