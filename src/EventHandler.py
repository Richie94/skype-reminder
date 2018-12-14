from skpy import SkypeEventLoop, SkypeNewMessageEvent
import re

PING_REGEX = re.compile('ping')
BATHROOM_REGEX = re.compile('bad \w*? \w*?$')
USERS_REGEX = re.compile('users')

class MySkype(SkypeEventLoop):

	def __init__(self, user, pwd):
		super(MySkype, self).__init__(user=user, pwd=pwd)
		self.ALL_REGEX = {PING_REGEX: self.pong,
		                  BATHROOM_REGEX: self.move_bathroom,
		                  USERS_REGEX: self.list_users}

	def onEvent(self, event):
		if (isinstance(event, SkypeNewMessageEvent)):
			from_person = event.msg.userId
			msg_content = event.msg.content

			print("Received new Message: ", from_person, msg_content)

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
