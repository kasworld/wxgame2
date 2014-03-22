wxgame2
=======

python game framework using wxpython

tested in
xubuntu 13.10
python 2.7.x ,
wxpython 2.8.x

if wxpython 3.0 and windows :
    wx.color->wx.colour

wxgame2server.py : no ui server
wxgame2client.py : ui client

client option
-s serverip
  server ip/name to connect
-t teamname
  AI team name to use (in sever)

if -t is ommitted client is work as observer mode (no ai team , just visualize game state)

korean discription is

http://kasw.blogspot.kr/2014/01/github.html

http://kasw.blogspot.kr/2014/03/wxgame2.html

http://kasw.blogspot.kr/2014/03/wxgame2_15.html

http://kasw.blogspot.kr/2014/03/wxgame2_22.html

update 2014-03-02
----------------

wxgame2.py

- some code refine, bug fix

wxgame2server.py, wxgame2client.py

- full refactoring for client/server version

- C/S communication using file/pickle


update 2014-03-07
----------------

wxgame2server.py, wxgame2client.py

- code refactoring
- full tcp networked client/server
- data packet changed to json
- AI client base work ( in progress )
- team score print


update 2014-03-22

- performance tunning
- observer mode
- remove resource not used
- resource load code rework
- fix cpu usage issue
