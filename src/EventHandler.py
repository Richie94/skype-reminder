from skpy import SkypeEventLoop, SkypeNewMessageEvent, SkypeImageMsg, SkypeTextMsg

import re
import io
import numpy as np

import time
import datetime

from PIL import Image

from keras.preprocessing.image import img_to_array
from keras.applications.resnet50 import preprocess_input, decode_predictions
from keras.applications import ResNet50

PING_REGEX = re.compile('ping')
BATHROOM_REGEX = re.compile('bad \w*? \w*?$')
USERS_REGEX = re.compile('users')


class MySkype(SkypeEventLoop):

	def __init__(self, user, pwd):
		super(MySkype, self).__init__(user=user, pwd=pwd)
		self.ALL_REGEX = {PING_REGEX: self.pong,
		                  BATHROOM_REGEX: self.move_bathroom,
		                  USERS_REGEX: self.list_users}
		self.resnet50 = None

	def cycle(self):
		super(MySkype, self).cycle()
		print(datetime.datetime.now())
		# hier käme der check, ob ich jetzt den task abschicken muss

	def loop(self):
		while True:
			self.cycle()
			time.sleep(1)

	def onEvent(self, event):
		if (isinstance(event, SkypeNewMessageEvent)):
			from_person = event.msg.userId
			msg_content = event.msg.content

			print("Received new Message: ", from_person, msg_content)

			if (isinstance(event.msg, SkypeImageMsg)):
				self.eva_picture(event)
			elif (isinstance(event.msg, SkypeTextMsg)):
				for REGEX in self.ALL_REGEX.keys():
					if REGEX.match(msg_content):
						self.ALL_REGEX.get(REGEX)(event)

	def pong(self, event):
		event.msg.chat.sendMsg("pong")

	def move_bathroom(self, event):
		persons = event.msg.content.split(" ")[1:]
		print(persons)
		event.msg.chat.sendMsg("verschiebe Badzimmer um 1 Woche für " + str(persons))

	def list_users(self, event):
		pass

	def eva_picture(self, event):
		image = Image.open(io.BytesIO(event.msg.fileContent))

		img_array = np.array([img_to_array(image.resize((224, 224)))])
		output = preprocess_input(img_array)

		# lazy load
		if self.resnet50 is None:
			self.resnet50 = ResNet50(weights='imagenet')
		predictions = self.resnet50.predict(output)

		res = str([x[1:] for x in decode_predictions(predictions, top=3)[0]])
		event.msg.chat.sendMsg(res)

evl = MySkype(user="u.unwichtiger@gmx.de", pwd="mstrprprspsswrt2")
evl.loop()