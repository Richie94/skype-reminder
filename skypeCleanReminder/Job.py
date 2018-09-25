class Job(object):

	def __init__(self, job_id, name):
		self.name = name
		self.id = job_id

class JobManager(object):

	def __init__(self, job_list):
		self.job_list = job_list

		self.sortJobs()

	def getJobById(self, job_id):
		for job in self.job_list:
			if job.id == job_id:
				return job

	def sortJobs(self):
		self.job_list = sorted(self.job_list, key = lambda x : x.id)

	def sortInOrder(self, order_list):
		_job_list = []
		for idx in order_list:
			_job_list.append(self.job_list[idx])
		self.job_list = _job_list
