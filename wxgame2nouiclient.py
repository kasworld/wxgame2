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
import time
from wxgame2server import SpriteObj, FPSlogicBase, AIClientMixin
from wxgame2server import getFrameTime, putParams2Queue, TCPGameClient
from wxgame2server import AI2 as GameObjectGroup


class AIGameClient(AIClientMixin, FPSlogicBase, TCPGameClient):

    def __init__(self, *args, **kwds):
        self.FPSTimerInit(getFrameTime, 60)
        self.initGroups(GameObjectGroup, SpriteObj)

        self.connInit(kwds.pop('connectTo'))

    def prfps(self, repeatinfo):
        print 'fps:', self.statFPS

    def initGroups(self, groupclass, spriteClass):
        self.dispgroup = {}
        self.dispgroup['effectObjs'] = groupclass().initialize(
            gameObj=self, spriteClass=spriteClass, teamcolor=(0x7f, 0x7f, 0x7f))
        self.dispgroup['objplayers'] = []

    def applyState(self, loadlist):
        AIClientMixin.applyState(self, GameObjectGroup, SpriteObj, loadlist)
        return

    def doFPSlogic(self):
        self.thistick = self.frameinfo['thistime']
        self.processCmd()

    def clientLoop(self):
        while self.conn.quit is not True:
            try:
                self.conn.protocol.sendrecv()
            except RuntimeError as e:
                if e.args[0] != "socket connection broken":
                    raise RuntimeError(e)
                self.conn.quit = True
                break

            self.FPSTimer(0)
            #time.sleep(self.newdur / 1000.)

    def connInit(self, connectTo):
        if connectTo[0] is None:
            connectTo = ('localhost', connectTo[1])
        TCPGameClient.__init__(self, connectTo)

        self.myteam = None
        teamname = 'AI_%08X' % random.getrandbits(32)
        teamcolor = (random.randint(0, 255),
                     random.randint(0, 255), random.randint(0, 255))
        print 'makeTeam', teamname, teamcolor
        putParams2Queue(
            self.conn.sendQueue,
            cmd='makeTeam',
            teamname=teamname,
            teamcolor=teamcolor
        )


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
    clients = []
    for i in range(args.aicount):
        clients.append(AIGameClient(
            connectTo=(args.server, 22517)
        ).runService())

    def sigstophandler(signum, frame):
        print 'User Termination'
        for cl, ct in clients:
            cl.shutdown()
        for cl, ct in clients:
            ct.join(1)
        sys.exit(0)
    signal.signal(signal.SIGINT, sigstophandler)

    while True:
        time.sleep(1)

if __name__ == "__main__":
    runClient()
