#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" wxgame noui AI ssclient
    wxGameFramework
    Copyright 2011,2013,1014 kasw <kasworld@gmail.com>
"""
import random
import argparse
import sys
import signal
import select
import Queue
import time
import logging
import socket
from wxgame2lib import SpriteObj, FPSlogicBase, SendRecvStatMixin, fromGzJson, ShootingGameMixin
from wxgame2lib import getFrameTime, putParams2Queue, I32sendrecv, getLogger
from wxgame2lib import AI2 as GameObjectGroup

Log = getLogger(level=logging.DEBUG, appname='wxgame2npc')
Log.critical('current loglevel is %s',
             logging.getLevelName(Log.getEffectiveLevel()))


class TCPGameClient(I32sendrecv):

    def __str__(self):
        return '[{}:{}]'.format(
            self.__class__.__name__,
            self.teaminfo,
        )

    def __init__(self, connectTo):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(connectTo)
        I32sendrecv.__init__(self, sock)

        self.teaminfo = None
        self.aiactionSent = False
        self.makeTeam()
        Log.info('client inited %s', self)

    def disconnect(self):
        self.sock.close()
        Log.info('disconnect %s', self)

    def makeTeam(self):
        teamname = 'AI_%08X' % random.getrandbits(32)
        teamcolor = (random.randint(0, 255),
                     random.randint(0, 255), random.randint(0, 255))
        Log.info('makeTeam %s %s', teamname, teamcolor)
        putParams2Queue(
            self.sendQueue,
            cmd='makeTeam',
            teamname=teamname,
            teamcolor=teamcolor
        )

    def madeTeam(self, cmdDict):
        teamname = cmdDict.get('teamname')
        teamid = cmdDict.get('teamid')
        self.teaminfo = {
            'teamname': teamname,
            'teamid': teamid,
            'teamStartTime': None,
        }
        Log.info('joined %s %s %s', teamname, teamid, self.teaminfo)

    def reqState(self):
        putParams2Queue(
            self.sendQueue,
            cmd='reqState',
        )


class NPCServer(ShootingGameMixin, FPSlogicBase, SendRecvStatMixin):

    def __init__(self, *args, **kwds):
        self.FPSTimerInit(getFrameTime, 60)
        self.dispgroup = {}
        self.dispgroup['effectObjs'] = GameObjectGroup().initialize(
            gameObj=self, spriteClass=SpriteObj, teamcolor=(0x7f, 0x7f, 0x7f))
        self.dispgroup['objplayers'] = []

        self.connInit(kwds.pop('connectTo'), kwds.pop('aicount'))
        SendRecvStatMixin.__init__(self)

        self.registerRepeatFn(self.prfps, 1)

    def prfps(self, repeatinfo):
        print 'fps:', self.statFPS
        print 'packet:', self.getStatInfo()

    def applyState(self, loadlist):
        ShootingGameMixin.applyState(self, GameObjectGroup, SpriteObj, loadlist)

    def doFPSlogic(self):
        self.thistick = self.frameinfo['thistime']
        self.processCmd()

    def processCmd(self):
        for client in self.clients:
            while not client.recvQueue.empty():
                self.process1Cmd(client)

    def makeClientAIAction(self, client):
        # make AI action
        if client.teaminfo is None:
            return False
        aa = self.getTeamByID(client.teaminfo['teamid'])
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
        putParams2Queue(
            client.sendQueue,
            cmd='act',
            team=client.teaminfo,
            actions=actionjson,
        )
        return True

    def process1Cmd(self, client):
        try:
            cmdDict = client.recvQueue.get_nowait()
            if cmdDict is None:
                return
        except Queue.Empty:
            return
        cmdDict = fromGzJson(cmdDict)
        cmd = cmdDict.get('cmd')
        if cmd == 'gameState':
            client.reqState()
            self.applyState(cmdDict)

            if not self.allInited:  # first time
                allSent = True
                for c in self.clients:
                    if self.makeClientAIAction(c) is not True:
                        allSent = False
                if allSent:
                    self.allInited = True

        elif cmd == 'actACK':
            if client.teaminfo is not None:
                self.makeClientAIAction(client)
        elif cmd == 'teamInfo':
            client.madeTeam(cmdDict)
            client.teaminfo['teamStartTime'] = self.thistick
        else:
            Log.warn('unknown cmd %s', cmdDict)

    def connInit(self, connectTo, aicount):
        self.quit = False
        self.allInited = False
        Log.info('NPC server started')

        if connectTo[0] is None:
            connectTo = ('localhost', connectTo[1])
        self.clients = []
        for i in range(aicount):
            self.clients.append(TCPGameClient(connectTo))

        self.clients[0].reqState()

    def clientLoop(self):
        Log.info('start clientLoop')
        self.sendlist = []

        while not self.quit:
            self.sendlist = [
                s for s in self.clients if s.canSend()]
            inputready, outputready, exceptready = select.select(
                self.clients, self.sendlist, [], 1.0 / 120)
            for i in inputready:
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

            self.FPSTimer(0)
            #time.sleep(self.newdur / 1000.)

        Log.info('ending clientLoop')
        for c in self.clients:
            c.disconnect()
        Log.info('%s', self.getStatInfo())

    def closeClient(self, client):
        client.disconnect()
        try:
            self.clients.remove(client)
        except ValueError:
            pass


def runClient():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-s', '--server'
    )
    parser.add_argument(
        '-n', '--aicount',
        default=8, type=int
    )
    args = parser.parse_args()

    # run main
    npcs = NPCServer(connectTo=(args.server, 22517), aicount=args.aicount)

    def sigstophandler(signum, frame):
        print 'User Termination'
        npcs.quit = True
        # sys.exit(0)
    signal.signal(signal.SIGINT, sigstophandler)

    npcs.clientLoop()

if __name__ == "__main__":
    runClient()
