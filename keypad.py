import pygame, os, requests, time, string, glob, struct, urllib, cv2, numpy, logging, json, random, pytz, io
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pygame.locals import *
from _thread import start_new_thread
from threading import Thread, current_thread
try:
  from urlparse import urlparse
except ImportError:
  from urllib.parse import urlparse

#useCustomTouchscreenHandling = True
#useX11 = False
#hideMouseCursor = True
#fixedSizeWindow = False

useCustomTouchscreenHandling = False  # Set to true if you run a raspi with touchscreen and need custom handling for correct coordinates in framebuffer mode.
useX11 = False # Set to true to force X11 graphics
hideMouseCursor = False # Set to true for touchscreens
fixedSizeWindow = True # Set to true if you run in a window manager and want to force the window size. Use False if you use framebuffer

firstFloorMode = False # Set to true if you want special handling for arming/disarming the alarm system
weatherOnlyMode = False # Set to true if you ONLY want the weather page to be displayed
useLocalStation = False # Set to true if you want to directly fetch data from a local EcoWitt weather station

touchDebug = False
loadStreamOnStart = False

localTimezone = pytz.timezone('Europe/Vienna')
tempangle = 0
weatherDisplayActive = False
code = ""
displayCode = ""
alarmStatus = "loading..."
inactivityTime = 0
e_battery = '0'
e_pv = '0'
e_use = '0'
e_grid = '0'
e_battuse = '0'
e_curtime = '0'
e_curdate = '0'
animationOffset = 0
maxAnimationOffset = 300
energyServerAddress = "http://192.168.178.11"
weatherServerAddress = "https://167dgn.airforce/query"
localWeatherStationAddress = "http://GW200X-WH268X.fritz.box/get_livedata_info"

device_file = '/dev/hidraw0'
packet_length = 56

videoFeed = False
font = False
weatherData = False
localWeatherData = False
hist_pv = False
hist_grid = False
hist_use = False
hist_battuse = False
lastCustomEvent = False
forceSwitchVideo = False
mapImages = []
mapBackground = False
lastMapLoadAttempt = 0
localWeatherData = {}

class mapImage:
    def __init__(self, image, timestamp, renderTimestamp):
        self.image = image
        self.timestamp = timestamp
        self.renderTimestamp = renderTimestamp
    
def sortByTimestamp(element):
    return int(element.timestamp)

def serve_forever(httpd):
    with httpd:
        httpd.serve_forever()

class ringRequestHandler(BaseHTTPRequestHandler):
  def log_request(self, *args):
    return
  def do_GET(self):
    global forceSwitchVideo
    request_path = urlparse(self.path).path
    #print('Request path: ' + request_path)
    responsecode = 200
    responsemessage = 'Succcess';
    if (request_path == '/ring'):
        forceSwitchVideo = True
    # Send response
    self.send_response(responsecode)
    self.send_header('Content-type','text/html')
    self.end_headers()
    self.wfile.write(bytes(responsemessage, "utf8"))


def reloadStatus():
    global alarmStatus
    try:
        r = requests.get('http://192.168.178.11:8081/get_status');
        alarmStatus = r.text
    except Exception as err:
        print(f'Error occured: {err}')
        alarmStatus = "malfunction"
    if (alarmStatus == "armed_away" or alarmStatus == "armed_home"):
        alarmStatus = "armed"

def sendCode(quietMode = False):
    global code
    global displayCode
    global successSound
    try:
        r = False
        if (quietMode == False):
            r = requests.get('http://192.168.178.11:8081/code/'+code);
        else:
            r = requests.get('http://192.168.178.11:8081/codeQuiet/'+code);
        if (r.status_code == 200):
            successSound.play()
    except Exception as err:
        print(f'Error occured: {err}')
    code = ""
    displayCode = ""

def getSOC():
    global energyServerAddress, e_battery, e_pv, e_use, e_grid, e_battuse, e_curtime, e_curdate
    try:
        r = requests.get(energyServerAddress + '/status/soc.txt');
        energyStatus = r.text.split('\n')
        e_battery = energyStatus[0]
        e_pv = energyStatus[1]
        e_use = energyStatus[2]
        if e_use == '-0':
            e_use = '0'
        e_grid = energyStatus[3]
        e_battuse = energyStatus[4]
        if e_battuse == '-0':
            e_battuse = '0'
        e_curtime = energyStatus[5]
        e_curdate = energyStatus[6]
    except Exception as err:
        print(f'Error occured: {err}')

def getHistograms():
    global hist_pv, hist_grid, hist_use, hist_battuse, energyServerAddress
    try:
        r = requests.get(energyServerAddress + '/status/lastpv.txt');
        hist_pv = r.text.split('\n')
        r = requests.get(energyServerAddress + '/status/lastgrid.txt');
        hist_grid = r.text.split('\n')
        r = requests.get(energyServerAddress + '/status/lastuse.txt');
        hist_use = r.text.split('\n')
        r = requests.get(energyServerAddress + '/status/lastbattuse.txt');
        hist_battuse = r.text.split('\n')
    except Exception as err:
        print(f'Error in Histograms: {err}')

def getWeather():
    global weatherData, weatherServerAddress
    try:
        r = requests.get(weatherServerAddress);
        weatherData = json.loads(r.text)
    except Exception as err:
        print(f'Error in weather data: {err}')

def isfloat(num):
    try:
        float(num)
        return True
    except ValueError:
        return False

def getLocalWeather():
    global localWeatherData, localWeatherStationAddress
    try:
#        print("Query local weather")
        r = requests.get(localWeatherStationAddress);
        localData = json.loads(r.text)
