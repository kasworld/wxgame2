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
import multiprocessing

from wxgame2lib import SpriteObj, FPSMixin, getLogger, ProfileMixin
from wxgame2lib import getFrameTime, putParams2Queue, I32ClientProtocol, fromGzJson
from wxgame2lib import AI2, GameObjectGroup, ShootingGameMixin

Log = getLogger(level=logging.WARN, appname='wxgame2npc')
Log.critical('current loglevel is %s',
             logging.getLevelName(Log.getEffectiveLevel()))

g_profile = False


class TCPGameClient(I32ClientProtocol):

    def __str__(self):
        return '[{}:{}]'.format(
            self.__class__.__name__,
            self.teaminfo,
        )

    def __init__(self, connectTo, recvcallback):
        def callback(packet):
            return recvcallback(self, packet)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(connectTo)
        I32ClientProtocol.__init__(self, sock, callback)

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


class NPCServer(multiprocessing.Process, ShootingGameMixin, FPSMixin):

    def prfps(self, repeatinfo):
        print 'fps:', self.frameinfo.stat
        print 'packet:', self.getStatInfo()

    def applyState(self, loadlist):
        ShootingGameMixin.applyState(self, AI2, SpriteObj, loadlist)

    def applyState_simple(self, loadlist):
        ShootingGameMixin.applyState(
            self, GameObjectGroup, SpriteObj, loadlist)

    def getStatInfo(self):
        t = time.time() - self.initedTime
        return 'recv:{} {}/s send:{} {}/s'.format(
            self.recvcount, self.recvcount / t,
            self.sendcount, self.sendcount / t
        )

    def __init__(self, connectTo, aicount):
        multiprocessing.Process.__init__(self)
        if connectTo[0] is None:
            self.connectTo = ('localhost', connectTo[1])
        self.aicount = aicount

    def run(self):
        self.profile = ProfileMixin(g_profile)
        self.profile.begin()
        self.FPSInit(getFrameTime, 30)
        self.dispgroup = {}
        self.dispgroup['effectObjs'] = GameObjectGroup().initialize(
            gameObj=self, spriteClass=SpriteObj, teamcolor=(0x7f, 0x7f, 0x7f))
        self.dispgroup['objplayers'] = []
        self.registerRepeatFn(self.prfps, 1)

        self.quit = False
        self.allInited = False
        self.recvcount, self.sendcount, self.initedTime = 0, 0, time.time()
        Log.info('NPC server started')

        self.clients = []
        for i in range(self.aicount):
            self.clients.append(
                TCPGameClient(self.connectTo, self.process1Cmd)
            )

        self.clients[0].reqState()

        Log.info('start clientLoop')
        self.sendlist = []

        while not self.quit:
            self.sendlist = [
                s for s in self.clients if s.canSend()]
            inputready, outputready, exceptready = select.select(
                self.clients, self.sendlist, [], 0)

            if len(inputready) == 0 and len(outputready) == 0:
                self.FPSRun()
                self.FPSYield()
                self.thistick = self.frameinfo.thisFrameTime

            for i in inputready:
                try:
                    r = i.recv()
                except socket.error:
                    self.closeClient(i)
                if r == 'complete':
                    self.recvcount += 1
                elif r == 'disconnected':
                    self.closeClient(i)

            for o in outputready:
                try:
                    if o.send() == 'complete':
                        self.sendcount += 1
                except socket.error:
                    self.closeClient(i)

        Log.info('ending clientLoop')
        for c in self.clients:
            c.disconnect()
        Log.info('%s', self.getStatInfo())
        self.profile.end()

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
            self.frameinfo.lastFPS,
            self.thistick
        )
        actions = aa.SelectAction(targets, aa[0])
        actionjson = self.serializeActions(actions)
        putParams2Queue(
            client.sendQueue,
            cmd='act',
            teamid=client.teaminfo['teamid'],
            actions=actionjson,
        )
        return True

    def process1Cmd(self, client, packet):
        cmdDict = fromGzJson(packet)
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

    def closeClient(self, client):
        client.disconnect()
        try:
            self.clients.remove(client)
        except ValueError:
            pass
        if len(self.clients) == 0:
            Log.critical('no more client')
            self.quit = True


def runNPC():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-s', '--server'
    )
    parser.add_argument(
        '-n', '--aicount',
        default=8, type=int
    )
    parser.add_argument(
        '-p', '--processcount',
        default=1, type=int
    )
    args = parser.parse_args()

    # run main
    for i in xrange(args.processcount):
        npc_process = NPCServer(
            connectTo=(args.server, 22517),
            aicount=args.aicount
        )
        npc_process.start()

if __name__ == "__main__":
    runNPC()
