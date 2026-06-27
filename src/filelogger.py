import os
import logging
from logging.handlers import RotatingFileHandler

filename = "app.log"
logFileDirectory = "logfile"
filePath = os.path.join(logFileDirectory, filename)

if not os.path.exists(logFileDirectory):
    os.makedirs(logFileDirectory)

file_handler = RotatingFileHandler(
    filename=filePath,
    maxBytes=1024*1024,
    backupCount=5,
    encoding="utf-8"
)
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

logger = logging.getLogger("AppLogger")
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)