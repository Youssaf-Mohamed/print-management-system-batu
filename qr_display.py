import qrcode
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageDraw, ImageFilter, ImageEnhance
import requests
import uuid
import time
import json
import logging
import threading
import os
from datetime import datetime
import math

# Setup logging
if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(
    filename=os.path.join('logs', 'qr_display.log'),
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Load configuration
try:
    with open('config.json', encoding='utf-8') as f:
        config = json.load(f)
    WEB_APP_URL = config['web_app_url']
    logging.info(f"Loaded WEB_APP_URL = {WEB_APP_URL}")
except Exception as e:
    logging.error(f"Error reading config.json: {e}")
    raise

# Define colors
DARK_BG = '#333333'  # Background color
PRIMARY_COLOR = '#4AAFAA'  # Primary color
PRIMARY_COLOR_DARK = '#3A8F8A'  # Darker primary color
SECONDARY_COLOR = '#5A8C52'  # Secondary color
ACCENT_COLOR = '#A6C264'  # Accent color
TEXT_COLOR = '#F8F9FA'  # Text color
GRAY_COLOR = '#E9ECEF'  # Gray color
SUCCESS_COLOR = '#5CB85C'  # Success color
ERROR_COLOR = '#D9534F'  # Error color
CARD_BG = '#FFFFFF'  # Card background color

# Initialize tkinter window
root = tk.Tk()
root.title("QR Login Display")
root.attributes('-fullscreen', True)
root.configure(bg=DARK_BG)
root.bind('<Escape>', lambda e: root.destroy())
root.protocol("WM_DELETE_WINDOW", lambda: root.destroy())

# Create main frame
main_frame = tk.Frame(root, bg=DARK_BG)
main_frame.pack(fill='both', expand=True)

# Create gradient background


def create_gradient_bg(width, height, color1, color2):
    """Generate a gradient background image."""
    gradient = Image.new('RGBA', (width, height), color1)
    draw = ImageDraw.Draw(gradient)

    for i in range(height):
        r1, g1, b1 = int(color1[1:3], 16), int(
            color1[3:5], 16), int(color1[5:7], 16)
        r2, g2, b2 = int(color2[1:3], 16), int(
            color2[3:5], 16), int(color2[5:7], 16)

        r = r1 + (r2 - r1) * i // height
        g = g1 + (g2 - g1) * i // height
        b = b1 + (b2 - b1) * i // height

        draw.line([(0, i), (width, i)], fill=(r, g, b))

    return gradient


# Create header frame
header_frame = tk.Frame(main_frame, bg=DARK_BG, pady=20)
header_frame.pack(fill='x')

# Load and display university logo
logo_frame = tk.Frame(header_frame, bg=DARK_BG)
logo_frame.pack(side='top', pady=(0, 10))

logo_path = os.path.join(os.path.dirname(__file__), 'static', 'logo.png')
try:
    logo_img = Image.open(logo_path)
    logo_img = logo_img.resize((150, 150), Image.Resampling.LANCZOS)
    enhancer = ImageEnhance.Brightness(logo_img)
    logo_img = enhancer.enhance(1.2)
    logo_tk = ImageTk.PhotoImage(logo_img)
    logo_lbl = tk.Label(logo_frame, image=logo_tk, bg=DARK_BG)
    logo_lbl.pack()
except Exception as e:
    logging.warning(f"Could not load logo: {e}")
    logo_lbl = tk.Label(logo_frame, text="شعار الجامعة",
                        fg=ACCENT_COLOR, bg=DARK_BG, font=("Arial", 16))
    logo_lbl.pack()

# Create title frame
title_frame = tk.Frame(header_frame, bg=DARK_BG)
title_frame.pack(side='top')

title_lbl = tk.Label(
    title_frame,
    text="نظام تسجيل الدخول عبر QR",
    fg=PRIMARY_COLOR, bg=DARK_BG,
    font=("Arial", 32, "bold")
)
title_lbl.pack()

subtitle_lbl = tk.Label(
    title_frame,
    text="امسح الرمز بتطبيق الجامعة للتسجيل",
    fg=TEXT_COLOR, bg=DARK_BG,
    font=("Arial", 16)
)
subtitle_lbl.pack(pady=(5, 0))

# Create QR display frame
qr_container = tk.Frame(main_frame, bg=DARK_BG)
qr_container.pack(expand=True, fill='both', pady=20)

qr_inner_frame = tk.Frame(
    qr_container,
    bg=DARK_BG,
    highlightbackground=PRIMARY_COLOR,
    highlightthickness=3,
    bd=0
)
qr_inner_frame.pack(expand=True, padx=20, pady=20)

# Add shadow effect
shadow_frame = tk.Frame(qr_inner_frame, bg=DARK_BG, padx=15, pady=15)
shadow_frame.pack(expand=True)

qr_padding_frame = tk.Frame(shadow_frame, bg=ACCENT_COLOR, padx=2, pady=2)
qr_padding_frame.pack(expand=True)

qr_display_frame = tk.Frame(qr_padding_frame, bg=CARD_BG, padx=20, pady=20)
qr_display_frame.pack(expand=True)

qr_lbl = tk.Label(qr_display_frame, bg='white')
qr_lbl.pack(expand=True)

# Create animated loading indicator
canvas_size = 60
loading_canvas = tk.Canvas(
    qr_container,
    width=canvas_size,
    height=canvas_size,
    bg=DARK_BG,
    highlightthickness=0
)
loading_canvas.pack(pady=(20, 0))

# Create status frame
status_frame = tk.Frame(main_frame, bg=DARK_BG, pady=10)
status_frame.pack(fill='x', pady=(0, 30))

status_lbl = tk.Label(
    status_frame,
    text="جاهز للمسح",
    fg=PRIMARY_COLOR, bg=DARK_BG,
    font=("Arial", 20, "bold")
)
status_lbl.pack()

instructions_lbl = tk.Label(
    status_frame,
    text="سيتم تحديث الرمز تلقائياً كل دقيقة",
    fg=GRAY_COLOR, bg=DARK_BG,
    font=("Arial", 14)
)
instructions_lbl.pack(pady=(5, 0))

# Create time display frame
time_frame = tk.Frame(main_frame, bg=DARK_BG)
time_frame.pack(side='bottom', fill='x', pady=10)

time_lbl = tk.Label(
    time_frame,
    text="",
    fg=TEXT_COLOR, bg=DARK_BG,
    font=("Arial", 14)
)
time_lbl.pack()

# Utility functions


def update_time():
    """Update displayed date and time."""
    now = datetime.now()
    time_str = now.strftime("%Y/%m/%d %H:%M:%S")
    time_lbl.config(text=time_str)
    root.after(1000, update_time)


def animate_loading(angle=0):
    """Animate a loading circle."""
    loading_canvas.delete("all")
    radius = canvas_size / 2 - 5
    center = canvas_size / 2

    loading_canvas.create_arc(
        5, 5, canvas_size-5, canvas_size-5,
        start=0, extent=359.9,
        outline=GRAY_COLOR, width=3, style=tk.ARC
    )

    loading_canvas.create_arc(
        5, 5, canvas_size-5, canvas_size-5,
        start=angle, extent=90,
        outline=PRIMARY_COLOR, width=3, style=tk.ARC
    )

    loading_canvas.create_oval(
        center-3, center-3, center+3, center+3,
        fill=PRIMARY_COLOR, outline=""
    )

    root.after(50, animate_loading, (angle + 10) % 360)


def create_fancy_qr(data, size=300):
    """Generate a styled QR code without a centered logo."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color=PRIMARY_COLOR_DARK,
                           back_color=CARD_BG).convert('RGBA')

    qr_img = qr_img.resize((size, size), Image.Resampling.LANCZOS)

    shadow = Image.new('RGBA', qr_img.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rectangle((5, 5, size-5, size-5), fill=(0, 0, 0, 30))
    shadow = shadow.filter(ImageFilter.GaussianBlur(5))

    combined = Image.alpha_composite(shadow, qr_img)

    return combined


def update_status(message, color=PRIMARY_COLOR):
    """Update the status message on the screen."""
    status_lbl.config(text=message, fg=color)


def display_qr(image: Image.Image):
    """Convert PIL Image to PhotoImage and display it."""
    tkimg = ImageTk.PhotoImage(image)
    qr_lbl.config(image=tkimg)
    qr_lbl.image = tkimg


def pulse_effect(widget, original_color, highlight_color, steps=10, duration=100):
    """Apply a pulse effect to a widget."""
    def single_step(step):
        if step >= steps * 2:
            widget.config(bg=original_color)
            return

        if step < steps:
            ratio = step / steps
            r = int(int(original_color[1:3], 16) * (1 -
                    ratio) + int(highlight_color[1:3], 16) * ratio)
            g = int(int(original_color[3:5], 16) * (1 -
                    ratio) + int(highlight_color[3:5], 16) * ratio)
            b = int(int(original_color[5:7], 16) * (1 -
                    ratio) + int(highlight_color[5:7], 16) * ratio)
        else:
            ratio = (step - steps) / steps
            r = int(int(highlight_color[1:3], 16) * (1 -
                    ratio) + int(original_color[1:3], 16) * ratio)
            g = int(int(highlight_color[3:5], 16) * (1 -
                    ratio) + int(original_color[3:5], 16) * ratio)
            b = int(int(highlight_color[5:7], 16) * (1 -
                    ratio) + int(original_color[1:3], 16) * ratio)

        color = f'#{r:02x}{g:02x}{b:02x}'
        widget.config(bg=color)
        root.after(duration // steps, single_step, step + 1)

    single_step(0)


def update_qr():
    """Generate a new QR code and monitor session status."""
    session_timeout = 220

    while True:
        try:
            session = str(uuid.uuid4())
            url = f"{WEB_APP_URL}/login?session={session}"
            logging.info(f"New QR URL: {url}")

            qr_img = create_fancy_qr(url, size=300)
            root.after(0, display_qr, qr_img)
            root.after(0, update_status, "جاهز للمسح")
            root.after(0, pulse_effect, qr_padding_frame,
                       ACCENT_COLOR, PRIMARY_COLOR)

            start_time = time.time()

            while time.time() - start_time < session_timeout:
                try:
                    logging.debug("Checking session status...")
                    resp = requests.get(
                        f"{WEB_APP_URL}/session_status?session={session}", timeout=5)
                    resp.raise_for_status()
                    data = resp.json()
                    logging.debug(f"Session status response: {data}")

                    remaining = int(session_timeout -
                                    (time.time() - start_time))
                    remaining_minutes = remaining // 60
                    remaining_seconds = remaining % 60
                    time_str = f"{remaining_minutes}:{remaining_seconds:02d}"

                    root.after(0, instructions_lbl.config,
                               {"text": f"الوقت المتبقي: {time_str} قبل تحديث الرمز"})

                    if data.get("completed", False):
                        logging.info(f"Session {session} completed.")
                        root.after(0, update_status,
                                   "تم تسجيل الدخول بنجاح", SUCCESS_COLOR)
                        root.after(0, pulse_effect, status_frame,
                                   DARK_BG, SUCCESS_COLOR)
                        time.sleep(3)
                        break

                    elif not data.get("active", True):
                        logging.info(f"Session {session} expired.")
                        root.after(0, update_status,
                                   "انتهت صلاحية الجلسة", ERROR_COLOR)
                        time.sleep(2)
                        break

                    time.sleep(1)

                except requests.RequestException as ex:
                    logging.error(f"Network error in update_qr: {ex}")
                    root.after(0, update_status,
                               "خطأ في الاتصال بالسيرفر", ERROR_COLOR)
                    time.sleep(5)

            if time.time() - start_time >= session_timeout:
                logging.info(f"Session {session} timed out.")
                root.after(0, update_status, "جاري تحديث الرمز...", GRAY_COLOR)
                time.sleep(1)

        except Exception as ex:
            logging.error(f"Unexpected error in update_qr: {ex}")
            root.after(0, update_status, "خطأ غير متوقع", ERROR_COLOR)
            time.sleep(5)


def start():
    """Initialize UI and start QR code updates."""
    update_time()
    animate_loading()

    threading.Thread(target=update_qr, daemon=True).start()

    root.mainloop()


if __name__ == "__main__":
    start()
