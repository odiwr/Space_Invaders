import pygame
from pygame import mixer
from pygame.locals import *
import random
import sys
import pygame
import sys

# ---------------------------
# Pygame initialization
# ---------------------------
pygame.mixer.pre_init(44100, -16, 2, 512)  # Preconfigure audio: sample rate, bit depth, channels, buffer
mixer.init()                               # Start pygame's sound mixer so sounds work
pygame.init()                              # Initialize all imported pygame modules

# ---------------------------
# Basic window / timing setup
# ---------------------------
clock = pygame.time.Clock()  # Clock object to control FPS
FPS = 60                     # Target frames per second

# We'll run in 4:3 aspect ratio, classic arcade style
SCREEN_W = 800
SCREEN_H = 600
screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))  # Main game surface
pygame.display.set_caption("Space Invaders")            # Window title

# ---------------------------
# Font loading helper
# ---------------------------
def load_pixel_font(size):
    """
    Try to load a pixel-style font from img/pixel_font.ttf.
    If that fails (file missing), fall back to Courier bold.
    """
    try:
        return pygame.font.Font("img/pixel_font.ttf", size)
    except:
        return pygame.font.SysFont("Courier", size, bold=True)

# Different font sizes we'll use for UI
font16 = load_pixel_font(16)
font20 = load_pixel_font(20)
font24 = load_pixel_font(24)
font32 = load_pixel_font(32)
font48 = load_pixel_font(48)

# ---------------------------
# Load sounds
# ---------------------------
# We assume these WAV files exist in img/
explosion_fx = pygame.mixer.Sound("img/explosion.wav")   # Player bullet hits alien / UFO
explosion_fx.set_volume(0.25)

explosion2_fx = pygame.mixer.Sound("img/explosion2.wav") # Alien bullet hits player
explosion2_fx.set_volume(0.25)

laser_fx = pygame.mixer.Sound("img/laser.wav")           # Player laser fire
laser_fx.set_volume(0.25)

# ---------------------------
# Colors we'll use for drawing HUD / health
# ---------------------------
RED   = (255, 0, 0)
GREEN = (0, 255, 0)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

# ---------------------------
# Game layout / tuning constants
# ---------------------------
ROWS = 5              # number of alien rows
COLS = 7              # number of alien columns
ALIEN_COOLDOWN = 900  # ms between alien shots
UFO_COOLDOWN   = 6000 # ms between potential UFO spawns
UFO_SPEED      = 2    # UFO horizontal speed (slow, drifts across top)

PLAYER_COOLDOWN = 500 # ms between player shots
PLAYER_SPEED    = 6   # how fast player moves left/right

BULLET_SPEED_PLAYER = -6 # player bullet goes upward (negative y)
BULLET_SPEED_ALIEN  = 3  # alien bullet goes downward

# Score values for each alien sprite "type"
# alien1.png -> 10 pts, alien2.png -> 20 pts, alien3.png -> 40 pts
# alien4.png (the UFO/red saucer) -> 100 pts
POINTS_TABLE = {
    1: 10,
    2: 20,
    3: 40,
    4: 100,
}

# ---------------------------
# High-level game state machine
# ---------------------------
# We'll run the game in one of these modes at a time.
STATE_TITLE      = "title"       # point-value legend + "press enter"
STATE_DIFF       = "difficulty"  # difficulty select menu
STATE_GAME       = "game"        # active gameplay
STATE_GAMEOVER   = "gameover"    # win/lose screen

game_state = STATE_TITLE         # start on title/legend screen
game_over_reason = None          # "win" or "lose" so we can show right message

# Difficulty options
difficulties = ["EASY", "MEDIUM", "HARD"]
diff_index = 0  # 0 = EASY, 1 = MEDIUM, 2 = HARD

# Horizontal step size for alien block movement by difficulty.
# This controls how FAR the invaders move left/right each "step".
alien_move_speed_by_diff = {
    "EASY":   9,
    "MEDIUM": 12,
    "HARD":   15
}

# ---------------------------
# Background image
# ---------------------------
bg = pygame.image.load("img/bg.png")                    # background art
bg = pygame.transform.scale(bg, (SCREEN_W, SCREEN_H))   # scale bg to fit window

def draw_bg():
    """Draw the background image each frame."""
    screen.blit(bg, (0, 0))

