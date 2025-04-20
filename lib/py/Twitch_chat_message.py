import os
import socket
import asyncio
from json import loads
from time import sleep
from requests import get, post
from dataclasses import dataclass
from base import getTwitchHeaders, twitch_getChannelOffStateData
from pandas import DataFrame
from discord_webhook_sender import DiscordWebhookSender

@dataclass
class twitchChatData:
	twitch_chat_msg_List: list
	sock: socket.socket

dfDataCheckList = DataFrame({'val':[]})
dfDataCheckListLen = 500
twitch_Client_ID = os.environ['twitch_Client_ID']
twitch_Client_secret = os.environ['twitch_Client_secret']

oauth_key = post(	"https://id.twitch.tv/oauth2/token?client_id=" +
					twitch_Client_ID + "&client_secret=" +
					twitch_Client_secret +
					"&grant_type=client_credentials")
authorization = 'Bearer ' + loads(oauth_key.text)["access_token"]
oauth = os.environ['oauth']

class twitch_chat_message:
	def chatMsg(self, init): #function to chat message
			if init.remainderChat != "NANCAHT" and init.remainderChat != "": #Check received chat error
				if init.remainderChat.find("PONG") != -1: init.remainderChat = "NANCAHT"; asyncio.create_task(DiscordWebhookSender._log_error("PONG"))
			try:
				init.sockDict["twitch"].send(bytes("PING\n", "ASCII")) #check non chat 
				# init.TFJoin["twitch"] = 0
			except:
				asyncio.create_task(DiscordWebhookSender._log_error("error: Failed to send message to twitch"))
				# init.TFJoin["twitch"] += 1
				return
			try:
				self.getChatList(init)
				if not init.DO_TEST: self.postChat(init) #post chat
			except: asyncio.create_task(DiscordWebhookSender._log_error("error chatMsg"))

	def getChatList(self, init): #get chat list
		data = recv(init.sockDict["twitch"], int(init.packetSize))  #recv chat data
		# self.checkPacket(init, len(data))
		data = data.replace("PONG :tmi.twitch.tv\r\n", "")
		while self.getName(data) != None or init.remainderChat != "NANCAHT":  # if have chat or if have truncated remainder
			if init.remainderChat != "NANCAHT":
				if self.getName(data) != None: data = init.remainderChat + data		
				else: break
			name = self.getName(data)  #chat person's name
			chat, data, channelID = self.getChatMsg(init ,data)  #get chatting message
			# if len(chat): print("채널 {2} message to send {0}: {1}".format(name, chat, channelID))    #all chat debugging
			if len(chat) and name in list(init.twitch_chatFilter["channelID"]):  #if have chat and if streamer in user list
				if chat.find("ACTION [KUKORO]") != -1: print("쿠코로 게임 시스템 채팅", end = "   ")
				else: init.twitch_chatList.append([name, chat, channelID])
				print("채널 {2} message to send {0}: {1}".format(name, chat, channelID))  #debugging

	def postChat(self, init): #send to chatting message
		try: 
			chatDic = self.addChat(init)
			for chatDicKwey in list(chatDic.keys()):
				list_of_urls = self.make_chat_list_of_urls(init, chatDic, chatDicKwey)
				# post_message(init, list_of_urls)
				if len(list_of_urls): print("post chat")
		except: asyncio.create_task(DiscordWebhookSender._log_error("error postChat"))

	def make_chat_list_of_urls(self, init, chatDic, chatDicKwey):
		list_of_urls = []
		name, channelID = chatDicKwey
		channelName = self.gettwitch_chatFilterName(init, name)
		chat = chatDic[name, channelID]
		if chat[0] == ">": chat = f"\{chat}"
		init.userStateData[f"{channelID}방 채팅알림"].index  = init.discordURLList
		try:
			for discordWebhookURL in init.discordURLList:  #user webhook URL 
				try:
					if channelName in init.userStateData[f"{channelID}방 채팅알림"][discordWebhookURL]:  #if user want recv to streamer chat, post message
						message = self.make_thumbnail_url(init, name, chat, channelName, channelID)
						list_of_urls.append((discordWebhookURL, message))
				except: pass
		except: asyncio.create_task(DiscordWebhookSender._log_error(f"error postChat test .{init.userStateData[f'{channelID}방 채팅알림']}."))
		return list_of_urls

	def addChat(self, init): #add chat
		try:
			chatDic = {}
			twitch_chatList = init.twitch_chatList[:]
			if twitch_chatList:
				for name, chat, channelID in twitch_chatList:
					if (name, channelID) not in list(chatDic.keys()) and len(chatDic) == 0:
						chatDic[name, channelID] = str(chat)
						init.twitch_chatList = init.twitch_chatList[1:]
					elif (name, channelID) not in list(chatDic.keys()) and len(chatDic) != 0: 
						break
					else:
						chatDic[name, channelID] = chatDic[name, channelID] + "\n" + str(chat)
						init.twitch_chatList = init.twitch_chatList[1:]
		except: asyncio.create_task(DiscordWebhookSender._log_error("error addChat"))
		return chatDic

	def checkPacket(self, init, dataLen):
		weighted_max = self.weighted_avg_func(init, dataLen)
		if   (init.packetSize- 4096*1) < (weighted_max): init.packetSize += 2048
		elif (init.packetSize- 4096*2) > (weighted_max): init.packetSize -= 2048

	def weighted_avg_func(self, init, dataLen):
		dfDataCheckList.loc[len(dfDataCheckList['val'])] = dataLen
		if len(dfDataCheckList['val']) > dfDataCheckListLen:
			dfDataCheckList.drop([0], axis=0, inplace=True)
			dfDataCheckList.index = [i for i in range(len(dfDataCheckList))]
		weighted_max = list(dfDataCheckList['val'])[-1]
		for i in range(1, len(dfDataCheckList['val'])):
			if i > 400: break
			if list(dfDataCheckList['val'])[-i] < list(dfDataCheckList['val'])[-i-1]: weighted_max = list(dfDataCheckList['val'])[-i-1]
		return weighted_max

	def make_thumbnail_url(self, init, name, chat, channelName, channelID):
		while True:
			try:
				headers = getTwitchHeaders()
				sleep(0.1)
				offState = get(self.getOffStateLink(channelName), headers=headers, timeout=10)
				if offState.status_code == 200:
					_, _, thumbnail_url = twitch_getChannelOffStateData(loads(offState.text)["data"], name)
					if thumbnail_url.find("https://static-cdn.jtvnw.net") != -1: break
				else: asyncio.create_task(DiscordWebhookSender._log_error("offState.status_code not 200"))
			except: asyncio.create_task(DiscordWebhookSender._log_error("error make thumbnail url ", str(offState.text)))

		return {'content'   : chat,
				"username"  : channelName + " >> " + init.channelList.loc[0,channelID],
				"avatar_url": thumbnail_url}

	def getName(self, data): #get chat person's name 
		try:	return data[data.index(":") + 1:data.index("!")]
		except: return None

	def getChatMsg(self, init, data): #get chatting message
		try:
			init.remainderChat = "NANCAHT"
			channelID  = data[data.index("#") + 1:data[1:].index(":")] 	#channel ID
			frontIndex = data[1:].index(":") + 2 						#chatting first index 
			backIndex  = data[1:].index("\n")							#chatting last index 
			return data[frontIndex:backIndex], data[backIndex + 2:], channelID.rstrip() # 1 chatting, other chatting, channel ID
		except:
			init.remainderChat = data
			return "", "", ""

	def gettwitch_chatFilterName(self, init, name):
		[channelName] = [init.twitch_chatFilter["channelName"][i] for i in range(len(list(init.twitch_chatFilter["channelID"]))) if init.twitch_chatFilter["channelID"][i] == name]
		return channelName

	def getOffStateLink(self, channelName): return "https://api.twitch.tv/helix/search/channels?query=" + channelName #offline state data link

