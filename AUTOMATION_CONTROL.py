import os
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class AutomationControl(FileSystemEventHandler):
    def on_created(self, event):
        print(f'File {event.src_path} created at {datetime.now()}')

if __name__ == '__main__':
    observer = Observer()
    observer.schedule(AutomationControl(), path='/path/to/monitor', recursive=False)
    observer.start()
    try:
        while True:
            pass
    except KeyboardInterrupt:
        observer.stop()
    observer.join()