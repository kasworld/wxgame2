#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
"""

from wxgame2 import *


class MyFrameBase(wx.Frame):

    def __init__(self, *args, **kwds):
        kwds["style"] = wx.DEFAULT_FRAME_STYLE
        self.exclass = kwds.pop('exclass', ex00)
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


class exBase(ShootingGameControl):

    def __init__(self, *args, **kwds):
        wxGameContentsControl.__init__(self, *args, **kwds)
        # self.SetBackgroundColour(wx.BLACK)
        # self.SetBackgroundStyle(wx.BG_STYLE_COLOUR)
        # self.ClearBackground()

        self.backgroup = None
        self.scoreFn = self.doScoreSimple

        self.effectObjs = GameObjectGroup()

        self.objplayers = []

        self.initObjects()

        self.dispgroup.extend(self.objplayers)
        self.dispgroup.append(self.effectObjs)

        nowstart = getFrameTime()
        for dg in self.dispgroup:
            for o in dg:
                self.createdTime = nowstart

    def initBackground(self):
        # add background
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

    def _OnPaint(self, evt):
        #pdc = wx.AutoBufferedPaintDC(self)
        pdc = wx.BufferedPaintDC(self)

        pdc.SetBackground(wx.BLACK_BRUSH)
        pdc.Clear()

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
            ischanagestatistic = self.scoreFn(resultdict)

        # 결과에 따라 삭제한다.
        for aa in self.objplayers:
            aa.RemoveDisabled()

        self.effectObjs.AutoMoveByTime(self.thistick).RemoveDisabled()

        # background move
        if self.backgroup is not None:
            self.backgroup.AutoMoveByTime(self.thistick)
            for o in self.backgroup:
                if random.random() < 0.001:
                    o.setAccelVector(o.getAccelVector().addAngle(random2pi()))

        self.Refresh(False)


class ex00(exBase):

    """
    display object
    """

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
                    },
                    effectObjs=self.effectObjs,
                ))


class ex01(exBase):

    """
    display object
    add background
    """

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
                    },
                    effectObjs=self.effectObjs,
                ))

        self.initBackground()


class ex02(exBase):

    """
    random move ( accel )
    """

    def initObjects(self):
        self.checkCollision = False
        teams = [
            {"AIClass": AI0Random},
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


class ex03(exBase):

    """
    random move ( accel )
    collision and destory
    """

    def initObjects(self):
        self.checkCollision = True
        teams = [
            {"AIClass": AI0Random},
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


class ex04(exBase):

    """
    random move ( accel )
    collision and destory
    fire
    """

    def initObjects(self):
        self.checkCollision = True
        teams = [
            {"AIClass": AI1},
        ] * 4
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
                        "bullet": 1.0 * 2,
                        "accel": 1.0 * 30
                    },
                    effectObjs=self.effectObjs,
                ))


class ex05(exBase):

    """
    random move ( accel )
    collision and destory
    fire homing
    """

    def initObjects(self):
        self.checkCollision = True
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
                    enableshield=False,
                    # inoutrate = d / 100.0,
                    actratedict={
                        #"circularbullet": 1.0 / 30 * 1,
                        #"superbullet": 1.0 / 10 * 1,
                        "hommingbullet": 1.0,
                        #"bullet": 1.0 * 2,
                        "accel": 1.0 * 30
                    },
                    effectObjs=self.effectObjs,
                ))


class ex06(exBase):

    """
    random move ( accel )
    collision and destory
    fire super
    """

    def initObjects(self):
        self.checkCollision = True
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
                    enableshield=False,
                    # inoutrate = d / 100.0,
                    actratedict={
                        #"circularbullet": 1.0 / 30 * 1,
                        "superbullet": 1.0,
                        #"hommingbullet": 1.0 / 10 * 1,
                        "bullet": 1.0 * 2,
                        "accel": 1.0 * 30
                    },
                    effectObjs=self.effectObjs,
                ))


class ex07(exBase):

    """
    random move ( accel )
    collision and destory
    fire circular
    """

    def initObjects(self):
        self.checkCollision = True
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
                    enableshield=False,
                    # inoutrate = d / 100.0,
                    actratedict={
                        "circularbullet": 1.0,
                        #"superbullet": 1.0,
                        #"hommingbullet": 1.0 / 10 * 1,
                        #"bullet": 1.0 * 2,
                        "accel": 1.0 * 30
                    },
                    effectObjs=self.effectObjs,
                ))


class ex08(exBase):

    """
    random move ( accel )
    collision and destory
    shield
    """

    def initObjects(self):
        self.checkCollision = True
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
                        "bullet": 1.0 * 2,
                        "accel": 1.0 * 30
                    },
                    effectObjs=self.effectObjs,
                ))


class ex09(exBase):

    """
    random move ( accel )
    collision and destory
    shield
    super shield
    """

    def initObjects(self):
        self.checkCollision = True
        self.scoreFn = self.doScore
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
                    enableshield=False,
                    # inoutrate = d / 100.0,
                    actratedict={
                        "bullet": 1.0 * 2,
                        "accel": 1.0 * 30
                    },
                    effectObjs=self.effectObjs,
                ))


class ex10(exBase):

    """
    random move ( accel )
    collision and destory
    advanced ai
    """

    def initObjects(self):
        self.checkCollision = True
        teams = [
            {"AIClass": AI2, "teamname": 'team0', 'resource': 0},
            {"AIClass": AI1, "teamname": 'team1', 'resource': 1},
            {"AIClass": AI1, "teamname": 'team2', 'resource': 2},
            {"AIClass": AI1, "teamname": 'team3', 'resource': 3},
            {"AIClass": AI1, "teamname": 'team4', 'resource': 4},
            {"AIClass": AI1, "teamname": 'team5', 'resource': 5},
            {"AIClass": AI1, "teamname": 'team6', 'resource': 6},
            {"AIClass": AI1, "teamname": 'team7', 'resource': 7},
        ]
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
                        "bullet": 1.0 * 2,
                        "accel": 1.0 * 30
                    },
                    effectObjs=self.effectObjs,
                ))


class ex11(exBase):

    """
    random move ( accel )
    collision and destory
    advanced ai
    mix it all
    """

    def initObjects(self):
        self.checkCollision = True
        teams = [
            {"AIClass": AI2, "teamname": 'team0', 'resource': 0},
            {"AIClass": AI2, "teamname": 'team1', 'resource': 1},
            {"AIClass": AI2, "teamname": 'team2', 'resource': 2},
            {"AIClass": AI2, "teamname": 'team3', 'resource': 3},
            {"AIClass": AI2, "teamname": 'team4', 'resource': 4},
            {"AIClass": AI2, "teamname": 'team5', 'resource': 5},
            {"AIClass": AI2, "teamname": 'team6', 'resource': 6},
            {"AIClass": AI2, "teamname": 'team7', 'resource': 7},
        ]
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
                        "circularbullet": 1.0,
                        "superbullet": 1.0,
                        "hommingbullet": 1.0 / 10 * 1,
                        "bullet": 1.0 * 2,
                        "accel": 1.0 * 30
                    },
                    effectObjs=self.effectObjs,
                ))


class ex12(exBase):

    """
    random move ( accel )
    collision and destory
    advanced ai
    mix it all
    and balance
    """

    def initObjects(self):
        self.checkCollision = True

        teams = [
            {"AIClass": AI2, "teamname": 'team0', 'resource': 0},
            {"AIClass": AI2, "teamname": 'team1', 'resource': 1},
            {"AIClass": AI2, "teamname": 'team2', 'resource': 2},
            {"AIClass": AI2, "teamname": 'team3', 'resource': 3},
            {"AIClass": AI2, "teamname": 'team4', 'resource': 4},
            {"AIClass": AI2, "teamname": 'team5', 'resource': 5},
            {"AIClass": AI2, "teamname": 'team6', 'resource': 6},
            {"AIClass": AI2, "teamname": 'team7', 'resource': 7},
        ]
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
                        "hommingbullet": 1.0,
                        "bullet": 1.0 * 2,
                        "accel": 1.0 * 30
                    },
                    effectObjs=self.effectObjs,
                ))


class ex13(exBase):

    """
    random move ( accel )
    collision and destory
    advanced ai
    mix it all
    and balance
    super shield
    """

    def initObjects(self):
        self.checkCollision = True
        self.scoreFn = self.doScore

        teams = [
            {"AIClass": AI2, "teamname": 'team0', 'resource': 0},
            {"AIClass": AI2, "teamname": 'team1', 'resource': 1},
            {"AIClass": AI2, "teamname": 'team2', 'resource': 2},
            {"AIClass": AI2, "teamname": 'team3', 'resource': 3},
            {"AIClass": AI2, "teamname": 'team4', 'resource': 4},
            {"AIClass": AI2, "teamname": 'team5', 'resource': 5},
            {"AIClass": AI2, "teamname": 'team6', 'resource': 6},
            {"AIClass": AI2, "teamname": 'team7', 'resource': 7},
        ]
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
                        "hommingbullet": 1.0,
                        "bullet": 1.0 * 2,
                        "accel": 1.0 * 30
                    },
                    effectObjs=self.effectObjs,
                ))


class ex14(exBase):

    """
    random move ( accel )
    collision and destory
    advanced ai
    mix it all
    and balance
    background
    """

    def initObjects(self):
        self.checkCollision = True
        self.scoreFn = self.doScore
        teams = [
            {"AIClass": AI2, "teamname": 'team0', 'resource': 0},
            {"AIClass": AI2, "teamname": 'team1', 'resource': 1},
            {"AIClass": AI2, "teamname": 'team2', 'resource': 2},
            {"AIClass": AI2, "teamname": 'team3', 'resource': 3},
            {"AIClass": AI2, "teamname": 'team4', 'resource': 4},
            {"AIClass": AI2, "teamname": 'team5', 'resource': 5},
            {"AIClass": AI2, "teamname": 'team6', 'resource': 6},
            {"AIClass": AI2, "teamname": 'team7', 'resource': 7},
        ]
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
                        "hommingbullet": 1.0,
                        "bullet": 1.0 * 2,
                        "accel": 1.0 * 30
                    },
                    effectObjs=self.effectObjs,
                ))

        self.initBackground()


def runEx(exobj):
    #app = wx.PySimpleApp(0)
    app = wx.App()
    # wx.InitAllImageHandlers()
    frame_1 = MyFrameBase(None, -1, "", size=(1000, 1000), exclass=exobj)
    app.SetTopWindow(frame_1)
    frame_1.Show()
    app.MainLoop()


if __name__ == "__main__":
    rundict = {
        '00': ex00,
        '01': ex01,
        '02': ex02,
        '03': ex03,
        '04': ex04,
        '05': ex05,
        '06': ex06,
        '07': ex07,
        '08': ex08,
        '09': ex09,
        '10': ex10,
        '11': ex11,
        '12': ex12,
        '13': ex13,
        '14': ex14
    }
    helpdoc = """
    wxgame examples
    run as
    python  ex.py NN
    NN : 00 ~ 14
    """
    while True:
        print helpdoc
        exnum = raw_input()
        try:
            clsobj = rundict[exnum]
        except:
            print helpdoc
            sys.exit()
        runEx(clsobj)
