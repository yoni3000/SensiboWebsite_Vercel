
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
logger = Logger('Log.txt')

# fileReader = open("key.txt")
# api_key = fileReader.readlines()[0]
# print(api_key)
# fileReader.close()

api_key = os.environ.get('api_key')

# Import timers
try:
    fileReader = open("Timers.txt")
    timersContents = fileReader.readlines()
    fileReader.close()
    timers = []
    for timerLine in timersContents:
        timerLineData = [x.strip() for x in timerLine.split(';')]
        timers.append({
            'time': timerLineData[0],
            'day': timerLineData[1],
            'temp': timerLineData[2],
            'mode': timerLineData[3],
            'active': timerLineData[4],
            'id': timerLineData[5]
        })
except Exception as e:
    print(
        "Error loading timer file on initialization.\nDetails of exception:\n" +
        repr(e))
    logger.log(
        "Error loading timer file on initialization.\nDetails of exception:\n" +
        repr(e))


# ===Define useful functions===

def print_and_log(message):
    global logger
    message = str(message)
    print(message)
    logger.log(message)


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
    global initialized, sensi, api_key
    if initialized:
        if request.method == 'POST':
            if request.is_json:  # unique to timer deletion or activation/deactivation
                postdat = request.get_json()
                timerIndex = int(postdat["id"])
                timerID = timers[timerIndex]['id']
                action = postdat["form"]
                if action == "deletetimer":
                    timers.pop(int(postdat["id"]))
                    delete_timer(timerID)
                    print_and_log("Timer deleted successfully.")
                elif action == "activatetimer":
                    timers[timerIndex]["active"] = postdat["activate"]
                    if not postdat["activate"]:
                        sched.pause_job(timers[timerIndex]['id'])
                    else:
                        sched.resume_job(timers[timerIndex]['id'])
                    print_and_log("Timer activated/deactivated successfully.")
                print(timers)
                write_timer(timers)
                return redirect(url_for('main'))
            else:
                if request.form["form"] == 'addtimer':
                    # check input data is valid
                    validEntry = True
                    days = [
                        day.strip() for day in request.form['timerDays'].strip().split(",")
                    ]
                    for day in days:
                        if dayCodes.count(day) < 1:
                            validEntry = False
                            error = "Invalid day entry"
                    if request.form['timerMode'] != "off":
                        if not isfloat(request.form['timerTemp'].strip()):
                            validEntry = False
                            error = "Invalid temperature entry"
                    if not time_format_check(request.form['timerTime'].strip(), "%H:%M"):
                        validEntry = False
                        error = "Invalid time entry"

                    # process input
                    if validEntry == True:
                        if request.form['timerMode'] == "off":
                            timerTemp = "-"
                        else:
                            timerTemp = request.form['timerTemp']

                        timerID = ''.join(
                            random.choice(string.ascii_letters + string.digits)
                            for i in range(4))
                        try:
                            fileReader2 = open("Timers.txt", 'a')
                            fileReader2.write(request.form['timerTime'].strip() + "; " +
                                              request.form['timerDays'].strip() + "; " +
                                              timerTemp.strip() + "; " +
                                              request.form['timerMode'].strip() +
                                              "; True; " + timerID + ";" + "\n")
                            fileReader2.close()
                        except IOError as e:
                            print_and_log("IO-error in adding timer.")
                        else:
                            timer = {
                                'time': request.form['timerTime'].strip(),
                                'day': request.form['timerDays'].strip(),
                                'temp': timerTemp.strip(),
                                'mode': request.form['timerMode'],
                                'active': "True",
                                'id': timerID
                            }
                            timers.append(timer)
                            add_timer(timer)
                            print_and_log("Timer added successfully.")
                        finally:
                            # return redirect(request.url)
                            return redirect(url_for('main'))
                    else:  # invalid entry for timer
                        flash(error)
                elif request.form["form"] == 'settemp':
                    try:
                        frmTemp = request.form['frmTemp'].strip()
                        if frmTemp == "off" or request.form['setTempOpt'] == 'Off':
                            sensi.turn_off()
                        elif isfloat(frmTemp):
                            sensi.set_temp(float(request.form['frmTemp']),
                                           set_mode=request.form['setTempOpt'].lower())
                        else:
                            error = "Invalid temperature entry"
                            flash(error)
                    except Exception as e:
                        print_and_log(
                            "Error setting sensibo temperature.\nDetails of exception:\n" +
                            repr(e))
                        flash("Sensibo communication error.")
        try:
            room_temperature = sensi.read_temperature()
        except Exception as e:
            print_and_log(
                "Error reading sensibo temperature.\nDetails of exception:\n" +
                repr(e))
            room_temperature = "Unknown"
        finally:
            current_setting = sensi.get_current_setting()
            return render_template('main.html.jinja',
                                   timers=timers,
                                   room_temperature=room_temperature,
                                   target_temperature=current_setting['temperature'],
                                   mode=current_setting['mode'],
                                   override=current_setting['override'])
    else:
        if manual_shutdown:  # program was intentionally turned off and needs to be manually restarted by entering api key through startup link
            return 'Welcome. AC is currently uninitialized. To initialize, click <a href="https://accontroller.onrender.com//startup">here</a>.'
        else:
            # if program uninitialized, startup, picking up with state prior to crash:
            try:  # read the last saved settings
                fileReader = open("CurrentSetting.txt")
                settingContents = fileReader.readlines()
                fileReader.close()
                set_temp = float(settingContents[0].strip())
                set_mode = settingContents[1].strip()
                set_on = str2bool(settingContents[2].strip())
                set_override = str2bool(settingContents[3].strip())
                local_ac_state = ast.literal_eval(settingContents[4].strip())
                set_time = settingContents[5].strip()
            except Exception as e:
                print_and_log(
                    "Error loading setting file on initialization.\nDetails of exception:\n"
                    + repr(e))
                set_temp = 24
                set_mode = "auto"
                set_on = False
                set_override = True
                set_time = "04-02-2023, 23:09:32"

            finally:
                try:
                    # Step 1: initialize sensibo controller with input api and to input setting
                    print_and_log("Attempt initiation of sensibo.")

                    timezone = pytz.timezone("Asia/Jerusalem")

                    # get date and time info of when program resumes
                    current_datetime = datetime.now(tz=timezone)
                    current_time = current_datetime.time()
                    current_date = current_datetime.date()

                    # get date and time info regarding last time setting was set
                    last_datetime = datetime.strptime(set_time, "%d-%m-%Y, %H:%M:%S")
                    last_time = last_datetime.time()
                    last_date = last_datetime.date()

                    # loop through missed days and find the last timer
                    choose_date = current_date
                    while choose_date >= last_date:

                        choose_day = dayCodes[choose_date.weekday()]
                        found = False
                        missedTimers = []
                        counter = 0

                        if choose_date == current_date:
                            max_time = current_time
                        else:
                            max_time = time(hour=23, minute=59, second=59)

                        if choose_date == last_date:
                            min_time = last_time
                        else:
                            min_time = time(hour=0, minute=0, second=0)

                        for timer in timers:
                            timer_time = datetime.strptime(timer['time'], '%H:%M').time()
                            if (choose_day in timer['day']) and min_time < timer_time < max_time and timer['active']:
                                found = True
                                missedTimers.append(counter)
                                print(timer['id'])
                            counter += 1

                        if found:
                            latest_time = min_time
                            latest_index = -99
                            for ii in missedTimers:
                                timer_time = datetime.strptime(timers[ii]['time'], '%H:%M').time()
                                if timer_time > latest_time:
                                    latest_time = timer_time
                                    latest_index = ii
                            break

                        choose_date = choose_date - timedelta(days=1)

                    # missed timer
                    if found:
                        if timers[latest_index]['mode'].lower() == 'off':
                            set_on = False
                            set_temp = 22  # dummy value
                            set_mode = 'auto'  # dummy value
                        else:
                            set_on = True
                            set_temp = float(timers[latest_index]['temp'].strip())
                            set_mode = timers[latest_index]['mode'].strip().lower()
                        sensi = SensiboControl(api=api_key,
                                               set_temperature=set_temp,
                                               set_mode=set_mode,
                                               set_on=set_on,
                                               set_override=False,
                                               set_log=True,
                                               set_log_name="Log.txt")
                    else:  # no missed timer
                        sensi = SensiboControl(api=api_key,
                                               set_temperature=set_temp,
                                               set_mode=set_mode,
                                               set_on=set_on,
                                               set_override=True,
                                               set_log=True,
                                               set_log_name="Log.txt")
                        sensi.set_local_ac_state(local_ac_state["on"], local_ac_state["mode"],
                                                 local_ac_state["fanLevel"],
                                                 local_ac_state["targetTemperature"])
                        sensi.set_override(False)
                        sensi.check_override()
                        sensi.poll()
                except Exception as e:
                    print_and_log(
                        "Unable to connect to sensibo or db. Sensibo might be offline or api key/room name may be invalid."
                    )
                    print_and_log("Details of exception:")
                    print_and_log(repr(e))
                    return "cannot initialize sensibo"
                else:
                    # Step 2: initialize AP Scheduler with polling and timers
                    initialized = True
                    for timer in timers:
                        if timer['mode'] == 'off':
                            sched.add_job(sensi.turn_off,
                                          'cron',
                                          day_of_week=timer['day'],
                                          hour=timer['time'].split(":")[0],
                                          minute=timer['time'].split(":")[1],
                                          timezone='Israel',
                                          id=timer['id'])
                        else:
                            sched.add_job(sensi.set_temp,
                                          'cron', [float(timer['temp']), timer['mode']],
                                          day_of_week=timer['day'],
                                          hour=timer['time'].split(":")[0],
                                          minute=timer['time'].split(":")[1],
                                          timezone='Israel',
                                          id=timer['id'])
                        if not timer['active']:
                            sched.pause_job(job_id=timer['id'])

                    sched.add_job(
                        sensi.poll,
                        'cron',
                        timezone='Israel',
                        minute='0,3,6,9,12,15,18,21,24,27,30,33,36,39,42,45,48,51,54,57',
                        second=30,
                        id="main")
                    sched.start()
                    print_and_log("Initialization successful.")
                    return redirect("/")


