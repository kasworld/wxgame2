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
import Queue
import multiprocessing.queues

from wxgame2lib import getFrameTime, toGzJson, SpriteObj, FPSMixin
from wxgame2lib import fromGzJson, Statistics, Storage, getSerial
from wxgame2lib import GameObjectGroup, ShootingGameMixin, toGzJsonParams, AI2


def getLogger(level=logging.DEBUG):
    logger = multiprocessing.log_to_stderr()
    logger.setLevel(level)
    return logger


Log = getLogger(level=logging.WARN)
Log.critical('current loglevel is %s',
             logging.getLevelName(Log.getEffectiveLevel()))

g_profile = False


class ServerType:
    Any = 0
    Npc = 1
    Tcp = 2
    Game = 3
    Main = 4
    Unknown = 0xfffe
    All = 0xffff


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


class ChannelPipe(object):

    def __init__(self, reader, writer):
        self.initedTime = time.time()
        self.recvcount, self.sendcount = 0, 0
        self.sendQueue = Queue.Queue()

        self.reader, self.writer = reader, writer
        self.canreadfn = self.reader.poll
        self.readfn = self.reader.recv
        self.writefn = self.writer.send

    def __str__(self):
        return '[{}:{}:{}:{}]'.format(
            self.__class__.__name__,
            self.reader,
            self.writer,
            self.getStatInfo(),
        )

    def getStatInfo(self):
        t = time.time() - self.initedTime
        return 'recv:{} {}/s send:{} {}/s'.format(
            self.recvcount, self.recvcount / t,
            self.sendcount, self.sendcount / t
        )

    def canReadFrom(self):
        return self.canreadfn()

    def readFrom(self):
        self.recvcount += 1
        return self.readfn()

    def canSend(self):
        return not self.sendQueue.empty()

    def writeFromQueue(self):
        if self.sendQueue.empty():
            return 'sleep'  # send queue empty
        self.writeTo(self.sendQueue.get())

    def writeTo(self, obj):
        self.sendcount += 1
        return self.writefn(obj)


def makeChannel():
    reader1, writer1 = multiprocessing.Pipe(duplex=False)
    reader2, writer2 = multiprocessing.Pipe(duplex=False)
    return ChannelPipe(reader1, writer2), ChannelPipe(reader2, writer1)


class TCPServer(multiprocessing.Process, ProfileMixin):

    def __init__(self, servertype):
        multiprocessing.Process.__init__(self)
        self.toGameCh, self.forGameCh = makeChannel()
        self.serverType = servertype

    def getChannel(self):
        return self.forGameCh

    def getStatInfo(self):
        return 'recv:{} send{}'.format(self.recvcount, self.sendcount)

    def run(self):
        self.startProfile()
        self.recvcount, self.sendcount = 0, 0

        Log.critical('TCPServer initing pid:%s', self.pid)

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
        Log.info('TCPServer started')

        # wait for game is ready
        while not self.toGameCh.canReadFrom():
            time.sleep(0)
        self.toGameCh.readFrom()  # recv start packet

        Log.info('start serverLoop')
        self.recvlist = [self.serversocket, self.toGameCh.reader]
        self.sendlist = []

        while not self.quit:
            self.sendlist = [
                self.toGameCh.writer] if self.toGameCh.canSend() else []
            self.sendlist += [s for s in self.recvlist[2:] if s.canSend()]
            inputready, outputready, exceptready = select.select(
                self.recvlist, self.sendlist, [], 1.0 / 120)

            for i in inputready:
                if i == self.serversocket:
                    # handle the server socket
                    sock, address = self.serversocket.accept()
                    self.addNewClient(sock, address)
                elif i == self.toGameCh.reader:
                    idno, packet = self.toGameCh.readFrom()
                    if idno[-1] == -1:
                        self.quit = True
                        break
                    if idno in self.clientDict:
                        self.clientDict[idno].sendQueue.put(packet)
                    else:
                        Log.critical('unknown client %s', idno)
                else:
                    try:
                        r = i.recv()
                    except socket.error as e:
                        # print traceback.format_exc()
                        self.closeClient(i)
                    if r == 'complete':
                        self.recvcount += 1
                    elif r == 'disconnected':
                        self.closeClient(i)

            for o in outputready:
                if o == self.toGameCh.writer:
                    self.toGameCh.writeFromQueue()
                else:
                    try:
                        if o.send() == 'complete':
                            self.sendcount += 1
                    except socket.error as e:
                        # print traceback.format_exc()
                        self.closeClient(i)

        Log.info('ending serverLoop')
        self.serversocket.close()
        for p in self.recvlist[2:]:
            self.closeClient(p)
        Log.info('end serverLoop')
        Log.critical('TCP stat %s', self.getStatInfo())
        Log.critical('Ch stat %s', self.toGameCh.getStatInfo())

        self.endProfile()

    def addNewClient(self, sock, address):
        Log.info('client connected %s %s', sock, address)

        def newPacketRecved(packet):
            self.toGameCh.sendQueue.put(
                ((self.serverType, sock.fileno()), packet)
            )
        protocol = I32ClientProtocol(sock, newPacketRecved)
        self.clientDict[(self.serverType, sock.fileno())] = protocol
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

        self.toGameCh.writeTo(
            ((self.serverType, p.safefileno), toGzJsonParams(cmd='del'))
        )
        try:
            del self.clientDict[(self.serverType, p.safefileno)]
        except KeyError:
            pass

        p.sock.close()


