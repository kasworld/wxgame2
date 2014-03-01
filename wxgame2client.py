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

from wxgame2server import SpriteLogic, GameObjectGroup, getFrameTime
from wxgamelib import *

g_rcs = GameResource('resource')


class BackGroundSplite(SpriteLogic):

    """
    background scroll class
    repeat to fill background
    display dc, move, change image
    """

    def __init__(self, kwds):
        SpriteLogic.__init__(self, kwds)
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


class ShootingGameObject(SpriteLogic):

    """
    display and shape
    """

    def __init__(self, kwds):
        argsdict = {
            "shapefn": ShootingGameObject.ShapeChange_None,
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
        self.loadArgs(argsdict)
        SpriteLogic.__init__(self, kwds)

        self.baseCollisionCricle = self.collisionCricle
        self.shapefnargs['memorydcs'] = self.shapefnargs.get('memorydcs', None)
        if self.shapefnargs['memorydcs'] and not self.shapefnargs.get('dcsize', None):
            self.shapefnargs['dcsize'] = self.shapefnargs[
                'memorydcs'][0].GetSizeTuple()
        self.currentimagenumber = self.shapefnargs['startimagenumber']
        self.shapefnargs['animationfps'] = self.shapefnargs.get(
            'animationfps', 10)

        self.registerAutoMoveFn(self.shapefn, [])
        self.registerAutoMoveFn(ShootingGameObject.changeImage, [])

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
        if not self.enabled or not self.visible:
            return
        if self.shapefnargs['memorydcs']:
            self.Draw_MDC(pdc, clientsize, sizehint)
        else:
            self.Draw_Shape(pdc, clientsize, sizehint)


class GameObjectDisplayGroup(GameObjectGroup):

    def setAttrs(self, defaultdict, kwds):
        for k, v in defaultdict.iteritems():
            setattr(self, k, kwds.pop(k, v))

    def loadResource(self):
        if self.resoueceReady is True:
            return
        self.balldcs = [
            g_rcs.loadBitmap2MemoryDCArray("%sball.gif" % self.resource),
            g_rcs.loadBitmap2MemoryDCArray(
                "%sball1.gif" % self.resource, reverse=True)
        ]
        self.bulletdcs = g_rcs.loadBitmap2MemoryDCArray(
            "%sbullet.png" % self.resource)
        self.superbulletdcs = g_rcs.loadBitmap2MemoryDCArray(
            "%ssuper.png" % self.resource)
        self.curcularmemorydc = g_rcs.loadBitmap2MemoryDCArray(
            "%sbullet1.png" % self.resource)

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
        self.resoueceReady = True

        self.rcsdict = {
            'bounceball': self.balldcs[0],
            'bullet': self.bulletdcs,
            'hommingbullet': self.ringmemorydcs,
            'superbullet': self.superbulletdcs,
            'circularbullet': self.curcularmemorydc,
            'shield': self.curcularmemorydc,
            'supershield': self.earthmemorydcs,
        }

    def __init__(self, *args, **kwds):
        self.resoueceReady = False
        GameObjectGroup.__init__(self, *args, **kwds)
        self.loadResource()

    def makeMember(self):
        self.loadResource()
        GameObjectGroup.makeMember(self)

    def addMember(self, newpos):
        target = self.AddBouncBall(
            objtype='bounceball',
            pos=newpos,
            group=self,
            shapefn=ShootingGameObject.ShapeChange_None,
            shapefnargs={
                'memorydcs': random.choice(self.balldcs)
            },
        )
        # target.level = 1
        target.fireTimeDict = {}
        if self.enableshield:
            for i, a in enumerate(range(0, 360, 30)):
                self.AddShield(
                    memorydcs=self.curcularmemorydc,
                    diffvector=Vector2(0.03, 0).addAngle(
                        2 * math.pi * a / 360.0),
                    target=target,
                    anglespeed=math.pi if i % 2 == 0 else -math.pi)
        return target

    def AddBouncBall(self, **kwargs):
        o = ShootingGameObject(kwargs)
        self.insert(0, o)
        return o

    def AddShield(self, memorydcs, target, diffvector, anglespeed):
        o = SpriteLogic(dict(
            pos=target.pos,
            movefnargs={
                "targetobj": target,
                "anglespeed": anglespeed
            },
            shapefn=ShootingGameObject.ShapeChange_None,
            shapefnargs={
                'memorydcs': memorydcs,
            },
            objtype="shield",
            group=self,
        ))
        self.append(o)
        return self

    def DrawToWxDC(self, pdc):
        clientsize = pdc.GetSize()
        sizehint = min(clientsize.x, clientsize.y)
        for a in self:
            a.DrawToWxDC(pdc, clientsize, sizehint)
        return self



# 주 canvas class 들 wxPython전용.
class ShootingGameControl(wx.Control, FPSlogic):

    def __init__(self, *args, **kwds):
        wx.Control.__init__(self, *args, **kwds)
        self.Bind(wx.EVT_PAINT, self._OnPaint)
        self.Bind(wx.EVT_SIZE, self._OnSize)
        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        self.FPSTimerInit(70)
        self.SetBackgroundColour(wx.Colour(0x0, 0x0, 0x0))

        self.dispgroup = {}
        self.dispgroup['backgroup'] = GameObjectDisplayGroup()
        self.dispgroup['backgroup'].append(
            self.makeBkObj()
        )
        self.dispgroup['objplayers'] = []
        self.dispgroup['effectObjs'] = GameObjectDisplayGroup()
        self.dispgroup['frontgroup'] = GameObjectDisplayGroup()

    def makeBkObj(self):
        return BackGroundSplite(dict(
            objtype="background",
            movevector=Vector2.rect(100.0, random2pi()),
            memorydc=g_rcs.loadBitmap2MemoryDCArray("background.gif")[0],
            drawfillfn=BackGroundSplite.DrawFill_Both,
        ))

    def OnKeyDown(self, evt):
        keycode = evt.GetKeyCode()
        if keycode == wx.WXK_ESCAPE:
            self.framewindow.Close()

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

    def applyState(self, loadlist):
        self.dispgroup['objplayers'] = []
        for og in loadlist:
            gog = GameObjectDisplayGroup(resource=og['resource'])
            for objid, objtype, objpos, objmovevector in og['objs']:
                if objtype in gog.rcsdict:
                    o = ShootingGameObject(dict(
                        objtype=objtype,
                        pos=objpos,
                        movevector=objmovevector,
                        group=gog,
                        shapefn=ShootingGameObject.ShapeChange_None,
                        shapefnargs={
                            'memorydcs': gog.rcsdict[objtype]
                        },
                    ))
                    gog.append(o)
            self.dispgroup['objplayers'].append(gog)

    def loadState(self):
        with open('state.pklz', 'rb') as f:
            recvdata = f.read()
        try:
            loadlist = pickle.loads(recvdata)
        except:
            print 'state load fail'
            return

        self.applyState(loadlist)
        return loadlist

    def doFPSlogic(self, frameinfo):
        self.loadState()

        self.thistick = getFrameTime()

        # for o in self.dispgroup['objplayers']:
        #     o.AutoMoveByTime(self.thistick)

        self.dispgroup['effectObjs'].AutoMoveByTime(
            self.thistick).RemoveDisabled()

        self.dispgroup['backgroup'].AutoMoveByTime(self.thistick)
        for o in self.dispgroup['backgroup']:
            if random.random() < 0.001:
                o.setAccelVector(o.getAccelVector().addAngle(random2pi()))
        # print self.dispgroup

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


def test():
    app = wx.App()
    GameObjectDisplayGroup()

if __name__ == "__main__":
    runtest()