# ---------------------------
# Text drawing helpers
# ---------------------------
def draw_text_center(text, font, color, y):
    """
    Render text centered horizontally on screen at vertical position y.
    Return rect in case we want it.
    """
    img = font.render(text, True, color)
    rect = img.get_rect(center=(SCREEN_W // 2, y))
    screen.blit(img, rect)
    return rect

def draw_text_topleft(text, font, color, x, y):
    """Render text with its top-left corner at (x, y)."""
    img = font.render(text, True, color)
    rect = img.get_rect(topleft=(x, y))
    screen.blit(img, rect)
    return rect

# ---------------------------
# Sprite groups (containers for all in-game entities)
# ---------------------------
spaceship_group     = pygame.sprite.Group()  # holds the player ship
bullet_group        = pygame.sprite.Group()  # holds player bullets
alien_group         = pygame.sprite.Group()  # holds invaders
alien_bullet_group  = pygame.sprite.Group()  # holds alien bullets
explosion_group     = pygame.sprite.Group()  # holds explosion animations
ufo_group           = pygame.sprite.Group()  # holds the red UFO

# ---------------------------
# Runtime / round variables that get reset each game
# ---------------------------
last_alien_shot = pygame.time.get_ticks()  # last time an alien fired
last_ufo_spawn  = pygame.time.get_ticks()  # last time we tried to spawn UFO

score = 0                                   # player score
countdown = 3                                # "GET READY" countdown (3,2,1)
last_count = pygame.time.get_ticks()         # timer to tick countdown down each second
can_shoot = False                            # NEW: Player can't shoot until countdown ends

# Alien formation movement control:
alien_dir = 1                # 1 = moving right, -1 = moving left
alien_step_down = 16         # how far they drop vertically when bouncing off a wall (will be overridden per difficulty)
alien_move_timer = 0         # frame counter for timing steps
alien_move_delay = 20        # how many frames between horizontal movement "steps" (will be overridden per difficulty)

# ---------------------------
# CLASS: Spaceship (the player)
# ---------------------------
class Spaceship(pygame.sprite.Sprite):
    def __init__(self, x, y, health):
        super().__init__()
        # Load the player ship image
        self.image = pygame.image.load("img/spaceship.png")
        # Set its rectangle so we can position and collide it
        self.rect = self.image.get_rect(center=(x, y))

        # Store health
        self.health_start = health
        self.health_remaining = health

        # Track last time we shot a bullet
        self.last_shot = pygame.time.get_ticks()

    def update(self):
        """
        Handle:
        - movement (arrow keys / A-D equiv using LEFT/RIGHT)
        - shooting (spacebar)
        - drawing health bar
        - checking if dead
        """
        global game_state, game_over_reason

        # Get keyboard state
        key = pygame.key.get_pressed()

        # Move left/right but not past edges of screen
        if key[pygame.K_LEFT] and self.rect.left > 0:
            self.rect.x -= PLAYER_SPEED
        if key[pygame.K_RIGHT] and self.rect.right < SCREEN_W:
            self.rect.x += PLAYER_SPEED

        # Shooting:
        # Only allow shooting if global can_shoot == True (countdown done)
        # AND respect cooldown so you can't spam
        now = pygame.time.get_ticks()
        if can_shoot and key[pygame.K_SPACE] and now - self.last_shot > PLAYER_COOLDOWN:
            laser_fx.play()  # play laser sound
            bullet = PlayerBullet(self.rect.centerx, self.rect.top)  # create bullet at ship nose
            bullet_group.add(bullet)  # add to the sprite group so game updates/draws it
            self.last_shot = now      # reset cooldown timer

        # Mask is used for pixel-perfect collisions
        self.mask = pygame.mask.from_surface(self.image)

        # Draw the health bar just under the ship
        bar_w = self.rect.width
        bar_x = self.rect.x
        bar_y = self.rect.bottom + 6   # small gap below ship

        # Red = full bar background
        pygame.draw.rect(screen, RED, (bar_x, bar_y, bar_w, 10))

        # Green = remaining health portion
        if self.health_remaining > 0:
            pygame.draw.rect(
                screen,
                GREEN,
                (bar_x, bar_y, int(bar_w * (self.health_remaining / self.health_start)), 10)
            )
        else:
            # Health hit 0 -> Player dies
            explosion_group.add(Explosion(self.rect.centerx, self.rect.centery, 3))
            self.kill()  # remove ship from its sprite group
            game_state = STATE_GAMEOVER
            game_over_reason = "lose"

# ---------------------------
# CLASS: PlayerBullet
# ---------------------------
class PlayerBullet(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        # Bullet sprite
        self.image = pygame.image.load("img/bullet.png")
        self.rect = self.image.get_rect(center=(x, y))

    def update(self):
        """
        Move bullet upward,
        check collision with aliens and UFO,
        award points and spawn explosions.
        """
        global score

        # Move bullet up the screen
        self.rect.y += BULLET_SPEED_PLAYER

        # If it goes off top, delete it
        if self.rect.bottom < 0:
            self.kill()
            return

        # Check collision with aliens
        hits = pygame.sprite.spritecollide(self, alien_group, True, pygame.sprite.collide_mask)
        if hits:
            self.kill()
            explosion_fx.play()
            for alien in hits:
                explosion_group.add(Explosion(self.rect.centerx, self.rect.centery, 2))
                score += POINTS_TABLE.get(alien.alien_type, 0)

        # Check collision with UFO (red saucer, 100 pts)
        hits_ufo = pygame.sprite.spritecollide(self, ufo_group, True, pygame.sprite.collide_mask)
        if hits_ufo:
            self.kill()
            explosion_fx.play()
            for ufo in hits_ufo:
                explosion_group.add(Explosion(self.rect.centerx, self.rect.centery, 2))
                score += POINTS_TABLE.get(ufo.alien_type, 0)

# ---------------------------
# CLASS: Alien (one invader)
# ---------------------------
class Alien(pygame.sprite.Sprite):
    def __init__(self, x, y, alien_type):
        """
        alien_type picks which sprite and how many points it's worth.
        1 = weak (10 pts), 2 = mid (20), 3 = strong (40)
        """
        super().__init__()
        self.alien_type = alien_type
        self.image = pygame.image.load(f"img/alien{alien_type}.png")
        self.rect = self.image.get_rect(center=(x, y))
        self.mask = pygame.mask.from_surface(self.image)

    def shift(self, dx, dy):
        """
        Move this alien by (dx, dy). We call this on the whole block
        so they march together.
        """
        self.rect.x += dx
        self.rect.y += dy

# ---------------------------
# CLASS: UFO (top saucer worth 100 pts)
# ---------------------------
class UFO(pygame.sprite.Sprite):
    def __init__(self, y=50):
        """
        Spawns just off the left of the screen and drifts across slowly.
        """
        super().__init__()
        self.alien_type = 4  # 100 pts value
        self.image = pygame.image.load("img/alien4.png")
        self.rect = self.image.get_rect(midleft=(-60, y))
        self.mask = pygame.mask.from_surface(self.image)

    def update(self):
        # Move UFO horizontally to the right
        self.rect.x += UFO_SPEED

        # If it's off the right edge, remove it
        if self.rect.left > SCREEN_W + 60:
            self.kill()

# ---------------------------
# CLASS: AlienBullet
# ---------------------------
class AlienBullet(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        # Alien bullet sprite
        self.image = pygame.image.load("img/alien_bullet.png")
        self.rect = self.image.get_rect(center=(x, y))

    def update(self):
        """
        Alien bullets fall downward, can hit the player.
        """
        self.rect.y += BULLET_SPEED_ALIEN

        # If bullet leaves bottom, remove it
        if self.rect.top > SCREEN_H:
            self.kill()
            return

        # Check collision with player ship
        hit_ship = pygame.sprite.spritecollide(self, spaceship_group, False, pygame.sprite.collide_mask)
        if hit_ship:
            self.kill()
            explosion2_fx.play()
            for ship in hit_ship:
                ship.health_remaining -= 1
            explosion_group.add(Explosion(self.rect.centerx, self.rect.centery, 1))

# ---------------------------
# CLASS: Explosion animation
# ---------------------------
class Explosion(pygame.sprite.Sprite):
    def __init__(self, x, y, size):
        """
        Plays through exp1.png -> exp5.png, scaled by 'size'.
        size 1 = tiny pop, size 3 = big boom.
        """
        super().__init__()
        self.images = []
        for num in range(1, 6):
            img = pygame.image.load(f"img/exp{num}.png")
            if size == 1:
                img = pygame.transform.scale(img, (20, 20))
            elif size == 2:
                img = pygame.transform.scale(img, (40, 40))
            elif size == 3:
                img = pygame.transform.scale(img, (120, 120))
            self.images.append(img)

        # Animation bookkeeping
        self.index = 0
        self.image = self.images[self.index]
        self.rect = self.image.get_rect(center=(x, y))
        self.counter = 0

    def update(self):
        """
        Step through explosion frames over time.
        """
        explosion_speed = 3  # lower = slower animation
        self.counter += 1

        # Every few ticks, advance to the next frame
        if self.counter >= explosion_speed and self.index < len(self.images) - 1:
            self.counter = 0
            self.index += 1
            self.image = self.images[self.index]

        # When done animating, delete the explosion
        if self.index >= len(self.images) - 1 and self.counter >= explosion_speed:
            self.kill()

# ---------------------------
# Alien formation helpers
# ---------------------------
def get_alien_bounds():
    """
    Look at all living aliens and figure out:
    - the leftmost x
    - the rightmost x
    - the lowest bottom y
    We use this to:
    - detect when to bounce off left/right wall
    - detect how low they've dropped (loss condition)
    """
    xs = [a.rect.x for a in alien_group]
    rs = [a.rect.right for a in alien_group]
    ys = [a.rect.bottom for a in alien_group]
    if not xs:
        return 0, 0, 0
    return min(xs), max(rs), max(ys)

def move_alien_block(move_speed):
    """
    Classic Space Invaders movement:
    - Aliens move sideways as a block.
    - If they hit a wall, reverse direction and drop down.
    Difficulty affects:
    - move_speed (how many pixels per horizontal step)
    - alien_step_down (how far down they drop on a bounce)
    """
    global alien_dir, alien_step_down

    # If all aliens are dead, nothing to move
    if len(alien_group) == 0:
        return

    left_edge, right_edge, _ = get_alien_bounds()

    # Margin from walls (20 px)
    hit_right_wall = (alien_dir > 0 and right_edge + move_speed >= SCREEN_W - 20)
    hit_left_wall  = (alien_dir < 0 and left_edge  - move_speed <= 20)

    if hit_right_wall or hit_left_wall:
        # Reverse horizontal direction
        alien_dir *= -1
        # Drop the whole block down by alien_step_down pixels
        for alien in alien_group:
            alien.shift(0, alien_step_down)
    else:
        # Normal sideways shift this frame
        for alien in alien_group:
            alien.shift(move_speed * alien_dir, 0)

def check_player_loss_by_invasion():
    """
    If the lowest alien gets too close to the player,
    player loses even if still alive.
    """
    global game_state, game_over_reason
    if len(alien_group) == 0:
        return
    _, _, lowest_y = get_alien_bounds()

    # If aliens are within ~140px of bottom of a 600px screen, you're done.
    if lowest_y >= SCREEN_H - 140:
        game_state = STATE_GAMEOVER
        game_over_reason = "lose"

# ---------------------------
# Level setup helpers
# ---------------------------
def create_aliens():
    """
    Populate alien_group with a grid of aliens in rows/cols.
    Rows closer to the player are worth more points.
    """
    alien_group.empty()

    # Positioning for alien grid
    start_x = 120
    start_y = 100
    x_gap  = 70
    y_gap  = 50

    for row in range(ROWS):
        # Decide alien type for this row (controls sprite + score)
        if row <= 1:
            a_type = 1   # top rows -> weak alien (10 pts)
        elif row <= 3:
            a_type = 2   # middle rows -> medium alien (20 pts)
        else:
            a_type = 3   # bottom row -> strong alien (40 pts)

        for col in range(COLS):
            x = start_x + col * x_gap
            y = start_y + row * y_gap
            alien_group.add(Alien(x, y, a_type))

def reset_game(selected_diff_name):
    """
    Reset EVERYTHING for a fresh round:
    - score
    - countdown
    - groups
    - player ship
    - alien formation
    - difficulty tuning:
        - how often aliens step (alien_move_delay)
        - how far down they drop (alien_step_down)
    """
    global score, countdown, last_count, last_alien_shot, last_ufo_spawn
    global can_shoot
    global alien_dir, alien_move_delay, alien_move_timer, alien_step_down

    # Reset scoreboard and countdown
    score = 0
    countdown = 3
    last_count = pygame.time.get_ticks()
    can_shoot = False  # important: lock shooting until countdown finishes

    # Reset alien/UFO timers
    last_alien_shot = pygame.time.get_ticks()
    last_ufo_spawn  = pygame.time.get_ticks()

    # Reset block movement state
    alien_dir = 1
    alien_move_timer = 0

    # Difficulty affects alien movement pacing and drop aggressiveness
    if selected_diff_name == "EASY":
        alien_move_delay = 28  # bigger delay = slower marching
        alien_step_down  = 16  # small drop per wall bounce
    elif selected_diff_name == "MEDIUM":
        alien_move_delay = 18
        alien_step_down  = 24
    else:  # "HARD"
        alien_move_delay = 8   # tiny delay = fast marching
        alien_step_down  = 32  # big drop per bounce

    # Clear all sprite groups
    spaceship_group.empty()
    bullet_group.empty()
    alien_group.empty()
    alien_bullet_group.empty()
    explosion_group.empty()
    ufo_group.empty()

    # Spawn player at bottom middle with 3 health "lives"
    ship = Spaceship(SCREEN_W // 2, SCREEN_H - 80, 3)
    spaceship_group.add(ship)

    # Spawn alien formation
    create_aliens()

# ---------------------------
# Screen drawing helpers for menus / game over
# ---------------------------
def draw_title_screen():
    """
    Title / legend screen.
    Shows each alien sprite with its point value,
    and asks the player to press Enter.
    """
    screen.fill(BLACK)

    rows_y = [200, 240, 280, 320]  # vertical positions for the legend rows
    pt_vals = ["    10 PTS", "    20 PTS", "    40 PTS", "   100 PTS"]
    alien_imgs = ["alien1.png", "alien2.png", "alien3.png", "alien4.png"]

    for i, y in enumerate(rows_y):
        # Draw alien sprite
        try:
            img = pygame.image.load("img/" + alien_imgs[i])
            img_rect = img.get_rect()
            img_rect.centerx = SCREEN_W // 2 - 70
            img_rect.centery = y
            screen.blit(img, img_rect)
        except:
            pass

        # Draw its point value centered horizontally
        draw_text_center(pt_vals[i], font24, WHITE, y)

    draw_text_center("PLAY SPACE INVADERS", font32, WHITE, 380)
    draw_text_center("PRESS ENTER", font24, WHITE, 420)

def draw_difficulty_screen(selected_i):
    """
    Difficulty selection screen.
    Arrow up/down changes selection, Enter starts game.
    """
    screen.fill(BLACK)
    draw_text_center("SELECT DIFFICULTY", font32, WHITE, 200)

    for i, name in enumerate(difficulties):
        color = WHITE if i == selected_i else (100, 100, 100)
        draw_text_center(name, font32, color, 260 + i * 40)

    draw_text_center("ARROWS TO MOVE  •  ENTER TO START", font16, WHITE, 380)

def draw_gameover_screen(reason):
    """
    Game over screen.
    Shows WIN / GAME OVER and final score.
    """
    screen.fill(BLACK)

    if reason == "win":
        draw_text_center("YOU WIN!", font32, WHITE, SCREEN_H // 2 - 40)
    else:
        draw_text_center("GAME OVER!", font32, WHITE, SCREEN_H // 2 - 40)

    draw_text_center("PRESS ENTER TO PLAY AGAIN", font24, WHITE, SCREEN_H // 2 + 10)
    draw_text_center(f"SCORE: {score}", font24, WHITE, SCREEN_H // 2 + 50)

# ---------------------------
# MAIN GAME LOOP
# ---------------------------
running = True
while running:
    clock.tick(FPS)  # Cap framerate

    # -----------------------
    # Input / events
    # -----------------------
    for event in pygame.event.get():
        if event.type == QUIT:
            running = False  # Window close button exits game

        if event.type == KEYDOWN:
            if game_state == STATE_TITLE:
                # From title screen, Enter goes to difficulty select
                if event.key == K_RETURN:
                    game_state = STATE_DIFF

            elif game_state == STATE_DIFF:
                # Up/down arrows move difficulty cursor
                if event.key == K_UP:
                    diff_index = (diff_index - 1) % len(difficulties)
                elif event.key == K_DOWN:
                    diff_index = (diff_index + 1) % len(difficulties)
                elif event.key == K_RETURN:
                    # Start a new round using current difficulty
                    reset_game(difficulties[diff_index])
                    game_state = STATE_GAME
                    game_over_reason = None

            elif game_state == STATE_GAMEOVER:
                # From game over screen, Enter goes back to difficulty select
                if event.key == K_RETURN:
                    game_state = STATE_DIFF

    # -----------------------
    # STATE: TITLE SCREEN
    # -----------------------
    if game_state == STATE_TITLE:
        draw_title_screen()
        pygame.display.update()
        continue

    # -----------------------
    # STATE: DIFFICULTY SELECT
    # -----------------------
    if game_state == STATE_DIFF:
        draw_difficulty_screen(diff_index)
        pygame.display.update()
        continue

    # -----------------------
    # STATE: GAMEPLAY
    # -----------------------
    if game_state == STATE_GAME:
        draw_bg()  # draw background

        # -------------------
        # COUNTDOWN PHASE
        # -------------------
        if countdown > 0:
            # Update all sprites visually but DO NOT:
            # - move aliens toward player
            # - let aliens shoot
            # - let player shoot (we locked can_shoot = False)
            spaceship_group.update()
            bullet_group.update()
            alien_group.update()
            alien_bullet_group.update()
            ufo_group.update()
            explosion_group.update()

            # Draw sprites to the screen
            spaceship_group.draw(screen)
            bullet_group.draw(screen)
            alien_group.draw(screen)
            alien_bullet_group.draw(screen)
            ufo_group.draw(screen)
            explosion_group.draw(screen)

            # Draw score in top-left corner
            draw_text_topleft(f"SCORE: {score}", font20, WHITE, 20, 20)

            # Big "GET READY" and countdown # on top (after sprites so it's visible)
            draw_text_center("GET READY!", font48, WHITE, SCREEN_H // 2 - 30)
            draw_text_center(str(countdown), font48, WHITE, SCREEN_H // 2 + 30)

            # Tick down countdown once per second
            now = pygame.time.get_ticks()
            if now - last_count > 1000:
                countdown -= 1
                last_count = now

                # When countdown hits 0 next frame, allow player shooting
                if countdown <= 0:
                    # clamp it at 0 so it doesn't keep going negative
                    countdown = 0
                    # flip can_shoot on so player can fire
                    can_shoot = True

            pygame.display.update()
            continue  # skip rest of gameplay logic until countdown is done

        # -------------------
        # NORMAL GAMEPLAY PHASE
        # -------------------

        now = pygame.time.get_ticks()

        # Aliens fire bullets sometimes
        if (now - last_alien_shot > ALIEN_COOLDOWN and
            len(alien_bullet_group) < 4 and len(alien_group) > 0):
            attacker = random.choice(alien_group.sprites())
            alien_bullet_group.add(AlienBullet(attacker.rect.centerx, attacker.rect.bottom))
            last_alien_shot = now

        # Possibly spawn UFO (red saucer worth 100 pts)
        if now - last_ufo_spawn > UFO_COOLDOWN:
            # 40% chance to spawn, only if no UFO currently on screen
            if random.random() < 0.4 and len(ufo_group) == 0:
                ufo_group.add(UFO())
            last_ufo_spawn = now

        # Control alien marching:
        # alien_move_timer counts frames. When it reaches alien_move_delay,
        # we step the whole block horizontally (and maybe drop down).
        alien_move_timer += 1
        if alien_move_timer >= alien_move_delay:
            alien_move_timer = 0
            move_alien_block(alien_move_speed_by_diff[difficulties[diff_index]])

        # Check if aliens got low enough that the player auto-loses
        check_player_loss_by_invasion()
        if game_state == STATE_GAMEOVER:
            # Player lost because invaders reached the bottom.
            # Draw GAME OVER immediately this frame.
            draw_gameover_screen(game_over_reason)
            pygame.display.update()
            continue

        # Check for instant WIN:
        # if no aliens remain and player ship still exists
        if len(alien_group) == 0 and len(spaceship_group) > 0:
            game_state = STATE_GAMEOVER
            game_over_reason = "win"
            draw_gameover_screen(game_over_reason)
            pygame.display.update()
            continue

        # Normal per-frame sprite updates
        spaceship_group.update()
        bullet_group.update()
        alien_group.update()
        alien_bullet_group.update()
        ufo_group.update()
        explosion_group.update()

        # Draw all active sprites
        spaceship_group.draw(screen)
        bullet_group.draw(screen)
        alien_group.draw(screen)
        alien_bullet_group.draw(screen)
        ufo_group.draw(screen)
        explosion_group.draw(screen)

        # HUD: Score in top-left
        draw_text_topleft(f"SCORE: {score}", font20, WHITE, 20, 20)

        pygame.display.update()
        continue

    # -----------------------
    # STATE: GAMEOVER SCREEN
    # -----------------------
    if game_state == STATE_GAMEOVER:
        draw_gameover_screen(game_over_reason)
        pygame.display.update()
        continue

# If we ever exit the main loop, quit pygame safely
pygame.quit()
sys.exit()
