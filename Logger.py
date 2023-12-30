import pytz, datetime
from datetime import datetime


class Logger:

    def __init__(self, file_name):
        global filename
        filename = file_name

    def timestamp(self):
        timezone = pytz.timezone("Asia/Jerusalem")
        current_time = datetime.now()
        time_stamp = current_time.timestamp()
        date_time = datetime.fromtimestamp(time_stamp, tz=timezone)
        date_time_format = date_time.strftime("%d-%m-%Y, %H:%M:%S")
        return date_time_format

    def log(self, message, include_timestamp=True, overwrite=False):
        if overwrite:
            mode = "w"
        else:
            mode = "a"

        if include_timestamp:
            message = self.timestamp() + ": " + message

        fileWriter = open(filename, mode)
        fileWriter.write(message + "\n")
        fileWriter.close()
