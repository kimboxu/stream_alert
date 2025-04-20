import base
import asyncio
from json import loads
from datetime import datetime
from os import remove, environ
from requests import post
from urllib.request import urlretrieve
from discord_webhook_sender import DiscordWebhookSender, get_list_of_urls
from my_app import send_push_notification

class chzzk_live_message():
	def __init__(self, init_var: base.initVar, chzzk_id):
		self.init = init_var
		self.DO_TEST = init_var.DO_TEST
		self.userStateData = init_var.userStateData
		self.chzzkIDList = init_var.chzzkIDList
		self.titleData = init_var.chzzk_titleData
		self.channel_id = chzzk_id
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
				await self._handle_offline_status(state_data)

		except Exception as e:
			asyncio.create_task(DiscordWebhookSender._log_error(f"testerror get state_data chzzk live{e}.{self.channel_id}.{str(state_data)}"))
			await base.update_flag('user_date', True)

	async def _get_state_data(self):
		return await base.get_message(
			"chzzk", 
			base.chzzk_getLink(self.chzzkIDList.loc[self.channel_id, "channel_code"])
		)
	
	def _is_valid_state_data(self, state_data):
		return state_data["code"] == 200

	def _update_title_if_needed(self):
		if (base.if_after_time(self.data.change_title_time) and 
			self.titleData.loc[self.channel_id,'title2'] != self.titleData.loc[self.channel_id,'title1']):
			self.titleData.loc[self.channel_id,'title2'] = self.titleData.loc[self.channel_id,'title1']

	def _get_stream_data(self, state_data):
		return base.chzzk_getChannelOffStateData(
			state_data["content"], 
			self.chzzkIDList.loc[self.channel_id, "channel_code"], 
			self.chzzkIDList.loc[self.channel_id, 'profile_image']
		)
	
	def _update_stream_info(self, stream_data, state_data):
		self.data.start_at["openDate"] = state_data['content']["openDate"]
		self.data.start_at["closeDate"] = state_data['content']["closeDate"]
		self.data.live, self.data.title, self.data.profile_image = stream_data
		self.chzzkIDList.loc[self.channel_id, 'profile_image'] = self.data.profile_image

	def _should_process_online_status(self):
		return ((self.checkStateTransition("OPEN") or 
		   (self.ifChangeTitle())) and
		   base.if_after_time(self.data.LiveCountEnd, sec = 15) )

	def _should_process_offline_status(self):
		return (self.checkStateTransition("CLOSE") and 
		  base.if_after_time(self.data.LiveCountStart, sec = 15))
	
	async def _handle_online_status(self, state_data):
		message = self.getMessage()
		json_data = await self.getOnAirJson(message, state_data)

		self.onLineTime(message)
		self.onLineTitle(message)

		self.data.livePostList.append((message, json_data))

		await base.save_profile_data(self.chzzkIDList, 'chzzk', self.channel_id)

		if message == "뱅온!": 
			self.data.LiveCountStart = datetime.now().isoformat()
		self.data.change_title_time = datetime.now().isoformat()

	async def _handle_offline_status(self, state_data):
		message = "뱅종"
		json_data = await self.getOffJson(state_data, message)

		self.offLineTitle()
		self.offLineTime()

		self.data.livePostList.append((message, json_data))

		self.data.LiveCountEnd = datetime.now().isoformat()
		self.data.change_title_time = datetime.now().isoformat()

	def _get_channel_name(self):
		return self.chzzkIDList.loc[self.channel_id, 'channelName']
	
	async def postLive_massge(self):
		try:
			if not self.data.livePostList: 
				return
			message, json_data = self.data.livePostList.pop(0)
			channel_name = self._get_channel_name()

			db_name = self._get_db_name(message)
			self._log_message(message, channel_name)

			list_of_urls= get_list_of_urls(self.DO_TEST, self.userStateData, channel_name, self.channel_id, db_name)

			asyncio.create_task(send_push_notification(list_of_urls, json_data))
			asyncio.create_task(DiscordWebhookSender().send_messages(list_of_urls, json_data))
			await base.save_airing_data(self.titleData, 'chzzk', self.channel_id)

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
		return self.titleData.loc[self.c,'title2']

	def onLineTitle(self, message):
		if message == "뱅온!":
			self.titleData.loc[self.channel_id, 'live_state'] = "OPEN"
		self.titleData.loc[self.channel_id,'title2'] = self.titleData.loc[self.channel_id,'title1']
		self.titleData.loc[self.channel_id,'title1'] = self.data.title

	def onLineTime(self, message):
		if message == "뱅온!":
			self.titleData.loc[self.channel_id,'update_time'] = self.getStarted_at("openDate")

	def offLineTitle(self):
		self.titleData.loc[self.channel_id, 'live_state'] = "CLOSE"

	def offLineTime(self):
		self.titleData.loc[self.channel_id,'update_time'] = self.getStarted_at("closeDate")


	def ifChangeTitle(self):
		return self.data.title not in [str(self.titleData.loc[self.channel_id,'title1']), str(self.titleData.loc[self.channel_id,'title2'])]

	async def getOnAirJson(self, message, state_data):
		channel_url = self.get_channel_url()
		
		if self.data.live == "CLOSE":
			return self.get_state_data_change_title_json(message, channel_url)
		
		started_at = self.getStarted_at("openDate")
		viewer_count = self.getViewer_count(state_data)
		live_thumbnail_image = await self.get_live_thumbnail_image(state_data, message)
		
		if message == "뱅온!":
			return self.get_online_state_json(
				message, channel_url, started_at, live_thumbnail_image, viewer_count
			)
		
		return self.get_online_titleChange_state_json(message, channel_url, started_at, live_thumbnail_image, viewer_count)

	async def get_live_thumbnail_image(self, state_data, message):
		for count in range(20):
			time_difference = (datetime.now() - datetime.fromisoformat(self.titleData.loc[self.channel_id, 'update_time'])).total_seconds()

			if message == "뱅온!" or self.titleData.loc[self.channel_id, 'live_state'] == "CLOSE" or time_difference < 15: 
				thumbnail_image = ""
				break

			thumbnail_image = self.get_thumbnail_image(state_data)
			if thumbnail_image is None:
				print(f"{datetime.now()} wait make thumbnail1 {count}")
				await asyncio.sleep(0.05)
				continue
			break

		else: thumbnail_image = ""
		
		return thumbnail_image

	def get_online_state_json(self, message, url, started_at, thumbnail, viewer_count):
		return {"username": self._get_channel_name(), "avatar_url": self.chzzkIDList.loc[self.channel_id, 'profile_image'],
				"embeds": [
					{"color": int(self.chzzkIDList.loc[self.channel_id, 'channel_color']),
					"fields": [
						{"name": "방제", "value": self.data.title, "inline": True},
						# {"name": ':busts_in_silhouette: 시청자수',
						# "value": viewer_count, "inline": True}
						],
					"title":  f"{self._get_channel_name()} {message}\n",
				"url": url,
				# "image": {"url": thumbnail},
				"footer": { "text": f"뱅온 시간", "inline": True, "icon_url": base.iconLinkData().chzzk_icon },
				"timestamp": base.changeUTCtime(started_at)}]}

	def get_online_titleChange_state_json(self, message, url, started_at, thumbnail, viewer_count):
		return {"username": self._get_channel_name(), "avatar_url": self.chzzkIDList.loc[self.channel_id, 'profile_image'],
		"embeds": [
			{"color": int(self.chzzkIDList.loc[self.channel_id, 'channel_color']),
			"fields": [
				{"name": "방제", "value": self.data.title, "inline": True},
				{"name": ':busts_in_silhouette: 시청자수',
				"value": viewer_count, "inline": True}
				],
			"title":  f"{self._get_channel_name()} {message}\n",
		"url": url,
		"image": {"url": thumbnail},
		"footer": { "text": f"뱅온 시간", "inline": True, "icon_url": base.iconLinkData().chzzk_icon },
		"timestamp": base.changeUTCtime(started_at)}]}
		# return {"username": self.chzzkIDList.loc[chzzkID, 'channelName'], "avatar_url": self.chzzkIDList.loc[chzzkID, 'profile_image'],
		# 		"embeds": [
		# 			{"color": int(self.chzzkIDList.loc[chzzkID, 'channel_color']),
		# 			"fields": [
		# 				{"name": "이전 방제", "value": str(self.titleData.loc[chzzkID,'title1']), "inline": True},
		# 				{"name": "현재 방제", "value": title, "inline": True},
		# 				{"name": ':busts_in_silhouette: 시청자수',
		# 				"value": viewer_count, "inline": True}],
		# 			"title":  f"{self.chzzkIDList.loc[chzzkID, 'channelName']} {message}\n",
		# 		"url": url,
		# 		"image": {"url": thumbnail},
		# 		"footer": { "text": f"뱅온 시간", "inline": True, "icon_url": base.iconLinkData().chzzk_icon },
		# 		"timestamp": base.changeUTCtime(started_at)}]}

	def get_state_data_change_title_json(self, message, url):
		return {"username": self._get_channel_name(), "avatar_url": self.chzzkIDList.loc[self.channel_id, 'profile_image'],
				"embeds": [
					{"color": int(self.chzzkIDList.loc[self.channel_id, 'channel_color']),
					"fields": [
						{"name": "이전 방제", "value": str(self.titleData.loc[self.channel_id,'title1']), "inline": True},
						{"name": "현재 방제", "value": self.data.title, "inline": True}],
					"title":  f"{self._get_channel_name()} {message}\n",
				"url": url}]}

	async def getOffJson(self, state_data, message):
		started_at = self.getStarted_at("closeDate")
		live_thumbnail_image = await self.get_live_thumbnail_image(state_data, message)
		
		return {"username": self._get_channel_name(), "avatar_url": self.chzzkIDList.loc[self.channel_id, 'profile_image'],
				"embeds": [
					{"color": int(self.chzzkIDList.loc[self.channel_id, 'channel_color']),
					"title":  self._get_channel_name() +" 방송 종료\n",
				"image": {"url": live_thumbnail_image},
				"footer": { "text": f"방종 시간", "inline": True, "icon_url": base.iconLinkData().chzzk_icon },
				"timestamp": base.changeUTCtime(started_at)}]}

	def get_channel_url(self): 
		return f'https://chzzk.naver.com/live/{self.chzzkIDList.loc[self.channel_id, "channel_code"]}'

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
		return state_data['content']['concurrentUserCount']

	def getMessage(self) -> str: 
		return "뱅온!" if (self.checkStateTransition("OPEN")) else "방제 변경"

	def get_thumbnail_image(self, state_data): #thumbnail shape do transformation able to send to discord
		try:
			if state_data['content']['liveImageUrl'] is not None:
				self.saveImage(state_data)
				file = {'file'      : open("explain.png", 'rb')}
				data = {"username"  : self._get_channel_name(),
						"avatar_url": self.chzzkIDList.loc[self.channel_id, 'profile_image']}
				thumbnail  = post(environ['recvThumbnailURL'], files=file, data=data, timeout=3)
				try: remove('explain.png')
				except: pass
				frontIndex = thumbnail.text.index('"proxy_url"')
				thumbnail  = thumbnail.text[frontIndex:]
				frontIndex = thumbnail.index('https://media.discordap')
				return thumbnail[frontIndex:thumbnail.index(".png") + 4]
			return None
		except Exception as e:
			asyncio.create_task(DiscordWebhookSender._log_error(f"{datetime.now()} wait make thumbnail2 {e}"))
			return None

	def saveImage(self, state_data): urlretrieve(self.getImageURL(state_data), "explain.png") # save thumbnail image to png

	def getImageURL(self, state_data) -> str:
		link = state_data['content']['liveImageUrl']
		link = link.replace("{type", "")
		link = link.replace("}.jpg", "0.jpg")
		return link

	def checkStateTransition(self, target_state: str):
		if self.data.live != target_state or self.titleData.loc[self.channel_id, 'live_state'] != ("CLOSE" if target_state == "OPEN" else "OPEN"):
			return False
		return self.getStarted_at(("openDate" if target_state == "OPEN" else "closeDate")) > self.titleData.loc[self.channel_id, 'update_time']
		