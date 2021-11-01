import pygame, os, requests
from pygame.locals import *

code = ""
displayCode = ""
alarmStatus = "loading..."
inactivityTime = 0

def reloadStatus():
    global alarmStatus
    try:
        r = requests.get('http://192.168.178.10:8081/get_status');
        alarmStatus = r.text
    except Exception as err:
        print(f'Error occured: {err}')
        alarmStatus = "malfunction"
    if (alarmStatus == "armed_away" or alarmStatus == "armed_home"):
        alarmStatus = "armed"

def sendCode():
    global code
    global displayCode
    global successSound
    try:
        r = requests.get('http://192.168.178.10:8081/code/'+code);
        if (r.status_code == 200):
            successSound.play()
    except Exception as err:
        print(f'Error occured: {err}')
    code = ""
    displayCode = ""


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
        sendCode()
    elif len(code) < 5:
        buttonSound.play()
        code = code + key
        displayCode = displayCode + "*"
    else:
        buttonErrorSound.play()

class SpriteObject(pygame.sprite.Sprite):
    def __init__(self, x, y, _buttonText):
        super().__init__() 
        self.buttonText = _buttonText
        color = (100, 100, 0)
        font = pygame.font.Font(os.path.join('SQR721BE.TTF'), 80)
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
            if event.type == pygame.MOUSEBUTTONDOWN:
                if self.rect.collidepoint(event.pos):
                    self.clicked = True
                    handleInput(self.buttonText)

        self.image = self.click_image if self.clicked else self.original_image

os.environ["SDL_VIDEODRIVER"] = "x11"

pygame.mixer.pre_init(44100, -16, 2, 1024)
pygame.mixer.init()
pygame.init()
pygame.mouse.set_cursor((8,8),(0,0),(0,0,0,0,0,0,0,0),(0,0,0,0,0,0,0,0))
pygame.display.set_caption('keypad')
window = pygame.display.set_mode()
clock = pygame.time.Clock()

keypad_x = 850
keypad_y = 150
group = pygame.sprite.Group([
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
])

run = True
font = pygame.font.Font(os.path.join('SQR721BE.TTF'), 80)
buttonSound = pygame.mixer.Sound("button.wav")
buttonErrorSound = pygame.mixer.Sound("buttonerror.wav")
successSound = pygame.mixer.Sound("success.wav")
reloadCounter = 0
while run:
    reloadCounter = reloadCounter + 1
    if reloadCounter == 1:
        reloadStatus()
    if reloadCounter > 40:
        reloadCounter = 0

    if inactivityTime < 300:
        inactivityTime = inactivityTime + 1
        clock.tick(30)
    else:
        clock.tick(5)

    for sprite in group.sprites():
        sprite.reset()
    event_list = pygame.event.get()
    for event in event_list:
        if event.type == pygame.QUIT:
            run = False 

    group.update(event_list)

    window.fill(0)
    group.draw(window)
    if len(code) > 0:
        pygame.draw.rect(window, (0,255,0), Rect(190,95,310,85), 4)
        codeImg = font.render(displayCode, True, (0,255,0))
        window.blit(codeImg, (200, 100))


    if (alarmStatus == "armed"):
        statusImg = font.render(alarmStatus, True, (255,0,0))
        window.blit(statusImg, (175, 300))
    elif (alarmStatus == "malfunction"):
        statusImg = font.render(alarmStatus, True, (255,0,0))
        window.blit(statusImg, (70, 300))
    else:
        statusImg = font.render(alarmStatus, True, (0,255,0))
        window.blit(statusImg, (110, 300))

    pygame.display.flip()

pygame.quit()
exit()
