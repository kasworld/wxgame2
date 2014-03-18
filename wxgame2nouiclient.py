#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" wxgame noui AI ssclient
    wxGameFramework
    Copyright 2011,2013,1014 kasw <kasworld@gmail.com>
"""
from wxgame2server import Version
import random
import math
import traceback
import os
import os.path
import sys
import socket
import select
import signal
import time
import argparse
import threading
import Queue
from euclid import Vector2
#from wxgame2server import GameObjectGroup
from wxgame2server import SpriteObj, random2pi, FPSlogicBase, updateDict, fromGzJson, Storage
from wxgame2server import getFrameTime, putParams2Queue, ShootingGameMixin, I32sendrecv
from wxgame2server import AI2 as GameObjectGroup

# ================ tcp client =========


class TCPGameClient(threading.Thread):

    def __str__(self):
        return self.conn.protocol.getStatInfo()

    def __init__(self, connectTo):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(connectTo)

        protocol = I32sendrecv(sock)
        self.conn = Storage({
            'protocol': protocol,
            'recvQueue': protocol.recvQueue,
            'sendQueue': protocol.sendQueue,
            'quit': False,
        })
        print self

    def clientLoop(self):
        try:
            while self.conn.quit is not True:
                self.conn.protocol.sendrecv()
        except RuntimeError as e:
            if e.args[0] != "socket connection broken":
                raise RuntimeError(e)

    def shutdown(self):
        self.conn.quit = True
        self.conn.protocol.sock.close()
        print 'end connection'
        print self


def runService(connectTo):
    client = TCPGameClient(connectTo)
    client_thread = threading.Thread(target=client.clientLoop)
    client_thread.start()
    return client, client_thread
# ================ tcp client end =========


class AIGameClient(ShootingGameMixin, FPSlogicBase):

    def __init__(self, *args, **kwds):
        self.conn = kwds.pop('conn')

        self.FPSTimerInit(getFrameTime, 60)
        ShootingGameMixin.initGroups(self, GameObjectGroup)

        self.myteam = None
        self.registerRepeatFn(self.prfps, 1)

    def prfps(self, repeatinfo):
        print 'fps:', self.statFPS
        print self.conn.protocol.getStatInfo()

    def applyState(self, loadlist):
        def makeGameObjectDisplayGroup(og):
            gog = GameObjectGroup(
            ).initialize(
                resource=og['resource'],
                gameObj=self
            ).deserialize(
                og,
                SpriteObj,
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

    def makeClientAIAction(self):
        # make AI action
        if self.myteam is None:
            return
        aa = self.getTeamByID(self.myteam['teamid'])
        if aa is None:
            return
        targets = [tt for tt in self.dispgroup[
            'objplayers'] if tt.teamname != aa.teamname]

        aa.prepareActions(
            targets,
            self.frameinfo['ThisFPS'],
            self.thistick
        )
        actions = aa.SelectAction(targets, aa[0])

        actionjson = self.serializeActions(actions)
        # print actions, actionjson

        putParams2Queue(
            self.conn.sendQueue,
            cmd='act',
            team=self.myteam,
            actions=actionjson,
        )

    def processCmd(self):

        while not self.conn.recvQueue.empty():
            try:
                cmdDict = self.conn.recvQueue.get_nowait()
                if cmdDict is None:
                    break
            except Queue.Empty:
                break
            except:
                print traceback.format_exc()
                break
            cmdDict = fromGzJson(cmdDict)

            cmd = cmdDict.get('cmd')

            if cmd == 'gameState':
                putParams2Queue(
                    self.conn.sendQueue,
                    cmd='reqState',
                )
                self.applyState(cmdDict)
                if self.myteam is not None:
                    self.makeClientAIAction()

            elif cmd == 'actACK':
                pass

            elif cmd == 'teamInfo':
                teamname = cmdDict.get('teamname')
                teamid = cmdDict.get('teamid')
                self.myteam = {
                    'teamname': teamname,
                    'teamid': teamid,
                    'teamStartTime': self.thistick,
                }
                print 'joined', teamname, teamid
                print self.myteam
                putParams2Queue(
                    self.conn.sendQueue,
                    cmd='reqState',
                )
            else:
                print 'unknown cmd', cmdDict

    def doFPSlogic(self):
        self.thistick = self.frameinfo['thistime']
        self.processCmd()

    def doGame(self):
        while not self.conn.quit:
            self.FPSTimer(0)
            time.sleep(self.newdur / 1000.)


def runtest(destip, teamname):
    if destip is None:
        destip = 'localhost'
    connectTo = destip, 22517
    print 'Client start, ', connectTo

    client, client_thread = runService(connectTo)

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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-s', '--server'
    )
    parser.add_argument(
        '-t', '--teamname'
    )
    args = parser.parse_args()
    runtest(args.server, args.teamname)
