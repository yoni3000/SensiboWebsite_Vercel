fileReader = open("Timers.txt")
timersContents = fileReader.readlines()
fileReader.close()
timers = {}
for timerLine in timersContents:
    timerLineData = [x.strip() for x in timerLine.split(';')]
    timers[timerLineData[5]]={
        'time': timerLineData[0],
        'day': timerLineData[1],
        'temp': timerLineData[2],
        'mode': timerLineData[3],
        'active': timerLineData[4],
    }
id= 'soZq'
timers.pop(id)

print(timers)