import random
import logging

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

from CleanPlanProvider import CleanPlanProvider

PING_REGEX = re.compile('ping')
BATHROOM_SWITCH_REGEX = re.compile('bad \w*? \w*?$')
BATHROOM_REGEX = re.compile('bad \w*? \w*?$')
USERS_REGEX = re.compile('users')


def write_message(event, msg):
	# TODO: format event to username
	logging.info("{}\t{}".format(event, msg))
	event.msg.chat.sendMsg(msg)


class MySkype(SkypeEventLoop):

	def __init__(self, user, pwd):
		super(MySkype, self).__init__(user=user, pwd=pwd)
		self.ALL_REGEX = {PING_REGEX: self.pong,
		                  BATHROOM_SWITCH_REGEX: self.move_bathroom,
		                  USERS_REGEX: self.list_users,
		                  BATHROOM_REGEX: self.print_bathroom}
		self.cpp = CleanPlanProvider()
		self.users = self.cpp.user
		self.user_names = [u.name for u in self.users.user_list]
		self.jobs = self.cpp.jobs

		self.bath_plan = self.cpp.get_bath_assignment()

		self.resnet50 = None

		self.path = "/mnt/data/workspace/python/skypeReminder/resources/"

	def cycle(self):
		super(MySkype, self).cycle()
		print(datetime.datetime.now())
	# hier käme der check, ob ich jetzt den task abschicken muss

	def loop(self):
		while True:
			self.cycle()
			time.sleep(1)

	def onEvent(self, event):
		if isinstance(event, SkypeNewMessageEvent):
			from_person = event.msg.userId
			msg_content = event.msg.content

			print("Received new Message: ", from_person, msg_content)

			if isinstance(event.msg, SkypeImageMsg):
				self.eva_picture(event)
			elif isinstance(event.msg, SkypeTextMsg):
				for REGEX in self.ALL_REGEX.keys():
					if REGEX.match(msg_content):
						self.ALL_REGEX.get(REGEX)(event)

	@staticmethod
	def pong(event):
		event.msg.chat.sendMsg("pong")

	def move_bathroom(self, event):
		persons = event.msg.content.split(" ")[1:]
		# check if persons do exist
		for person in persons:
			if person not in self.user_names:
				write_message(event, "User {} ist mir unbekannt".format(person))
				return

		# postpone bathroom
		self.postpone_bathroom(event, persons)
		write_message(event, "verschiebe Badzimmer um 1 Woche für " + str(persons))

	# Takes list of user names
	def postpone_bathroom(self, event, persons):
		allowed_user_names = [u.name for u in self.user.user_list]
		for user in persons:
			if user in allowed_user_names:
				self.bath_plan[user] = str((1 + int(self.bath_plan[user])) % len(self.jobs.job_list))
				self.cpp.postpone_bathroom(user, self.bath_plan[user])

		for user in self.user.user_list:
			self.write_message_to(user.contact, "{} updated bathroom_plan".format(event.msg.userId))

	def list_users(self, event):
		write_message(event, ", ".join([u["name"] for u in self.users.user_list]))

	def eva_picture(self, event):
		image = Image.open(io.BytesIO(event.msg.fileContent))

		img_array = np.array([img_to_array(image.resize((224, 224)))])
		output = preprocess_input(img_array)

		# lazy load
		if self.resnet50 is None:
			self.resnet50 = ResNet50(weights='imagenet')
		predictions = self.resnet50.predict(output)

		res = str([x[1:] for x in decode_predictions(predictions, top=3)[0]])
		write_message(event, res)

	def motivational_tweet(self, contact):
		quotes = set(open(self.path + "positiveQuotes.txt", "r").read().split("\n"))
		chosen_quote = random.sample(quotes, 1)[0]
		self.write_message_to(contact, "Und übrigends: {}".format(chosen_quote))

	def print_bathroom(self, event):
		format_bathroom = ""
		for name, job_id in self.bath_plan.items():
			format_bathroom += name + ": " + self.jobs.getJobById(job_id) + "\n"
		write_message(event, format_bathroom)

	def write_message_to(self, to, msg):
		chat = self.contacts[to]
		chat.chat.sendMsg(msg)
		logging.info("{}\t{}".format(to, msg))

	def do_normal_jobs(self):
		weekday = datetime.datetime.today().weekday()
		# Montag
		logging.info("Current Day: {}".format(weekday))
		if weekday == 0:
			text = "Meister Proper hier, deine Mission diese Woche: {}"
			self.send_out_cleaning_message(text)
		# Freitag
		elif weekday == 4:
			text = "Meister Proper hier, falls du es immernoch nicht auf die Reihe bekommen haben solltest: {}"
			self.send_out_cleaning_message(text)

		self.motivational_tweet(self.users.getContact("Melanie"))

		logging.info("Finished Skype Reminder")

	def send_out_cleaning_message(self, text):
		today = datetime.datetime.now()
		calendar_week = today.isocalendar()[1]

		for current_assignment in self.bath_plan:
			user = current_assignment["user"]
			job = self.jobs.getJobById(current_assignment["job"])
			to = self.users.getContact(user)

			self.write_message_to(to, text.format(job.name))
			bath_text = "Außerdem bist du mit Bad dran."

			if self.cpp.get_bath_assignment()[user] == job.id:
				self.write_message_to(to, bath_text)

			if job.name == "Müll" and calendar_week % 3 == 2:
				self.write_message_to(to, "Denk an die Flaschen, du Flasche ;)")


if __name__ == "__main__":
	logging.basicConfig(
		format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO,
		filename='/mnt/data/workspace/python/skypeReminder/resources/reminder.log',
		filemode="a")
	logFormatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
	consoleHandler = logging.StreamHandler()
	consoleHandler.setFormatter(logFormatter)
	logging.getLogger().addHandler(consoleHandler)

	evl = MySkype(user="u.unwichtiger@gmx.de", pwd="mstrprprspsswrt2")
	evl.loop()