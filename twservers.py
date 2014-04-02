#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" wxgame server
게임 서버용으로 수정, wxpython code를 제거
"""

import sys
if __name__ == '__main__' and sys.platform == 'linux2':
    print 'running by epollreactor'
    from twisted.internet import epollreactor
    epollreactor.install()
from twisted.internet import reactor

from twisted.internet import protocol
from twisted.protocols.basic import Int32StringReceiver
from twisted.internet.protocol import ReconnectingClientFactory, ClientFactory
from twisted.internet import task
from twisted.python import log

import time
import math
import zlib
import random

from wxgame2lib import Statistics, FPSMixin, getFrameTime
from wxgame2lib import fromGzJson, toGzJsonParams, toGzJson
from wxgame2lib import GameObjectGroup, ShootingGameMixin, SpriteObj, AI2

log.startLogging(sys.stdout)


class ServerType:
    Any = 0
    Npc = 1
    Tcp = 2
    Game = 3
    Main = 4
    Unknown = 0xfffe
    All = 0xffff


class NPCProtocol(Int32StringReceiver):

    def connectionMade(self):
        self.factory.clientCount += 1
        self.teaminfo = None
        self.aiactionSent = False
        self.makeTeam()
        self.factory.clients.append(self)
        log.msg('client inited')

    def connectionLost(self, reason):
        self.factory.clientCount -= 1
        self.factory.clients.remove(self)
        if len(self.factory.clients) == 0:
            reactor.stop()

    def stringReceived(self, string):
        self.factory.recvcount += 1
        self.factory.sendcount += 1
        cmdDict = fromGzJson(string)
        self.factory.process1Cmd(self, cmdDict)

    def makeTeam(self):
        teamname = 'AI_%08X' % random.getrandbits(32)
        teamcolor = (random.randint(0, 255),
                     random.randint(0, 255), random.randint(0, 255))
        log.msg('makeTeam %s %s', teamname, teamcolor)
        self.sendString(toGzJsonParams(
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

    def reqState(self):
        self.sendString(toGzJsonParams(
            cmd='reqState',
        ))


class NPCServer(ClientFactory, ShootingGameMixin, FPSMixin):
    protocol = NPCProtocol

    def printStat(self):
        log.msg('fps: ', self.frameinfo.stat)
        log.msg(self.getStatInfo())
        self.recvcount, self.sendcount, self.initedTime = 0, 0, time.time()

    def applyState(self, loadlist):
        ShootingGameMixin.applyState(self, AI2, SpriteObj, loadlist)

    def getStatInfo(self):
        t = time.time() - self.initedTime
        return 'recv:{} {}/s send:{} {}/s'.format(
            self.recvcount, self.recvcount / t,
            self.sendcount, self.sendcount / t
        )

    def startFactory(self):
        self.FPSInit(getFrameTime, 60)
        self.recvcount, self.sendcount, self.initedTime = 0, 0, time.time()
        self.clientCount = 0

        self.dispgroup = {}
        self.dispgroup['effectObjs'] = GameObjectGroup().initialize(
            gameObj=self, spriteClass=SpriteObj, teamcolor=(0x7f, 0x7f, 0x7f))
        self.dispgroup['objplayers'] = []
        self.clients = []

        task.LoopingCall(self.printStat).start(1.0)
        task.LoopingCall(self.FPSRun).start(1.0 / 60)
        log.msg('NPC server started')

    def makeClientAIAction(self, client):
        # make AI action
        if client.teaminfo is None:
            return False
        aa = self.getTeamByID(client.teaminfo['teamid'])
        if aa is None:
            client.sendString(toGzJsonParams(
                cmd='act',
                teamid=client.teaminfo['teamid'],
                actions=[],
            ))
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
        client.sendString(toGzJsonParams(
            cmd='act',
            teamid=client.teaminfo['teamid'],
            actions=actionjson,
        ))
        return True

    def process1Cmd(self, client, cmdDict):
        cmd = cmdDict.get('cmd')
        if cmd == 'gameState':
            self.applyState(cmdDict)

        elif cmd == 'actACK':
            self.makeClientAIAction(client)
        elif cmd == 'teamInfo':
            client.madeTeam(cmdDict)
            client.teaminfo['teamStartTime'] = self.thistick
            print self.makeClientAIAction(client), client.teaminfo
        else:
            log.msg('unknown cmd ', cmdDict)

    def FPSMain(self):
        self.thistick = self.frameinfo.thisFrameTime
        if len(self.clients) > 0:
            self.clients[0].reqState()


class GameLogicProtocol(Int32StringReceiver):

    def connectionMade(self):
        self.factory.clientCount += 1

    def stringReceived(self, string):
        self.factory.recvcount += 1
        self.factory.sendcount += 1
        cmdDict = fromGzJson(string)
        self.factory.do1ClientCmd(self, cmdDict)

        # self.sendString(string)

    def connectionLost(self, reason):
        self.factory.clientCount -= 1


class GameLogicServer(ShootingGameMixin, FPSMixin, protocol.Factory):
    protocol = GameLogicProtocol

    def printStat(self):
        self.diaplayScore()
        log.msg('objs: ', self.statObjN)
        log.msg('cmps: ', self.statCmpN)
        log.msg('gamestatelen: ', self.statGState)
        log.msg('fps: ', self.frameinfo.stat)
        log.msg(self.getStatInfo())
        self.recvcount, self.sendcount, self.initedTime = 0, 0, time.time()

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

        log.msg("{:12} {:15} {:>16} {:>8} {:>8} {:8}".format(
            'teamname', 'color', 'AI type', 'member', 'score', 'objcount'
        ))
        sortedinfo = sorted(
            teamscore.keys(), key=lambda x: -teamscore[x]['teamscore'])

        for j in sortedinfo:
            log.msg("{:12} {:15} {:>16} {:8} {:8.4f} {:8}".format(
                j,
                teamscore[j]['color'],
                teamscore[j]['ai'],
                teamscore[j]['member'],
                teamscore[j]['teamscore'],
                teamscore[j]['objcount']
            ))

    def getStatInfo(self):
        t = time.time() - self.initedTime
        return 'clients:{} recv:{} {}/s send:{} {}/s'.format(
            self.clientCount,
            self.recvcount, self.recvcount / t,
            self.sendcount, self.sendcount / t
        )

    def doScore(self, resultdict):
        for src, targets in resultdict.iteritems():
            src.enabled = False
            if src.objtype != 'bounceball':
                self.dispgroup['effectObjs'].addSpriteExplosionEffect(src)
            else:
                # 충돌한 것이 bounceball 이면
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
                            for i in xrange(inclevel):
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
            'frameinfo': {'thisFrameTime': time.time()},
            'objplayers': [og.serialize() for og in self.dispgroup['objplayers']],
            'effectObjs': self.dispgroup['effectObjs'].serialize()
        }
        return savelist

    def saveState(self):
        try:
            savelist = toGzJson(self.makeState())
            self.gameState = savelist
        except zlib.error:
            log.msg('zlib compress fail')
            return 0
        except ValueError:
            log.msg('encode fail')
            return 0

        return len(savelist)

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

    def startFactory(self):
        self.FPSInit(getFrameTime, 60)
        self.recvcount, self.sendcount, self.initedTime = 0, 0, time.time()
        self.clientCount = 0

        self.dispgroup = {}
        self.dispgroup['effectObjs'] = GameObjectGroup().initialize(
            gameObj=self, spriteClass=SpriteObj, teamcolor=(0x7f, 0x7f, 0x7f))
        self.dispgroup['objplayers'] = []

        self.statObjN = Statistics()
        self.statCmpN = Statistics()
        self.statGState = Statistics()

        self.gameState = toGzJson(self.makeState())
        task.LoopingCall(self.printStat).start(1.0)
        task.LoopingCall(self.FPSRun).start(1.0 / 60)
        log.msg('Factory inited')

    def do1ClientCmd(self, clinentprotocol, cmdDict):
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

            clinentprotocol.sendString(toGzJsonParams(
                cmd='teamInfo', teamname=tn, teamid=o.ID))

        elif cmd == 'del':
            try:
                self.delTeamByID(cmdDict['teamid'])
            except KeyError:
                pass

        elif cmd == 'reqState':
            clinentprotocol.sendString(self.gameState)

        elif cmd == 'act':
            clinentprotocol.sendString(toGzJsonParams(cmd='actACK'))

            actions = cmdDict.get('actions')
            tid = cmdDict['teamid']
            thisTeam = self.getTeamByID(tid)
            if thisTeam.servermove:
                log.msg('invalid client team ', thisTeam)
                return
            actionjson = cmdDict['actions']
            actions = self.deserializeActions(actionjson)

            enemyTeamList = self.getEnemyTeamList(thisTeam)
            thisTeam.prepareActions(
                enemyTeamList,
                self.frameinfo.lastFPS,
                self.thistick
            )

            thisTeam.applyActions(actions)

        else:
            log.msg('unknown cmd ', cmdDict)

    def FPSMain(self):
        self.thistick = self.frameinfo.thisFrameTime

        objcount = sum([len(a) for a in self.dispgroup['objplayers']])
        self.statObjN.update(objcount)

        # 그룹내의 team 들을 automove 한다.
        for thisTeam in self.dispgroup['objplayers']:
            thisTeam.AutoMoveByTime(self.thistick)

        # make collision dictionary
        resultdict, cmpcount = self.makeCollisionDict()

        self.statCmpN.update(cmpcount)
        # do score
        self.doScore(resultdict)

        # 결과에 따라 삭제한다.
        for aa in self.dispgroup['objplayers']:
            aa.RemoveDisabled()

        self.dispgroup['effectObjs'].AutoMoveByTime(
            self.thistick).RemoveDisabled()

        self.statGState.update(self.saveState())


def makeServer():
    reactor.listenTCP(22517, GameLogicServer())
    reactor.run()


def makeClients(cn):
    for i in xrange(cn):
        reactor.connectTCP('localhost', 22517, NPCServer())
    reactor.run()


if __name__ == "__main__":

    if sys.argv[1] == 's':
        print 'makeserver'
        makeServer()
    else:
        print 'makeclient'
        makeClients(int(sys.argv[1]))
