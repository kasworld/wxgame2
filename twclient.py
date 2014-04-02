#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" wxgame client
    wxGameFramework
    Copyright 2011,2013,1014 kasw <kasworld@gmail.com>
"""

from twisted.internet import wxreactor
wxreactor.install()

# import t.i.reactor only after installing wxreactor:
from twisted.internet import reactor
from twisted.internet import protocol
from twisted.protocols.basic import Int32StringReceiver
from twisted.internet.protocol import ReconnectingClientFactory, ClientFactory
from twisted.internet import task
from twisted.python import log

from wxgame2lib import Version
import random
import math
import os
import os.path
import sys
import time
import argparse
import Queue

import wx
import wx.grid
import wx.lib.colourdb

from euclid import Vector2

from wxgame2lib import SpriteObj, random2pi, FPSMixin, updateDict, fromGzJson
from wxgame2lib import getFrameTime, putParams2Queue, toGzJsonParams
from wxgame2lib import ShootingGameMixin, Storage
from wxgame2lib import AI2 as GameObjectGroup


class GameResource(object):

    """ game resource loading with cache
    """

    def __init__(self, dirname):
        wx.InitAllImageHandlers()
        self.srcdir = os.path.dirname(os.path.abspath(sys.argv[0]))
        self.resourcedir = dirname
        self.rcsCache = {}

    def getcwdfilepath(self, filename):
        return os.path.join(self.srcdir, self.resourcedir, filename)

    def memorized(self, fn, name, *args, **kwds):
        key = (name, args, str(kwds))
        if self.rcsCache.get(key) is None:
            self.rcsCache[key] = fn(self.getcwdfilepath(name), *args, **kwds)
        return self.rcsCache[key]

    def Dir2MDCList(self, name, *args, **kwds):
        return self.memorized(GameResource._Dir2MDCList, name, *args, **kwds)

    def File2OPedMDCList(self, name, *args, **kwds):
        return self.memorized(GameResource._File2OPedMDCList, name, *args, **kwds)

    @staticmethod
    def makeRotatedImage(image, angle):
        rad = math.radians(-angle)
        xlen, ylen = image.GetWidth(), image.GetHeight()
        rimage = image.Rotate(rad, (xlen / 2, ylen / 2), True)
        xnlen, ynlen = rimage.GetWidth(), rimage.GetHeight()
        rsimage = rimage.Size(
            (xlen, ylen), (-(xnlen - xlen) / 2, -(ynlen - ylen) / 2))
        return rsimage

    @staticmethod
    def listOp(imglist, listop):
        if 'reverse' in listop:
            imglist.reverse()
        if 'addreverse' in listop:
            rrtn = imglist[:]
            rrtn.reverse()
            imglist += rrtn

    @staticmethod
    def rotateOp(image, *rotarg):
        rtn = []
        for a in range(*rotarg):
            rtn.append(wx.MemoryDC(
                GameResource.makeRotatedImage(image, a).ConvertToBitmap()
            ))
        return rtn

    @staticmethod
    def _File2OPedMDCList(imagefilename, scalearg=None, adjcharg=None, rotarg=None, slicearg=None, listop=()):
        """
        scalearg : tuple (width,height) : pixel
        adjcharg : tuple ( t, g, b, alpha) : float
        rotarg : tuple for range arg (start, end, step) : int
        slicearg : tuple (xslicenum,yslicenum,totalslice,yfirst) : int int int bool
        listop : tuple ('reverse' ,'addreverse' )
        """
        image = wx.Bitmap(imagefilename).ConvertToImage()
        if scalearg is not None:
            image = image.Scale(*scalearg)
        if adjcharg is not None:
            image = image.AdjustChannels(*adjcharg)

        if rotarg is not None:
            rtn = GameResource.rotateOp(image, *rotarg)
            GameResource.listOp(rtn, listop)
        elif slicearg is not None:
            rtn = GameResource.sliceOp(image, *slicearg)
            GameResource.listOp(rtn, listop)
        else:
            rtn = [wx.MemoryDC(image.ConvertToBitmap())]
        return rtn

    @staticmethod
    def sliceOp(image, *slicearg):
        rtn = []
        xslicenum, yslicenum, totalslice, yfirst = slicearg
        dcsize = image.GetSize()
        w, h = dcsize[0] / xslicenum, dcsize[1] / yslicenum
        if yfirst:
            for x in range(xslicenum):
                for y in range(yslicenum):
                    rtn.append(wx.MemoryDC(
                        image.GetSubImage(
                            wx.Rect(x * w, y * h, w, h)).ConvertToBitmap()
                    ))
        else:
            for y in range(yslicenum):
                for x in range(xslicenum):
                    rtn.append(wx.MemoryDC(
                        image.GetSubImage(
                            wx.Rect(x * w, y * h, w, h)).ConvertToBitmap()
                    ))
        if totalslice is not None:
            rtn = rtn[:totalslice]
        return rtn

    @staticmethod
    def _Dir2MDCList(dirname, reverse=False, addreverse=False):
        rtn = []
        filenames = sorted(os.listdir(dirname), reverse=reverse)
        for a in filenames:
            rtn.append(wx.MemoryDC(wx.Bitmap(dirname + "/" + a)))
        if addreverse:
            rrtn = rtn[:]
            rrtn.reverse()
            rtn += rrtn
        return rtn


g_rcs = GameResource('resource')
g_frameinfo = {}
log.startLogging(sys.stdout)


class BackGroundSprite(SpriteObj):

    """
    background scroll class
    repeat to fill background
    display dc, move, change image
    """

    def initialize(self, kwds):
        SpriteObj.initialize(self, kwds)
        if self.memorydc and not self.dcsize:
            self.dcsize = self.memorydc.GetSizeTuple()
        return self

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


class ForegroundSprite(SpriteObj):

    """
    display and shape
    """

    def initialize(self, args):
        argsdict = {
            "shapefn": ForegroundSprite.ShapeChange_None,
            "shapefnargs": {
                'radiusSpeed': 0,
                "pen": None,
                "brush": None,
                "memorydcs": None,
                "dcsize": None,
                "startimagenumber": 0,
            },
            "afterremovefn": None,
            "afterremovefnarg": (),
        }
        updateDict(argsdict, args)
        SpriteObj.initialize(self, argsdict)

        self.baseCollisionCricle = self.collisionCricle
        self.registerAutoMoveFn(self.shapefn, [])
        self.registerAutoMoveFn(ForegroundSprite.changeImage, [])
        self.initResource(self.shapefnargs.get('memorydcs'))
        return self

    def initResource(self, rcs):
        if rcs is None:
            self.shapefnargs['brush'] = wx.Brush(
                self.group.teamcolor, wx.SOLID)
            self.shapefnargs['pen'] = wx.Pen(self.group.teamcolor)
        else:
            self.shapefnargs['memorydcs'] = rcs
            self.shapefnargs['dcsize'] = self.shapefnargs[
                'memorydcs'][0].GetSizeTuple()
            self.currentimagenumber = self.shapefnargs['startimagenumber']

        return self

    def ShapeChange_None(self):
        pass

    def changeImage(self):
        if self.shapefnargs['memorydcs']:
            self.currentimagenumber = int(self.shapefnargs['startimagenumber'] + self.getAge(
                self.thistick) * self.shapefnargs['animationfps']) % len(self.shapefnargs['memorydcs'])

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


class ShootingGameObject(SpriteObj):

    """
    display and shape
    """

    def initialize(self, args):
        argsdict = {
            "shapefn": ShootingGameObject.ShapeChange_None,
            "shapefnargs": {
                'radiusSpeed': 0,
                "pen": None,
                "brush": None,
                "memorydcs": None,
                "dcsize": None,
                "startimagenumber": 0,
            },
            "afterremovefn": None,
            "afterremovefnarg": (),
        }
        updateDict(argsdict, args)
        SpriteObj.initialize(self, argsdict)

        self.baseCollisionCricle = self.collisionCricle
        self.registerAutoMoveFn(self.shapefn, [])
        self.registerAutoMoveFn(ShootingGameObject.changeImage, [])
        self.initResource(self.shapefnargs.get('memorydcs'))
        return self

    def initResource(self, rcs):
        if rcs is None:
            self.shapefnargs['brush'] = wx.Brush(
                self.group.teamcolor, wx.SOLID)
            self.shapefnargs['pen'] = wx.Pen(self.group.teamcolor)
        else:
            self.shapefnargs['memorydcs'] = rcs
            self.shapefnargs['dcsize'] = self.shapefnargs[
                'memorydcs'][0].GetSizeTuple()
            self.currentimagenumber = self.shapefnargs['startimagenumber']

        return self

    def ShapeChange_None(self):
        pass

    def changeImage(self):
        if self.shapefnargs['memorydcs']:
            self.currentimagenumber = int(
                self.shapefnargs['startimagenumber'] + self.getAge(
                    self.thistick) * self.shapefnargs[
                        'animationfps']) % len(self.shapefnargs['memorydcs'])
        # self.currentimagenumber = g_frameinfo[
        #     'stat'].datadict['count'] % len(self.shapefnargs['memorydcs'])

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

    def type2RcsArgs2(self, objtype):
        collisionCricle = self.spriteClass.typeDefaultDict[
            objtype]['collisionCricle']
        sizehint = 1000 * 2
        r, g, b = self.teamcolor

        return {
            'scalearg': (collisionCricle * sizehint, collisionCricle * sizehint),
            'adjcharg': (r / 128.0, g / 128.0, b / 128.0, 1.0)
        }

    def loadResource(self):
        self.rcsdict = {
            'spriteexplosioneffect': g_rcs.File2OPedMDCList(
                "EvilTrace.png", slicearg=(1, 8, None, True)),
            'ballexplosioneffect': g_rcs.File2OPedMDCList(
                "explo1e.png", slicearg=(8, 1, None, True)),
            'spawneffect': g_rcs.File2OPedMDCList(
                "spawn.png", slicearg=(1, 6, None, True), listop=['reverse']),
        }

        loadlist = [
            ('bounceball', "grayball.png", None),
            ('bullet', "grayball.png", None),
            ('hommingbullet', "spiral.png", (0, 360, 10)),
            ('superbullet', "spiral.png", (0, 360, 10)),
            ('circularbullet', "grayball.png", None),
            ('shield', "grayball.png", None),
            ('supershield', "spiral.png", (0, 360, 10))
        ]
        for ot, img, rotarg in loadlist:
            argdict = self.type2RcsArgs2(ot)
            argdict.update({'rotarg': rotarg})

            self.rcsdict[ot] = g_rcs.File2OPedMDCList(
                img, **argdict)

    def initialize(self, *args, **kwds):
        GameObjectGroup.initialize(self, *args, **kwds)
        self.loadResource()
        return self

    def DrawToWxDC(self, pdc):
        clientsize = pdc.GetSize()
        sizehint = min(clientsize.x, clientsize.y)
        for a in self:
            a.DrawToWxDC(pdc, clientsize, sizehint)
        return self


class ShootingGameClient(ShootingGameMixin, wx.Control, FPSMixin):

    def initGroups(self, groupclass, spriteClass):
        self.dispgroup = {}
        self.dispgroup['backgroup'] = groupclass().initialize(
            gameObj=self, spriteClass=BackGroundSprite, teamcolor=(0x7f, 0x7f, 0x7f))
        self.dispgroup['effectObjs'] = groupclass().initialize(
            gameObj=self, spriteClass=spriteClass, teamcolor=(0x7f, 0x7f, 0x7f))
        self.dispgroup['frontgroup'] = groupclass().initialize(
            gameObj=self, spriteClass=ForegroundSprite, teamcolor=(0x7f, 0x7f, 0x7f))
        self.dispgroup['objplayers'] = []

    def makeFrontObj(self):
        o = ForegroundSprite().initialize(dict(
            objtype="cloud",
            pos=Vector2(random.random(), random.random()),
            movevector=Vector2.rect(0.01, math.pi),
            movelimit=0.1,
            group=self.dispgroup['frontgroup'],
            movefnargs={"accelvector": Vector2(1, 0)},
            shapefnargs={}
        ))
        o.initResource(
            [random.choice(g_rcs.File2OPedMDCList(
                "Clouds.png",
                slicearg=(1, 4, None, True),
            ))]
        )
        return o

    def makeBkObj(self):
        return BackGroundSprite().initialize(dict(
            objtype="background",
            movevector=Vector2.rect(100.0, -math.pi),
            drawfillfn=BackGroundSprite.DrawFill_Both,
            memorydc=g_rcs.File2OPedMDCList("background.gif", )[0]
        ))

    def OnKeyDown(self, evt):
        keycode = evt.GetKeyCode()
        if keycode == wx.WXK_ESCAPE:
            reactor.stop()

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

    def addNewObj2Team(self, team, objdef):
        ShootingGameMixin.addNewObj2Team(self, team, objdef)
        team[-1].initResource(team.rcsdict[team[-1].objtype])

    def applyState(self, loadlist):
        ShootingGameMixin.applyState(
            self, GameObjectDisplayGroup, ShootingGameObject, loadlist)

    def printStat(self):
        log.msg('fps: ', self.frameinfo.stat)
        log.msg(self.getStatInfo())
        self.recvcount, self.sendcount, self.initedTime = 0, 0, time.time()

    def getStatInfo(self):
        t = time.time() - self.initedTime
        return 'recv:{} {}/s send:{} {}/s'.format(
            self.recvcount, self.recvcount / t,
            self.sendcount, self.sendcount / t
        )

    def __init__(self, *args, **kwds):
        self.FPSInit(getFrameTime, 60)
        self.recvcount, self.sendcount, self.initedTime = 0, 0, time.time()

        self.factory = kwds.pop('factory')
        self.factory.game = self
        self.teamname = kwds.pop('teamname')
        self.teaminfo = None
        wx.Control.__init__(self, *args, **kwds)

        self.Bind(wx.EVT_PAINT, self._OnPaint)
        self.Bind(wx.EVT_SIZE, self._OnSize)
        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        self.FPSInit(getFrameTime, 60)
        self.SetBackgroundColour(wx.Colour(0x0, 0x0, 0x0))

        self.initGroups(GameObjectDisplayGroup, ShootingGameObject)

        self.dispgroup['backgroup'].append(
            self.makeBkObj()
        )
        for i in range(4):
            self.dispgroup['frontgroup'].append(self.makeFrontObj())

        task.LoopingCall(self.printStat).start(1.0)
        task.LoopingCall(self.FPSRun).start(1.0 / 60)

    def FPSMain(self):
        g_frameinfo.update(self.frameinfo)
        self.thistick = self.frameinfo.thisFrameTime

        for gog in self.dispgroup['objplayers']:
            gog.AutoMoveByTime(self.thistick)

        angle = random2pi() / 10
        bgmoved = False
        self.dispgroup['backgroup'].AutoMoveByTime(self.thistick)
        for o in self.dispgroup['backgroup']:
            if random.random() < 0.1:
                o.setAccelVector(o.getAccelVector().addAngle(angle))
                bgmoved = True

        self.dispgroup['effectObjs'].AutoMoveByTime(
            self.thistick).RemoveDisabled()

        self.dispgroup['frontgroup'].AutoMoveByTime(self.thistick)
        for o in self.dispgroup['frontgroup']:
            if bgmoved and random.random() < 0.9:
                o.setAccelVector(o.getAccelVector().addAngle(-angle))

        self.Refresh(False)

    def process1Cmd(self, conn, cmdDict):
        cmd = cmdDict.get('cmd')
        if cmd == 'gameState':
            self.reqState(conn)
            self.applyState(cmdDict)
            if self.teaminfo is not None:
                self.makeClientAIAction(conn)
        elif cmd == 'actACK':
            pass
        elif cmd == 'teamInfo':
            self.madeTeam(cmdDict)
            self.reqState(conn)
        else:
            log.msg('unknown cmd ', cmdDict)

    def makeClientAIAction(self, conn):
        # make AI action
        if self.teaminfo is None:
            return
        aa = self.getTeamByID(self.teaminfo['teamid'])
        if aa is None:
            return
        targets = [tt for tt in self.dispgroup[
            'objplayers'] if tt.teamname != aa.teamname]
        aa.prepareActions(
            targets,
            self.frameinfo.lastFPS,
            self.thistick
        )
        actions = aa.SelectAction(targets, aa[0])
        actionjson = self.serializeActions(actions)
        conn.sendString(toGzJsonParams(
            cmd='act',
            teamid=self.teaminfo['teamid'],
            actions=actionjson,
        ))

    def reqState(self, conn):
        conn.sendString(toGzJsonParams(
            cmd='reqState',
        ))

    def makeTeam(self, conn):
        teamname = 'AI_%08X' % random.getrandbits(32)
        teamcolor = (random.randint(0, 255),
                     random.randint(0, 255), random.randint(0, 255))
        log.msg('makeTeam %s %s', teamname, teamcolor)
        conn.sendString(toGzJsonParams(
            cmd='makeTeam',
            teamname=teamname,
            teamcolor=teamcolor
        ))

    def madeTeam(self, cmdDict):
        teamname = cmdDict.get('teamname')
        teamid = cmdDict.get('teamid')
        self.teaminfo = {
            'teamname': teamname,
            'teamid': teamid,
            'teamStartTime': None,
        }
        log.msg('joined ', teamname, teamid, self.teaminfo)

    def connected(self, conn):
        if self.teamname:
            self.makeTeam(conn)
        else:  # observer mode
            log.msg('observer mode')
            self.reqState(conn)


class MyFrame(wx.Frame):

    def __init__(self, *args, **kwds):
        kwds["style"] = wx.DEFAULT_FRAME_STYLE
        factory = kwds.pop('factory')
        teamname = kwds.pop('teamname')
        wx.Frame.__init__(self, *args, **kwds)
        self.gamePannel = ShootingGameClient(
            self, -1, size=(1000, 1000),
            factory = factory,
            teamname = teamname,
        )
        self.gamePannel.framewindow = self
        self.__set_properties()
        self.__do_layout()

    def __set_properties(self):
        self.SetTitle("wxGame2 %s by kasworld" % Version)
        self.gamePannel.SetMinSize((1000, 1000))

    def __do_layout(self):
        sizer_1 = wx.BoxSizer(wx.VERTICAL)
        sizer_2 = wx.BoxSizer(wx.HORIZONTAL)
        sizer_2.Add(self.gamePannel, 0, wx.FIXED_MINSIZE, 0)
        sizer_1.Add(sizer_2, 1, wx.EXPAND, 0)
        self.SetSizer(sizer_1)
        sizer_1.Fit(self)
        self.Layout()
        self.gamePannel.SetFocus()


class NPCProtocol(Int32StringReceiver):

    def connectionMade(self):
        log.msg('client connected')
        self.factory.game.connected(self)

    def connectionLost(self, reason):
        reactor.stop()

    def stringReceived(self, string):
        cmdDict = fromGzJson(string)
        self.factory.game.process1Cmd(self, cmdDict)


class NPCServer(ClientFactory):
    protocol = NPCProtocol


def runClient():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-s', '--server'
    )
    parser.add_argument(
        '-t', '--teamname'
    )
    args = parser.parse_args()
    if args.server is None:
        args.server = 'localhost'

    log.msg('Client start')

    npc_factory = NPCServer()
    app = wx.App()
    frame_1 = MyFrame(
        None, -1, "", size=(1000, 1000),
        factory = npc_factory,
        teamname=args.teamname
    )
    app.SetTopWindow(frame_1)
    frame_1.Show()

    reactor.registerWxApp(app)
    reactor.connectTCP(args.server, 22517, npc_factory)
    reactor.run()
    log.msg('end client')


if __name__ == "__main__":
    runClient()
