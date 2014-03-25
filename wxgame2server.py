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
from wxgame2lib import putParams2Queue, fromGzJson, FPSlogicBase, Statistics
from wxgame2lib import GameObjectGroup, ShootingGameMixin, Storage, toGzJsonParams


def getLogger(level=logging.DEBUG):
    logger = multiprocessing.log_to_stderr()
    logger.setLevel(level)
    return logger


Log = getLogger(level=logging.DEBUG)
Log.critical('current loglevel is %s',
             logging.getLevelName(Log.getEffectiveLevel()))


def makeBiPipe():
    # return ( canread , read , write ) * 2
    _reader1, _writer1 = multiprocessing.Pipe(duplex=False)
    _reader2, _writer2 = multiprocessing.Pipe(duplex=False)
    return (_reader1.poll, _reader1.recv, _writer2.send), (_reader2.poll, _reader2.recv, _writer1.send)


class I32sendrecv(object):

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


class TCPGameServer(multiprocessing.Process, SendRecvStatMixin):

    def __init__(self):
        multiprocessing.Process.__init__(self)
        SendRecvStatMixin.__init__(self)
        my, self.forgame = makeBiPipe()
        self.canReadFromGame, self.readFromGame, self.writeToGame = my

    def getChannel(self):
        return self.forgame

    def run(self):
        def sigstophandler(signum, frame):
            Log.info('User Termination TCPGameServer')
            self.quit = True

        signal.signal(signal.SIGINT, sigstophandler)

        # self.tcpprofile = Profile.Profile()
        # self.tcpprofile.enable()

        Log.info('TCPGameServer initing pid:%s', self.pid)

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

        SendRecvStatMixin.__init__(self)
        self.quit = False
        self.clientDict = {}
        self.recvlist = [self.serversocket]
        self.sendlist = []
        Log.info('TCPGameServer started')

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
        for p in self.recvlist:
            self.closeClient(p)
        Log.info('end serverLoop')
        Log.info('%s', self.getStatInfo())

        # self.tcpprofile.disable()
        # self.tcpprofile.strip_dirs().sort_stats('tottime').print_stats(40)

    def addNewClient(self, client, address):
        Log.info('client connected %s %s', client, address)

        def newPacketRecved(packet):
            self.writeToGame((client.fileno(), packet))
        protocol = I32sendrecv(client, newPacketRecved)
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


class NPCServer(multiprocessing.Process, SendRecvStatMixin):
    pass


class ShootingGameServer(ShootingGameMixin, FPSlogicBase, SendRecvStatMixin):

    def __init__(self, *args, **kwds):
        def setAttr(name, defaultvalue):
            self.__dict__[name] = kwds.pop(name, defaultvalue)
            return self.__dict__[name]

        SendRecvStatMixin.__init__(self)
        self.FPSTimerInit(getFrameTime, 60)

        self.dispgroup = {}
        self.dispgroup['effectObjs'] = GameObjectGroup().initialize(
            gameObj=self, spriteClass=SpriteObj, teamcolor=(0x7f, 0x7f, 0x7f))
        self.dispgroup['objplayers'] = []

        self.statObjN = Statistics()
        self.statCmpN = Statistics()
        self.statGState = Statistics()

        self.clients = {}  # sockid : team info
        self.gameState = None
        self.quit = False

        self.canReadFromTcp, self.readFromTcp, self.writeToTcp = kwds.pop(
            'qameCh')

        Log.info('ShootingGameServer inited')
        self.registerRepeatFn(self.prfps, 1)

    def prfps(self, repeatinfo):
        self.diaplayScore()

        Log.critical('objs: %s', self.statObjN)
        Log.critical('cmps: %s', self.statCmpN)
        Log.critical('gamestatelen: %s', self.statGState)
        Log.critical('fps: %s', self.frameinfo['stat'])
        Log.critical('packets %s', self.getStatInfo())

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
            sockid, packet = self.readFromTcp()
            cmdDict = fromGzJson(packet)
            self.do1ClientCmd(sockid, cmdDict)

    def do1ClientCmd(self, sockid, cmdDict):
        teaminfo = self.clients.get(sockid)
        if teaminfo is None:
            self.clients[sockid] = {}
            teaminfo = self.clients[sockid]
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
            self.writeToTcp((sockid, toGzJsonParams(
                cmd='teamInfo', teamname=tn, teamid=o.ID)))
            Log.info('Join team %s %s', tn, o.ID)

        elif cmd == 'del':
            Log.info('Leave team %s', teaminfo)
            try:
                self.delTeamByID(teaminfo['teamid'])
            except KeyError:
                pass
            del self.clients[sockid]

        elif cmd == 'reqState':
            self.writeToTcp((sockid, self.gameState))

        elif cmd == 'act':
            self.writeToTcp((sockid, toGzJsonParams(cmd='actACK')))

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

    def doGame(self):
        while not self.quit:
            self.FPSTimer(0)
            time.sleep(self.newdur / 1000.)
        self.writeToTcp((-1, None))  # quit tcp server
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

    Log.info('wxgame2server starting')

    tcp_process = TCPGameServer()
    tcp_process.start()

    print tcp_process.getChannel()
    game = ShootingGameServer(qameCh=tcp_process.getChannel())

    def sigstophandler(signum, frame):
        Log.info('User Termination')
        game.quit = True
        tcp_process.join(1)
        Log.info('wxgame2server end')
        sys.exit(0)

    signal.signal(signal.SIGINT, sigstophandler)

    game.doGame()


if __name__ == "__main__":
    runServer()
