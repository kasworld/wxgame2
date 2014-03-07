#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" wxgame server framework
게임 서버용으로 수정, wxpython code를 제거

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

import time
import math
import random
import itertools
import pprint
import zlib
import copy
try:
    import simplejson as json
except:
    import json
from euclid import Vector2

# ======== game lib ============
getSerial = itertools.count().next


def getFrameTime():
    return time.time()


def random2pi(m=2):
    return math.pi * m * (random.random() - 0.5)


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

    def getStat(self):
        return self.datadict

    def __str__(self):
        return self.formatstr % self.datadict


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

# ======== game lib end ============


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
        'thistick': 0,
    }

    def __init__(self):
        """ create obj
        """
        Storage.__init__(self)

        # initailize default field, value
        self.update(copy.deepcopy(self.validFields))
        self.ID = getSerial()
        self.createdTime = getFrameTime()
        self.lastAutoMoveTick = self.createdTime

    def loadDefaultByType(self, objtype):
        """ load default by type
        """
        self.updateObj(
            SpriteObj.typeDefaultDict.get(objtype, {})
        )
        return self

    def updateObj(self, params):
        """ update obj
        """
        for k, v in params.iteritems():
            if k in ['movefnargs', 'shapefnargs']:
                self.setdefault(k, {}).update(v)
            elif k in ['autoMoveFns']:
                self[k] = v
            else:
                self[k] = v

    def __str__(self):
        return pprint.pformat(dict(self))

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
        self.loadDefaultByType(params.get('objtype'))
        self.updateObj(params)

        #self.autoMoveFns = []
        self.registerAutoMoveFn(self.movefn, [])
        self.registerAutoMoveFn(SpriteObj.Move_byMoveVector, [])
        self.registerAutoMoveFn(self.wallactionfn, [])

        # pprint.pprint(self)
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

    def getLifeRate(self, tick):
        return (tick - self.createdTime) / self.secToLifeEnd

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
            self.movefn = SpriteObj.Move_NoAccel

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

    def Move_SyncTarget(self, args):
        if self.movefnargs["targetobj"] is None:
            return
        self.enabled = self.movefnargs["targetobj"].enabled
        if not self.enabled:
            return
        dur = (self.thistick - self.lastAutoMoveTick)
        self.movefnargs["diffvector"] = self.movefnargs["diffvector"].rotate(
            Vector2(0, 0), self.movefnargs["anglespeed"] * dur)
        self.movevector = (self.movefnargs[
                           "targetobj"].pos - self.pos + self.movefnargs["diffvector"]) / dur

    def Move_FollowTarget(self, args):
        if self.movefnargs["targetobj"] is None:
            return
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
        },
        "ballexplosioneffect": {
            "objtype": 'ballexplosioneffect',
            'secToLifeEnd': 0.5,
            'collisionCricle': 0,
            'collisionTarget': [],
            'movefn': Move_Vector,
            'wallactionfn': WallAction_Remove,
            'movefnargs': {"accelvector": Vector2(0, 0)},
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
    """

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

            "membercount": 1,
            "teamname": "red",
            "teamcolor": "red",
            "resource": "red"
        }
        self.setAttrs(defaultdict, kwds)

        self.ID = getSerial()
        self.initStat()
        return self

    def makeMember(self):
        while len(self) < self.membercount or self[self.membercount - 1].objtype != "bounceball":
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
                diffvector=Vector2(0.03, 0).addAngle(
                    2 * math.pi * a / 360.0),
                anglespeed=math.pi if i % 2 == 0 else -math.pi
            )
        return target

    # 이후는 SpriteObj를 편하게 생성하기위한 factory functions
    def AddBouncBall(self, newpos):
        o = SpriteObj().initialize(dict(
            objtype='bounceball',
            pos=newpos,
            group=self,
        ))
        self.insert(0, o)
        return o

    def AddShield(self, target, diffvector, anglespeed):
        o = SpriteObj().initialize(dict(
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

    def AddCircularBullet2(self, centerpos):
        for a in range(0, 360, 5):
            o = SpriteObj().initialize(dict(
                pos=centerpos + Vector2.rect(0.03, math.radians(a)),
                movevector=Vector2.rect(1, math.radians(a)),
                objtype="circularbullet",
                group=self,
            ))
            self.append(o)
        return self

    def AddTargetFiredBullet(self, startpos, tagetpos):
        o = SpriteObj().initialize(dict(
            pos=startpos.copy(),
            movevector=Vector2.rect(1, (tagetpos - startpos).phase()),
            objtype="bullet",
            group=self,
        ))
        self.append(o)
        return self

    def AddHommingBullet(self, startpos, target, expireFn=None):
        o = SpriteObj().initialize(dict(
            expireFn=expireFn,
            pos=startpos.copy(),
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
        o = SpriteObj().initialize(dict(
            pos=startpos.copy(),
            movevector=Vector2.rect(1, Vector2.phase(tagetpos - startpos)),
            objtype="superbullet",
            group=self,
        ))
        self.append(o)
        return self

    def AddSuperShield(self, target, expireFn):
        diffvector = Vector2(0.06, 0).addAngle(random2pi())
        o = SpriteObj().initialize(dict(
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

    def addSpriteExplosionEffect(self, src):
        self.append(
            SpriteObj().initialize(dict(
                pos=src.pos,
                movevector=src.movevector / 4,
                afterremovefn=None,
                afterremovefnarg=(),
                objtype="spriteexplosioneffect"
            )))

    def addBallExplosionEffect(self, effectObjs, g1, b):
        self.append(
            SpriteObj().initialize(dict(
                pos=b.pos,
                movevector=b.movevector / 4,
                afterremovefn=self.addSpawnEffect,
                afterremovefnarg=(effectObjs, g1),
                objtype="ballexplosioneffect"
            )))

    def addSpawnEffect(self, effectObjs, g1):
        newpos = Vector2(random.random(), random.random())
        self.append(
            SpriteObj().initialize(dict(
                pos=newpos,
                afterremovefn=g1.addMember,
                afterremovefnarg=(newpos,),
                objtype="spawneffect"
            )))

    # game logics
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
    def makeAimingTargetList(self, objgrouplist):
        rtn = []
        for og in objgrouplist:
            if self.teamname != og.teamname:
                rtn.append(og)
        return rtn

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
            self.doSelectedActions(actions, src)
        self.AutoMoveByTime(thistick)
        return self

    def doSelectedActions(self, actions, src):
        for act, actargs in actions:
            if self.actCount(act) > 0:
                self.statistic['act'][act] += 1
                if act == "circularbullet":
                    self.AddCircularBullet2(src.pos)
                elif act == "superbullet":
                    if actargs:
                        self.AddTargetSuperBullet(
                            src.pos, actargs)
                    else:
                        print "Error %s %s %s" % (act, src, actargs)
                elif act == "hommingbullet":
                    if actargs:
                        self.AddHommingBullet(
                            src.pos,
                            actargs,
                            expireFn=self.effectObjs.addSpriteExplosionEffect
                        )
                    else:
                        print "Error %s %s %s" % (act, src, actargs)
                elif act == "bullet":
                    if actargs:
                        self.AddTargetFiredBullet(src.pos, actargs)
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

    def serialize(self):
        rtn = {
            'id': self.ID,
            'teamname': self.teamname,
            'resource': self.resource,
            'objs': []
        }
        for o in self:
            rtn['objs'].append(
                (o.ID, o.objtype, (o.pos.x, o.pos.y),
                 (o.movevector.x, o.movevector.y))
            )
        return rtn

    def deserialize(self, jsondict, objclass, classargsdict):
        self.ID = jsondict['id']
        self.teamname = jsondict['teamname']
        self.resource = jsondict['resource']
        for objid, objtype, objpos, objmovevector in jsondict['objs']:
            argsdict = dict(
                objtype=objtype,
                pos=Vector2(*objpos),
                movevector=Vector2(*objmovevector),
                group=self
            )
            argsdict.update(classargsdict)
            self.append(objclass().initialize(argsdict))
        return self

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


class AI1(GameObjectGroup):

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


class AI2(GameObjectGroup):

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
        supertargetpos = self.getAimPos(
            src.pos,
            SpriteObj.typeDefaultDict['superbullet']['movelimit'],
            supertarget
        ) if supertarget else None

        bullettarget = self.selectByLenRate(
            nearlen, src.fireTimeDict.get("bullet", 0),
            ((0.3, 1 / self.actRatePerSec("bullet") / 4, neartarget),
            (2, 1 / self.actRatePerSec("bullet") / 1.5, randomtarget),)
        )
        bullettargetpos = self.getAimPos(
            src.pos,
            SpriteObj.typeDefaultDict['bullet']['movelimit'],
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


class AI0Test(GameObjectGroup):

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
        bullettargetpos = self.getAimPos(
            src.pos,
            SpriteObj.typeDefaultDict['bullet']['movelimit'],
            bullettarget) if bullettarget else None
        actions = (
            # action, probability, object
            ("bullet", 0.2, bullettargetpos),
        )
        return self.mapPro2Act(actions, True)


class AI0Inner(GameObjectGroup):

    def SelectAction(self, aimingtargetlist, src):
        accelvector = (Vector2(0.5, 0.5) - src.pos).normalized() / 20.0

        actions = (
            # action, probability, object
            ("accel", 0.5, accelvector),
        )
        return self.mapPro2Act(actions, True)


class AI0Random(GameObjectGroup):

    def SelectAction(self, aimingtargetlist, src):
        accelvector = Vector2.rect(random.random() / 14.0, random2pi())

        actions = (
            # action, probability, object
            ("accel", 0.5, accelvector),
        )
        return self.mapPro2Act(actions, True)


gameState = ''


class ShootingGameServer(FPSlogicBase):

    def makeTeam(self):
        randteam = [
            {"resource": "white", "color": (0xff, 0xff, 0xff)},
            {"resource": "orange", "color": (0xff, 0x7f, 0x00)},
            {"resource": "purple", "color": (0xff, 0x00, 0xff)},
            {"resource": "grey", "color": (0x7f, 0x7f, 0x7f)},
            {"resource": "red", "color": (0xff, 0x00, 0x00)},
            {"resource": "yellow", "color": (0xff, 0xff, 0x00)},
            {"resource": "green", "color": (0x00, 0xff, 0x00)},
            {"resource": "blue", "color": (0x00, 0xff, 0xff)},
        ]
        teams = [
            {"AIClass": AI2, "teamname": 'team0', 'resource': 0},
            {"AIClass": AI2, "teamname": 'team1', 'resource': 1},
            {"AIClass": AI2, "teamname": 'team2', 'resource': 2},
            {"AIClass": AI2, "teamname": 'team3', 'resource': 3},
            {"AIClass": AI2, "teamname": 'team4', 'resource': 4},
            {"AIClass": AI2, "teamname": 'team5', 'resource': 5},
            {"AIClass": AI2, "teamname": 'team6', 'resource': 6},
            {"AIClass": AI2, "teamname": 'team7', 'resource': 7},
        ] * 2
        teamobjs = []
        for sel, d in zip(itertools.cycle(randteam), teams):
            selpos = d.get('resource', -1)
            if selpos >= 0 and selpos < len(randteam):
                sel = randteam[selpos]
                o = d["AIClass"]().initialize(
                    resource=sel["resource"],
                    teamcolor=sel["color"],
                    teamname=d["teamname"],
                    membercount=1,
                    effectObjs=self.dispgroup['effectObjs'],
                )
                o.makeMember()
            teamobjs.append(o)
        return teamobjs

    def __init__(self, *args, **kwds):
        def setAttr(name, defaultvalue):
            self.__dict__[name] = kwds.pop(name, defaultvalue)
            return self.__dict__[name]
        self.FPSTimerInit(getFrameTime, 70)

        self.dispgroup = {}
        self.dispgroup['backgroup'] = GameObjectGroup().initialize()
        self.dispgroup['effectObjs'] = GameObjectGroup().initialize()
        self.dispgroup['frontgroup'] = GameObjectGroup().initialize()
        self.dispgroup['objplayers'] = self.makeTeam()

        nowstart = getFrameTime()
        for dg in self.dispgroup['objplayers']:
            for o in dg:
                self.createdTime = nowstart

        self.statObjN = Statistics()
        self.statCmpN = Statistics()
        self.statPacketL = Statistics()

        print 'end init'

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

    def doScoreSimple(self, resultdict):
        ischanagestatistic = False
        for src, targets in resultdict.iteritems():
            # 충돌한 것이 bounceball 이면
            if src.objtype == 'bounceball':
                ischanagestatistic = True
                src.group.addBallExplosionEffect(
                    self.dispgroup['effectObjs'], src.group, src)
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
                self.dispgroup['effectObjs'].addSpriteExplosionEffect(src)
        return ischanagestatistic

    def doScore(self, resultdict):
        ischanagestatistic = False
        for src, targets in resultdict.iteritems():
            # 충돌한 것이 bounceball 이면
            if src.objtype == 'bounceball':
                ischanagestatistic = True
                src.group.addBallExplosionEffect(
                    self.dispgroup['effectObjs'], src.group, src)
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
                                    target=target.group[0],
                                    expireFn=self.dispgroup[
                                        'effectObjs'].addSpriteExplosionEffect
                                )

                    if target.objtype not in ['bounceball', 'supershield', 'shield']:
                        target.group.statistic["teamscore"] += uplevel
                        target.group.statistic["maxscore"] = max(target.group.statistic[
                                                                 "maxscore"], target.group.statistic["teamscore"])
            else:
                src.enabled = False
                self.dispgroup['effectObjs'].addSpriteExplosionEffect(src)
        return ischanagestatistic

    def doFireAndAutoMoveByTime(self, frameinfo):
        # 그룹내의 bounceball 들을 AI automove 한다.
        # 자신과 같은 팀을 제외한 targets을 만든다.
        selmov = self.dispgroup['objplayers'][:]
        random.shuffle(selmov)
        for aa in selmov:
            targets = aa.makeAimingTargetList(self.dispgroup['objplayers'])
            aa.FireAndAutoMoveByTime(
                targets, frameinfo['ThisFPS'], self.thistick)

    def makeState(self):
        savelist = []
        for og in self.dispgroup['objplayers']:
            savelist.append(og.serialize())

        og = self.dispgroup['effectObjs']
        savelist.append(og.serialize())
        return savelist

    def saveState(self):
        global gameState
        savelist = self.makeState()
        tosenddata = zlib.compress(json.dumps(savelist))
        gameState = tosenddata
        return len(tosenddata)

    def doFPSlogic(self, frameinfo):
        self.thistick = frameinfo['thistime']

        self.frameinfo = frameinfo
        self.frameinfo['objcount'] = sum(
            [len(a) for a in self.dispgroup['objplayers']])

        self.statObjN.update(self.frameinfo['objcount'])

        self.doFireAndAutoMoveByTime(frameinfo)

        # make collision dictionary
        resultdict, self.frameinfo['cmpcount'] = self.makeCollisionDict()
        self.statCmpN.update(self.frameinfo['cmpcount'])
        # do score
        ischanagestatistic = self.doScore(resultdict)
        # ischanagestatistic = self.doScoreSimple(resultdict)

        # 결과에 따라 삭제한다.
        for aa in self.dispgroup['objplayers']:
            aa.RemoveDisabled()

        self.dispgroup['effectObjs'].AutoMoveByTime(
            self.thistick).RemoveDisabled()

        self.statPacketL.update(self.saveState())

        # 화면에 표시
        if ischanagestatistic:
            print 'objs:', self.statObjN
            print 'cmps:', self.statCmpN
            print 'packetlen:', self.statPacketL
            print 'fps:', self.frameinfo['stat']
            self.diaplayScore()

        return ''

    def diaplayScore(self):
        print "{:8} {:8} {:>8} {:>8} {:>8}".format(
            'teamname', 'color', 'AI type', 'member', 'score'
        )
        sortedinfo = sorted(
            self.dispgroup['objplayers'], key=lambda x: -x.statistic['teamscore'])

        for j in sortedinfo:
            print "{:8} {:8} {:>8} {:8} {:8.4f}".format(
                j.teamname,
                j.resource,
                j.__class__.__name__,
                j.membercount,
                j.statistic['teamscore'],
            )

    def doGame(self):
        while True:
            self.FPSTimer(0)
            time.sleep(self.newdur / 1000.)

# ================ tcp server ========

import threading
import SocketServer
import struct
headerStruct = struct.Struct('!I')


class ThreadedTCPRequestHandler(SocketServer.BaseRequestHandler):

    def handle(self):
        # data = self.request.recv(1024)
        # cur_thread = threading.current_thread()
        # response = "{}: {}".format(cur_thread.name, data)
        senddata = gameState
        self.request.sendall(headerStruct.pack(len(senddata)))
        self.request.sendall(senddata)


class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    allow_reuse_address = True
    pass


import signal
import sys


def runService():
    HOST, PORT = "localhost", 22517

    server = ThreadedTCPServer((HOST, PORT), ThreadedTCPRequestHandler)
    #ip, port = server.server_address

    # Start a thread with the server -- that thread will then start one
    # more thread for each request
    server_thread = threading.Thread(target=server.serve_forever)
    # Exit the server thread when the main thread terminates
    server_thread.daemon = True
    #server_thread.daemon = False
    server_thread.start()

    def sigstophandler(signum, frame):
        print 'User Termination'
        server.shutdown()
        server_thread.join(1)
        sys.exit(0)
    signal.signal(signal.SIGINT, sigstophandler)

# ================ tcp server end =======


if __name__ == "__main__":
    runService()
    ShootingGameServer().doGame()
