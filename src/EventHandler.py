import sys
sys.path.insert(0,'../')
import resources.config

import random
import logging
import multiprocessing

import skpy
from skpy import SkypeEventLoop, SkypeNewMessageEvent, SkypeImageMsg, SkypeTextMsg

import requests
import re
import io
import numpy as np

import time
import datetime

from PIL import Image

from keras.preprocessing.image import img_to_array
from keras.applications import  inception_v3

from CleanPlanProvider import CleanPlanProvider


THRESH_HOUR = 7

USERS_LIST = ('users', 'list all users')
JOBS_CMD = ('(jobs)|(aufgaben)( \d*)?$', 'lists current assignments e.g. "jobs x" with x as the number of weeks to advance')
BATHROOM_LIST = ('bad', 'show current bathroom assignments')
BATHROOM_SWITCH_CMD = ('bad \w*? \w*?$', 'postpone bathroom for two people e.g. "bad Peter Bernd"')
PING_CMD = ('ping', 'basic ping-pong')
HELP_CMD = ('(help)|(hilfe)', 'shows this')
JOKE_CMD = ('(joke)|(witz)', 'get dad joke')

class MySkype(SkypeEventLoop):

	def __init__(self):
		self.cpp = CleanPlanProvider()
		super(MySkype, self).__init__(user=self.cpp.login_data["email"], pwd=self.cpp.login_data["password"],
		                              tokenFile=resources.config.path + "tokenFile")
		self.ALL_COMMANDS = {PING_CMD: self.pong,
		                     BATHROOM_SWITCH_CMD: self.move_bathroom,
		                     USERS_LIST: self.list_users,
		                     BATHROOM_LIST: self.print_bathroom,
		                     HELP_CMD: self.print_help,
		                     JOBS_CMD: self.current_job_assignments,
		                     JOKE_CMD: self.print_dad_joke}
		self.users = self.cpp.user
		self.user_names = [u.name for u in self.users.user_list]
		self.allowed_contacts = [u.contact for u in self.users.user_list]
		self.jobs = self.cpp.jobs

		self.bath_plan = self.cpp.get_bath_assignment()

		self.model = None

		self.path = resources.config.path
		self.send_today = False

		self.test_mode = resources.config.test_mode
		self.last_messages = []

	def cycle(self):
		try :
			super(MySkype, self).cycle()
			now = datetime.datetime.now()
			today = now.strftime("%d-%m-%Y")

			if (now.hour > THRESH_HOUR) & (self.cpp.get_last_daily_write() != today):
				self.cpp.set_last_daily_write()
				self.do_once_a_day()
		except KeyboardInterrupt:
			sys.exit()
		except skpy.core.SkypeAuthException as e:
			print(e, "Wait 600s")
			time.sleep(600)
		except Exception as e:
			print(e, "Wait 10s")
			time.sleep(10)

	def loop(self):
		while True:
			self.cycle()
			time.sleep(1)

	def onEvent(self, event):
		if isinstance(event, SkypeNewMessageEvent):
			from_person = event.msg.userId

			if from_person not in self.allowed_contacts:
				return

			msg_content = event.msg.content
			print("Received new Message from {} : '{}'".format(from_person, msg_content))

			matched = False
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
		logging.info("{}\t{}".format(event.msg.userId, msg))
		self.last_messages.append("{}\t{}".format(event, msg))
		if not self.test_mode:
			event.msg.chat.sendMsg(msg)

	def print_dad_joke(self, event):
		r = requests.get('https://icanhazdadjoke.com/', headers={"Accept": "application/json"})
		self.write_message(event, r.json()["joke"])

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

				job_number = int(self.bath_plan[user])
				job_number += 1
				self.bath_plan[user] = str(job_number % len(self.users.user_list))

				if not self.test_mode:
					self.cpp.postpone_bathroom(user, self.bath_plan[user])

		for user in self.users.user_list:
			self.write_message_to(user.contact, "{} updated bathroom_plan".format(event.msg.userId))

	def list_users(self, event):
		self.write_message(event, ", ".join(self.user_names))

	def current_job_assignments(self, event):
		offset = 0
		split = event.msg.content.split(" ")
		if len(split) > 1:
			if split[1].isdigit():
				offset = int(split[1])
		text = ""

		for current_assignment in  self.cpp.get_current_assignments(offset=offset):
			job = self.jobs.getJobById(current_assignment["job"])
			user = current_assignment["user"]

			text += "{}: {}\n".format(user, job.name)

		self.write_message(event, text)

	def eva_picture(self, event):
		image = Image.open(io.BytesIO(event.msg.fileContent))

		img_array = np.array([img_to_array(image.resize((224, 224)))])
		output = inception_v3.preprocess_input(img_array)

		# lazy load
		if self.model is None:
			self.model = inception_v3.InceptionV3(weights='imagenet')
		predictions = self.model.predict(output)

		res = str([x[1:] for x in inception_v3.decode_predictions(predictions, top=5)[0]])
		self.write_message(event, res)

	def motivational_tweet(self, contact):
		quotes = set(open(self.path + "positiveQuotes.txt", "r").read().split("\n"))
		chosen_quote = random.sample(quotes, 1)[0]
		self.write_message_to(contact, "Und übrigends: {}".format(chosen_quote))

	def print_bathroom(self, event):
		format_bathroom = "Badezimmer korreliert mit: \n"
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

	def send_out_cleaning_message(self, text):
		today = datetime.datetime.now()
		calendar_week = today.isocalendar()[1]

		for current_assignment in self.cpp.get_current_assignments():
			user = current_assignment["user"]
			job = self.jobs.getJobById(current_assignment["job"])
			to = self.users.getContact(user)

			self.write_message_to(to, text.format(job.name))

			if self.cpp.get_bath_assignment()[user] == job.id:
				self.write_message_to(to, "Außerdem bist du mit Bad dran.")

			if job.name == "Müll" and calendar_week % 3 == 2:
				self.write_message_to(to, "Denk an die Flaschen, du Flasche ;)")


if __name__ == "__main__":
	logging.basicConfig(
		format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO,
		filename=resources.config.path + 'reminder.log',
		filemode="a")
	logFormatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
	consoleHandler = logging.StreamHandler()
	consoleHandler.setFormatter(logFormatter)
	logging.getLogger().addHandler(consoleHandler)

	evl = MySkype()
	evl.loop()
	#cycleCounter = 0
	#while True:
		# skype enfores relogin after 24h / expires token, so we do that manually
		#if cycleCounter > 20000:
		#	logging.info("Restart Client to Request new Token")
		#	evl = MySkype()
		#	cycleCounter = 0

		#cycleCounter += 1
		# do cycle in process because it seems to freeze after some time so we can kill it
		#p = multiprocessing.Process(target=evl.cycle)
		#p.start()
		#time.sleep(1)
		#p.join(600)
		#evl.cycle()

		#if p.is_alive():
		#	logging.error("Task not finished after 600s, terminate")
		#	p.terminate()