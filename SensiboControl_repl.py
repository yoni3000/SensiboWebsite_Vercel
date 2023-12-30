# the following lines are for local version.
# in repl replace with
# from replit import db
db = {'CurrentSetting': {}}

from sensibo_client import SensiboClientAPI
from Logger import Logger

# define global variables
initialize = True
last_temperature = 22  # dummy value
current_temperature = 22  # dummy value
buffer = 0.5  # delta used in temperature control feedback. OBSOLETE
buf1 = 0.7  # delta used for threshold of medium fan
buf2 = 1.2  # delta used for threshold of high fan
momentum = 0  # stores where current ac state is coming from
local_ac_state = {}  # stores what ac state setting should be from this program alone
current_ac_state = {}


# server for sensibo communication
_SERVER = 'https://home.sensibo.com/api/v2'


# ac_state = client.pod_ac_state(uid)
# self.print_and_log(ac_state)
# measurement = client.pod_measurement(uid)[0]
# self.print_and_log(measurement)

# TODO: Add logging - temperature vs. time, current setting, current ac state

class SensiboControl:

  def __init__(self,
               api,
               device_name="Main Room",
               set_temperature=23,
               set_mode='auto',
               set_on=True,
               set_override=False,
               set_log=False,
               set_log_name="",
               state_file="CurrentSetting.txt"):
    global temperature, local_ac_state, On, override, mode, logging, log_name, client, uid, logger, current_setting_file, error_off

    # set temperature setting
    temperature = set_temperature
    On = set_on
    mode = set_mode
    override = set_override
    logging = set_log
    log_name = set_log_name
    current_setting_file = state_file
    error_off = False

    if logging:
      logger = Logger(log_name)

    # initialize sensibo client
    try:
      client = SensiboClientAPI(api)
      devices = client.devices()
      uid = devices[device_name]
    except Exception as e:
      raise Exception(
        "Cannot open sensibo client...\nDetails of exception:\n" + repr(e))
    else:
      self.print_and_log("Successfully connected to sensibo")
      try:
        if not override:
          if set_on:
            self.print_and_log("Initialize to temperature: " +
                               str(temperature))
            self.set_ac_state()
          else:
            self.turn_off()
        local_ac_state = self.read_ac_state()
        self.write_setting()
      except Exception as e:
        raise Exception(e)
    return

  def set_temp(self, temp, set_mode='default'):
    global temperature, override, On, initialize, mode
    if set_mode == 'auto' or set_mode == 'heat' or set_mode == 'cool':
      mode = set_mode
    temperature = temp
    override = False
    On = True
    initialize = True
    self.print_and_log("Change temperature setting to: " + str(temperature))
    self.write_setting()
    try:
      self.set_ac_state()
    except Exception as e:
      raise Exception(e)

  def turn_off(self):
    global override, On, error_off
    override = False
    On = False
    error_off = True
    self.print_and_log("Change setting to: OFF")
    try:
      current_state = self.read_ac_state()
      client.pod_change_ac_state(uid, current_state, "on", False)
    except Exception as e:
      raise Exception("Error turning off sensibo...\nDetails of exception:\n" +
                      repr(e))
    else:
      error_off = False
      self.set_local_ac_state(False, current_state["mode"],
                              current_state["fanLevel"],
                              current_state["targetTemperature"])

    self.write_setting()

  def set_ac_state(self):
    global local_ac_state, current_ac_state
    global momentum, last_temperature, current_temperature, initialize

    off = False
    update = True
    ac_mode = 'cool'  # put in dummy value in case it is to be turned off
    fan_speed = 'high'
    last_temperature = current_temperature

    try:
      current_temperature = self.read_temperature()
      self.print_and_log("The current room temperature is:" +
                         str(current_temperature))
      distance = current_temperature - temperature
      self.print_and_log("Room temp - set temp = " + str(distance))
      temperature_target = round(temperature - distance)
      if temperature_target < 16:
        temperature_target = 16
      if temperature_target > 30:
        temperature_target = 30
      # if setting temperature for first time, use high fan speed
      if initialize:
        if mode == "auto":
          if abs(distance) <= 0.3:
            off = True
          else:
            fan_speed = "high"
            if distance > 0:
              ac_mode = "cool"
            else:
              ac_mode = "heat"
        elif mode == "heat":
          if distance >= 0:
            off = True
          else:
            fan_speed = "high"
            ac_mode = "heat"
        elif mode == "cool":
          if distance <= 0:
            off = True
          else:
            fan_speed = "high"
            ac_mode = "cool"
      else:  # if not initialize then use threshold for state change
        if ((last_temperature > temperature) &
            (current_temperature <= temperature)) or (
              (last_temperature < temperature) &
              (current_temperature >= temperature)):
          off = True
        elif (mode == "auto" or mode == "cool") & (
          ((last_temperature > temperature + buf1) &
           (current_temperature <= temperature + buf1)) or
          ((last_temperature < temperature + buf1) &
           (current_temperature >= temperature + buf1))):
          fan_speed = "medium"
          ac_mode = "cool"
        elif (mode == "auto" or mode == "heat") & (
          ((last_temperature < temperature - buf1) &
           (current_temperature >= temperature - buf1)) or
          ((last_temperature > temperature - buf1) &
           (current_temperature <= temperature - buf1))):
          fan_speed = "medium"
          ac_mode = "heat"
        elif (mode == "auto" or mode == "cool") & (
          ((last_temperature > temperature + buf2) &
           (current_temperature <= temperature + buf2)) or
          ((last_temperature < temperature + buf2) &
           (current_temperature >= temperature + buf2))):
          fan_speed = "high"
          ac_mode = "cool"
        elif (mode == "auto" or mode == "heat") & (
          ((last_temperature < temperature - buf2) &
           (current_temperature >= temperature - buf2)) or
          ((last_temperature > temperature - buf2) &
           (current_temperature <= temperature - buf2))):
          fan_speed = "high"
          ac_mode = "heat"
        else:
          update = False

      if update:
        if off:
          new_state = self.read_ac_state(
          )  # when turning off must input with current_ac_state because other parameters are ignored. Otherwise a false override could occur.
          new_state["on"] = False
        else:
          new_state = {
            "on": True,
            "mode": ac_mode,
            "fanLevel": fan_speed,
            "targetTemperature": temperature_target
          }
        self.print_and_log("Setting AC to state:" + str(new_state))
        self.adjust_ac(new_state)
        local_ac_state = new_state
        self.write_setting()
      initialize = False
    except Exception as e:
      raise Exception("Error adjusting AC state...\nDetails of exception:\n" +
                      repr(e))

  def set_local_ac_state(self, on, mode, fanLevel, targetTemperature):
    global local_ac_state
    local_ac_state = {
      "on": on,
      "mode": mode,
      "fanLevel": fanLevel,
      "targetTemperature": targetTemperature
    }
    self.write_setting()

  def adjust_ac(self, new_state):
    try:
      current_state = self.read_ac_state()
      if current_state != new_state:
        new_state["temperatureUnit"] = "C"
        client.pod_change_ac_state2(uid, {"acState": new_state})
        new_state.pop("temperatureUnit")
    except Exception as e:
      raise Exception(e)

  def get_current_setting(self):
    if On:
      set_temp = temperature
    else:
      set_temp = 'off'
    current_setting = {
      'temperature': set_temp,
      'mode': mode,
      'override': override
    }
    return current_setting

  def check_override(self):
    global override
    self.print_and_log("Check override...")
    self.print_and_log("current state:" + str(self.read_ac_state()))
    self.print_and_log("local state:" + str(local_ac_state))
    try:
      if override == False:
        if self.read_ac_state() == local_ac_state:
          override = False
        else:
          override = True
    except Exception as e:
      raise Exception("Error checking override:\n" + repr(e))
    else:
      self.print_and_log("Override=" + str(override))
      self.write_setting()
      return override

  def set_override(self, status):
    global override
    override = status
    self.write_setting()

  def read_ac_state(self):
    # global ac_state
    global current_ac_state
    try:
      ac_state = client.pod_ac_state(uid)
      client.pod_change_ac_state(uid, ac_state, "temperatureUnit", "C")
      ac_state = client.pod_ac_state(uid)
    except Exception as e:
      raise Exception("Error reading AC state...\nDetails of exception:\n" +
                      repr(e))
    else:
      current_ac_state = {
        "on": ac_state['on'],
        "mode": ac_state['mode'],
        "fanLevel": ac_state['fanLevel'],
        "targetTemperature": ac_state['targetTemperature']
      }
      return current_ac_state

  def read_temperature(self):
    # code here to read from sensibo and pass temperature as number (and worry about units)
    try:
      measure = client.pod_measurement(uid)[0]
    except Exception as e:
      raise Exception("Error reading temperature...\nDetails of exception:\n" +
                      repr(e))
    else:
      return measure['temperature']

  def write_setting(self):
    global temperature, On, mode, override, local_ac_state
    db['CurrentSetting'] = {
      'temp': temperature,
      'mode': mode,
      'on': On,
      'override': override,
      'local_ac_state': local_ac_state,
      'datetime': logger.timestamp()
    }

  def poll(self):
    try:
      if On:
        if self.check_override() == False:
          self.set_ac_state()
      elif error_off:
        if self.check_override() == False:
          self.turn_off()
    except Exception as e:
      self.print_and_log("Error in poll...\nDetails of exception:\n" + repr(e))

  def print_and_log(self, message):
    global logging, logger
    message = str(message)
    print(message)
    if logging:
      logger.log(message)
