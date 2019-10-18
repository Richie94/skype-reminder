import unittest

from skpy import SkypeNewMessageEvent, SkypeMessageEvent

from EventHandler import MySkype
from unittest.mock import MagicMock

class BotTest(unittest.TestCase):

	def __init__(self):
		super(BotTest, self).__init__()
		self.sk = MySkype()
		self.sk.send_out_cleaning_message = MagicMock()

	def test_ping(self):
		#self.sk.pong(SkypeMessageEvent().o)
		pass

if __name__ == '__main__':
	unittest.main()
