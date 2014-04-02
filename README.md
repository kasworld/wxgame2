# wxgame2

## python game framework using wxpython

- 2d shooting game library
- game AI 
- game observer mode
- server/client works like mmorpg 
- server run game logic and decision 
- client get environment info from server and send AI action to serve
- separated NPC(AI) server, game logic server, client reception server

### requirement (tested and developed by)

- (x)ubuntu 13.10 
- python 2.7.x
- wxpython 2.8.x


### twserver.py 

- twisted version game server and npc server
- run game server with s arg
- run npc server with int(number of ai npc) arg

### twclient.py

- twisted version wxpython game client 
- see wxgameclient.py option 

### wxgame2server.py

- game server
- no need wxpython, and can be run by pypy
- fork 4 process
	- main : main process
	- game logic : GameLogicServer class : game logic decision 
	- npc : NPCServer class : server side NPC AI 
	- tcp : TCPServer class : client connection reception 
- see help by -h option

### wxgame2client.py

- ui client / observer
- need wxpython 
- client option
	-s serverip
	: server ip/name to connect
	-t teamname
	: AI team name to use (in sever)
	: if -t is ommitted client is work as observer mode (no ai team , just visualize game state)

### wxgame2npc.py

- non ui AI client for server load test 

### wxgame2lib.py

- common library code

### wxgame2single.py

- old standalone wxgame2 

## korean discription is

http://kasw.blogspot.kr/2014/01/github.html

http://kasw.blogspot.kr/2014/03/wxgame2.html

http://kasw.blogspot.kr/2014/03/wxgame2_15.html

http://kasw.blogspot.kr/2014/03/wxgame2_22.html

## update 2014-03-02

wxgame2.py

- some code refine, bug fix

wxgame2server.py, wxgame2client.py

- full refactoring for client/server version

- C/S communication using file/pickle


## update 2014-03-07

wxgame2server.py, wxgame2client.py

- code refactoring
- full tcp networked client/server
- data packet changed to json
- AI client base work ( in progress )
- team score print


## update 2014-03-22

- performance tunning
- observer mode
- remove resource not used
- resource load code rework
- fix cpu usage issue


## update 2014-03-28

server loop changed to select 

inter server communication use pipe 

profile and time-run add for performance test 

standalone npc server(for load test)

server process added

- server/client works like mmorpg 
- server run game logic and decision 
- client get environment info from server and send AI action to serve
- separated NPC(AI) server, game logic server, client reception server

## update 2014-04-2

twisted version added 

- twservers.py 
- twclient.py 


## C/S protocol

zlib compressed json : Vector2 => (x, y)

	client send
	{
		cmd : makeTeam,
		teamname : teamname
	}
	Server send
	{
		cmd : teamInfo
		teamname : teamname,
		teamid : teamid
	}

	client send
	{
		cmd='reqState',
	}
	server send state
	{
		'cmd': 'gameState',
		'frameinfo': {k: v for k, v in self.frameinfo.iteritems() if k not in ['stat']},
		'objplayers': [og.serialize() for og in self.dispgroup['objplayers']],
		'effectObjs': self.dispgroup['effectObjs'].serialize()
	}

	client send
	{
		cmd='act',
		team=self.myteam,
		actions=actionjson,
	}
	server send
	{
		cmd='actACK',
	}

	server send to server
	{
		cmd: del
	}
