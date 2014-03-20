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
from wxgame2server import SpriteObj, FPSlogicBase, AIClientMixin
from wxgame2server import getFrameTime, putParams2Queue, TCPGameClient
from wxgame2server import AI2 as GameObjectGroup


class AIGameClient(AIClientMixin, FPSlogicBase):

    def __init__(self, *args, **kwds):
        AIClientMixin.__init__(self, *args, **kwds)

        self.FPSTimerInit(getFrameTime, 60)
        AIClientMixin.initGroups(self, GameObjectGroup, SpriteObj)
        self.registerRepeatFn(self.prfps, 1)

    def prfps(self, repeatinfo):
        print 'fps:', self.statFPS
        print self.conn.protocol.getStatInfo()

    def applyState(self, loadlist):
        def makeGameObjectDisplayGroup(groupdict):
            gog = GameObjectGroup(
            ).initialize(
                teamcolor=groupdict['teamcolor'],
                teamname=groupdict['teamname'],
                gameObj=self,
                spriteClass=SpriteObj
            ).deserialize(
                groupdict,
                {}
            )
            return gog

        self.frameinfo.update(loadlist['frameinfo'])

        oldgog = self.dispgroup['objplayers']
        self.dispgroup['objplayers'] = []
        for og in loadlist['objplayers']:
            gog = makeGameObjectDisplayGroup(og)

            oldteam = self.getTeamByIDfromList(oldgog, gog.ID)
            if oldteam is not None:
                gog.statistic = oldteam.statistic
                if oldteam.hasBounceBall() and gog.hasBounceBall():
                    gog[0].fireTimeDict = oldteam[0].fireTimeDict
                    gog[0].createdTime = oldteam[0].createdTime
                    gog[0].lastAutoMoveTick = oldteam[0].lastAutoMoveTick
                    gog[0].ID = oldteam[0].ID

            self.dispgroup['objplayers'].append(gog)
        return

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