@app.route("/startup", methods=('GET', 'POST'))
def startup():
    global initialized, api_key, sensi, temp_target, manual_shutdown
    if request.method == 'POST':
        validEntry = True
        if (request.form["api"] == 'shutdown' or request.form["mode"] == 'Shutdown') and initialized:
            for timer in timers:
                delete_timer(timer['id'])
            delete_timer('main')
            initialized = False
            sched.shutdown(wait=False)
            del sensi
            print_and_log("Shutdown")
            manual_shutdown = True
        elif not initialized:
            try:
                # Step 1: initialize sensibo controller with input api and to input setting
                print_and_log("Attempt initiation of sensibo.")
                api_key = request.form["api"]
                tempSetting = request.form["temperature"].strip()
                if tempSetting == 'override':
                    sensi = SensiboControl(api=api_key,
                                           set_temperature=22,
                                           set_on=False,
                                           set_override=True,
                                           set_log=True,
                                           set_log_name="Log.txt")
                elif tempSetting == 'off' or tempSetting == 'Off' or request.form["mode"] == 'Off':
                    sensi = SensiboControl(api=api_key,
                                           set_temperature=22,
                                           set_on=False,
                                           set_override=False,
                                           set_log=True,
                                           set_log_name="Log.txt")
                else:
                    if isfloat(tempSetting):
                        temp_target = float(tempSetting)
                        mode_set = request.form['mode'].lower()
                        sensi = SensiboControl(api=api_key,
                                               set_temperature=temp_target,
                                               set_mode=mode_set,
                                               set_on=True,
                                               set_override=False,
                                               set_log=True,
                                               set_log_name="Log.txt")
                    else:
                        validEntry = False
                        sensi = SensiboControl(api=api_key,
                                               set_temperature=22,
                                               set_on=False,
                                               set_override=True,
                                               set_log=True,
                                               set_log_name="Log.txt")
                        error = "Invalid temperature entry. Set to override=true."
            except Exception as e:
                print_and_log(
                    "Unable to connect to sensibo. Sensibo is offline or api key/room name may be invalid."
                )
                print_and_log("Details of exception:")
                print_and_log(repr(e))
                return render_template('Startup.html.jinja')
            else:
                # Step 2: initialize AP Scheduler with polling and timers
                initialized = True
                manual_shutdown = False
                for timer in timers:
                    if timer['mode'] == 'off':
                        sched.add_job(sensi.turn_off,
                                      'cron',
                                      day_of_week=timer['day'],
                                      hour=timer['time'].split(":")[0],
                                      minute=timer['time'].split(":")[1],
                                      timezone='Israel',
                                      id=timer['id'])
                    else:
                        sched.add_job(sensi.set_temp,
                                      'cron', [float(timer['temp']), timer['mode']],
                                      day_of_week=timer['day'],
                                      hour=timer['time'].split(":")[0],
                                      minute=timer['time'].split(":")[1],
                                      timezone='Israel',
                                      id=timer['id'])
                    if not timer['active']:
                        sched.pause_job(job_id=timer['id'])

                sched.add_job(
                    sensi.poll,
                    'cron',
                    timezone='Israel',
                    minute='0,3,6,9,12,15,18,21,24,27,30,33,36,39,42,45,48,51,54,57',
                    second=30,
                    id="main")
                sched.start()
                # process input
                if validEntry == True:
                    print_and_log("Initialization successful.")
                    # return redirect("/")
                    return redirect(url_for('main'))
                else:
                    print_and_log(
                        "Initialization complete with invalid setting entry. Setting set to override."
                    )
                    flash(error)
    return render_template('Startup.html.jinja')


