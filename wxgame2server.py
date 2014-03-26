#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" wxgame server
게임 서버용으로 수정, wxpython code를 제거
"""
import time
import math
import zlib
import multiprocessing
import cProfile as Profile
import pstats
import random
import socket
import select
try:
    import simplejson as json
except:
    import json
import struct
import logging
import sys
import argparse
import signal
import Queue

from wxgame2lib import getFrameTime, toGzJson, SpriteObj, SendRecvStatMixin
from wxgame2lib import fromGzJson, FPSlogicBase, Statistics, Storage, getSerial
from wxgame2lib import GameObjectGroup, ShootingGameMixin, toGzJsonParams, AI2


def getLogger(level=logging.DEBUG):
    logger = multiprocessing.log_to_stderr()
    logger.setLevel(level)
    return logger


Log = getLogger(level=logging.WARN)
Log.critical('current loglevel is %s',
             logging.getLevelName(Log.getEffectiveLevel()))

g_profile = False


def makeBiPipe():
    # return ( canread , read , write ) * 2
    _reader1, _writer1 = multiprocessing.Pipe(duplex=False)
    _reader2, _writer2 = multiprocessing.Pipe(duplex=False)
    return (_reader1.poll, _reader1.recv, _writer2.send), (_reader2.poll, _reader2.recv, _writer1.send)


class I32ClientProtocol(object):

    headerStruct = struct.Struct('!I')
    headerLen = struct.calcsize('!I')

    def __init__(self, sock, recvcallback):
        self.recvcallback = recvcallback
        self.sendQueue = Queue.Queue()
        self.sock = sock
        self.safefileno = sock.fileno()
        self.readbuf = []  # memorybuf, toreadlen , buf state
        self.writebuf = []  # memorybuf, towritelen

    def __str__(self):
        return '[{}:{}:{}:{}]'.format(
            self.__class__.__name__,
            self.sock,
            self.readbuf,
            self.writebuf,
        )

    def recv(self):
        """ async recv
        recv completed packet is put to recv packet
        """
        if self.readbuf == []:  # read header
            self.readbuf = [
                memoryview(bytearray(self.headerLen)),
                self.headerLen,
                'header'
            ]

        nbytes = self.sock.recv_into(
            self.readbuf[0][-self.readbuf[1]:], self.readbuf[1])
        if nbytes == 0:
            return 'disconnected'
        self.readbuf[1] -= nbytes

        if self.readbuf[1] == 0:  # complete recv
            if self.readbuf[2] == 'header':
                bodylen = self.headerStruct.unpack(
                    self.readbuf[0].tobytes())[0]
                self.readbuf = [
                    memoryview(bytearray(bodylen)),
                    bodylen,
                    'body'
                ]
            elif self.readbuf[2] == 'body':
                self.recvcallback(self.readbuf[0].tobytes())
                self.readbuf = []
                return 'complete'
            else:
                Log.error('invalid recv state %s', self.readbuf[2])
                return 'unknown'
        return 'cont'

    def canSend(self):
        return not self.sendQueue.empty() or len(self.writebuf) != 0

    def send(self):
        if self.sendQueue.empty() and len(self.writebuf) == 0:
            return 'sleep'  # send queue empty
        if len(self.writebuf) == 0:  # send new packet
            tosenddata = self.sendQueue.get()
            headerdata = self.headerStruct.pack(len(tosenddata))
            self.writebuf = [
                [memoryview(headerdata), 0],
                [memoryview(tosenddata), 0]
            ]
        wdata = self.writebuf[0]
        sentlen = self.sock.send(wdata[0][wdata[1]:])
        if sentlen == 0:
            raise RuntimeError("socket connection broken")
        wdata[1] += sentlen
        if len(wdata[0]) == wdata[1]:  # complete send
            del self.writebuf[0]
            if len(self.writebuf) == 0:
                return 'complete'
        return 'cont'

    def fileno(self):
        return self.sock.fileno()


class ProfileMixin(object):

    def startProfile(self):
        if g_profile:
            self.profile = Profile.Profile()
            self.profile.enable()

    def endProfile(self):
        if g_profile:
            self.profile.disable()
            pstats.Stats(self.profile).strip_dirs().sort_stats(
                'time').print_stats(20)


class TCP2PipeServer(multiprocessing.Process, SendRecvStatMixin, ProfileMixin):

    def __init__(self):
        multiprocessing.Process.__init__(self)
        my, self.forgame = makeBiPipe()
        self.canReadFromGame, self.readFromGame, self.writeToGame = my

    def getChannel(self):
        return self.forgame

    def run(self):
        self.startProfile()

        Log.critical('TCP2PipeServer initing pid:%s', self.pid)
        SendRecvStatMixin.__init__(self)

        # create an INET, STREAMing socket
        self.serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # reuse address
        self.serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.serversocket.setsockopt(
            socket.IPPROTO_TCP, socket.TCP_NODELAY, True)
        # bind the socket to a public host,
        # and a well-known port
        self.serversocket.bind(('0.0.0.0', 22517))
        # become a server socket
        self.serversocket.listen(5)

        self.quit = False
        self.clientDict = {}
        self.recvlist = [self.serversocket]
        self.sendlist = []
        Log.info('TCP2PipeServer started')

        self.serverLoop()

    def serverLoop(self):
        Log.info('start serverLoop')

        while not self.quit:
            self.sendlist = [
                s for s in self.recvlist[1:] if s.canSend()]
            inputready, outputready, exceptready = select.select(
                self.recvlist, self.sendlist, [], 1.0 / 120)

            for i in inputready:
                if i == self.serversocket:
                    # handle the server socket
                    client, address = self.serversocket.accept()
                    self.addNewClient(client, address)
                else:
                    try:
                        r = i.recv()
                    except socket.error as e:
                        # print traceback.format_exc()
                        self.closeClient(i)
                    if r == 'complete':
                        self.updateRecvStat()
                    elif r == 'disconnected':
                        self.closeClient(i)

            for o in outputready:
                try:
                    if o.send() == 'complete':
                        self.updateSendStat()
                except socket.error as e:
                    # print traceback.format_exc()
                    self.closeClient(i)

            while self.canReadFromGame():
                sockid, packet = self.readFromGame()
                if sockid == -1:
                    self.quit = True
                    break
                if sockid in self.clientDict:
                    self.clientDict[sockid].sendQueue.put(packet)

        Log.info('ending serverLoop')
        self.serversocket.close()
        for p in self.recvlist[1:]:
            self.closeClient(p)
        Log.info('end serverLoop')
        Log.info('%s', self.getStatInfo())

        self.endProfile()

    def addNewClient(self, client, address):
        Log.info('client connected %s %s', client, address)

        def newPacketRecved(packet):
            self.writeToGame((client.fileno(), packet))
        protocol = I32ClientProtocol(client, newPacketRecved)
        self.clientDict[client.fileno()] = protocol
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

        self.writeToGame((p.safefileno, toGzJsonParams(cmd='del')))
        try:
            del self.clientDict[p.safefileno]
        except KeyError:
            pass

        p.sock.close()


class NPCServer(multiprocessing.Process, FPSlogicBase, ShootingGameMixin, ProfileMixin):

    def __init__(self, aicount):
        multiprocessing.Process.__init__(self)
        my, self.forgame = makeBiPipe()
        self.canReadFromGame, self.readFromGame, self.writeToGame = my
        self.aicount = aicount

    def prfps(self, repeatinfo):
        print 'fps:', self.statFPS

    def getChannel(self):
        return self.forgame

    def applyState(self, loadlist):
        ShootingGameMixin.applyState(
            self, AI2, SpriteObj, loadlist)

    def run(self):
        self.startProfile()
        Log.critical('NPCServer initing pid:%s', self.pid)
        self.FPSTimerInit(getFrameTime, 60)

        self.dispgroup = {}
        self.dispgroup['effectObjs'] = GameObjectGroup().initialize(
            gameObj=self, spriteClass=SpriteObj, teamcolor=(0x7f, 0x7f, 0x7f))
        self.dispgroup['objplayers'] = []

        #self.registerRepeatFn(self.prfps, 1)

        self.quit = False
        Log.info('NPCServer started')
        self.allInited = False
        self.thistick = getFrameTime()
        self.clientDict = {}
        for i in range(self.aicount):
            idno = (1, getSerial())
            self.clientDict[idno] = Storage(
                idno=idno,
                teamname=None,
                teamcolor=None,
                teamid=None,
                teamStartTime=None,
            )
            self.makeTeam(idno)

        Log.info('NPC server started')
        self.clientLoop()

    def makeTeam(self, idno):
        teamname = 'AI_%08X' % random.getrandbits(32)
        teamcolor = (random.randint(0, 255),
                     random.randint(0, 255), random.randint(0, 255))
        Log.debug('makeTeam %s %s', teamname, teamcolor)
        self.writeToGame((idno, toGzJsonParams(
            cmd='makeTeam',
            teamname=teamname,
            teamcolor=teamcolor
        )))

    def madeTeam(self, idno, cmdDict):
        teamname = cmdDict.get('teamname')
        teamid = cmdDict.get('teamid')
        self.clientDict[idno].teamname = teamname
        self.clientDict[idno].teamid = teamid
        self.clientDict[idno].teamStartTime = self.thistick
        Log.debug('joined %s ', self.clientDict[idno])

    def reqState(self):
        self.writeToGame(((1, 0), toGzJsonParams(cmd='reqState')))

    def doFPSlogic(self):
        self.thistick = self.frameinfo['thistime']

    def clientLoop(self):
        Log.info('start clientLoop')
        self.sendlist = []
        self.reqState()

        while not self.quit:
            if self.canReadFromGame():
                idno, packet = self.readFromGame()
                if idno == -1:
                    self.quit = True
                    break
                if packet is not None:
                    self.process1Cmd(idno, packet)

            self.FPSTimer(0)
            time.sleep(self.newdur / 1000.)

        Log.info('ending clientLoop')
        self.endProfile()

    def process1Cmd(self, idno, packet):
        cmdDict = fromGzJson(packet)
        cmd = cmdDict.get('cmd')
        if cmd == 'gameState':
            self.reqState()
            self.applyState(cmdDict)

            if not self.allInited:  # first time
                allSent = True
                for idno, c in self.clientDict.iteritems():
                    if self.makeClientAIAction(idno) is not True:
                        allSent = False
                if allSent:
                    self.allInited = True

        elif cmd == 'actACK':
            self.makeClientAIAction(idno)
        elif cmd == 'teamInfo':
            self.madeTeam(idno, cmdDict)
        else:
            Log.warn('unknown cmd %s', cmdDict)

    def makeClientAIAction(self, idno):
        # make AI action
        if idno not in self.clientDict:
            return False
        client = self.clientDict[idno]
        aa = self.getTeamByID(client.teamid)
        if aa is None:
            return False
        targets = [tt for tt in self.dispgroup[
            'objplayers'] if tt.teamname != aa.teamname]
        aa.prepareActions(
            targets,
            self.frameinfo['ThisFPS'],
            self.thistick
        )
        actions = aa.SelectAction(targets, aa[0])
        actionjson = self.serializeActions(actions)
        self.writeToGame((idno, toGzJsonParams(
            cmd='act',
            teamid=client.teamid,
            actions=actionjson,
        )))
        return True


class GameLogicServer(multiprocessing.Process, ShootingGameMixin, FPSlogicBase, ProfileMixin):

    def __init__(self, qameCh, npcCh):
        multiprocessing.Process.__init__(self)
        self.canReadFromTcp, self.readFromTcp, self.writeToTcp = qameCh
        self.canReadFromNpc, self.readFromNpc, self.writeToNpc = npcCh

        my, self.formain = makeBiPipe()
        self.canReadFromMain, self.readFromMain, self.writeToMain = my

    def getChannel(self):
        return self.formain

    def run(self):
        self.startProfile()
        Log.critical('GameLogicServer initing pid:%s', self.pid)
        self.FPSTimerInit(getFrameTime, 60)

        self.dispgroup = {}
        self.dispgroup['effectObjs'] = GameObjectGroup().initialize(
            gameObj=self, spriteClass=SpriteObj, teamcolor=(0x7f, 0x7f, 0x7f))
        self.dispgroup['objplayers'] = []

        self.statObjN = Statistics()
        self.statCmpN = Statistics()
        self.statGState = Statistics()

        self.clients = {}  # clientid : team info
        self.gameState = None
        self.quit = False

        Log.info('GameLogicServer inited')
        #self.registerRepeatFn(self.prfps, 1)

        self.gameLoop()

    def gameLoop(self):
        while not self.quit:
            if self.canReadFromMain():
                break
            self.FPSTimer(0)
            time.sleep(self.newdur / 1000.)

        self.writeToTcp((-1, None))  # quit tcp server
        self.writeToNpc((-1, None))  # quit tcp server
        Log.info('end doGame')
        self.prfps(0)
        self.endProfile()

    def prfps(self, repeatinfo):
        self.diaplayScore()

        Log.critical('objs: %s', self.statObjN)
        Log.critical('cmps: %s', self.statCmpN)
        Log.critical('gamestatelen: %s', self.statGState)
        Log.critical('fps: %s', self.frameinfo['stat'])
        Log.critical('clients %s ', len(self.clients))

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

        Log.critical("{:12} {:15} {:>16} {:>8} {:>8} {:8}".format(
            'teamname', 'color', 'AI type', 'member', 'score', 'objcount'
        ))
        sortedinfo = sorted(
            teamscore.keys(), key=lambda x: -teamscore[x]['teamscore'])

        for j in sortedinfo:
            Log.critical("{:12} {:15} {:>16} {:8} {:8.4f} {:8}".format(
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
            self.gameState = savelist
        except zlib.error:
            Log.exception('zlib compress fail')
            return 0
        except ValueError:
            Log.exception('encode fail')
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

    def processClientCmd(self):
        while self.canReadFromTcp():
            clientid, packet = self.readFromTcp()
            cmdDict = fromGzJson(packet)
            self.do1ClientCmd(clientid, cmdDict)

        while self.canReadFromNpc():
            clientid, packet = self.readFromNpc()
            cmdDict = fromGzJson(packet)
            self.do1ClientCmd(clientid, cmdDict)

    def do1ClientCmd(self, clientid, cmdDict):
        teaminfo = self.clients.get(clientid)
        if isinstance(clientid, tuple):
            writefn = self.writeToNpc
        else:
            writefn = self.writeToTcp
        if teaminfo is None:
            self.clients[clientid] = {}
            teaminfo = self.clients[clientid]
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
            teaminfo['teamid'] = o.ID
            teaminfo['teamname'] = tn
            writefn((clientid, toGzJsonParams(
                cmd='teamInfo', teamname=tn, teamid=o.ID)))
            Log.debug('Join team %s %s', tn, o.ID)

        elif cmd == 'del':
            Log.debug('Leave team %s', teaminfo)
            try:
                self.delTeamByID(teaminfo['teamid'])
            except KeyError:
                pass
            del self.clients[clientid]

        elif cmd == 'reqState':
            writefn((clientid, self.gameState))

        elif cmd == 'act':
            writefn((clientid, toGzJsonParams(cmd='actACK')))

            actions = cmdDict.get('actions')
            tid = cmdDict['teamid']
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

    def doFPSlogic(self):
        self.thistick = self.frameinfo['thistime']

        self.frameinfo['objcount'] = sum(
            [len(a) for a in self.dispgroup['objplayers']])

        self.statObjN.update(self.frameinfo['objcount'])

        # 그룹내의 bounceball 들을 AI automove 한다.
        for thisTeam in self.dispgroup['objplayers']:
            thisTeam.AutoMoveByTime(self.thistick)

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

        self.statGState.update(self.saveState())


def runServer():
    global g_profile

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-n', '--aicount',
        type=int,
        help='server ai count'
    )
    parser.add_argument(
        '-t', '--time',
        type=int,
        help='time sec to run'
    )
    parser.add_argument(
        '-p', '--profile',
        type=bool,
        help='do profile'
    )
    args = parser.parse_args()
    aicount = args.aicount
    if aicount is None:
        aicount = 8
    timetorun = args.time
    if timetorun is None:
        timetorun = 60

    if args.profile is not None:
        g_profile = args.profile

    Log.critical('wxgame2server starting')

    tcp_process = TCP2PipeServer()
    tcp_process.start()
    npc_process = NPCServer(aicount=aicount)
    npc_process.start()

    game_process = GameLogicServer(
        qameCh=tcp_process.getChannel(), npcCh=npc_process.getChannel())
    game_process.start()
    canReadFromGame, readFromGame, writeToGame = game_process.getChannel()

    time.sleep(timetorun)

    Log.critical('wxgame2server ending')
    writeToGame((-1, None))
    game_process.join(1)
    tcp_process.join(1)
    npc_process.join(1)

if __name__ == "__main__":
    runServer()
