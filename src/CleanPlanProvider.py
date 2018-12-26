import datetime

from pymongo import MongoClient

from utils import UserManager, User, JobManager, Job


class CleanPlanProvider(object):

	def __init__(self):
		client = MongoClient(port=27017)
		self.db = client.cleanjobs
		self.user = UserManager([User(x["name"], x["contact"]) for x in self.db.contacts.find()])
		self.jobs = JobManager([Job(x["_id"], x["name"]) for x in self.db.jobs.find()])


	def get_current_assignments(self):
		today = datetime.datetime.now()
		assignment_key = self.assignment_key_from_date(today)

		self.calendarWeek = today.isocalendar()[1]

		self.currentAssignments = list(self.db.assignments.find({"date": assignment_key}))
		if len(self.currentAssignments) == 0:
			self.generate_cleanplan()
			self.currentAssignments = list(self.db.assignments.find({"date": assignment_key}))
		return self.currentAssignments

	def get_bath_assignment(self):
		return {x["name"]: x["job_id"] for x in self.db.bathroom.find()}

	def postpone_bathroom(self, user, job_id):
		self.db.bathroom.update_one({"name": user}, {"$_set": {"job_id": job_id}})

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

	@staticmethod
	def assignment_key_from_date(date):
		return "{}-{}".format(date.isocalendar()[1], date.year)

