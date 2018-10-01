#!/usr/bin/env python
from skpy import Skype
import skpy
import datetime
import random
import logging

from pymongo import MongoClient

from utils import User, UserManager, Job, JobManager

class SkypeReminder(object):

	def __init__(self):
		logging.info("Init Skype Reminder")
		client = MongoClient(port=27017)
		self.db = client.cleanjobs
		login_data = self.db.user.find_one()
		self.user = UserManager([User(x["name"], x["contact"]) for x in self.db.contacts.find()])
		self.jobs = JobManager([Job(x["_id"], x["name"]) for x in self.db.jobs.find()])

		self.path = "/mnt/data/workspace/python/skypeReminder/resources/"

		self.skype = Skype(login_data["email"], login_data["password"])
		today = datetime.datetime.now()
		assignment_key = self.assignment_key_from_date(today)

		self.calendarWeek = today.isocalendar()[1]

		self.currentAssignments = list(self.db.assignments.find({"date": assignment_key}))
		if len(self.currentAssignments) == 0:
			self.generate_cleanplan()
			self.currentAssignments = list(self.db.assignments.find({"date": assignment_key}))

		self.bath_plan = {x["name"]: x["job_id"] for x in self.db.bathroom.find()}

	def generate_cleanplan(self):
		now = datetime.datetime.now()

		cycle = datetime.timedelta(days=7)

		for _ in range(1000):
			# write to database
			date_identifier = self.assignment_key_from_date(now)
			for idx, user in enumerate(self.user.user_list):
				self.db.assignments.insert_one({"user": user.name, "job": self.jobs.job_list[idx].id, "date": date_identifier})
			# permutate users
			self.user.permutate()

			now = now + cycle

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

		self.motivational_tweet(self.user.getContact("Melanie"))

		#self.evaluate_picture()

		logging.info("Finished Skype Reminder")

	# Takes list of user names
	#def postpone_bathroom(self, users):
	#	job_amount = len(self.jobs)
	#	for user in users:
	#		current_linked_task = self.bath_plan[user]
	#		current_linked_task_id = int([x for x in self.jobs if x.endswith(current_linked_task)][0].split("__")[0])
	#		new_task = [x for x in self.jobs
	#		            if x.startswith(str((current_linked_task_id+1) % job_amount))][0]
	#		self.bath_plan[user] = new_task
	#	json.dump(self.bath_plan, open(self.path + "bathplan.json", "w"))

	def motivational_tweet(self, contact):
		quotes = set(open(self.path + "positiveQuotes.txt", "r").read().split("\n"))
		chosen_quote = random.sample(quotes, 1)[0]
		self.write_message(contact, "Und übrigends: {}".format(chosen_quote))

	def invite_new_user(self, contact):
		self.skype.contacts[contact].invite(
			"Hallo {}. Dies ist dein neuer Erinnerungsservice zum Putzen. " +
			"Grüße von deinem neuen Peiniger.".format(contact))

	def write_message(self, to, msg):
		chat = self.skype.contacts[to]
		chat.chat.sendMsg(msg)
		logging.info("{}\t{}".format(to, msg))

	def send_out_cleaning_message(self, text):
		for current_assignment in self.currentAssignments:
			user = current_assignment["user"]
			job = self.jobs.getJobById(current_assignment["job"])
			to = self.user.getContact(user)

			self.write_message(to, text.format(job.name))
			bath_text = "Außerdem bist du mit Bad dran."

			if self.bath_plan[user] == job.id:
				self.write_message(to, bath_text)

			if job.name == "Müll" and self.calendarWeek % 3 == 2:
				self.write_message(to, "Denk an die Flaschen, du Flasche ;)")

	def write_msg_id(self, msg_id):
		with open(self.path+"msgIds.csv", "a") as f:
			f.write(str(msg_id) + ",")

	def get_read_messages(self):
		with open(self.path+"msgIds.csv", "r") as f:
			return f.read().split(",")[:-1]

	def get_messages(self):
		msgs = {}
		# TODO: ensure it is new
		for contact in self.skype.contacts:
			msgs[contact] = self.skype.contacts[contact].chat.getMsgs()
		return msgs

	# possible commands:
	# bathroom sven markus -> postpone_bathroom + inform
	# help -> shows all current functions
	# list users -> returns all users

	def evaluate_picture(self):
		for chat in self.skype.contacts:
			msgs = chat.chat.getMsgs()

			read_messages = self.get_read_messages()

			for msg in msgs:
				if type(msg) == skpy.msg.SkypeImageMsg and msg.id not in read_messages:
					logging.info("Found ImageMsg")
					from PIL import Image
					import io
					image = Image.open(io.BytesIO(msg.fileContent))

					from keras.preprocessing.image import img_to_array
					from keras.applications.resnet50 import preprocess_input, decode_predictions
					import numpy as np
					from keras.applications import ResNet50

					img_array = np.array([img_to_array(image.resize((224, 224)))])
					output = preprocess_input(img_array)

					if self.myModel is None:
						self.myModel = ResNet50(weights='imagenet')
					predictions = self.myModel.predict(output)

					res = str([x[1:] for x in decode_predictions(predictions, top=3)[0]])
					chat.chat.sendMsg(res)
					self.write_msg_id(msg.id)

	def write_tex(self, until):
		now = datetime.datetime.now()
		cycle = datetime.timedelta(days=7)
		d = "{}-W{}".format(now.year, now.isocalendar()[1])
		current_monday = datetime.datetime.strptime(d + '-1', "%Y-W%W-%w")
		with open(self.path + "putzplan_table.tex", "w") as f:
			while now < until:
				assignment_key = self.assignment_key_from_date(current_monday)
				current_assignments = self.db.assignments.find({"date": assignment_key})
				line = current_monday.strftime("%d/%m") + "&"
				current_monday += cycle
				for assignment in current_assignments:
					line += "{}& & ".format(self.jobs.getJobById(assignment["job"]))

				f.write("{}\\\n".format(line))

	@staticmethod
	def assignment_key_from_date(date):
		return "{}-{}".format(date.isocalendar()[1], date.year)


if __name__ == "__main__":
	logging.basicConfig(
		format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO,
		filename='/mnt/data/workspace/python/skypeReminder/resources/reminder.log',
		filemode="a")
	logFormatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
	consoleHandler = logging.StreamHandler()
	consoleHandler.setFormatter(logFormatter)
	logging.getLogger().addHandler(consoleHandler)

	reminder = SkypeReminder()
	#reminder.write_tex()
	reminder.do_normal_jobs()
