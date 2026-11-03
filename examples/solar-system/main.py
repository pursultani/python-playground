# Solar System
# A view of our planets going round the Sun, seen from high above.
# Press the G key to show or hide a grid and the axes.

import math
import random

# Deep space: a very dark blue.
canvas(background="#0b1026")

# One dictionary for each planet. Change the numbers to design your own planets!
#   distance = how far from the Sun, size = the planet's radius,
#   speed = how many degrees it moves every tick, angle = where it starts.
planets = [
    {"name": "Mercury", "distance": 62, "size": 11, "color": "#c2b6a8", "speed": 3.0, "angle": 40},
    {"name": "Venus", "distance": 102, "size": 15, "color": "#f2c47c", "speed": 2.1, "angle": 200},
    {"name": "Earth", "distance": 145, "size": 17, "color": "#5fb6ff", "speed": 1.5, "angle": 100},
    {"name": "Mars", "distance": 188, "size": 13, "color": "#ef6b4a", "speed": 1.1, "angle": 300},
    {"name": "Jupiter", "distance": 232, "size": 24, "color": "#e3b07e", "speed": 0.6, "angle": 90},
    {"name": "Saturn", "distance": 273, "size": 19, "color": "#f0dc96", "speed": 0.4, "angle": 20},
]


def orbit(distance, angle):
    """Find a spot on a circle around the middle of the canvas."""
    radians = math.radians(angle)  # cos and sin want radians, not degrees
    return distance * math.cos(radians), distance * math.sin(radians)


# A sprinkle of tiny stars. Each one is a little circle in a random place.
for _ in range(60):
    star = Circle(random.randint(-390, 390), random.randint(-290, 290))
    star.radius = random.choice([1, 1, 1.5, 2])
    star.color = "white"
    star.opacity = random.choice([0.3, 0.5, 0.8])

# Faint orbit paths: big see-through discs stacked on top of each other.
# We draw the biggest first, so every orbit gets a soft edge.
for planet in reversed(planets):
    Circle(radius=planet["distance"], color="white", opacity=0.04)

# The Sun has two glowing circles behind it.
Circle(radius=58, color="#ff9f1c", opacity=0.18)
Circle(radius=46, color="#ffb627", opacity=0.3)
sun = Circle(radius=36, color="#ffd23f", title="Sun")

# Make the planets with a loop. Each planet remembers its own shape.
for planet in planets:
    planet["shape"] = Circle(
        radius=planet["size"],
        color=planet["color"],
        title=planet["name"],
        name=planet["name"],
    )

# Earth gets a moon, a tiny grey circle.
earth = get("Earth")
moon = Circle(radius=5, color="#dcdcdc")
moon_angle = 0

# The grid and axes start hidden. They come out when you press G.
grid = Grid(color="white", opacity=0.2)
axis = Axis(color="white", opacity=0.5)
grid.hide()
axis.hide()
Text("Press G for the grid", -290, 278, size=16, color="#8e9ac4")


def key_pressed(key):
    # The grid and axes swap between hidden and shown.
    if key == "g" or key == "G":
        grid.visible = not grid.visible
        axis.visible = not axis.visible


on_key(key_pressed)

# Every tick, move each planet a little further round its orbit.
while True:
    for planet in planets:
        planet["angle"] += planet["speed"]
        planet["shape"].x, planet["shape"].y = orbit(planet["distance"], planet["angle"])

    # The moon circles the Earth, so we add Earth's position to its own.
    moon_angle += 6
    around_x, around_y = orbit(32, moon_angle)
    moon.x = earth.x + around_x
    moon.y = earth.y + around_y

    wait(0.03)  # also lets the G key do its job
