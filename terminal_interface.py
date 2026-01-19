import os
import subprocess
import sys

class TerminalInterface:
	def __init__(self):
		self.commands = []
		self.output = ''

	def execute(self, command):
		if command == '':
			return
		else:
			self.commands.append(command)
			try:
				result = subprocess.check_output(command, shell=True)
				self.output += result.decode('utf-8')
				return self.output
			except subprocess.CalledProcessError as e:
				print(e)
				return 'Command not found'

	def list_dir(self, path):
		if os.path.isdir(path):
			files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
			return files
		else:
			print('Path not found')
			return []

	def main(self):
		while True:
			command = input('>>> ')
			if command == 'exit':
				break
			else:
				result = self.execute(command)
				print(result)