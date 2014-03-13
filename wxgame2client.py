#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" wxgame client
    wxGameFramework
    Copyright 2011 kasw <kasworld@gmail.com>
    wxpython을 사용해서 게임을 만들기위한 프레임웍과 테스트용 게임 3가지
    기본적인 가정은
    좌표계는 0~1.0 인 정사각형 실수 좌표계
    collision은 원형: 현재 프레임의 위치만을 기준으로 검출한다.
    모든? action은 frame 간의 시간차에 따라 보정 된다.
    문제점은 frame간에 지나가 버린 경우 이동 루트상으론 collision 이 일어나야 하지만 검출 불가.
"""
Version = '2.1.0'
import random
import math
import traceback
import os
import os.path
import sys
import socket
import signal
import threading
import Queue
import wx
import wx.grid
import wx.lib.colourdb
from euclid import Vector2
#from wxgame2server import GameObjectGroup
from wxgame2server import SpriteObj, random2pi, FPSlogicBase
from wxgame2server import getFrameTime, I32gzJsonPacket, putJson2Queue, ShootingGameMixin
from wxgame2server import AI2 as GameObjectGroup
#from wxgame2server import GameObjectGroup
# ======== game lib ============


class GameResource(object):

    """ game resource loading with cache
    """

    def __init__(self, dirname):
        wx.InitAllImageHandlers()
        self.srcdir = os.path.dirname(os.path.abspath(sys.argv[0]))
        self.resourcedir = dirname
        self.rcsdict = {}

    def getcwdfilepath(self, filename):
        return os.path.join(self.srcdir, self.resourcedir, filename)

    def loadBitmap2MemoryDCArray(self, name, *args, **kwds):
        key = (name, args, str(kwds))
        if not self.rcsdict.get(key, None):
            self.rcsdict[key] = GameResource._loadBitmap2MemoryDCArray(
                self.getcwdfilepath(name), *args, **kwds)
        return self.rcsdict[key]

    def loadDirfiles2MemoryDCArray(self, name, *args, **kwds):
        key = (name, args, str(kwds))
        if not self.rcsdict.get(key, None):
            self.rcsdict[key] = GameResource._loadDirfiles2MemoryDCArray(
                self.getcwdfilepath(name), *args, **kwds)
        return self.rcsdict[key]

    def loadBitmap2RotatedMemoryDCArray(self, name, *args, **kwds):
        key = (name, args, str(kwds))
        if not self.rcsdict.get(key, None):
            self.rcsdict[key] = GameResource._loadBitmap2RotatedMemoryDCArray(
                self.getcwdfilepath(name), *args, **kwds)
        return self.rcsdict[key]

    @staticmethod
    def _loadBitmap2MemoryDCArray(bitmapfilename, xslicenum=1, yslicenum=1, totalslice=10000, yfirst=True, reverse=False, addreverse=False):
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

    @staticmethod
    def _loadDirfiles2MemoryDCArray(dirname, reverse=False, addreverse=False):
        rtn = []
        filenames = sorted(os.listdir(dirname), reverse=reverse)
        for a in filenames:
            rtn.append(wx.MemoryDC(wx.Bitmap(dirname + "/" + a)))
        if addreverse:
            rrtn = rtn[:]
            rrtn.reverse()
            rtn += rrtn
        return rtn

    @staticmethod
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

    @staticmethod
    def _loadBitmap2RotatedMemoryDCArray(imagefilename, rangearg=(0, 360, 10), reverse = False, addreverse = False):
        rtn = []
        fullimage = wx.Bitmap(imagefilename).ConvertToImage()
        for a in range(*rangearg):
            rtn.append(wx.MemoryDC(
                GameResource.makeRotatedImage(fullimage, a).ConvertToBitmap()
            ))
        if reverse:
            rtn.reverse()
        if addreverse:
            rrtn = rtn[:]
            rrtn.reverse()
            rtn += rrtn
        return rtn


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
# ======== game lib end ============
g_rcs = GameResource('resource')
g_frameinfo = {}


class BackGroundSplite(SpriteObj):

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


class ShootingGameObject(SpriteObj):

    """
    display and shape
    """

    def initialize(self, args):
        SpriteObj.initialize(self, args)
        argsdict = {
            "shapefn": ShootingGameObject.ShapeChange_None,
            "shapefnargs": {
                'radiusSpeed': 0,
                "pen": None,
                "brush": None,
                "memorydcs": None,
                "dcsize": None,
                "startimagenumber": 0,
                "animationfps": 10,
            },
            "afterremovefn": None,
            "afterremovefnarg": (),
        }
        self.updateObj(argsdict)

        self.baseCollisionCricle = self.collisionCricle
        self.registerAutoMoveFn(self.shapefn, [])
        self.registerAutoMoveFn(ShootingGameObject.changeImage, [])
        self.loadResource(self.shapefnargs.get('memorydcs'))
        return self

    def loadResource(self, rcs):
        if rcs is None:
            return
        self.shapefnargs['memorydcs'] = rcs
        self.shapefnargs['dcsize'] = self.shapefnargs[
            'memorydcs'][0].GetSizeTuple()
        self.currentimagenumber = self.shapefnargs['startimagenumber']
        self.shapefnargs['animationfps'] = self.shapefnargs.get(
            'animationfps', 10)

        return self

    def ShapeChange_None(self, args):
        pass

    def changeImage(self, args):
        if self.shapefnargs['memorydcs']:
            self.currentimagenumber = int(
                self.shapefnargs['startimagenumber'] + (
                    self.thistick - self.createdTime
                ) * self.shapefnargs['animationfps']) % len(self.shapefnargs['memorydcs'])

    def Draw_Shape(self, pdc, clientsize, sizehint):
        pdc.SetPen(self.shapefnargs['pen'])
        pdc.SetBrush(self.shapefnargs['brush'])
        pdc.DrawCircle(
            clientsize.x * self.pos.x,
            clientsize.y * self.pos.y,
            max(sizehint * self.collisionCricle, 1)
        )

    def Draw_MDC(self, pdc, clientsize, sizehint):
        self.currentimagenumber = g_frameinfo[
            'frameCount'] % len(self.shapefnargs['memorydcs'])
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

    def loadResource(self):
        if self.resoueceReady is True:
            return

        self.rcsdict = {
            'bounceball': [
                g_rcs.loadBitmap2MemoryDCArray("%sball.gif" % self.resource),
                g_rcs.loadBitmap2MemoryDCArray(
                    "%sball1.gif" % self.resource, reverse=True)
            ],
            'bullet': g_rcs.loadBitmap2MemoryDCArray(
                "%sbullet.png" % self.resource),
            'hommingbullet': g_rcs.loadBitmap2MemoryDCArray("ring.png", 4, 4),
            'superbullet': g_rcs.loadBitmap2MemoryDCArray(
                "%ssuper.png" % self.resource),
            'circularbullet': g_rcs.loadBitmap2MemoryDCArray(
                "%sbullet1.png" % self.resource),
            'shield': g_rcs.loadBitmap2MemoryDCArray(
                "%sbullet1.png" % self.resource),
            'supershield': [
                g_rcs.loadDirfiles2MemoryDCArray("earth"),
                g_rcs.loadDirfiles2MemoryDCArray("earth", reverse=True)
            ],
            'spriteexplosioneffect': g_rcs.loadBitmap2MemoryDCArray(
                "EvilTrace.png", 1, 8),
            'ballexplosioneffect': g_rcs.loadBitmap2MemoryDCArray(
                "explo1e.png", 8, 1),
            'spawneffect': g_rcs.loadBitmap2MemoryDCArray(
                "spawn.png", 1, 6, reverse=True),
        }
        self.resoueceReady = True

    def initialize(self, *args, **kwds):
        GameObjectGroup.initialize(self, *args, **kwds)
        self.resoueceReady = False
        self.loadResource()
        return self

    def DrawToWxDC(self, pdc):
        clientsize = pdc.GetSize()
        sizehint = min(clientsize.x, clientsize.y)
        for a in self:
            a.DrawToWxDC(pdc, clientsize, sizehint)
        return self
# ================ tcp client =========


class TCPGameClient(threading.Thread):

    def __init__(self, connectTo, queues):
        self.recvQueue, self.cmdQueue = queues
        self.quit = False
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(connectTo)
        self.protocol = I32gzJsonPacket(sock)

    def recvCmd(self):
        try:
            rdata = self.protocol.recvJson()
        except socket.timeout:
            return 'timeout'
        except socket.error as msg:
            print msg
            return 'socket error'
        try:
            self.recvQueue.put(rdata)
        except Queue.Full:
            print 'queue full'
            return 'queue full'
        return 'OK'

    def sendCmd(self):
        try:
            cmd = self.cmdQueue.get_nowait()
        except Queue.Empty:
            return 'queue empty'
        if cmd == 'QUIT':
            self.shutdown()
            return 'QUIT'
        try:
            self.protocol.sendJson(cmd)
        except socket.timeout:
            return 'timeout'
        except socket.error as msg:
            print msg
            return 'socket error'
        return 'OK'

    def clientLoop(self):
        while self.quit is not True:
            if self.recvCmd() in ['socket error']:
                break
            if self.sendCmd() in ['socket error', 'QUIT']:
                break

        self.protocol.sock.close()

    def shutdown(self):
        self.protocol.finish()
        self.quit = True


def runService(connectTo, queues):
    client = TCPGameClient(connectTo, queues)

    client_thread = threading.Thread(target=client.clientLoop)
    client_thread.start()

    return client, client_thread
# ================ tcp client end =========


class ShootingGameClient(ShootingGameMixin, wx.Control, FPSlogic):

    def makegroups(self):
        self.dispgroup = {}
        self.dispgroup['backgroup'] = GameObjectDisplayGroup().initialize()
        self.dispgroup['effectObjs'] = GameObjectDisplayGroup().initialize()
        self.dispgroup['frontgroup'] = GameObjectDisplayGroup().initialize()

        self.dispgroup['objplayers'] = []

    def __init__(self, *args, **kwds):
        self.recvQueue, self.cmdQueue = kwds.pop('queues')
        wx.Control.__init__(self, *args, **kwds)
        self.Bind(wx.EVT_PAINT, self._OnPaint)
        self.Bind(wx.EVT_SIZE, self._OnSize)
        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        self.FPSTimerInit(getFrameTime, 60)
        self.SetBackgroundColour(wx.Colour(0x0, 0x0, 0x0))

        self.makegroups()
        self.dispgroup['backgroup'].append(
            self.makeBkObj()
        )

        #self.registerRepeatFn(self.prfps, 1)

        self.myteam = None

    def prfps(self, repeatinfo):
        print 'fps:', self.statFPS

    def makeBkObj(self):
        return BackGroundSplite().initialize(dict(
            objtype="background",
            movevector=Vector2.rect(100.0, random2pi()),
            memorydc=g_rcs.loadBitmap2MemoryDCArray("background.gif")[0],
            drawfillfn=BackGroundSplite.DrawFill_Both,
        ))

    def OnKeyDown(self, evt):
        keycode = evt.GetKeyCode()
        if keycode == wx.WXK_ESCAPE:
            self.framewindow.Close()
            # self.cmdQueue.put('QUIT')

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
        def makeGameObjectDisplayGroup(og):
            gog = GameObjectDisplayGroup(
            ).initialize(
                resource=og['resource']
            ).deserialize(
                og,
                ShootingGameObject,
                dict(
                    shapefn=ShootingGameObject.ShapeChange_None,
                )
            )

            for o in gog:
                rcs = gog.rcsdict[o.objtype]
                if o.objtype in ['bounceball', 'supershield']:
                    rcs = random.choice(rcs)
                o.loadResource(rcs)
            return gog

        def getTeamByID(goglist, id):
            findteam = None
            for t in goglist:
                if t.ID == id:
                    findteam = t
                    break
            return findteam

        self.frameinfo.update(loadlist['frameinfo'])

        oldgog = self.dispgroup['objplayers']
        self.dispgroup['objplayers'] = []
        for og in loadlist['objplayers']:
            gog = makeGameObjectDisplayGroup(og)

            oldteam = getTeamByID(oldgog, gog.ID)
            if oldteam is not None:
                gog.statistic = oldteam.statistic
                if oldteam.hasBounceBall() and gog.hasBounceBall():
                    gog[0].fireTimeDict = oldteam[0].fireTimeDict
                    gog[0].createdTime = oldteam[0].createdTime
                    gog[0].lastAutoMoveTick = oldteam[0].lastAutoMoveTick
                    gog[0].ID = oldteam[0].ID

            self.dispgroup['objplayers'].append(gog)

        gog = makeGameObjectDisplayGroup(loadlist['effectObjs'])
        self.dispgroup['effectObjs'] = gog

        return

    def processCmd(self):
        try:
            cmdDict = self.recvQueue.get_nowait()
            if cmdDict is None:
                return
        except Queue.Empty:
            return
        except:
            print traceback.format_exc()
            return
        cmd = cmdDict.get('cmd')
        if cmd == 'gamestate':
            try:
                self.applyState(cmdDict)
            except:
                print traceback.format_exc()
                return

        if cmd == 'teaminfo':
            teamname = cmdDict.get('teamname')
            teamid = cmdDict.get('teamid')
            self.myteam = {
                'teamname': teamname,
                'teamid': teamid,
                'teamStartTime': self.thistick,
            }
            print 'joined', teamname, teamid, self.teams[teamname]
            print self.myteam

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

        putJson2Queue(
            self.cmdQueue,
            cmd='act',
            team=self.myteam,
            actions=actionjson,
        )

    def doFPSlogic(self):
        g_frameinfo.update(self.frameinfo)
        self.thistick = self.frameinfo['thistime']

        self.processCmd()
        self.makeClientAIAction()
        for gog in self.dispgroup['objplayers']:
            gog.AutoMoveByTime(self.thistick)

        self.dispgroup['backgroup'].AutoMoveByTime(self.thistick)
        for o in self.dispgroup['backgroup']:
            if random.random() < 0.001:
                o.setAccelVector(o.getAccelVector().addAngle(random2pi()))

        self.dispgroup['effectObjs'].AutoMoveByTime(
            self.thistick).RemoveDisabled()

        self.dispgroup['frontgroup'].AutoMoveByTime(self.thistick)
        for o in self.dispgroup['frontgroup']:
            if random.random() < 0.001:
                o.setAccelVector(o.getAccelVector().addAngle(random2pi()))

        self.Refresh(False)


class MyFrame(wx.Frame):

    def __init__(self, *args, **kwds):
        kwds["style"] = wx.DEFAULT_FRAME_STYLE
        queues = kwds.pop('queues')
        wx.Frame.__init__(self, *args, **kwds)
        self.panel_1 = ShootingGameClient(
            self, -1, size=(1000, 1000), queues = queues)
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
    if len(sys.argv) == 2:
        destip = sys.argv[1]
    else:
        destip = 'localhost'
    (recvQueue, cmdQueue) = Queue.Queue(), Queue.Queue()

    connectTo = destip, 22517
    print 'Client start, ', connectTo
    client, client_thread = runService(connectTo, (recvQueue, cmdQueue))

    def sigstophandler(signum, frame):
        print 'User Termination'
        client.shutdown()
        client_thread.join(1)
        sys.exit(0)
    signal.signal(signal.SIGINT, sigstophandler)

    app = wx.App()
    frame_1 = MyFrame(
        None, -1, "", size=(1000, 1000),
        queues= (recvQueue, cmdQueue))
    app.SetTopWindow(frame_1)
    frame_1.Show()
    app.MainLoop()
    print 'end client'
    sigstophandler(0, 0)


if __name__ == "__main__":
    runtest()
