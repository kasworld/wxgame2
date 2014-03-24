#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" wxgame server
게임 서버용으로 수정, wxpython code를 제거
"""
import time
import math
import random
import itertools
import zlib
import threading
import socket
import select
try:
    import simplejson as json
except:
    import json
import sys
import argparse
import signal
import Queue
import logging

from euclid import Vector2
from wxgame2lib import getFrameTime, getLogger, toGzJson, SpriteObj, SendRecvStatMixin
from wxgame2lib import putParams2Queue, fromGzJson, FPSlogicBase, Statistics, AI2
from wxgame2lib import GameObjectGroup, ShootingGameMixin, I32sendrecv, Storage

Log = getLogger(level=logging.ERROR, appname='wxgame2server')
Log.critical('current loglevel is %s',
             logging.getLevelName(Log.getEffectiveLevel()))


class TCPGameServer(threading.Thread, SendRecvStatMixin):

    def __init__(self, clientCommDict):
        self.clientCommDict = clientCommDict
        Log.info('tcp server starting')
        # create an INET, STREAMing socket
        self.serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # reuse address
        self.serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.serversocket.setsockopt(
            socket.IPPROTO_TCP, socket.TCP_NODELAY, True)

        # bind the socket to a public host,
        # and a well-known port
        #self.serversocket.bind((socket.gethostname(), 22517))
        self.serversocket.bind(('0.0.0.0', 22517))
        # become a server socket
        self.serversocket.listen(5)
        self.quit = False
        self.recvlist = [self.serversocket]
        self.sendlist = []
        SendRecvStatMixin.__init__(self)
        Log.info('tcp server started')

    def runService(self):
        tcp_thread = threading.Thread(target=self.serverLoop)
        tcp_thread.start()
        return self, tcp_thread

    def addNewClient(self, client, address):
        Log.info('client connected %s %s', client, address)
        protocol = I32sendrecv(client)
        conn = Storage({
            'protocol': protocol,
            'recvQueue': protocol.recvQueue,
            'sendQueue': protocol.sendQueue,
            'quit': False,
            'teamname': None,
            'teamid': None
        })
        self.clientCommDict['clients'].append(conn)
        self.recvlist.append(protocol)

    def closeClient(self, p):
        Log.info('client disconnected %s', p)
        try:
            self.recvlist.remove(p)
        except ValueError:
            pass
        try:
            self.sendlist.remove(p)
        except ValueError:
            pass

        putParams2Queue(
            p.recvQueue,
            cmd='del'
        )
        p.sock.close()

    def serverLoop(self):
        Log.info('start serverLoop')

        while not self.quit:
            self.sendlist = [
                s for s in self.recvlist[1:] if s.canSend()]
            # self.sendlist = [
            # s for s in self.recvlist if s != self.serversocket and
            # s.canSend()]
            inputready, outputready, exceptready = select.select(
                self.recvlist, self.sendlist, [], 1.0 / 120)
            for i in inputready:
                if i == self.serversocket:
                    # handle the server socket
                    client, address = self.serversocket.accept()
                    self.addNewClient(client, address)
                else:
                    try:
                        if i.recv() == 'complete':
                            self.updateRecvStat()
                    except RuntimeError as e:
                        if e.args[0] != "socket connection broken":
                            raise
                        self.closeClient(i)
                    except socket.error as e:
                        # print traceback.format_exc()
                        self.closeClient(i)

            for o in outputready:
                try:
                    if o.send() == 'complete':
                        self.updateSendStat()
                except socket.error as e:
                    # print traceback.format_exc()
                    self.closeClient(i)

        Log.info('closing serversocket')
        self.serversocket.close()
        Log.info('end serverLoop')
        Log.info('%s', self.getStatInfo())

    def shutdown(self):
        Log.info('tcp server ending')
        self.quit = True


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
        self.aicount = kwds.pop('aicount')
        self.server = kwds.pop('server')
        self.FPSTimerInit(getFrameTime, 60)
        self.initGroups(GameObjectGroup, SpriteObj)

        for i in range(self.aicount):
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
        Log.info('ShootingGameServer inited')
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
                Log.info("%s %s", conn.teamname, conn.protocol.getStatInfo())
        Log.critical('objs: %s', self.statObjN)
        Log.critical('cmps: %s', self.statCmpN)
        Log.critical('packetlen: %s', self.statPacketL)
        Log.critical('fps: %s', self.frameinfo['stat'])
        Log.critical('packets %s', self.server.getStatInfo())

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

        Log.info("{:12} {:15} {:>16} {:>8} {:>8} {:8}".format(
            'teamname', 'color', 'AI type', 'member', 'score', 'objcount'
        ))
        sortedinfo = sorted(
            teamscore.keys(), key=lambda x: -teamscore[x]['teamscore'])

        for j in sortedinfo:
            Log.info("{:12} {:15} {:>16} {:8} {:8.4f} {:8}".format(
                j,
                teamscore[j]['color'],
                teamscore[j]['ai'],
                teamscore[j]['member'],
                teamscore[j]['teamscore'],
                teamscore[j]['objcount']
            ))

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
            Log.exception('zlib compress fail')
            return 0
        except ValueError:
            Log.exception('encode fail')
            return 0

        return len(savelist)

    def processClientCmd(self):
        dellist = []
        for conn in self.clientCommDict['clients']:
            if conn is None:
                continue
            while not conn.recvQueue.empty():
                cmdDict = None
                try:
                    cmdDict = conn.recvQueue.get_nowait()
                except Queue.Empty:
                    break
                if cmdDict is None:
                    break
                cmdDict = fromGzJson(cmdDict)
                if self.do1ClientCmd(conn, cmdDict) is not None:
                    dellist.append(conn)
        for conn in dellist:
            try:
                self.clientCommDict['clients'].remove(conn)
            except ValueError:
                #Log.exception('not in clientCommDict %s', conn)
                pass

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
            Log.info('Join team %s %s', tn, o.ID)
            putParams2Queue(
                conn.sendQueue,
                cmd='teamInfo',
                teamname=tn,
                teamid=o.ID
            )

        elif cmd == 'del':
            Log.info('Leave team %s %s', conn.teamname, conn.teamid)
            self.delTeamByID(conn.teamid)
            return conn

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
                Log.error('invalid client team %s', thisTeam)
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

        else:
            Log.warn('unknown cmd %s', cmdDict)

    def doFireAndAutoMoveByTime(self):
        # 그룹내의 bounceball 들을 AI automove 한다.
        selmov = self.dispgroup['objplayers'][:]
        random.shuffle(selmov)
        for thisTeam in selmov:
            if thisTeam.servermove is not True:
                thisTeam.AutoMoveByTime(self.thistick)
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
        Log.info('end doGame')


def runServer():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-n', '--aicount',
        type=int,
        help='server ai count'
    )
    args = parser.parse_args()
    aicount = args.aicount
    if aicount is None:
        aicount = 8

    clientCommDict = {
        'gameState': '',
        'clients': [],
        'quit': False
    }
    Log.info('game Server starting')

    server, server_thread = TCPGameServer(clientCommDict).runService()

    def sigstophandler(signum, frame):
        Log.info('User Termination')
        clientCommDict['quit'] = True
        server.shutdown()
        server_thread.join(1)
        Log.info('server end')
        sys.exit(0)

    signal.signal(signal.SIGINT, sigstophandler)

    ShootingGameServer(
        clientCommDict=clientCommDict, aicount=aicount, server=server).doGame()


if __name__ == "__main__":
    runServer()
