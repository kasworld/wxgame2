#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" wxgame noui AI ssclient
    wxGameFramework
    Copyright 2011,2013,1014 kasw <kasworld@gmail.com>
"""
import random
import sys
import signal
import time
import argparse
from euclid import Vector2
from wxgame2server import SpriteObj, FPSlogicBase, AIClientMixin
from wxgame2server import getFrameTime, putParams2Queue, TCPGameClient
from wxgame2server import AI2 as GameObjectGroup


class AIGameClient(AIClientMixin, FPSlogicBase):

    def __init__(self, *args, **kwds):
        AIClientMixin.__init__(self, *args, **kwds)

        self.FPSTimerInit(getFrameTime, 60)
        self.initGroups(GameObjectGroup, SpriteObj)
        self.registerRepeatFn(self.prfps, 1)

    def prfps(self, repeatinfo):
        print 'fps:', self.statFPS
        print self.conn.protocol.getStatInfo()

    def initGroups(self, groupclass, spriteClass):
        self.dispgroup = {}
        self.dispgroup['backgroup'] = groupclass().initialize(
            gameObj=self, spriteClass=spriteClass, teamcolor=(0x7f, 0x7f, 0x7f))
        self.dispgroup['effectObjs'] = groupclass().initialize(
            gameObj=self, spriteClass=spriteClass, teamcolor=(0x7f, 0x7f, 0x7f))
        self.dispgroup['frontgroup'] = groupclass().initialize(
            gameObj=self, spriteClass=spriteClass, teamcolor=(0x7f, 0x7f, 0x7f))
        self.dispgroup['objplayers'] = []

    def applyState(self, loadlist):
        self.frameinfo.update(loadlist['frameinfo'])
        self.migrateExistTeamObj(
            self.dispgroup['effectObjs'], loadlist['effectObjs'])

        oldgog = self.dispgroup['objplayers']
        self.dispgroup['objplayers'] = []
        for groupdict in loadlist['objplayers']:
            aliveteam = self.getTeamByIDfromList(oldgog, groupdict['ID'])
            if aliveteam is not None:  # copy oldteam to new team
                self.dispgroup['objplayers'].append(aliveteam)
                # now copy members
                self.migrateExistTeamObj(aliveteam, groupdict)
            else:  # make new team
                self.dispgroup['objplayers'].append(
                    self.makeNewTeam(GameObjectGroup, SpriteObj, groupdict)
                )

    def doFPSlogic(self):
        self.thistick = self.frameinfo['thistime']
        self.processCmd()

    def doGame(self):
        while not self.conn.quit:
            self.FPSTimer(0)
            time.sleep(self.newdur / 1000.)


def runClient():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-s', '--server'
    )
    parser.add_argument(
        '-t', '--teamname'
    )
    args = parser.parse_args()
    #runtest(args.server, args.teamname)
    destip, teamname = args.server, args.teamname

    if destip is None:
        destip = 'localhost'
    connectTo = destip, 22517
    print 'Client start, ', connectTo

    client, client_thread = TCPGameClient(connectTo).runService()

    if teamname:
        teamcolor = (random.randint(0, 255),
                     random.randint(0, 255), random.randint(0, 255))
        print 'makeTeam', teamname, teamcolor
        putParams2Queue(
            client.conn.sendQueue,
            cmd='makeTeam',
            teamname=teamname,
            teamcolor=teamcolor
        )
    else:  # observer mode
        print 'observer mode'
        putParams2Queue(
            client.conn.sendQueue,
            cmd='reqState',
        )

    def sigstophandler(signum, frame):
        print 'User Termination'
        client.shutdown()
        client_thread.join(1)
        sys.exit(0)
    signal.signal(signal.SIGINT, sigstophandler)

    # run main
    AIGameClient(conn=client.conn).doGame()

    print 'end client'
    sigstophandler(0, 0)

if __name__ == "__main__":
    runClient()