#        print(r.text)
#        localWeatherData = {}
        for data in localData["common_list"]:
            if (data["id"] == "0x02" and isfloat(data["val"])):
                localWeatherData["curtemperature"] = float(data["val"])
            if (data["id"] == "0x0B" and isfloat(data["val"].split()[0])):
                localWeatherData["curwindspeed"] = float(data["val"].split()[0])
            if (data["id"] == "0x0C" and isfloat(data["val"].split()[0])):
                localWeatherData["curwindgust"] = float(data["val"].split()[0])
            if (data["id"] == "0x0A" and isfloat(data["val"])):
                localWeatherData["curwinddir"] = int(data["val"])
    except Exception as err:
        print(f'Error in local weather data: {err}')



def handleTouchscreen():
    global lastCustomEvent, touchDebug
    previousClickedState = False
    while True:
        try:
            with open(device_file, 'rb') as f:
                while True:
                    packet = f.read(packet_length)
                    if (touchDebug == True):
                        print("Received: %s" %(packet.hex()))
                    (tag, clicked, x, y) = struct.unpack_from('<c?HH', packet)
                    if (clicked == True and previousClickedState == False):
                        previousClickedState = True
                        if (touchDebug == True):
                            print("Pressed X=%d Y=%d" % (x, y))
                        lastCustomEvent = pygame.event.Event(pygame.JOYBUTTONDOWN, {'pos': (x, y), 'button': 1})
                    elif (clicked == False and previousClickedState == True):
                        previousClickedState = False
                        if (touchDebug == True):
                            print("Released X=%d Y=%d" % (x, y))
                        lastCustomEvent = pygame.event.Event(pygame.JOYBUTTONUP, {'pos': (x, y), 'button': 1})
                    time.sleep(0.01)

        except Exception as err:
            print(f'Error occured: {err}')


def handleInput(key):
    global code
    global displayCode
    global buttonSound
    global buttonErrorSound
    global inactivityTime
    inactivityTime = 0
    if key == "C":
        buttonSound.play()
        code = ""
        displayCode = ""
    elif key == "E":
        buttonSound.play()
        sendCode(firstFloorMode)
    elif len(code) < 5:
        buttonSound.play()
        code = code + key
        displayCode = displayCode + "*"
    else:
        buttonErrorSound.play()

def drawHorizontalPowerAnimation(window, startx, starty, endx, endy, num_dots, dir, animationOffset, maxAnimationOffset):
    if (dir == 0):
        x = 0;
        while (x < (endx - startx)):
            if (x == animationOffset or (num_dots > 1 and x == animationOffset - 20) or (num_dots > 2 and x == animationOffset - 40) or (num_dots > 3 and x == animationOffset - 60) ):
                for i in range(10):
                    if (x < (endx - startx)):
                        pygame.draw.line(window, (255,255,255), (x+startx, starty), (x+startx, endy), 1)
                    x += 1
            else:
                x += 1
    else:
        x = (endx - startx)
        while (x > 0):
            if (x == (maxAnimationOffset-animationOffset) or (num_dots > 1 and x == (maxAnimationOffset-animationOffset) - 20) or (num_dots > 2 and x == (maxAnimationOffset-animationOffset) - 40) or (num_dots > 3 and x == (maxAnimationOffset-animationOffset) - 60)):
                for i in range(10):
                    if (x > 0):
                        pygame.draw.line(window, (255,255,255), (x+startx, starty), (x+startx, endy), 1)
                    x -= 1
            else:
                x -= 1

def drawVerticalPowerAnimation(window, startx, starty, endx, endy, num_dots, dir, animationOffset, maxAnimationOffset):
    if (dir == 0):
        y = 0;
        while (y < (endy - starty)):
            if (y == animationOffset or (num_dots > 1 and y == animationOffset - 20) or (num_dots > 2 and y == animationOffset - 40) or (num_dots > 3 and y == animationOffset - 60) ):
                for i in range(10):
                    if (y < (endy - starty)):
                        pygame.draw.line(window, (255,255,255), (startx, y+starty), (endx, y+starty))
                    y += 1
            else:
                y += 1
    else:
        y = (endy - starty)
        while (y > 0):
            if (y == (maxAnimationOffset-animationOffset) or (num_dots > 1 and y == (maxAnimationOffset-animationOffset) - 20) or (num_dots > 2 and y == (maxAnimationOffset-animationOffset) - 40) or (num_dots > 3 and y == (maxAnimationOffset-animationOffset) - 60)):
                for i in range(10):
                    if (y > 0):
                        pygame.draw.line(window, (255,255,255), (startx, y+starty), (endx, y+starty))
                    y -= 1
            else:
                y -= 1

def printCentered(window, msg, color, x, y):
    et = smallFont.render(msg, True, color)
    width = len(msg) * 20
    window.blit(et, (x- (width / 2), y))

def printCenteredBig(window, msg, color, x, y):
    et = bigFont.render(msg, True, color)
    width = len(msg) * 70
    window.blit(et, (x- (width / 2), y))

def getDrawColor(color):
    if color == "red":
        return (255,0,0)
    elif color == "green":
        return (0,255,0)
    elif color == "blue":
        return (50,50,255)
    elif color == "yellow":
        return (255,200,0)
    if color == "white":
        return (200, 200, 200)
    if color == "black":
        return (0, 0, 0)
    return (100,100,100)

def getDrawGradientColor(color, gradient):
    if color == "red":
        return (gradient,0,0)
    elif color == "green":
        return (0,gradient,0)
    elif color == "blue":
        return (0,0,gradient)
    elif color == "purple":
        return (gradient,0,gradient)
    elif color == "yellow":
        return (gradient,gradient,0)
    elif color == "white":
        return (gradient,gradient,gradient)
    return (gradient, gradient, gradient)