@app.route("/api")
def api():
    global sensi
    if initialized:
        try:
            frmTemp = request.args.get('temp')
            frmMode = request.args.get('mode').lower()
            if frmTemp.lower() == "off" or frmMode == "off":
                sensi.turn_off()
                return "Success"
            elif isfloat(frmTemp) and frmMode in ("cool", "auto", "heat"):
                sensi.set_temp(float(frmTemp), set_mode=frmMode)
                return "Success"
            else:
                return "Invalid entry"
        except Exception:
            return "Error"
    else:
        return "sensibo not initialized"


@app.route("/api/off")
def api_off():
    global sensi
    if initialized:
        try:
            sensi.turn_off()
            return "Success"
        except Exception:
            return "Error"
    else:
        return "sensibo not initialized"


def delete_timer(TimerID):
    global sched
    sched.remove_job(TimerID)


def add_timer(timer):
    global sched
    if timer['mode'] == 'off':
        sched.add_job(sensi.turn_off,
                      'cron',
                      day_of_week=timer['day'],
                      hour=timer['time'].split(":")[0],
                      minute=timer['time'].split(":")[1],
                      timezone='Israel',
                      id=timer['id'])
    else:
        sched.add_job(sensi.set_temp,
                      'cron', [float(timer['temp']), timer['mode']],
                      day_of_week=timer['day'],
                      hour=timer['time'].split(":")[0],
                      minute=timer['time'].split(":")[1],
                      timezone='Israel',
                      id=timer['id'])
    if not timer['active']:
        sched.pause_job(job_id=timer['id'])


def write_timer(timers):
    try:
        fileReader2 = open("Timers.txt", 'w')
        for timer in timers:
            fileReader2.write(timer['time'] + "; " + timer['day'] + "; " +
                              timer['temp'] + "; " + timer['mode'] + "; " +
                              str(timer['active']) + "; " + timer['id'] + ";" +
                              "\n")
        fileReader2.close()
    except Exception as e:
        print_and_log(
            "Error updating timer file. "
            "Possible discrepancy may exist between timer file and internal timer variable."
        )


def isfloat(num):
    try:
        float(num)
        return True
    except ValueError:
        return False

# if __name__ == "__main__":
# app = create_app()
#  app.run(debug=True)