class NPCServer(multiprocessing.Process, FPSMixin, ShootingGameMixin, ProfileMixin):

    def __init__(self, servertype, aicount):
        multiprocessing.Process.__init__(self)
        self.toGameCh, self.forGameCh = makeChannel()
        self.aicount = aicount
        self.serverType = servertype

    def prfps(self, repeatinfo):
        Log.critical('fps: %s', self.frameinfo.stat)
        Log.critical('game ch %s', self.toGameCh.getStatInfo())

    def getChannel(self):
        return self.forGameCh

    def applyState(self, loadlist):
        ShootingGameMixin.applyState(self, AI2, SpriteObj, loadlist)

    def applyState_test(self, loadlist):
        ShootingGameMixin.applyState(
            self, GameObjectGroup, SpriteObj, loadlist)

    def reqState(self):
        self.toGameCh.sendQueue.put(
            ((self.serverType, 0),
             toGzJsonParams(cmd='reqState')
             ))

    def makeTeam(self):
        idno = (self.serverType, getSerial())
        self.clientDict[idno] = Storage(
            teamname=None,
            teamid=None,
            teamStartTime=None,
        )
        teamname = 'AI_%08X' % random.getrandbits(32)
        teamcolor = [random.randint(0, 255) for i in [0, 1, 2]]
        Log.debug('makeTeam %s %s', teamname, teamcolor)
        self.toGameCh.sendQueue.put(
            (idno,
             toGzJsonParams(
                 cmd='makeTeam',
                 teamname=teamname,
                 teamcolor=teamcolor
             )))

    def madeTeam(self, oid, cmdDict):
        teamname = cmdDict.get('teamname')
        teamid = cmdDict.get('teamid')
        self.clientDict[oid].teamname = teamname
        self.clientDict[oid].teamid = teamid
        self.clientDict[oid].teamStartTime = self.thistick
        Log.debug('joined %s ', self.clientDict[oid])

    def run(self):
        self.startProfile()
        Log.critical('NPCServer initing pid:%s', self.pid)
        self.FPSInit(getFrameTime, 60)

        self.dispgroup = {}
        self.dispgroup['effectObjs'] = GameObjectGroup().initialize(
            gameObj=self, spriteClass=SpriteObj, teamcolor=(0x7f, 0x7f, 0x7f))
        self.dispgroup['objplayers'] = []

        self.quit = False
        self.allInited = False
        self.thistick = getFrameTime()
        self.clientDict = {}

        self.registerRepeatFn(self.prfps, 1)
        Log.info('NPCServer inited')

        # wait for game is ready
        while not self.toGameCh.canReadFrom():
            time.sleep(0)
        self.toGameCh.readFrom()  # recv start packet
        self.reqState()
        for i in range(self.aicount):
            self.makeTeam()

        Log.info('start serverLoop')

        self.recvlist = [self.toGameCh.reader]
        self.sendlist = []
        while not self.quit:
            self.sendlist = [
                self.toGameCh.writer] if self.toGameCh.canSend() else []
            inputready, outputready, exceptready = select.select(
                self.recvlist, self.sendlist, [], 1.0 / 120)

            if len(inputready) == 0 and len(outputready) == 0:
                self.FPSRun()
                self.FPSYield()
                self.thistick = self.frameinfo.thisFrameTime

            for i in inputready:
                if i == self.toGameCh.reader:
                    idno, packet = self.toGameCh.readFrom()
                    if idno[-1] == -1:
                        self.quit = True
                        break
                    if packet is not None:
                        self.process1Cmd(idno, packet)

            for o in outputready:
                if o == self.toGameCh.writer:
                    self.toGameCh.writeFromQueue()

        Log.critical('NPCServer end.')
        self.prfps(0)

        self.endProfile()

    def FPSMain(self):
        return

    def process1Cmd(self, idno, packet):
        cmdDict = fromGzJson(packet)
        cmd = cmdDict.get('cmd')
        if cmd == 'gameState':
            self.reqState()
            self.applyState(cmdDict)

            if not self.allInited:  # first time
                allSent = True
                for i, c in self.clientDict.iteritems():
                    if self.makeClientAIAction(i) is not True:
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
            self.frameinfo.lastFPS,
            self.thistick
        )
        actions = aa.SelectAction(targets, aa[0])
        actionjson = self.serializeActions(actions)
        self.toGameCh.sendQueue.put(
            (idno,
             toGzJsonParams(
                 cmd='act',
                 teamid=client.teamid,
                 actions=actionjson,
             )))
        return True


