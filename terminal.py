import os
import subprocess
def execute(command):
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
    output = process.communicate()[0]
    return output.decode('utf-8')

if __name__ == '__main__':
    command = input('Enter a command: ')
    print(execute(command))