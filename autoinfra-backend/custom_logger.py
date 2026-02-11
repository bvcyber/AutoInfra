import logging
from flask import Flask

class CustomFormatter(logging.Formatter):
    def __init__(self, fmt=None, datefmt=None):
        super().__init__(fmt=fmt, datefmt=datefmt)
    
    def format(self, record):
        original_format = super().format(record)
        return original_format

def setup_logger():
    logger = logging.getLogger("backend-logs")
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    console_handler = logging.StreamHandler()
    log_format = (
        "\n"
        "Time: %(asctime)s\n"
        "Level: %(levelname)s\n"
        "Message: %(message)s\n"
    )
    date_format = "%Y-%m-%d %I:%M %p"
    formatter = CustomFormatter(log_format, datefmt=date_format)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    logger.setLevel(logging.DEBUG)
    return logger