def twitch_joinchat(init): #join twitch chat,(30/20SEC recv able)
	while True: 
		try:
			# init.TFJoin["twitch"] = 0
			mytwitchID = "boxu20"
			addr = "irc.chat.twitch.tv"
			port = 6667
			sock = socket.socket()
			sock.connect((addr, port))
			sock.settimeout(2.0)
			send(sock, f"PASS {init.oauth}", init)
			send(sock, f"NICK {init.mytwitchID}", init)
			for twitchID in init.twitchIDList.columns[1:]: send(sock, f"JOIN #{twitchID}", init)
			sleep(1)
			# pprint(base.recv(sock, int(init.packetSize/2), init))
			recv(sock, int(init.packetSize/8))
			break
		except: asyncio.create_task(DiscordWebhookSender._log_error("join error"))
	init.sockDict["twitch"] = sock

def send(sock, msg, init):
	try: sock.send((msg + "\n").encode())
	except Exception as e: 
		asyncio.create_task(DiscordWebhookSender._log_error(f"send error {e}"))
		init.count = -1

def recv(sock, buff_size):
	try:
		recv = sock.recv(buff_size).decode('UTF-8')
		return recv
	except Exception as e:
		asyncio.create_task(DiscordWebhookSender._log_error(f"recv error {e}.{buff_size}."))
		return ""
