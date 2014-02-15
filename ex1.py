#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
"""

from wxgame2 import *


class MyFrameBase(wx.Frame):

    def __init__(self, *args, **kwds):
        kwds["style"] = wx.DEFAULT_FRAME_STYLE
        self.exclass = kwds.pop('exclass', ex1)
        wx.Frame.__init__(self, *args, **kwds)

        self.initGameClass(self.exclass)

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

    def initGameClass(self, exclass):
        self.panel_1 = exclass(self, -1, size=(1000, 1000))


class exBase(wxGameContentsControl):

    def __init__(self, *args, **kwds):
        wxGameContentsControl.__init__(self, *args, **kwds)
        self.SetBackgroundColour(wx.Colour(0x0, 0x0, 0x0))
        self.ClearBackground()

        self.effectObjs = GameObjectGroup()

        self.objplayers = []

        self.initObjects()

        self.dispgroup.extend(self.objplayers)
        self.dispgroup.append(self.effectObjs)

        nowstart = getFrameTime()
        for dg in self.dispgroup:
            for o in dg:
                self.createdTime = nowstart

    def _OnPaint(self, evt):
        pdc = wx.AutoBufferedPaintDC(self)
        # pdc = wx.BufferedPaintDC(self)
        self.DrawToWxDC(pdc)

    def doFPSlogic(self, frameinfo):
        self.thistick = getFrameTime()
        wxGameContentsControl.doFPSlogic(self, frameinfo)
        self.frameinfo = frameinfo
        self.frameinfo['objcount'] = sum([len(a) for a in self.objplayers])

        self.doFireAndAutoMoveByTime(frameinfo)

        # make collision dictionary
        resultdict, self.frameinfo['cmpcount'] = self.makeCollisionDict()

        if self.checkCollision is True:
            ischanagestatistic = self.doScoreSimple(resultdict)

        # 결과에 따라 삭제한다.
        for aa in self.objplayers:
            aa.RemoveDisabled()

        self.effectObjs.AutoMoveByTime(self.thistick).RemoveDisabled()

        # 화면에 표시
        # if ischanagestatistic:
        #     self.updateInfoGrid({})
        self.Refresh(False)


class ex1(exBase):

    def initObjects(self):
        self.checkCollision = False
        teams = [
            {"AIClass": AI0Test},
        ] * 20
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
                        "accel": 1.0 * 30
                    },
                    effectObjs=self.effectObjs,
                ))


class ex2(exBase):

    def initObjects(self):
        self.checkCollision = True
        teams = [
            {"AIClass": AI0Test},
        ] * 20
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
                        # "circularbullet": 1.0 / 30 * 1,
                        # "superbullet": 1.0 / 10 * 1,
                        # "hommingbullet": 1.0 / 10 * 1,
                        # "bullet": 1.0 * 2,
                        "accel": 1.0 * 30
                        # "circularbullet": 0,
                        # "superbullet": 0,
                        # "hommingbullet": 0.1,
                        # "bullet": 0.01,
                        # "accel": 1.0 * 30
                    },
                    effectObjs=self.effectObjs,
                ))


class ex3(exBase):

    def initObjects(self):
        self.checkCollision = True
        teams = [
            {"AIClass": AI0Test},
        ] * 8
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
                        "circularbullet": 1.0 / 30 * 1,
                        "superbullet": 1.0 / 10 * 1,
                        "hommingbullet": 1.0 / 10 * 1,
                        "bullet": 1.0 * 2,
                        "accel": 1.0 * 30
                        # "circularbullet": 0,
                        # "superbullet": 0,
                        # "hommingbullet": 0.1,
                        # "bullet": 0.01,
                        # "accel": 1.0 * 30
                    },
                    effectObjs=self.effectObjs,
                ))


class ex4(exBase):

    def initObjects(self):
        self.checkCollision = False
        teams = [
            {"AIClass": AI1},
        ] * 2
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
                    enableshield=True,
                    # inoutrate = d / 100.0,
                    actratedict={
                        "circularbullet": 1.0 / 30 * 1,
                        "superbullet": 1.0 / 10 * 1,
                        "hommingbullet": 1.0 / 10 * 1,
                        "bullet": 1.0 * 2,
                        "accel": 1.0 * 30
                        # "circularbullet": 0,
                        # "superbullet": 0,
                        # "hommingbullet": 0.1,
                        # "bullet": 0.01,
                        # "accel": 1.0 * 30
                    },
                    effectObjs=self.effectObjs,
                ))


def runEx(exobj):
    app = wx.PySimpleApp(0)
    wx.InitAllImageHandlers()
    frame_1 = MyFrameBase(None, -1, "", size=(1000, 1000), exclass=exobj)
    app.SetTopWindow(frame_1)
    frame_1.Show()
    app.MainLoop()


if __name__ == "__main__":
    runEx(ex4)