def drawHistogram(window, values, color, xpos, ypos, maxValueStart = 0.0, drawEnergyBackflow = False):
    pygame.draw.rect(window, (100,100,100), Rect(xpos-2,ypos-2,135,56), 1)
    minValue = 0.001
    maxValue = 0.001
    if values != False:
        for i, line in enumerate(values):
            if (line != ''):
                v = float(line)
                if v > maxValue:
                    maxValue = v
                if v < minValue:
                    minValue = v
        if maxValueStart != 0.0:
            maxValue = maxValueStart
        if (drawEnergyBackflow == True):
            if abs(minValue) > maxValue:
                maxValue = abs(minValue)

        #Draw gradient
        for i, line in enumerate(values):
            if (line != ''):
                v = float(line)/maxValue
                if (drawEnergyBackflow == False):
                    pygame.draw.line(window, getDrawGradientColor(color, 70+(i/1.5)), (xpos+i, ypos+(50-50*v)), (xpos+i, ypos + 50))
                else:
                    c = color
                    if (color == "blue") and (v > 0.0):
                        c = "purple"
                    elif (color == "red") and (v < 0.0):
                        c = "yellow"
                    pygame.draw.line(window, getDrawGradientColor(c, 70+(i/1.5)), (xpos+i, ypos+(25-25*v)), (xpos+i, ypos + 25))

        #Draw curve
        prevValue = False
        for i, line in enumerate(values):
            if (line != ''):
                v = float(line)/maxValue
                if prevValue != False:
                    if (drawEnergyBackflow == False):
                        pygame.draw.line(window, getDrawColor(color), (xpos+i, ypos+(50-50*v)), (xpos+i-1, ypos + (50-50*prevValue)))
                    else:
                        pygame.draw.line(window, getDrawColor(color), (xpos+i, ypos+(25-25*v)), (xpos+i-1, ypos + (25-25*prevValue)))
                prevValue = v
                    
        if (drawEnergyBackflow == False):
            et = tinyFont.render(str(round(minValue/1000, 2)), True, getDrawColor(color))
        else:
            et = tinyFont.render("-" + str(round(maxValue/1000, 2)), True, getDrawColor(color))
        window.blit(et, (xpos + 140, ypos + 40))
        et = tinyFont.render(str(round(maxValue/1000, 2)), True, getDrawColor(color))
        window.blit(et, (xpos + 140, ypos-6))

def displayVideo():
    global lastCustomEvent, useCustomTouchscreenHandling, videoFeed, buttonSound, loadStreamOnStart
    if (videoFeed == False or videoFeed.isOpened() != True):
        window.fill(0)
        pygame.draw.rect(window, (0, 0, 255), Rect(300,310,750,140), 2)
        printCenteredBig(window, 'Loading...', (100,100,255), 685, 320)
        pygame.display.flip()
        videoFeed = cv2.VideoCapture("rtsp://192.168.178.107:554/stream=0")
    keepRunning = True
    lastCustomEvent = False
    buttonIsReleased = False
    startTime = time.time()
    while(videoFeed.isOpened() and keepRunning):
        currentTime = time.time()
        if (currentTime - startTime > 300):
            keepRunning = False

        clock.tick(30)
        ret, frame = videoFeed.read()
        frame=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
        frame=numpy.rot90(frame)
        frame=numpy.flipud(frame)
        frame=pygame.surfarray.make_surface(frame)
        window.fill(0)
        window.blit(frame, (40,20))
        pygame.display.flip()
        event_list = pygame.event.get()
        if (useCustomTouchscreenHandling == True and lastCustomEvent != False):
            event_list.append(lastCustomEvent)
        eventActive = False
        for event in event_list:
            if (useCustomTouchscreenHandling == False and event.type == pygame.MOUSEBUTTONDOWN) or (useCustomTouchscreenHandling == True and event.type == pygame.JOYBUTTONDOWN):
                eventActive = True
        if (eventActive == False):
            buttonIsReleased = True
        if (eventActive == True and buttonIsReleased == True):
            keepRunning = False
    buttonSound.play()
    lastCustomEvent = False
    if (loadStreamOnStart == False):
        videoFeed.release()

