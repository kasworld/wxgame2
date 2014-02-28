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

from wxgamelib import *


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


class GameChar(GameObjectGroup):

    """
    주 오브젝트와 그에 종속되는 shield, bullet 들
    """

    def __init__(self, *args, **kwds):
        def setAttr(name, defaultvalue):
            self.__dict__[name] = kwds.pop(name, defaultvalue)
            return self.__dict__[name]
        setAttr("enableshield", True)

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
                                expireFn=self.dispgroup[
                                    'effectObjs'].addSpriteExplosionEffect
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
        self.dispgroup = {}
        self.FPSTimerInit(70)

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

        self.dispgroup['backgroup'].DrawToWxDC(pdc)
        for o in self.dispgroup['objplayers']:
            o.DrawToWxDC(pdc)
        self.dispgroup['effectObjs'].DrawToWxDC(pdc)
        self.dispgroup['frontgroup'].DrawToWxDC(pdc)

    def doFPSlogic(self, frameinfo):
        return ''

    def makeState(self):
        """{
        'class': 'AI2',
        'id': 87,
        'objs': [(88, 'bounceball', Vector2(0.64, 0.50), Vector2(0.14, -0.24)),
               (91, 'shield', Vector2(0.61, 0.52), Vector2(0.09, -0.32)),
               (98, 'shield', Vector2(0.61, 0.51), Vector2(0.14, -0.15)),
               (99, 'shield', Vector2(0.66, 0.52), Vector2(0.08, -0.16)),
               (100, 'shield', Vector2(0.62, 0.48), Vector2(0.06, -0.19)),
               (277, 'supershield', Vector2(0.69, 0.47), Vector2(0.09, -0.31)),
               (369, 'bullet', Vector2(0.35, 0.23), Vector2(-0.39, -0.31))],
        'teamname': 'team6'},
        """
        savelist = []
        for og in self.dispgroup['objplayers']:
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
        return savelist

    def applyState(self, loadlist):
        self.dispgroup['objplayers'] = []
        for og in loadlist:
            if len(og['objs']) < 1:
                continue
            ol = og['objs'][0]

            # print ol
            gog = ShootingAI()
            gog.AddBouncBall(
                memorydcs=random.choice(gog.balldcs),
                pos= ol[2],
                movevector=ol[3]
            )
            self.dispgroup['objplayers'].append(gog)

    def saveState(self):
        # tosenddata = zlib.compress(pickle.dumps(savelist,
        # pickle.HIGHEST_PROTOCOL))
        savelist = self.makeState()
        tosenddata = pickle.dumps(savelist, pickle.HIGHEST_PROTOCOL)
        with open('state.pklz', 'wb') as f:
            f.write(tosenddata)

    def loadState(self):
        with open('state.pklz', 'rb') as f:
            recvdata = f.read()
        # loadlist = pickle.loads(zlib.decompress(recvdata) )
        try:
            loadlist = pickle.loads(recvdata)
        # pprint.pprint(loadlist)
            self.applyState(loadlist)
            return loadlist
        except:
            return


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

        self.dispgroup['backgroup'] = GameObjectGroup()
        self.dispgroup['backgroup'].append(
            self.makeBkObj(
                g_rcs.loadBitmap2MemoryDCArray("background.gif")[0],
                drawfillfn=BackGroundSplite.DrawFill_Both,
                movevector=Vector2.rect(100.0, random2pi()),
                movefnargs={"accelvector": Vector2(1, 0)}
            )
        )
        self.dispgroup['objplayers'] = []
        self.dispgroup['effectObjs'] = GameObjectGroup()
        self.dispgroup['frontgroup'] = GameObjectGroup()

    def doFPSlogic(self, frameinfo):
        self.loadState()

        self.thistick = getFrameTime()

        for o in self.dispgroup['objplayers']:
            o.AutoMoveByTime(self.thistick)

        self.dispgroup['effectObjs'].AutoMoveByTime(
            self.thistick).RemoveDisabled()
        self.dispgroup['backgroup'].AutoMoveByTime(self.thistick)
        for o in self.dispgroup['backgroup']:
            if random.random() < 0.001:
                o.setAccelVector(o.getAccelVector().addAngle(random2pi()))
        self.dispgroup['frontgroup'].AutoMoveByTime(self.thistick)
        for o in self.dispgroup['frontgroup']:
            if random.random() < 0.001:
                o.setAccelVector(o.getAccelVector().addAngle(random2pi()))

        self.Refresh(False)


class MyFrame(wx.Frame):

    def __init__(self, *args, **kwds):
        kwds["style"] = wx.DEFAULT_FRAME_STYLE
        wx.Frame.__init__(self, *args, **kwds)
        self.panel_1 = ShootingGameControl(self, -1, size=(1000, 1000))
        self.panel_1.framewindow = self

        self.__set_properties()
        self.__do_layout()

    def __set_properties(self):
        self.SetTitle("wxGameFramework %s by kasworld" % Version)
        self.panel_1.SetMinSize((1000, 1000))

    def __do_layout(self):
        sizer_1 = wx.BoxSizer(wx.VERTICAL)
        sizer_2 = wx.BoxSizer(wx.HORIZONTAL)
        sizer_2.Add(self.panel_1, 0, wx.FIXED_MINSIZE, 0)
        sizer_1.Add(sizer_2, 1, wx.EXPAND, 0)
        self.SetSizer(sizer_1)
        sizer_1.Fit(self)
        self.Layout()
        self.panel_1.SetFocus()


def runtest():
    app = wx.App()
    frame_1 = MyFrame(None, -1, "", size=(1000, 1000))
    app.SetTopWindow(frame_1)
    frame_1.Show()
    app.MainLoop()

if __name__ == "__main__":
    runtest()
