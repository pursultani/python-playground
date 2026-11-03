# Catch the Stars!
# Move the rocket with the LEFT and RIGHT arrow keys and catch the falling stars.
# You can also click a star to pop it for a bonus. Press a key or click the page first.

import random
import time

GAME_SECONDS = 30  # how long the game lasts
STAR_CHANCE = 0.07  # chance of a new star on every tick (0.07 = 7 in 100)
STEP = 30  # how far the rocket moves for each key press
POINTS_CATCH = 1  # points for catching a star with the rocket
POINTS_CLICK = 2  # bonus points for popping a star with a click

canvas(background="#14173d")  # night sky

# A sprinkle of tiny background stars. They are just decoration.
for _ in range(60):
    Circle(random.randint(-400, 400), random.randint(-300, 300),
           radius=random.choice([1, 2, 2, 3]), color="white", opacity=random.random())

Circle(-310, -120, radius=45, color="#f4f1de", opacity=0.9)  # the moon
Rectangle(0, -300, width=800, height=60, color="#2a2d5c")  # the ground

player = Triangle(0, -255, width=90, height=70, color="#ff6b6b", title="🚀")
score_text = Text("Score: 0", -260, 255, size=44, color="white")
time_text = Text(f"Time: {GAME_SECONDS}", 290, 262, size=32, color="#ffd166")

score = 0
stars = []  # a list that remembers every star on the screen


class Star(Text):
    """A falling star. It is a Text, so it can show an emoji."""

    def __init__(self):
        super().__init__("⭐", random.randint(-350, 350), 340, size=56)
        self.speed = random.randint(4, 9)  # how many steps to fall on each tick
        self.on_click(self.pop)  # clicking THIS star runs its pop() method

    def fall(self):
        self.y -= self.speed
        self.rotation += self.speed  # spin a little while falling

    def pop(self):
        stars.remove(self)
        self.remove()  # take the star off the screen
        add_points(POINTS_CLICK)


def add_points(amount):
    global score
    score += amount
    score_text.text = f"Score: {score}"


def key_pressed(key):
    if key == "ArrowLeft":
        player.x = max(-350, player.x - STEP)  # max() stops us at the left edge
    elif key == "ArrowRight":
        player.x = min(350, player.x + STEP)  # min() stops us at the right edge


def touches_player(star):
    return abs(star.x - player.x) < 60 and abs(star.y - player.y) < 55


on_key(key_pressed)

# The game loop: every tick we make stars, move them, and check what happened.
end_time = time.time() + GAME_SECONDS
while time.time() < end_time:
    if random.random() < STAR_CHANCE:
        stars.append(Star())

    for star in list(stars):  # list() makes a copy, so we may remove stars safely
        star.fall()
        if touches_player(star):
            stars.remove(star)
            star.remove()
            add_points(POINTS_CATCH)
        elif star.y < -330:  # missed! it fell off the bottom
            stars.remove(star)
            star.remove()

    time_text.text = f"Time: {int(end_time - time.time()) + 1}"
    wait(0.03)  # pause a moment. Keys and clicks are handled here too

# The game is over: dim the sky and show the result.
time_text.text = "Time: 0"
Rectangle(0, 0, width=800, height=600, color="black", opacity=0.6)
Text(f"Game over! Score: {score}", 0, 20, size=64, color="#ffd166")
Text("Save the file to play again", 0, -50, size=28, color="white")
print("Final score:", score)

# There is no loop at the end, so the program finishes here.