class GameLogicServer(multiprocessing.Process, ShootingGameMixin, FPSMixin, ProfileMixin):

    def prfps(self, repeatinfo):
        self.diaplayScore()

        Log.critical('objs: %s', self.statObjN)
        Log.critical('cmps: %s', self.statCmpN)
        Log.critical('gamestatelen: %s', self.statGState)
        Log.critical('fps: %s', self.frameinfo.stat)
        Log.critical('clients %s ', len(self.clients))
        Log.critical('main channel %s ', self.toMainCh.getStatInfo())
        for c in self.channels:
            Log.critical('channel %s ', c.getStatInfo())

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

    def getChannel(self):
        return self.forMainCh

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
            'frameinfo': {k: v for k, v in self.frameinfo.iteritems() if k in ['thisFrameTime']},
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

    def __init__(self, servertype, channels):
        multiprocessing.Process.__init__(self)
        self.serverType = servertype
        self.channels = channels
        self.toMainCh, self.forMainCh = makeChannel()

    def run(self):
        self.startProfile()
        self.recvcount, self.sendcount = 0, 0
        Log.critical('GameLogicServer initing pid:%s', self.pid)
        self.FPSInit(getFrameTime, 60)

        self.dispgroup = {}
        self.dispgroup['effectObjs'] = GameObjectGroup().initialize(
            gameObj=self, spriteClass=SpriteObj, teamcolor=(0x7f, 0x7f, 0x7f))
        self.dispgroup['objplayers'] = []

        self.statObjN = Statistics()
        self.statCmpN = Statistics()
        self.statGState = Statistics()

        self.clients = {}  # clientid : team info
        self.gameState = toGzJson({
            'cmd': 'gameState',
            'frameinfo': {k: v for k, v in self.frameinfo.iteritems() if k in ['thisFrameTime']},
            'objplayers': [og.serialize() for og in self.dispgroup['objplayers']],
            'effectObjs': self.dispgroup['effectObjs'].serialize()
        })
        self.quit = False
        self.registerRepeatFn(self.prfps, 1)

        self.r2c = {}
        self.w2c = {}
        for c in self.channels:
            self.r2c[c.reader] = c
            self.w2c[c.writer] = c
        Log.info('GameLogicServer inited')

        for ch in self.channels:
            ch.writeTo(((0, 0), None))  # run server

        # main loop
        self.recvlist = [self.toMainCh.reader] + [
            c.reader for c in self.channels]
        self.sendlist = []

        while not self.quit:
            self.sendlist = [o.writer for o in self.channels if o.canSend()]
            inputready, outputready, exceptready = select.select(
                self.recvlist, self.sendlist, [], 0)

            if len(inputready) == 0 and len(outputready) == 0:
                self.FPSRun()
                self.FPSYield()

            for i in inputready:
                if i == self.toMainCh.reader:
                    self.quit = True
                    break
                else:
                    if i in self.r2c:
                        clientid, packet = self.r2c[i].readFrom()
                        cmdDict = fromGzJson(packet)
                        self.do1ClientCmd(self.r2c[i], clientid, cmdDict)
                    else:
                        Log.critical('invalid reader %s', i)

            for o in outputready:
                if o in self.w2c:
                    self.w2c[o].writeFromQueue()
                else:
                    Log.critical('invalid writer %s', i)

        for ch in self.channels:
            ch.writeTo(((0, -1), None))  # quit server

        Log.info('end doGame')
        self.prfps(0)
        self.endProfile()

    def do1ClientCmd(self, ch, clientid, cmdDict):
        teaminfo = self.clients.get(clientid)
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
            ch.sendQueue.put((clientid, toGzJsonParams(
                cmd='teamInfo', teamname=tn, teamid=o.ID)))
            Log.debug('Join team %s %s', clientid, teaminfo)

        elif cmd == 'del':
            Log.debug('Leave team %s', teaminfo)
            try:
                self.delTeamByID(teaminfo['teamid'])
            except KeyError:
                pass
            del self.clients[clientid]

        elif cmd == 'reqState':
            ch.sendQueue.put((clientid, self.gameState))

        elif cmd == 'act':
            ch.sendQueue.put((clientid, toGzJsonParams(cmd='actACK')))

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
                self.frameinfo.lastFPS,
                self.thistick
            )

            thisTeam.applyActions(actions)

        else:
            Log.warn('unknown cmd %s', cmdDict)

    def FPSMain(self):
        self.thistick = self.frameinfo.thisFrameTime

        objcount = sum([len(a) for a in self.dispgroup['objplayers']])
        self.statObjN.update(objcount)

        # 그룹내의 bounceball 들을 AI automove 한다.
        for thisTeam in self.dispgroup['objplayers']:
            thisTeam.AutoMoveByTime(self.thistick)

        # process client cmds
        # self.processClientCmd()

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

    tcp_process = TCPServer(servertype=ServerType.Tcp)
    tcp_process.start()
    npc_process = NPCServer(aicount=aicount, servertype=ServerType.Npc)
    npc_process.start()

    game_process = GameLogicServer(
        channels=[tcp_process.getChannel(), npc_process.getChannel()],
        servertype=ServerType.Game
    )
    game_process.start()

    toGameCh = game_process.getChannel()

    time.sleep(timetorun)

    Log.critical('wxgame2server ending')
    toGameCh.writeTo(((0, -1), None))
    game_process.join(1)
    tcp_process.join(1)
    npc_process.join(1)


def chbench():
    me, you = makeChannel()
    st = time.time()
    count = 1000000
    for i in xrange(count):
        me.writeTo('hello')
        you.readFrom()
    ed = time.time()
    print ed - st, count / (ed - st)


if __name__ == "__main__":
    runServer()
    # chbench()
