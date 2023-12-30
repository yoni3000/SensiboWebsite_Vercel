from flask import Flask, render_template, request, url_for, flash, redirect
# from markupsafe import escape
from datetime import datetime, time, timedelta
import string
import random
import ast, pytz
from apscheduler.schedulers.background import BackgroundScheduler
# from apscheduler.schedulers.blocking import BlockingScheduler
from SensiboControl import SensiboControl
from Logger import Logger
import os


# Define constants
dayCodes = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# define some global variables
sched = BackgroundScheduler()
initialized = False
manual_shutdown = False

api_key = os.environ.get('api_key')




def time_format_check(test_str, format):
    try:
        res = bool(datetime.strptime(test_str, format))
    except ValueError:
        res = False
    return res


def str2bool(v):
    return v.lower() in ("yes", "true", "t", "1")


#  ========   flask application    ==========
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your secret key'


@app.route("/", methods=('GET', 'POST'))
def main():
    sched.add_job(
        printer,
        'cron',
        timezone='Israel',
        minute='0,3,6,7,8,9,10,11,12,15,18,21,24,27,30,33,36,39,42,45,48,51,54,57',
        second=30,
        id="main")
    return "hello"

def printer():
    print("yes")