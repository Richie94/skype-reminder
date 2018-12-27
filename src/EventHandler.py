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

THRESH_HOUR = 7

USERS_LIST = ('users', 'list all users')
BATHROOM_LIST = ('bad', 'show current bathroom assignments')
BATHROOM_SWITCH_CMD = ('bad \w*? \w*?$', 'postpone bathroom for two people')
PING_CMD = ('ping', 'basic ping-pong')
HELP_CMD = ('help', 'shows this')

class MySkype(SkypeEventLoop):

	def __init__(self, user, pwd):
		super(MySkype, self).__init__(user=user, pwd=pwd)
		self.ALL_COMMANDS = {PING_CMD: self.pong,
		                     BATHROOM_SWITCH_CMD: self.move_bathroom,
		                     USERS_LIST: self.list_users,
		                     BATHROOM_LIST: self.print_bathroom,
		                     HELP_CMD: self.print_help}
		self.cpp = CleanPlanProvider()
		self.users = self.cpp.user
		self.user_names = [u.name for u in self.users.user_list]
		self.jobs = self.cpp.jobs

		self.bath_plan = self.cpp.get_bath_assignment()

		self.resnet50 = None

		self.path = "/mnt/data/workspace/python/skypeReminder/resources/"
		self.send_today = False

		self.test_mode = True
		self.last_messages = []

	def cycle(self):
		super(MySkype, self).cycle()
		now = datetime.datetime.now()

		if (now.hour < THRESH_HOUR):
			self.send_today = False

		if (now.hour > THRESH_HOUR) & self.send_today == False:
			self.do_once_a_day()
			self.send_today = True


	def loop(self):
		while True:
			self.cycle()
			time.sleep(1)

	def onEvent(self, event):
		if isinstance(event, SkypeNewMessageEvent):
			matched = False
			from_person = event.msg.userId
			msg_content = event.msg.content

			print("Received new Message: ", from_person, msg_content)

			if isinstance(event.msg, SkypeImageMsg):
				self.eva_picture(event)
				matched = True
			elif isinstance(event.msg, SkypeTextMsg):
				for CMD in self.ALL_COMMANDS.keys():
					REGEX = re.compile(CMD[0])
					if REGEX.match(msg_content):
						self.ALL_COMMANDS.get(CMD)(event)
						matched = True

			if not matched:
				self.write_message(event, "Befehl nicht verstanden!")


	def write_message(self, event, msg):
		# TODO: format event to username
		logging.info("{}\t{}".format(event.msg.userId, msg))
		self.last_messages.append("{}\t{}".format(event, msg))
		if not self.test_mode:
			event.msg.chat.sendMsg(msg)

	def print_help(self, event):
		help_text = ""
		for CMD in self.ALL_COMMANDS:
			help_text += "{} - {}\n".format(CMD[0], CMD[1])
		self.write_message(event, help_text)

	def pong(self, event):
		self.write_message(event, "pong")

	def move_bathroom(self, event):
		persons = event.msg.content.split(" ")[1:]
		# check if persons do exist
		for person in persons:
			if person not in self.user_names:
				self.write_message(event, "User {} ist mir unbekannt".format(person))
				return

		# postpone bathroom
		self.postpone_bathroom(event, persons)
		self.write_message(event, "verschiebe Badzimmer um 1 Woche für " + str(persons))

	# Takes list of user names
	def postpone_bathroom(self, event, persons):
		for user in persons:
			if user in self.user_names:
				if (int(self.bath_plan[user]) == 0):
					self.bath_plan[user] = str(len(self.jobs.job_list))
				else:
					self.bath_plan[user] = str(int(self.bath_plan[user]) - 1)

				if not self.test_mode:
					self.cpp.postpone_bathroom(user, self.bath_plan[user])

		for user in self.users.user_list:
			self.write_message_to(user.contact, "{} updated bathroom_plan".format(event.msg.userId))

	def list_users(self, event):
		self.write_message(event, ", ".join(self.user_names))

	def eva_picture(self, event):
		image = Image.open(io.BytesIO(event.msg.fileContent))

		img_array = np.array([img_to_array(image.resize((224, 224)))])
		output = preprocess_input(img_array)

		# lazy load
		if self.resnet50 is None:
			self.resnet50 = ResNet50(weights='imagenet')
		predictions = self.resnet50.predict(output)

		res = str([x[1:] for x in decode_predictions(predictions, top=3)[0]])
		self.write_message(event, res)

	def motivational_tweet(self, contact):
		quotes = set(open(self.path + "positiveQuotes.txt", "r").read().split("\n"))
		chosen_quote = random.sample(quotes, 1)[0]
		self.write_message_to(contact, "Und übrigends: {}".format(chosen_quote))

	def print_bathroom(self, event):
		format_bathroom = ""
		for name, job_id in self.bath_plan.items():
			format_bathroom += name + ": " + self.jobs.getJobById(job_id).name + "\n"
		self.write_message(event, format_bathroom)

	def write_message_to(self, to, msg):
		chat = self.contacts[to]
		if not self.test_mode:
			chat.chat.sendMsg(msg)
		self.last_messages.append("{}\t{}".format(to, msg))
		logging.info("{}\t{}".format(to, msg))

	def do_once_a_day(self):
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