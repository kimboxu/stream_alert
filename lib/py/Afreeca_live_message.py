import base
import asyncio
from json import loads
from datetime import datetime
from requests import post
from os import remove, environ
from urllib.request import urlretrieve
from discord_webhook_sender import DiscordWebhookSender, get_list_of_urls
from my_app import send_push_notification

class afreeca_live_message():
	def __init__(self, init_var: base.initVar, channel_id):
		self.init = init_var
		self.DO_TEST = init_var.DO_TEST
		self.userStateData = init_var.userStateData
		self.afreecaIDList = init_var.afreecaIDList
		self.titleData = init_var.afreeca_titleData
		self.channel_id = channel_id
		self.data = base.LiveData()

	async def start(self):
		await self.addMSGList()
		await self.postLive_massge()

	async def addMSGList(self):

		try:
			state_data = await self._get_state_data()
			
			if not self._is_valid_state_data(state_data):
				return
			
			self._update_title_if_needed()

			# 스트림 데이터 얻기
			stream_data = self._get_stream_data(state_data)
			self._update_stream_info(stream_data, state_data)

			# 온라인/오프라인 상태 처리
			if self._should_process_online_status():
				await self._handle_online_status(state_data)
			elif self._should_process_offline_status():
				await self._handle_offline_status()

		except Exception as e:
			asyncio.create_task(DiscordWebhookSender._log_error(f"error get state_data afreeca live .{self.channel_id}.{e}"))
			await base.update_flag('user_date', True)
			
	def _is_valid_state_data(self, state_data):
		try:
			state_data["station"]["user_id"]
			return True
		except:
			return False
			
	async def _get_state_data(self):
		return await base.get_message(
			"afreeca", 
			base.afreeca_getLink(self.afreecaIDList.loc[self.channel_id, "afreecaID"])
		)

	def _update_title_if_needed(self):
		if (base.if_after_time(self.data.change_title_time) and 
	  		(self.titleData.loc[self.channel_id,'title2'] != self.titleData.loc[self.channel_id,'title1'])):
			self.titleData.loc[self.channel_id,'title2'] = self.titleData.loc[self.channel_id,'title1']

	def _get_stream_data(self, state_data):
		return base.afreeca_getChannelOffStateData(
			state_data,
			self.afreecaIDList.loc[self.channel_id, "afreecaID"],
			self.afreecaIDList.loc[self.channel_id, 'profile_image']
		)

	def _update_stream_info(self, stream_data, state_data):
		self.update_broad_no(state_data)
		self.data.start_at["openDate"] = state_data["station"]["broad_start"]
		self.data.live, self.data.title, self.data.profile_image = stream_data
		self.afreecaIDList.loc[self.channel_id, 'profile_image'] = self.data.profile_image

	def _should_process_online_status(self):
		return ((self.turnOnline() or 
				(self.data.title and self.ifChangeTitle())) and 
				base.if_after_time(self.data.LiveCountEnd, sec = 15))

	def _should_process_offline_status(self):
		return (self.turnOffline() and
		  		base.if_after_time(self.data.LiveCountStart, sec = 15))

	async def _handle_online_status(self, state_data):
		message = self.getMessage()
		json_data = await self.getOnAirJson(message, state_data)
		
		self.onLineTime(message)
		self.onLineTitle(message)
		
		self.data.livePostList.append((message, json_data))
		
		await base.save_profile_data(self.afreecaIDList, 'afreeca', self.channel_id)

		if message == "뱅온!": 
			self.data.LiveCountStart = datetime.now().isoformat()
		self.data.change_title_time = datetime.now().isoformat()

	async def _handle_offline_status(self):
		message = "뱅종"
		json_data = self.getOffJson()
		
		self.offLineTitle()

		self.data.livePostList.append((message, json_data))
		
		self.data.LiveCountEnd = datetime.now().isoformat()
		self.data.change_title_time = datetime.now().isoformat()

	def update_broad_no(self, state_data):
		if state_data["broad"] and state_data["broad"]["broad_no"] != self.titleData.loc[self.channel_id, 'chatChannelId']:
			self.titleData.loc[self.channel_id, 'oldChatChannelId'] = self.titleData.loc[self.channel_id, 'chatChannelId']
			self.titleData.loc[self.channel_id, 'chatChannelId'] = state_data["broad"]["broad_no"]
	
	def _get_channel_name(self):
		return self.afreecaIDList.loc[self.channel_id, 'channelName']

	async def postLive_massge(self):
		try:
			if not self.data.livePostList:
				return
			message, json_data = self.data.livePostList.pop(0)
			channel_name = self._get_channel_name()

			db_name = self._get_db_name(message)
			self._log_message(message, channel_name)

			list_of_urls = get_list_of_urls(self.DO_TEST, self.userStateData, channel_name, self.channel_id, db_name)
			
			asyncio.create_task(send_push_notification(list_of_urls, json_data))
			asyncio.create_task(DiscordWebhookSender().send_messages(list_of_urls, json_data))

			await base.save_airing_data(self.titleData, 'afreeca', self.channel_id)

		except Exception as e:
			asyncio.create_task(DiscordWebhookSender._log_error(f"postLiveMSG {e}"))
			self.data.livePostList.clear()

	def _get_db_name(self, message):
		"""메시지에 맞는 DB 이름 반환"""
		if message == "뱅온!":
			return "뱅온 알림"
		elif message == "방제 변경":
			return "방제 변경 알림"
		elif message == "뱅종":
			return "방종 알림"
		return "알림"
	
	def _log_message(self, message, channel_name):
		"""메시지 로깅"""
		now = datetime.now()
		if message == "뱅온!":
			print(f"{now} onLine {channel_name} {message}")
		elif message == "방제 변경":
			old_title = self._get_old_title()
			print(f"{now} onLine {channel_name} {message}")
			print(f"{now} 이전 방제: {old_title}")
			print(f"{now} 현재 방제: {self.data.title}")
		elif message == "뱅종":
			print(f"{now} offLine {channel_name}")

	def _get_old_title(self):
		return self.titleData.loc[self.channel_id,'title2']

	def onLineTitle(self, message): #change title. state to online
		if message == "뱅온!": self.titleData.loc[self.channel_id,'live_state'] = "OPEN"
		self.titleData.loc[self.channel_id,'title2'] = self.titleData.loc[self.channel_id,'title1']
		self.titleData.loc[self.channel_id,'title1'] = self.data.title

	def onLineTime(self, message): #change time. state to online
		if message == "뱅온!": 
			self.titleData.loc[self.channel_id,'update_time'] = self.getStarted_at("openDate")

	def offLineTitle(self): self.titleData.loc[self.channel_id,'live_state'] = "CLOSE" # change state to offline  

	def ifChangeTitle(self):
		return self.data.title not in [str(self.titleData.loc[self.channel_id,'title1']), str(self.titleData.loc[self.channel_id,'title2'])] #if title change

	async def getOnAirJson(self, message, state_data):
		channel_url  = self.get_channel_url()
		started_at   = self.getStarted_at("openDate")
		viewer_count = self.getViewer_count(state_data)
		thumbnail = await self.get_live_thumbnail_image(state_data)

		return self.get_online_state_json(message, channel_url, started_at, thumbnail, viewer_count)

	async def get_live_thumbnail_image(self, state_data):
		for count in range(20):
			thumbnail_image = self.get_thumbnail_image()
			if thumbnail_image is None: 
				print(f"{datetime.now()} wait make thumbnail 1 .{str(self.getImageURL(state_data))}")
				await asyncio.sleep(0.05)
				continue
			break
		else: thumbnail_image = ""

		return thumbnail_image

	def get_online_state_json(self, message, url, started_at, thumbnail, viewer_count):
		return {"username": self._get_channel_name(), "avatar_url": self.afreecaIDList.loc[self.channel_id, 'profile_image'],\
				"embeds": [
					{"color": int(self.afreecaIDList.loc[self.channel_id, 'channel_color']),
					"fields": [
						{"name": "방제", "value": self.data.title, "inline": True},
						{"name": ':busts_in_silhouette: 시청자수',
						"value": viewer_count, "inline": True}],
					"title":  f"{self._get_channel_name()} {message}\n",\
				"url": url, \
				"image": {"url": thumbnail},
				"footer": { "text": f"뱅온 시간", "inline": True, "icon_url": base.iconLinkData().soop_icon },
				"timestamp": base.changeUTCtime(started_at)}]}
	
	# def get_online_titleChange_state_json(self, message, title, url, started_at, thumbnail):
	# 	return {"username": self._get_channel_name(), "avatar_url": self.afreecaIDList.loc[self.channel_id, 'profile_image'],\
	# 			"embeds": [
	# 				{"color": int(self.afreecaIDList.loc[self.channel_id, 'channel_color']),
	# 				"fields": [
	# 					{"name": "이전 방제", "value": str(self.titleData.loc[self.channel_id,'title1']), "inline": True},
	# 					{"name": "현재 방제", "value": title, "inline": True}],
	# 				"title":  f"{self._get_channel_name()} {message}\n",\
	# 			"url": url, \
	# 			"image": {"url": thumbnail},
	# 			"footer": { "text": f"뱅온 시간", "inline": True, "icon_url": base.iconLinkData().soop_icon },
	# 			"timestamp": base.changeUTCtime(started_at)}]}

	def getOffJson(self): #offJson
		return {"username": self._get_channel_name(), "avatar_url": self.afreecaIDList.loc[self.channel_id, 'profile_image'],\
				"embeds": [
					{"color": int(self.afreecaIDList.loc[self.channel_id, 'channel_color']),
					"title":  self._get_channel_name() +" 방송 종료\n",\
				# "image": {"url": self.afreecaIDList.loc[self.channel_id, 'offLine_thumbnail']}
				}]}

	def get_channel_url(self):
		afreecaID = self.afreecaIDList.loc[self.channel_id, "afreecaID"]
		bno = self.titleData.loc[self.channel_id, 'chatChannelId']
		return f"https://play.sooplive.co.kr/{afreecaID}/{bno}"

	def getStarted_at(self, status: str): 
		time_str = self.data.start_at[status]
		if not time_str or time_str == '0000-00-00 00:00:00': 
			return None
		try:
			time = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
			return time.isoformat()
		except ValueError:
			return None

	def getViewer_count(self, state_data):
		return state_data['broad']['current_sum_viewer'] #get viewer data

	def getMessage(self): return "뱅온!" if (self.turnOnline()) else "방제 변경" #turnOn or change title

	def get_thumbnail_image(self): #thumbnail shape do transformation able to send to discord
		try:
			self.saveImage()
			file = {'file'      : open("explain.png", 'rb')}
			data = {"username"  : self._get_channel_name(),
					"avatar_url": self.afreecaIDList.loc[self.channel_id, 'profile_image']}
			thumbnail  = post(environ['recvThumbnailURL'], files=file, data=data, timeout=3)
			try: remove('explain.png')
			except: pass
			frontIndex = thumbnail.text.index('"proxy_url"')
			thumbnail  = thumbnail.text[frontIndex:]
			frontIndex = thumbnail.index('https://media.discordap')
			return thumbnail[frontIndex:thumbnail.index(".png") + 4]
		except:
			return None
	def saveImage(self): urlretrieve(self.getImageURL(), "explain.png") # save thumbnail image to png

	def getImageURL(self) -> str:
		return f"https://liveimg.afreecatv.com/m/{self.titleData.loc[self.channel_id, 'chatChannelId']}"

	def turnOnline(self):
		now_time = self.getStarted_at("openDate")
		old_time = self.titleData.loc[self.channel_id,'update_time']
		return self.data.live == 1 and self.titleData.loc[self.channel_id,'live_state'] == "CLOSE" and now_time > old_time #turn online

	def turnOffline(self):
		# now_time = self.getStarted_at(state_data)
		# old_time = self.titleData.loc[self.channel_id,'update_time']
		return self.data.live == 0 and self.titleData.loc[self.channel_id,'live_state'] == "OPEN" #turn offline