def drawEnergyStatus(window, energypos_x, energypos_y):
    global energyImage, e_battery, e_pv, e_use, e_battuse, hist_pv, hist_use
    window.blit(energyImage, (energypos_x, energypos_y))
    barHeightMax = 169
    barHeight = barHeightMax * (float(e_battery) / 100.0)
    window.fill((0,0,255), Rect(energypos_x+16,energypos_y+163+barHeightMax-barHeight,64,barHeight))
    printCentered(window, e_battery+'%', (255, 255, 255), energypos_x+46, energypos_y+220)
    et = smallFont.render(e_pv+'kW', True, (255,255,0))
    window.blit(et, (energypos_x+400, energypos_y-15))
    et = smallFont.render(e_use+'kW', True, (0,255,0))
    window.blit(et, (energypos_x+400, energypos_y+380))

    printCentered(window, e_grid+'kW', (255, 0, 0), energypos_x+440, energypos_y+290)
    printCentered(window, e_battuse+'kW', (10, 10, 255), energypos_x+190, energypos_y+290)


    drawHistogram(window, hist_pv, "yellow", energypos_x+400, energypos_y+30, 7800, False)
    drawHistogram(window, hist_use, "green", energypos_x+400, energypos_y+425, 0.0, False)
    drawHistogram(window, hist_grid, "red", energypos_x+520, energypos_y+310, 0.0, True)
    drawHistogram(window, hist_battuse, "blue", energypos_x-18, energypos_y+360, 0.0, True)

    numArrows = 0
    battDirection = 0
    fval = float(e_battuse)
    window.fill((50,50,50), Rect(energypos_x+100,energypos_y+228,165,20))
    if (fval < -0.1):
        if (fval >= -0.7):
            numBattArrows = 1
        elif (fval >= -1.4):
            numBattArrows = 2
        else:
            numBattArrows = 3
        battDirection = 0
        drawHorizontalPowerAnimation(window, energypos_x+100, energypos_y+228, energypos_x+265, energypos_y+248, numBattArrows, battDirection, animationOffset, maxAnimationOffset)
    elif (fval >= 0.1):
        if (fval <= 0.7):
            numBattArrows = 1
        elif (fval <= 1.4):
            numBattArrows = 2
        else:
            numBattArrows = 3
        battDirection = 1
        drawHorizontalPowerAnimation(window, energypos_x+100, energypos_y+228, energypos_x+265, energypos_y+248, numBattArrows, battDirection, animationOffset, maxAnimationOffset)

    fval = float(e_grid)
    window.fill((50,50,50), Rect(energypos_x+375,energypos_y+228,155,20))
    if (fval < -0.1):
        if (fval >= -0.7):
            numBattArrows = 1
        elif (fval >= -1.4):
            numBattArrows = 2
        else:
            numBattArrows = 3
        battDirection = 0
        drawHorizontalPowerAnimation(window, energypos_x+375, energypos_y+228, energypos_x+530, energypos_y+248, numBattArrows, battDirection, animationOffset, maxAnimationOffset)
    elif (fval > 0.1):
        if (fval <= 0.7):
            numBattArrows = 1
        elif (fval <= 1.4):
            numBattArrows = 2
        else:
            numBattArrows = 3
        battDirection = 1
        drawHorizontalPowerAnimation(window, energypos_x+375, energypos_y+228, energypos_x+530, energypos_y+248, numBattArrows, battDirection, animationOffset, maxAnimationOffset)

    fval = float(e_pv)
    window.fill((50,50,50), Rect(energypos_x+310,energypos_y+85,20,100))
    if (fval <= -0.1):
        if (fval >= -0.7):
            numBattArrows = 1
        elif (fval >= -1.4):
            numBattArrows = 2
        else:
            numBattArrows = 3
        battDirection = 1
        drawVerticalPowerAnimation(window, energypos_x+310, energypos_y+85, energypos_x+330, energypos_y+185, numBattArrows, battDirection, animationOffset, maxAnimationOffset)
    elif (fval >= 0.1):
        if (fval <= 0.7):
            numBattArrows = 1
        elif (fval <= 1.4):
            numBattArrows = 2
        else:
            numBattArrows = 3
        battDirection = 0
        drawVerticalPowerAnimation(window, energypos_x+310, energypos_y+85, energypos_x+330, energypos_y+185, numBattArrows, battDirection, animationOffset, maxAnimationOffset)

    fval = float(e_use)
    window.fill((50,50,50), Rect(energypos_x+310,energypos_y+292,20,80))
    if (fval <= -0.1):
        if (fval >= -0.7):
            numBattArrows = 1
        elif (fval >= -1.4):
            numBattArrows = 2
        else:
            numBattArrows = 3
        battDirection = 1
        drawVerticalPowerAnimation(window, energypos_x+310, energypos_y+292, energypos_x+330, energypos_y+372, numBattArrows, battDirection, animationOffset, maxAnimationOffset)
    elif (fval >= 0.1):
        if (fval <= 0.7):
            numBattArrows = 1
        elif (fval <= 1.4):
            numBattArrows = 2
        else:
            numBattArrows = 3
        battDirection = 0
        drawVerticalPowerAnimation(window, energypos_x+310, energypos_y+292, energypos_x+330, energypos_y+372, numBattArrows, battDirection, animationOffset, maxAnimationOffset)

def drawWeatherDiagram(window, title, values, values2, color, color2, xpos, ypos, size = 600, maxValueStart = 0.0):
    pygame.draw.rect(window, (100,100,100), Rect(xpos-2,ypos-2,size+5,106), 1)
    minValue = 0.001
    maxValue = 0.001
    if values != False:
        for i, line in enumerate(values):
            v = float(line)
            if v > maxValue:
                maxValue = v
            if v < minValue:
                minValue = v
        if maxValueStart != 0.0:
            maxValue = maxValueStart
        if (values2 != False):
            for i, line in enumerate(values2):
                v = float(line)
                if v > maxValue:
                    maxValue = v
                if v < minValue:
                    minValue = v
            if maxValueStart != 0.0:
                maxValue = maxValueStart

        #Draw gradient
        medianValue1 = 0
        for i, line in enumerate(values):
            v = float(line)/maxValue
            if (medianValue1 == 0):
                medianValue1 = v
            average = (v+medianValue1) / 2
            pygame.draw.line(window, getDrawGradientColor(color, 20+(i/5)), (xpos+i, ypos+(100-100*average)), (xpos+i, ypos + 100))
            medianValue1 = average

        #Draw curve
        prevValue = False
        medianValue1 = 0
        for i, line in enumerate(values):
            v = float(line)/maxValue
            if (medianValue1 == 0):
                medianValue1 = v
            average = (v+medianValue1) / 2
            if prevValue != False:
                pygame.draw.line(window, getDrawColor(color), (xpos+i, ypos+(100-100*average)), (xpos+i-1, ypos + (100-100*prevValue)))
            prevValue = average
            medianValue1 = average

        if (values2 != False):
            #Draw values2 curve
            prevValue = False
            medianValue1 = 0
            for i, line in enumerate(values2):
                v = float(line)/maxValue
                if (medianValue1 == 0):
                    medianValue1 = v
                average = (v+medianValue1) / 2
                if prevValue != False:
                    pygame.draw.line(window, getDrawColor(color2), (xpos+i, ypos+(100-100*average)), (xpos+i-1, ypos + (100-100*prevValue)))
                prevValue = average
                medianValue1 = average
                    
        et = tinyFont.render(str(round(minValue, 1)), True, getDrawColor(color))
        window.blit(et, (xpos + size + 5, ypos + 88))
        et = tinyFont.render(str(round(maxValue, 1)), True, getDrawColor(color))
        window.blit(et, (xpos + size + 5, ypos-6))
        et = tinyFont.render(title, True, getDrawColor(color))
        window.blit(et, (xpos , ypos - 20))

