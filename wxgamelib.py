#!/usr/bin/env python
# -*- coding: utf-8 -*-


"""
    kasworld's wxgame lib ver 1.3.1

    Copyright 2011,2013 kasw <kasworld@gmail.com>

"""

import wx
import time
import math
import os
import random
import itertools

wx.InitAllImageHandlers()

import sys
import os.path

# general util

srcdir = os.path.dirname(os.path.abspath(sys.argv[0]))

getSerial = itertools.count().next


def getFrameTime():
    return time.time()


def random2pi(m=2):
    return math.pi * m * (random.random() - 0.5)


def getHMSAngle(mst, hands):
    """ clock hands angle
    0 : hour
    1 : minute
    2 : second
    mst = time.time()"""

    lt = time.localtime(mst)
    ms = mst - int(mst)
    if hands == 0:  # hour
        return math.radians(lt[3] * 30.0 + lt[4] / 2.0 + lt[5] / 120.0 + 90)
    elif hands == 1:  # minute
        return math.radians(lt[4] * 6.0 + lt[5] / 10.0 + ms / 10 + 90)
    elif hands == 2:  # second
        return math.radians(lt[5] * 6.0 + ms * 6 + 90)
    else:
        return None


class FastStorage(dict):

    """from gluon storage.py """

    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)
        self.__dict__ = self

    def __getattr__(self, key):
        return getattr(self, key) if key in self else None

    def __getitem__(self, key):
        return dict.get(self, key, None)

    def copy(self):
        self.__dict__ = {}
        s = FastStorage(self)
        self.__dict__ = self
        return s

    def __repr__(self):
        return '<Storage %s>' % dict.__repr__(self)

    def __getstate__(self):
        return dict(self)

    def __setstate__(self, sdict):
        dict.__init__(self, sdict)
        self.__dict__ = self

    def update(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)
        self.__dict__ = self


class Statistics(object):

    def __init__(self):
        self.datadict = {
            'min': None,
            'max': None,
            'avg': None,
            'sum': 0,
            'last': None,
            'count': 0,
        }
        self.formatstr = '%(last)s(%(min)s~%(max)s), %(avg)s=%(sum)s/%(count)d'

    def update(self, data):
        data = float(data)
        self.datadict['count'] += 1
        self.datadict['sum'] += data

        if self.datadict['last'] != None:
            self.datadict['min'] = min(self.datadict['min'], data)
            self.datadict['max'] = max(self.datadict['max'], data)
            self.datadict['avg'] = self.datadict[
                'sum'] / self.datadict['count']
        else:
            self.datadict['min'] = data
            self.datadict['max'] = data
            self.datadict['avg'] = data
            self.formatstr = '%(last).2f(%(min).2f~%(max).2f), %(avg).2f=%(sum).2f/%(count)d'

        self.datadict['last'] = data

        return self

    def getStat(self):
        return self.datadict

    def __str__(self):
        return self.formatstr % self.datadict


# wx specific


def loadBitmap2MemoryDCArray(bitmapfilename, xslicenum=1, yslicenum=1,
                             totalslice=10000,  yfirst=True, reverse=False, addreverse=False):
    rtn = []
    fullbitmap = wx.Bitmap(bitmapfilename)
    dcsize = fullbitmap.GetSize()
    w, h = dcsize[0] / xslicenum, dcsize[1] / yslicenum
    if yfirst:
        for x in range(xslicenum):
            for y in range(yslicenum):
                rtn.append(wx.MemoryDC(
                    fullbitmap.GetSubBitmap(wx.Rect(x * w, y * h, w, h))))
    else:
        for y in range(yslicenum):
            for x in range(xslicenum):
                rtn.append(wx.MemoryDC(
                    fullbitmap.GetSubBitmap(wx.Rect(x * w, y * h, w, h))))
    totalslice = min(xslicenum * yslicenum, totalslice)
    rtn = rtn[:totalslice]
    if reverse:
        rtn.reverse()
    if addreverse:
        rrtn = rtn[:]
        rrtn.reverse()
        rtn += rrtn
    return rtn


def loadDirfiles2MemoryDCArray(dirname, reverse=False, addreverse=False):
    rtn = []
    filenames = sorted(os.listdir(dirname), reverse=reverse)
    for a in filenames:
        rtn.append(wx.MemoryDC(wx.Bitmap(dirname + "/" + a)))
    if addreverse:
        rrtn = rtn[:]
        rrtn.reverse()
        rtn += rrtn
    return rtn


def makeRotatedImage(image, angle):
    rad = math.radians(-angle)
    xlen, ylen = image.GetWidth(), image.GetHeight()
    #offset = wx.Point()
    # ,wx.Point(xlen,ylen) )
    rimage = image.Rotate(rad, (xlen / 2, ylen / 2), True)
    # rimage =  image.Rotate( rad, (0,0) ,True) #,wx.Point() )
    xnlen, ynlen = rimage.GetWidth(), rimage.GetHeight()
    rsimage = rimage.Size(
        (xlen, ylen), (-(xnlen - xlen) / 2, -(ynlen - ylen) / 2))
    # print angle, xlen , ylen , xnlen , ynlen , rsimage.GetWidth() ,
    # rsimage.GetHeight()
    return rsimage


