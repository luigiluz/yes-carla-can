import pygame
import sys

pygame.init()

# Setup screen
WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Keyboard Visualizer")

# Fonts
font = pygame.font.SysFont(None, 36)
small_font = pygame.font.SysFont(None, 24)
big_font = pygame.font.SysFont(None, 48)

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (200, 200, 200)
GREEN = (100, 255, 100)
DARK_GRAY = (50, 50, 50)

# Key definitions: (pygame_key_code, label, note)
key_definitions = [
    (pygame.K_q, 'Q', 'Reverse'),
    (pygame.K_w, 'W', 'Move Forward'),
    (pygame.K_i, 'I', 'Interior Light'),
    (pygame.K_o, 'O', 'Doors'),

    (pygame.K_a, 'A', 'Move Left'),
    (pygame.K_s, 'S', 'Brake'),
    (pygame.K_d, 'D', 'Move Right'),
    (pygame.K_l, 'L', 'Light type'),

    (pygame.K_z, 'Z', 'Left Blinker'),
    (pygame.K_x, 'X', 'Right Blinker'),  # Added X here
    (pygame.K_m, 'M', 'Manual'),
    (pygame.K_COMMA, ',', 'Gear Up'),
    (pygame.K_PERIOD, '.', 'Gear Down'),

    (pygame.K_LSHIFT, 'SHIFT', ''),
    (pygame.K_SPACE, 'SPACE', 'Hand Brake'),
    (pygame.K_ESCAPE, 'ESC', 'Exit'),

    (pygame.K_UP, 'UP', 'Move Forward'),
    (pygame.K_DOWN, 'DOWN', 'Brake'),
    (pygame.K_LEFT, 'LEFT', 'Steer Left'),
    (pygame.K_RIGHT, 'RIGHT', 'Steer Right'),
]

# Keyboard grid positions → column, row
# We'll space columns by 1 unit, and rows by 1 unit vertically
# These are approximate positions matching a QWERTY layout
key_positions = {
    'Q': (1, 1),
    'W': (2, 1),  # Added W here
    'I': (8, 1),
    'O': (9, 1),

    'A': (1.5, 2),
    'S': (2.5, 2),
    'D': (3.5, 2),
    'L': (8.5, 2),

    'Z': (2, 3),
    'X': (3, 3),  # Added X here
    'M': (7, 3),
    ',': (8, 3),
    '.': (9, 3),

    'SHIFT': (0.5, 4),
    'SPACE': (4, 4),
    'ESC': (0, 0),  # top-left corner (fixed)

    # Arrow keys layout
    'UP': (12, 3.5),
    'LEFT': (11.5, 4.5),
    'DOWN': (12, 4.5),
    'RIGHT': (12.5, 4.5),
}

# Layout parameters
key_width_frac = 0.06  # ~6% of screen width
key_height_frac = 0.1  # ~10% of screen height
h_spacing = 0.01  # horizontal spacing between keys
v_spacing = 0.02  # vertical spacing between keys
start_x_frac = 0.1  # starting x offset
start_y_frac = 0.15  # starting y offset

# Build final keys list with positions
keys = []
for key_code, label, note in key_definitions:
    if label in key_positions:
        col, row = key_positions[label]
        x_frac = start_x_frac + col * (key_width_frac + h_spacing)
        y_frac = start_y_frac + row * (key_height_frac + v_spacing)

        # Make space key wider
        if label == "SPACE":
            w_frac = key_width_frac * 5
        else:
            w_frac = key_width_frac

        keys.append((key_code, label, note, (x_frac, y_frac, key_width_frac, key_height_frac)))
    else:
        print(f"Warning: No position defined for key {label}")

def main():
    # Track pressed state of each key
    pressed_state = {key_code: False for key_code, *_ in keys}

    # Keep track of the last key pressed (for displaying note)
    last_pressed_note = ""

    # Main loop
    clock = pygame.time.Clock()
    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key in pressed_state:
                    pressed_state[event.key] = True
                    # Update last_pressed_note
                    for key_code, label, note, _ in keys:
                        if event.key == key_code:
                            last_pressed_note = note

            elif event.type == pygame.KEYUP:
                if event.key in pressed_state:
                    pressed_state[event.key] = False
                    # If no keys pressed, clear last_pressed_note
                    if not any(pressed_state.values()):
                        last_pressed_note = ""

        # Clear screen
        screen.fill(BLACK)

        # Draw the top note rectangle
        top_rect_w = WIDTH * 0.6
        top_rect_h = HEIGHT * 0.1
        top_rect_x = (WIDTH - top_rect_w) // 2
        top_rect_y = HEIGHT * 0.03

        pygame.draw.rect(screen, DARK_GRAY, (top_rect_x, top_rect_y, top_rect_w, top_rect_h), border_radius=12)
        note_text = last_pressed_note if last_pressed_note else "Press a key"
        note_surf = big_font.render(note_text, True, WHITE)
        note_rect = note_surf.get_rect(center=(WIDTH // 2, top_rect_y + top_rect_h // 2))
        screen.blit(note_surf, note_rect)

        # Draw keys
        for key_code, label, note, rect_frac in keys:
            x_frac, y_frac, w_frac, h_frac = rect_frac
            x = int(x_frac * WIDTH)
            y = int(y_frac * HEIGHT)
            w = int(w_frac * WIDTH)
            h = int(h_frac * HEIGHT)

            color = GREEN if pressed_state[key_code] else GRAY
            pygame.draw.rect(screen, color, (x, y, w, h), border_radius=8)

            # Draw label (centered)
            label_surf = font.render(label, True, BLACK)
            label_rect = label_surf.get_rect(center=(x + w/2, y + h/2))
            screen.blit(label_surf, label_rect)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
