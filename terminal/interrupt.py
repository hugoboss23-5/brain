import signal

# Define a function to handle SIGINT
def handler(signum, frame):
    print('Response interrupted by user')
signal.signal(signal.SIGINT, handler)

# Set the interrupt signal
signal.setitimer(signal.ITIMER_REAL, 0.1)