def loadBitmap2RotatedMemoryDCArray(imagefilename, rangearg=(0, 360, 10),
                                    reverse = False, addreverse = False):
    rtn = []
    fullimage = wx.Bitmap(imagefilename).ConvertToImage()
    for a in range(*rangearg):
        rtn.append(wx.MemoryDC(
            makeRotatedImage(fullimage, a).ConvertToBitmap()
        ))
    if reverse:
        rtn.reverse()
    if addreverse:
        rrtn = rtn[:]
        rrtn.reverse()
        rtn += rrtn
    return rtn


class GameResource(object):

    def __init__(self, dirname):
        self.resourcedir = dirname
        self.rcsdict = {}

    def getcwdfilepath(self, filename):
        return os.path.join(srcdir, self.resourcedir, filename)

    def loadBitmap2MemoryDCArray(self, name, *args, **kwds):
        key = (name, args, str(kwds))
        if not self.rcsdict.get(key, None):
            self.rcsdict[key] = loadBitmap2MemoryDCArray(
                self.getcwdfilepath(name), *args, **kwds)
        return self.rcsdict[key]

    def loadDirfiles2MemoryDCArray(self, name, *args, **kwds):
        key = (name, args, str(kwds))
        if not self.rcsdict.get(key, None):
            self.rcsdict[key] = loadDirfiles2MemoryDCArray(
                self.getcwdfilepath(name), *args, **kwds)
        return self.rcsdict[key]

    def loadBitmap2RotatedMemoryDCArray(self, name, *args, **kwds):
        key = (name, args, str(kwds))
        if not self.rcsdict.get(key, None):
            self.rcsdict[key] = loadBitmap2RotatedMemoryDCArray(
                self.getcwdfilepath(name), *args, **kwds)
        return self.rcsdict[key]


class FPSlogicBase(object):

    def FPSTimerInit(self, frameTime, maxFPS=70, ):
        self.maxFPS = maxFPS
        self.repeatingcalldict = {}
        self.pause = False
        self.statFPS = Statistics()
        self.frameTime = frameTime
        self.frames = [self.frameTime()]
        self.first = True

    def registerRepeatFn(self, fn, dursec):
        """
            function signature
            def repeatFn(self,repeatinfo):
            repeatinfo is {
            "dursec" : dursec ,
            "oldtime" : time.time() ,
            "starttime" : time.time(),
            "repeatcount":0 }
        """
        self.repeatingcalldict[fn] = {
            "dursec": dursec,
            "oldtime": self.frameTime(),
            "starttime": self.frameTime(),
            "repeatcount": 0}
        return self

    def unRegisterRepeatFn(self, fn):
        return self.repeatingcalldict.pop(fn, [])

    def FPSTimer(self, evt):
        thistime = self.frameTime()
        self.frames.append(thistime)
        difftime = self.frames[-1] - self.frames[-2]

        while(self.frames[-1] - self.frames[0] > 1):
            del self.frames[0]

        if len(self.frames) > 1:
            fps = len(self.frames) / (self.frames[-1] - self.frames[0])
        else:
            fps = 0
        if self.first:
            self.first = False
        else:
            self.statFPS.update(fps)

        frameinfo = {
            "ThisFPS": 1 / difftime,
            "sec": difftime,
            "FPS": fps,
            'stat': self.statFPS,
            'thistime': thistime
        }

        if not self.pause:
            self.doFPSlogic(frameinfo)

        for fn, d in self.repeatingcalldict.iteritems():
            if thistime - d["oldtime"] > d["dursec"]:
                self.repeatingcalldict[fn]["oldtime"] = thistime
                self.repeatingcalldict[fn]["repeatcount"] += 1
                fn(d)

        nexttime = (self.frameTime() - thistime) * 1000
        newdur = min(1000, max(difftime * 800, 1000 / self.maxFPS) - nexttime)
        if newdur < 1:
            newdur = 1
        self.newdur = newdur

    def doFPSlogic(self, thisframe):
        pass


class FPSlogic(FPSlogicBase):

    def FPSTimerInit(self, frameTime, maxFPS=70):
        FPSlogicBase.FPSTimerInit(self, frameTime, maxFPS)
        self.Bind(wx.EVT_TIMER, self.FPSTimer)
        self.timer = wx.Timer(self)
        self.timer.Start(1000 / self.maxFPS, oneShot=True)

    def FPSTimer(self, evt):
        FPSlogicBase.FPSTimer(self, evt)
        self.timer.Start(self.newdur, oneShot=True)

    def FPSTimerDel(self):
        self.timer.Stop()

if __name__ == "__main__":
    pass
