import base
import asyncio
from random import randint
from datetime import datetime
from os import remove, environ
from requests import post, get
from urllib.request import urlretrieve
from discord_webhook_sender import DiscordWebhookSender

class twitch_live_message():

	async def twitch_liveMsg(self, init): #if online, send to message
		await self.addMSGList(init)
		if len(init.iflivePostList["twitch"]):
			for i in range(len(init.iflivePostList["twitch"])):
				(_, live, message, _, _, _) = init.iflivePostList["twitch"][i]
				if live == "CLOSE" and message == "방제 변경": await self.addMSGList(init); asyncio.create_task(DiscordWebhookSender._log_error("test"))
		await self.postLiveMSG(init)

	async def addMSGList(self, init): #if online, send to message
		headers = base.getTwitchHeaders()
		for _ in range(10):
			try: list_of_offState_twitchID = await base.get_message(self.getTwitchDataList(init), "twitch"); break
			except: await asyncio.sleep(0.1)
		try:
			for offState_twitchID in list_of_offState_twitchID:
				for offState, twitchID, TF in offState_twitchID:
					# if offState.status_code != 200: continue
					if not TF: continue
					live, title, thumbnail_url = base.twitch_getChannelOffStateData(offState["data"], twitchID)
					if ((self.ifChangeTitle(init, title, twitchID)) or self.turnOnline(init, live, twitchID)) and init.ifPostLiveCountEnd[twitchID] == 0: #on air or the change title
						message = self.getMessage(init, title, twitchID)
						# self.onAirChat(init, twitchID, message) #if trun on air send chat 
						json    = await self.getOnAirJson(init, twitchID, message, headers, thumbnail_url, title, live)
						old_title = init.twitch_titleData.loc[twitchID,'title1']
						self.onLineTitle(init, title, twitchID, message)  #broadcast state update
						init.iflivePostList["twitch"].append((twitchID, live, message, title, old_title, json))
						await base.save_airing_data(init, 'twitch', twitchID) # save data
						await base.save_profile_data(init, 'twitch', twitchID)
						if message == "뱅온!": init.ifPostLiveCountStart[twitchID] = init.ifPostLiveCountNum
						init.changeTitle[twitchID] = init.ifPostLiveCountNum
					elif self.turnOffline(init, live, twitchID) and init.ifPostLiveCountStart[twitchID] == 0: 
						message = "뱅종"
						# self.offAirChat(init, twitchID)
						json = self.getOffJson(init, twitchID)
						old_title = init.twitch_titleData.loc[twitchID,'title1']
						self.offLineTitle(init, twitchID)
						init.iflivePostList["twitch"].append((twitchID, live, message, title, old_title, json))
						await base.save_airing_data(init, 'twitch', twitchID)
						init.ifPostLiveCountEnd[twitchID] = init.ifPostLiveCountNum
						init.changeTitle[twitchID] = init.ifPostLiveCountNum
		except: 
			asyncio.create_task(DiscordWebhookSender._log_error(f"error get stateData .{twitchID}.{offState}."))
			if offState.find("error") != -1: len(1)

	async def postLiveMSG(self, init):
		try:
			if len(init.iflivePostList["twitch"])==0: return
			(twitchID, live, message, title, old_title, json) = init.iflivePostList["twitch"].pop(0)
			if message in ["뱅온!", "방제 변경"]: #on air or the change title
				print(f"{datetime.now()} onLine {init.twitchIDList.loc[twitchID, 'channelName']} {message}")
				if not message == "뱅온!": 
					print(f"{datetime.now()} 이전 방제: {old_title}")
					print(f"{datetime.now()} 현재 방제: {title}")
				_, list_of_urls = self.make_online_list_of_urls(init, twitchID, message, json)
				# if message == "뱅온!": asyncio.create_task(base.async_post_message(onair_list_of_urls))
				asyncio.create_task(DiscordWebhookSender().send_messages(list_of_urls))
				# asyncio.create_task(base.async_post_message(list_of_urls))
			elif message in ["뱅종"]: 
				print(f"{datetime.now()} offLine {init.twitchIDList.loc[twitchID, 'channelName']}")
				list_of_urls = self.make_offline_list_of_urls(init, twitchID, json)
				asyncio.create_task(DiscordWebhookSender().send_messages(list_of_urls))
				# asyncio.create_task(base.async_post_message(list_of_urls))
		except: asyncio.create_task(DiscordWebhookSender._log_error("postLiveMSG"));init.iflivePostList["twitch"] = []

	def getTwitchDataList(self, init):
		list_of_offState = []
		headers = base.getTwitchHeaders()
		for twitchID in init.twitchIDList["channelID"]:
			channelName = self.getChatFilterName(init, twitchID)
			list_of_offState.append([(self.getOffStateLink(channelName), headers), twitchID])
		return list_of_offState

	def make_online_list_of_urls(self, init, twitchID, message, json):
		onair_list_of_urls = []
		list_of_urls = []
		if init.DO_TEST: list_of_urls.append((environ['errorPostBotURL'], json))
		else:
			for discordWebhookURL in init.userStateData['discordURL']:
				try:
					if self.ifAlarm(init, discordWebhookURL, twitchID, message): #if user recv to online Alarm
						list_of_urls.append((discordWebhookURL, json))
				except: pass
		return onair_list_of_urls, list_of_urls

	def make_offline_list_of_urls(self, init, twitchID, json):
		if init.DO_TEST: return [(environ['errorPostBotURL'], json)]
		else: return [(discordWebhookURL, json) for discordWebhookURL in init.userStateData['discordURL'] if self.ifOffAlarm(init, twitchID, discordWebhookURL)]

	def onLineTitle(self, init, title, twitchID, message): #change title. state to online
		init.twitch_titleData.loc[twitchID,'title1'] = title
		if message == "뱅온!": init.twitch_titleData.loc[twitchID,'live_state'] = "OPEN"

	def offLineTitle(self, init, twitchID): 
		init.twitch_titleData.loc[twitchID,'live_state'] = "CLOSE" # change state to offline  

	def ifAlarm(self, init, discordWebhookURL, twitchID, message): #if user recv to online Alarm
		if message == "뱅온!": return init.twitchIDList.loc[twitchID, 'channelName'] in init.userStateData["뱅온 알림"][discordWebhookURL]
		else: return init.twitchIDList.loc[twitchID, 'channelName'] in init.userStateData[f"방제 변경 알림"][discordWebhookURL]

	def ifChangeTitle(self, init, title, twitchID): return title != str(init.twitch_titleData.loc[twitchID,'title1']) #if title change

	def ifOffAlarm(self, init, twitchID, discordWebhookURL):
		try: return init.twitchIDList.loc[twitchID, 'channelName'] in init.userStateData["방종 알림"][discordWebhookURL] #if offline Alarm
		except: return False

	async def getOnAirJson(self, init, twitchID, message, headers, thumbnail_url, title, live): #get on air json
		url = self.getURL(twitchID)
		init.twitchIDList.loc[twitchID, 'channel_thumbnail'], = thumbnail_url
		if live==0: return self.get_offState_change_title_json(init, twitchID, message, title, url)
		init.dfDataCheckList.loc[len(init.dfDataCheckList['val'])] = 16384
		started_at, viewer_count, thumbnail = await self.getJsonVars(init, twitchID, headers)
		return self.get_online_state_json(init, twitchID, message, title, url, started_at, thumbnail, viewer_count) 
		# return self.get_online_titleChange_state_json(init, twitchID, message, title, url, started_at, thumbnail)

	async def getJsonVars(self, init, twitchID, headers):
		while True:
			try:
				stateData = get(self.getLink(twitchID), headers=headers, timeout=3)  #get channel state, 0.2/SEC  at 1 channel 
				try:
					started_at   = self.getStarted_at(stateData)
					viewer_count = self.getViewer_count(stateData) #get viewer data
					thumbnail    = self.getThumbnail(init, twitchID, stateData)
					break
				except: 
					print(f"{datetime.now()} wait make thumbnail")
					await asyncio.sleep(0.1)
			except: asyncio.create_task(DiscordWebhookSender._log_error("error stateData"))
		return started_at, viewer_count, thumbnail

	def get_online_state_json(self, init, twitchID, message, title, url, started_at, thumbnail, viewer_count):
		return {"username": init.twitchIDList.loc[twitchID, 'channelName'], "avatar_url": init.twitchIDList.loc[twitchID, 'channel_thumbnail'],\
				"embeds": [
					{"color": int(init.twitchIDList.loc[twitchID, 'channel_color']),
					"fields": [
						{"name": "방제", "value": title, "inline": True},
						{"name": ':busts_in_silhouette: 시청자수',
						"value": viewer_count, "inline": True}],
					"title":  f"{init.twitchIDList.loc[twitchID, 'channelName']} {message}\n",\
				"url": url, \
				"image": {"url": thumbnail},
				"footer": { "text": f"뱅온 시간", "inline": True, "icon_url": "https://url.kr/x79ipj" },
				"timestamp": base.changeUTCtime(started_at)}]}
	
	# def get_online_titleChange_state_json(self, init, twitchID, message, title, url, started_at, thumbnail, viewer_count):
	# 	return {"username": init.twitchIDList.loc[twitchID, 'channelName'], "avatar_url": init.twitchIDList.loc[twitchID, 'channel_thumbnail'],\
	# 			"embeds": [
	# 				{"color": int(init.twitchIDList.loc[twitchID, 'channel_color']),
	# 				"fields": [
	# 					{"name": "이전 방제", "value": str(init.twitch_titleData.loc[twitchID,'title1']), "inline": True},
	# 					{"name": "현재 방제", "value": title, "inline": True},
	# 					{"name": ':busts_in_silhouette: 시청자수',
	# 					"value": viewer_count, "inline": True}],
	# 				"title":  f"{init.twitchIDList.loc[twitchID, 'channelName']} {message}\n",\
	# 			"url": url, \
	# 			"image": {"url": thumbnail},
	# 			"footer": { "text": f"뱅온 시간", "inline": True, "icon_url": "https://url.kr/x79ipj" },
	# 			"timestamp": base2.changeUTCtime(started_at)}]}

	def get_offState_change_title_json(self, init, twitchID, message, title, url):
		return {"username": init.twitchIDList.loc[twitchID, 'channelName'], "avatar_url": init.twitchIDList.loc[twitchID, 'channel_thumbnail'],\
				"embeds": [
					{"color": int(init.twitchIDList.loc[twitchID, 'channel_color']),
					"fields": [
						{"name": "이전 방제", "value": str(init.twitch_titleData.loc[twitchID,'title1']), "inline": True},
						{"name": "현재 방제", "value": title, "inline": True}],
					"title":  f"{init.twitchIDList.loc[twitchID, 'channelName']} {message}\n",\
				"url": url}]}

	def getOffJson(self, init, twitchID): #offJson
		return {"username": init.twitchIDList.loc[twitchID, 'channelName'], "avatar_url": init.twitchIDList.loc[twitchID, 'channel_thumbnail'],\
				"embeds": [
					{"color": int(init.twitchIDList.loc[twitchID, 'channel_color']),
					"title":  init.twitchIDList.loc[twitchID, 'channelName'] +" 방종함\n",\
				"image": {"url": init.twitchIDList.loc[twitchID, 'offLine_thumbnail']}}]}

	def getChatFilterName(self, init, name):
		[channelName] = [init.twitch_chatFilter["channelName"][i] for i in range(len(list(init.twitch_chatFilter["channelID"]))) if init.twitch_chatFilter["channelID"][i] == name]
		return channelName

	def getName(self, data): #get chat person's name 
		try:	return data[data.index(":") + 1:data.index("!")]
		except: return None

	def getLink(self, twitchID): return 'https://api.twitch.tv/helix/streams?user_login=' + twitchID #get twitch api link

	def getOffStateLink(self, channelName): return "https://api.twitch.tv/helix/search/channels?query=" + channelName #offline state data link

	def getURL(self, twitchID): return 'https://www.twitch.tv/' + twitchID #get channel URL

	def getStarted_at(self, stateData): return stateData['data'][0]["started_at"] #get started_at

	def getViewer_count(self, stateData): return stateData['data'][0]['viewer_count'] #get viewer data

	def getMessage(self, init, title, twitchID): return "방제 변경" if (self.ifChangeTitle(init, title, twitchID)) else "뱅온!" #turnOn or change title

	def getImage(self, init, stateData): #get thumbnail image
		width  = randint(init.width - init.randNum[0], init.width)
		height = randint(init.height - init.randNum[1], init.height)
		img = stateData['data'][0]['thumbnail_url']
		img = img.replace("{width", str(width))
		img = img.replace("{height", str(height))
		img = img.replace("}", "")
		return img

	def getThumbnail(self, init, twitchID, stateData): #thumbnail shape do transformation able to send to discord
		self.saveImage(init, stateData)
		file = {'file'      : open("explain.png", 'rb')}
		data = {"username"  : init.twitchIDList.loc[twitchID, 'channelName'],
				"avatar_url": init.twitchIDList.loc[twitchID, 'channel_thumbnail'],}
		thumbnail  = post(environ['recvThumbnailURL'], files=file, data=data, timeout=3)
		try: remove('explain.png')
		except: asyncio.create_task(DiscordWebhookSender._log_error("error png"))
		frontIndex = thumbnail.text.index('"proxy_url"')
		thumbnail  = thumbnail.text[frontIndex:]
		frontIndex = thumbnail.index('https://media.discordap')
		return thumbnail[frontIndex:thumbnail.index(".png") + 4]

	def getCustomMentData(self, init, discordWebhookURL, twitchID): #get customMent 
		# init.userStateData["커스텀 멘트"].index = init.discordURLList
		CustomMent = init.userStateData["커스텀 멘트"][discordWebhookURL]
		data = {"username": init.twitchIDList.loc[twitchID, 'channelName'],
				"avatar_url": init.twitchIDList.loc[twitchID, 'channel_thumbnail'],
				'content': CustomMent}
		return (str(type(CustomMent))) == "<class 'str'>", data

	def saveImage(self, init, stateData): urlretrieve(self.getImage(init, stateData), "explain.png") # save thumbnail image to png

	def turnOnline(self, init, live, twitchID): return live and init.twitch_titleData.loc[twitchID,'live_state'] == "CLOSE" #turn online

	def turnOffline(self, init, live, twitchID): return not live and init.twitch_titleData.loc[twitchID,'live_state'] == "OPEN" #turn offline

	# def onAirChat(self, init, twitchID, message): #if trun on air send chat
	# 	if twitchID =="charmel"    and message == "뱅온!": print("send hi"); base.send(init.sockDict["twitch"],f"PRIVMSG #{twitchID} : 챠하" + "\r\n", init)
	# 	if twitchID =="mawang0216" and message == "뱅온!": print("send hi"); base.send(init.sockDict["twitch"],f"PRIVMSG #{twitchID} : 마하" + "\r\n", init)
	# 	if twitchID =="bighead033" and message == "뱅온!": print("send hi"); base.send(init.sockDict["twitch"],f"PRIVMSG #{twitchID} : 빅하" + "\r\n", init)
	# 	if twitchID =="bercellion" and message == "뱅온!": print("send hi"); base.send(init.sockDict["twitch"],f"PRIVMSG #{twitchID} : 베하" + "\r\n", init)
	# 	if twitchID =="kdaomm"     and message == "뱅온!": print("send hi"); base.send(init.sockDict["twitch"],f"PRIVMSG #{twitchID} : 마하" + "\r\n", init)
	# def offAirChat(self, init, twitchID): #if trun off air send chat

	# 	if twitchID =="charmel"   : print("send bye"); base.send(init.sockDict["twitch"],f"PRIVMSG #{twitchID} : charme15BYE charme15BYE" + "\r\n", init)
	# 	if twitchID =="mawang0216": print("send bye"); base.send(init.sockDict["twitch"],f"PRIVMSG #{twitchID} : 마바" + "\r\n", init)
	# 	if twitchID =="bighead033": print("send bye"); base.send(init.sockDict["twitch"],f"PRIVMSG #{twitchID} : 빅바" + "\r\n", init)