def drawWindrose(window, angle, speed, x, y):
    global windroseBgImage, windroseRedImage, windroseYellowImage, windroseGreenImage
    image = windroseRedImage
    if (speed < 20):
        image = windroseGreenImage
    elif (speed < 30):
        image = windroseYellowImage
    rotated_image = pygame.transform.rotate(image, 360-angle)
    new_rect = rotated_image.get_rect(center = image.get_rect(center = (x, y)).center)
    new_rect.center = (x+250, y+250)
    window.blit(windroseBgImage, (x, y))
    window.blit(rotated_image, new_rect)
    et = smallFont.render("N", True, getDrawColor("red"))
    window.blit(et, (x+245, y+15))
    et = smallFont.render("S", True, getDrawColor("black"))
    window.blit(et, (x+245, y+470))
    et = smallFont.render("W", True, getDrawColor("black"))
    window.blit(et, (x+20, y+240))
    et = smallFont.render("E", True, getDrawColor("black"))
    window.blit(et, (x+475, y+240))

def renderMap(window, frame):
    global mapBackground, mapImages, localTimezone, mediumFont, lastMapLoadAttempt
    cropWindow = (1080, 985, 690, 660)
    if (mapBackground == False):
#        r = requests.get("https://meteoradar.co.uk/content/maps/kaart-eu-tmc.png");
#        mapBackground = pygame.image.load(io.BytesIO(r.content))
        mapBackground = pygame.image.load('map.png')

    curTime = time.time()
    if (curTime - lastMapLoadAttempt > 20) :
        lastMapLoadAttempt = curTime
        # Build a list of timestamps for the images to fetch
        nowDT = datetime.now(pytz.timezone('UTC')) - timedelta(minutes=15)
        last_quarter_minute = 15 * (nowDT.minute // 15)
        stepTime = nowDT.replace(minute = last_quarter_minute)
        timestamps = []
        dts = []
        for i in range(12):
            timestamp = stepTime.strftime("%Y%m%d%H%M")
            timestamps.append(timestamp)
            dts.append(stepTime)
            stepTime = stepTime - timedelta(minutes=15)
    
        # Sort by increasing timestamp
        timestamps.reverse()
        dts.reverse()
        
        for dt in dts:
            timestamp = dt.strftime("%Y%m%d%H%M")
#           print("T: " + timestamp)
            imageIsLoaded = False
            for i in mapImages:
                if i.timestamp == timestamp:
                    imageIsLoaded = True
    
            if (imageIsLoaded == False):
                print("Image " + timestamp + " loading...")
                url = "https://api.meteoradar.co.uk/image/1.0/?time=" + timestamp + "&type=radareuropabliksem#f"
                renderTimestamp = dt.astimezone(localTimezone).strftime("%H:%M")
                daemon = Thread(target=getMapFrame, args=(url,timestamp,renderTimestamp), daemon=True, name=timestamp)
                daemon.start()
#                getMapFrame(url, timestamp, renderTimestamp);

                print("Done!")
      
        
    mapImages.sort(key=sortByTimestamp)
    # If we loaded more than 12 images, delete the oldest one
    while len (mapImages) > 12:
        mapImages.pop(0)
    window.blit(mapBackground, (50, 60), cropWindow)
    actualFrame = frame
    if (actualFrame > 11):
        actualFrame = 11
    try: 
        window.blit(mapImages[actualFrame].image, (50, 60), cropWindow)

        rect = pygame.Surface((218,58), pygame.SRCALPHA, 32)
        rect.fill((0,0,0,220))
        window.blit(rect, (515,75))

        et = mediumFont.render(mapImages[actualFrame].renderTimestamp, True, (0, 0, 0))
        window.blit(et, (522, 70))
        et = mediumFont.render(mapImages[actualFrame].renderTimestamp, True, (255, 255, 255))
        window.blit(et, (520, 68))
    except:
        print("Error rendering animation frame")

def getMapFrame(url: str, timestamp: str, renderTimestamp: str):
    global mapImages
    r = requests.get(url)
    try: 
        image = pygame.image.load(io.BytesIO(r.content)).convert_alpha()
        mapImages.append(mapImage(image, timestamp, renderTimestamp))
    except:
        print("Error loading animation frame")

def displayWeather(window):
    global lastCustomEvent, useCustomTouchscreenHandling, videoFeed, buttonSound, loadStreamOnStart, windReloadTime, useLocalStation
    global weatherData, localWeatherData, localTimezone
    global tempangle
#    if (tempangle > 360):
#        tempangle = 0
#        weatherData["curwinddir"] = random.uniform(0.0, 360.0)
#    tempangle = tempangle + 2
    keepRunning = True
    lastCustomEvent = False
    buttonIsReleased = False
    startTime = time.time()
    weatherReloadTime = 0
    displayMap = False
    mapFrame = 0
    while(keepRunning):
        currentTime = time.time()
#        if (currentTime - startTime > 300):
#            keepRunning = False

        if (currentTime - weatherReloadTime > 30):
            weatherReloadTime = currentTime
            start_new_thread(getWeather,())
        if (useLocalStation == True):
            if (currentTime - windReloadTime > 3):
                windReloadTime = currentTime
                start_new_thread(getLocalWeather,())

        clock.tick(2)
        
        if ((displayMap == True and currentTime - startTime >= 10) or (displayMap == False and currentTime - startTime >= 5)):
            displayMap = not displayMap
            startTime = currentTime
            mapFrame = 0

        if (weatherData == False):
            return
        window.fill(0)
        et = smallFont.render(datetime.now(localTimezone).strftime("%H:%M:%S"), True, (130,130,130))
        window.blit(et, (10, 10))
        x = 60
        y = 70
        if (displayMap):
            renderMap(window, mapFrame)
            mapFrame = mapFrame + 1
            if (mapFrame > 20):
                mapFrame = 0
        else:
            drawWeatherDiagram(window, "Wind km/h", weatherData["windspeeds"], weatherData["windgusts"], "white", "red", x, y)
            y += 140
            drawWeatherDiagram(window, "Temperatur °C", weatherData["temperature"], False, "green", False, x, y)
            y += 140
            drawWeatherDiagram(window, "Luftfeuchte %", weatherData["humidity"], False, "blue", False, x, y)
            y += 140
            drawWeatherDiagram(window, "Sonnenstrahlung W/m2", weatherData["solarradiation"], False, "yellow", False, x, y)
            y += 140
            drawWeatherDiagram(window, "Regen mm/h", weatherData["rain"], False, "purple", False, x, y)

        windSpeed = weatherData["curwindspeed"]
        windDirection = weatherData["curwinddir"]
        windGust = weatherData["curwindgust"]
        temperature = weatherData["curtemperature"]
        if (useLocalStation == True and localWeatherData != False and "curwindspeed" in localWeatherData):
            windSpeed = localWeatherData["curwindspeed"]
            windDirection = localWeatherData["curwinddir"]
            windGust = localWeatherData["curwindgust"]
            temperature = localWeatherData["curtemperature"]

        drawWindrose(window, windDirection, windGust, 800, 50)
        windcolor = "red"
        if windGust < 20:
            windcolor = "green"
        elif windGust < 30:
            windcolor = "yellow"
        et = mediumFont.render(f'{windGust:.1f}' + " km/h", True, getDrawColor(windcolor))
        window.blit(et, (900, 580))

        if (windGust > windSpeed + 10.0):
            et = smallFont.render(f'{windSpeed:.1f}' + " km/h Minimum", True, getDrawColor(windcolor))
            window.blit(et, (900, 645))

        et = mediumFont.render(f'{temperature:.1f}' + "°C", True, getDrawColor("white"))
        window.blit(et, (900, 680))
        pygame.display.flip()
        event_list = pygame.event.get()
        if (useCustomTouchscreenHandling == True and lastCustomEvent != False):
            event_list.append(lastCustomEvent)
        eventActive = False
        for event in event_list:
            if (useCustomTouchscreenHandling == False and event.type == pygame.MOUSEBUTTONDOWN) or (useCustomTouchscreenHandling == True and event.type == pygame.JOYBUTTONDOWN):
                eventActive = True
        if (eventActive == False):
            buttonIsReleased = True
        if (eventActive == True and buttonIsReleased == True):
            keepRunning = False
    buttonSound.play()
    lastCustomEvent = False
        
    

class CamSpriteObject(pygame.sprite.Sprite):
    def __init__(self, x, y, _buttonText):
        super().__init__() 
        global videoFont
        width = 205
        height = 80
        self.buttonText = _buttonText
        self.original_image = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(self.original_image, (0,128,0), Rect(0,0,width,height), 4)
        textSurface = videoFont.render(self.buttonText, True, (0,255,0), None)
        self.original_image.blit(textSurface, (28, 15))

        self.click_image = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(self.click_image, (0,128,0), Rect(0,0,width, height))
        textSurface2 = videoFont.render(self.buttonText, True, (0,0,0), None)
        self.click_image.blit(textSurface2, (28, 15))
        self.image = self.original_image 
        self.rect = self.image.get_rect(center = (x, y))
        self.clicked = False

    def reset(self):
       self.clicked = False
       self.image = self.original_image

    def update(self, event_list):
        global buttonSound
        for event in event_list:
            if (useCustomTouchscreenHandling == False and event.type == pygame.MOUSEBUTTONDOWN) or (useCustomTouchscreenHandling == True and event.type == pygame.JOYBUTTONDOWN):
                if self.rect.collidepoint(event.pos):
                    self.clicked = True
                    buttonSound.play()
                    displayVideo()

        self.image = self.click_image if self.clicked else self.original_image

class WeatherSpriteObject(pygame.sprite.Sprite):
    def __init__(self, x, y, _buttonText):
        super().__init__() 
        global videoFont
        width = 205
        height = 80
        self.buttonText = _buttonText
        self.original_image = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(self.original_image, (0,128,0), Rect(0,0,width,height), 4)
        textSurface = videoFont.render(self.buttonText, True, (0,255,0), None)
        self.original_image.blit(textSurface, (10, 15))

        self.click_image = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(self.click_image, (0,128,0), Rect(0,0,width, height))
        textSurface2 = videoFont.render(self.buttonText, True, (0,0,0), None)
        self.click_image.blit(textSurface2, (10, 15))
        self.image = self.original_image 
        self.rect = self.image.get_rect(center = (x, y))
        self.clicked = False

    def reset(self):
       self.clicked = False
       self.image = self.original_image

    def update(self, event_list):
        global buttonSound, weatherDisplayActive
        for event in event_list:
            if (useCustomTouchscreenHandling == False and event.type == pygame.MOUSEBUTTONDOWN) or (useCustomTouchscreenHandling == True and event.type == pygame.JOYBUTTONDOWN):
                if self.rect.collidepoint(event.pos):
                    self.clicked = True
                    buttonSound.play()
                    weatherDisplayActive = not weatherDisplayActive

        self.image = self.click_image if self.clicked else self.original_image


class SpriteObject(pygame.sprite.Sprite):
    def __init__(self, x, y, _buttonText):
        super().__init__() 
        global font
        self.fadeCounter = 0
        self.buttonText = _buttonText
        self.original_image = pygame.Surface((128, 128), pygame.SRCALPHA)
        pygame.draw.rect(self.original_image, (0,128,0), Rect(0,0,128,128), 4)
        textSurface = font.render(self.buttonText, True, (0,255,0), None)
        self.original_image.blit(textSurface, (25, 15))

        self.click_image = pygame.Surface((128, 128), pygame.SRCALPHA)
        pygame.draw.rect(self.click_image, (0,128,0), Rect(0,0,128,128))
        textSurface2 = font.render(self.buttonText, True, (0,0,0), None)
        self.click_image.blit(textSurface2, (25, 15))
        self.image = self.original_image 
        self.rect = self.image.get_rect(center = (x, y))
        self.clicked = False

    def reset(self):
       self.clicked = False
       self.image = self.original_image

    def update(self, event_list):
        global buttonSound
        for event in event_list:
            if (useCustomTouchscreenHandling == False and event.type == pygame.MOUSEBUTTONDOWN) or (useCustomTouchscreenHandling == True and event.type == pygame.JOYBUTTONDOWN):
                if self.rect.collidepoint(event.pos):
                    self.clicked = True
                    self.fadeCounter = 10
                    handleInput(self.buttonText)
        if (self.fadeCounter > 1):
            self.fadeCounter -= 1;
            self.original_image = pygame.Surface((128, 128), pygame.SRCALPHA)
            self.original_image.fill((0,self.fadeCounter*25,0), Rect(0,0,128,128))
            pygame.draw.rect(self.original_image, (0,128,0), Rect(0,0,128,128), 4)
            textSurface = font.render(self.buttonText, True, (0,255,0), None)
            self.original_image.blit(textSurface, (25, 15))
        elif (self.fadeCounter == 1):
            self.fadeCounter -= 1;
            self.original_image = pygame.Surface((128, 128), pygame.SRCALPHA)
            pygame.draw.rect(self.original_image, (0,128,0), Rect(0,0,128,128), 4)
            textSurface = font.render(self.buttonText, True, (0,255,0), None)
            self.original_image.blit(textSurface, (25, 15))

        self.image = self.click_image if self.clicked else self.original_image

if (useX11 == True):
    os.environ["SDL_VIDEODRIVER"] = "x11"
#else:
#    os.environ["SDL_VIDEODRIVER"] = "rpi"
#    os.environ["SDL_FBDEV"] = "/dev/fb0"

#pygame.mixer.pre_init(44100, -16, 2, 512)
pygame.mixer.pre_init(44100, -16, 2, 1024)
pygame.mixer.init()
pygame.init()

    
pygame.display.set_caption('keypad')

if (fixedSizeWindow == False):
    window = pygame.display.set_mode()
else:
    window = pygame.display.set_mode((1366, 768)) #Windows

if (hideMouseCursor == True):
    pygame.mouse.set_cursor((8,8),(0,0),(0,0,0,0,0,0,0,0),(0,0,0,0,0,0,0,0))

font = pygame.font.Font(os.path.join('SQR721BE.TTF'), 80)
videoFont = pygame.font.Font(os.path.join('SQR721BE.TTF'), 40)
bigFont = pygame.font.Font(os.path.join('Terminal.ttf'), 100)
mediumFont = pygame.font.Font(os.path.join('Terminal.ttf'), 60)
smallFont = pygame.font.Font(os.path.join('Terminal.ttf'), 30)
tinyFont = pygame.font.Font(os.path.join('Terminal.ttf'), 15)
buttonSound = pygame.mixer.Sound("button.wav")
buttonErrorSound = pygame.mixer.Sound("buttonerror.wav")
successSound = pygame.mixer.Sound("success.wav")
energyImage = pygame.image.load('bgcolor_big.png')
windroseBgImage = pygame.image.load('windrose_bg.png').convert_alpha()
windroseRedImage = pygame.image.load('windrose_red.png').convert_alpha()
windroseYellowImage = pygame.image.load('windrose_yellow.png').convert_alpha()
windroseGreenImage = pygame.image.load('windrose_green.png').convert_alpha()

    
clock = pygame.time.Clock()

keypad_x = 900
keypad_y = 100
codeinput_x = 250
codeinput_y = 120
energypos_x = 80
energypos_y = 140

buttonGroup1 = pygame.sprite.Group([
    SpriteObject(keypad_x, keypad_y, "1"),
    SpriteObject(keypad_x+150, keypad_y, "2"),
    SpriteObject(keypad_x+300, keypad_y, "3"),
    SpriteObject(keypad_x, keypad_y+150, "4"),
    SpriteObject(keypad_x+150, keypad_y+150, "5"),
    SpriteObject(keypad_x+300, keypad_y+150, "6"),
    SpriteObject(keypad_x, keypad_y+300, "7"),
    SpriteObject(keypad_x+150, keypad_y+300, "8"),
    SpriteObject(keypad_x+300, keypad_y+300, "9"),
    SpriteObject(keypad_x, keypad_y+450, "C"),
    SpriteObject(keypad_x+150, keypad_y+450, "0"),
    SpriteObject(keypad_x+300, keypad_y+450, "E"),
    CamSpriteObject(keypad_x+262, keypad_y+585, "Video"),
    WeatherSpriteObject(keypad_x+38, keypad_y+585, "Wetter"),
])

run = True
reloadCounter = 0
energyReloadTime = 0
histogramReloadTime = 0
weatherReloadTime = 0
windReloadTime = 0

if (loadStreamOnStart == True):
    videoFeed = cv2.VideoCapture("rtsp://192.168.178.107:554/stream=0")
if (useCustomTouchscreenHandling == True):
    start_new_thread(handleTouchscreen, ())

logging.getLogger("urllib3").setLevel(logging.WARNING)
print('starting server...')
server_address = ('0.0.0.0', 80)
httpd = HTTPServer(server_address, ringRequestHandler)
print('running server...')
#httpd.server_bind()
#httpd.server_activate()
def serve_forever(httpd):
    with httpd:
        httpd.serve_forever()

thread = Thread(target=serve_forever, args=(httpd, ))
thread.setDaemon(True)
thread.start()

framecounter = 0
while run:

    if (forceSwitchVideo == True):
        forceSwitchVideo = False
        displayVideo()
        
    if (weatherDisplayActive == True or weatherOnlyMode == True):
        weatherDisplayActive = False
        displayWeather(window)
        
    currentTime = time.time()
    if (weatherOnlyMode == False):
        if (currentTime - energyReloadTime > 10):
            energyReloadTime = currentTime
            start_new_thread(getSOC,())
        if (currentTime - histogramReloadTime > 65):
            histogramReloadTime = currentTime
            start_new_thread(getHistograms,())
    if (currentTime - weatherReloadTime > 65):
        weatherReloadTime = currentTime
        start_new_thread(getWeather,())
    if (useLocalStation == True):
        if (currentTime - windReloadTime > 3):
            windReloadTime = currentTime
            start_new_thread(getLocalWeather,())
    
    reloadCounter = reloadCounter + 1
    if (weatherOnlyMode == False):
        if reloadCounter == 1:
            start_new_thread(reloadStatus,())
    if reloadCounter > 40:
        reloadCounter = 0

#    if inactivityTime < 300:
#        inactivityTime = inactivityTime + 1
    clock.tick(30)

    framecounter = framecounter + 4
    if framecounter > 220:
         framecounter = 0

    animationOffset += 8
#    else:
#        clock.tick(10)
#        animationOffset += 30

    if (animationOffset > maxAnimationOffset):
        animationOffset = 0


    for sprite in buttonGroup1.sprites():
        sprite.reset()



    event_list = pygame.event.get()
    for event in event_list:
        if event.type == pygame.QUIT:
            run = False 

    if (useCustomTouchscreenHandling == True and lastCustomEvent != False):
        event_list.append(lastCustomEvent)
        lastCustomEvent = False


    window.fill(0)

    et = smallFont.render(str(e_curtime), True, (130,130,130))
    window.blit(et, (10, 10))

    if (weatherOnlyMode == False and weatherDisplayActive == False):
        buttonGroup1.update(event_list)
        buttonGroup1.draw(window)
        if len(code) > 0:
            pygame.draw.rect(window, (0,255,0), Rect(codeinput_x,codeinput_y,310,85), 4)
            codeImg = font.render(displayCode, True, (0,255,0))
            window.blit(codeImg, (codeinput_x+10, codeinput_y+5))


#        if (alarmStatus == "armed"):
#            pygame.draw.rect(window, (100, 0, 0), Rect(100,310,620,140), 2)
#            printCenteredBig(window, alarmStatus, (255,0,0), 410, 320)
        if (alarmStatus == "malfunction"):
            pygame.draw.rect(window, (100, 0, 0), Rect(100,310,620,140), 2)
            printCenteredBig(window, "error", (255,0,0), 410, 320)
        elif (alarmStatus != "armed" and alarmStatus != "disarmed" and alarmStatus != "alarm"):
            pygame.draw.rect(window, (0, 100, 0), Rect(100,310,620,140), 2)
            printCenteredBig(window, alarmStatus, (0,255,0), 410, 320)
        elif len(code) == 0:
            drawEnergyStatus(window, energypos_x, energypos_y)
        
        if (alarmStatus == "armed"):
            rect = pygame.Surface((618,138), pygame.SRCALPHA, 32)
            rect.fill((0,0,0,220))
            window.blit(rect, (101,311))
            pygame.draw.rect(window, (100, 100, 0), Rect(100,310,620,140), 2)
            acolor = 255 - framecounter
            if acolor < 150:
               acolor = 150 
            printCenteredBig(window, alarmStatus, (acolor,acolor,0), 410, 320)
        elif (alarmStatus == "alarm"):
            rect = pygame.Surface((618,138), pygame.SRCALPHA, 32)
            rect.fill((0,0,0,220))
            window.blit(rect, (101,311))
            pygame.draw.rect(window, (100, 0, 0), Rect(100,310,620,140), 2)
            acolor = 255
            if framecounter  < 30:
               acolor = 150 
            if framecounter > 60:
               framecounter = 0
            printCenteredBig(window, alarmStatus, (acolor,0,0), 410, 320)
    else:
        displayWeather(window)

    pygame.display.flip()

pygame.quit()
exit()
