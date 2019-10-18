class User(object):

	def __init__(self, name, contact):
		self.name = name
		self.contact = contact


class UserManager(object):

	def __init__(self, user_list):
		self.user_list = user_list

	def getContact(self, name):
		for user in self.user_list:
			if user.name == name:
				return user.contact
		return ""

	def permutate(self):
		self.user_list = [self.user_list[-1]] + self.user_list[:-1]
