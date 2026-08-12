import os
import io
import base64
import qrcode
from PIL import Image
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer, SquareModuleDrawer, CircleModuleDrawer
from flask import Flask, render_template, request, url_for
from werkzeug.utils import secure_filename
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)

# --- USER LIMIT SETUP ---
# Har user ke IP address ke hisaab se limit lagegi
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["100 per day", "20 per hour"], # Default global limit
    storage_uri="memory://"
)

UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

THEMES = {
    'instagram': {'fill': '#E1306C', 'back': '#FFFFFF', 'drawer': CircleModuleDrawer()},
    'whatsapp': {'fill': '#075E54', 'back': '#E5DDD5', 'drawer': RoundedModuleDrawer()},
    'cyberpunk': {'fill': '#38BDF8', 'back': '#06080D', 'drawer': RoundedModuleDrawer()},
    'classic': {'fill': '#000000', 'back': '#FFFFFF', 'drawer': SquareModuleDrawer()},
}

# Limit error message custom handler
@app.errorhandler(429)
def ratelimit_handler(e):
    return render_template(
        "index.html",
        error_msg="⚠️ Aapne limit cross kar di hai! Kripya 1 minute baad try karein.",
        qr_type="text",
        fill_color="#38BDF8",
        back_color="#06080D",
        qr_style="cyberpunk",
        frame_text="SCAN ME"
    ), 429

@app.route('/', methods=['GET', 'POST'])
@limiter.limit("5 per minute")  # 👈 SPECIFIC LIMIT: User 1 minute me max 5 QR hi bana sakta hai
def index():
    user_data = ""
    ssid = ""
    wifi_pass = ""
    qr_style = "cyberpunk"
    fill_color = "#38BDF8"
    back_color = "#06080D"
    qr_type = "text"
    qr_generated = False
    qr_img_base64 = ""
    qr_subtitle = ""
    error_msg = ""
    frame_text = "SCAN ME"

    if request.method == "POST":
        qr_type = request.form.get("qr_type", "text")
        qr_style = request.form.get("qr_style", "cyberpunk")
        frame_text = request.form.get("frame_text", "SCAN ME").strip()

        if qr_style == "custom":
            fill_color = request.form.get("fill_color", "#38BDF8")
            back_color = request.form.get("back_color", "#06080D")
            drawer_style = RoundedModuleDrawer()
        elif qr_style in THEMES:
            fill_color = THEMES[qr_style]['fill']
            back_color = THEMES[qr_style]['back']
            drawer_style = THEMES[qr_style]['drawer']
        else:
            drawer_style = RoundedModuleDrawer()

        payload = ""

        if qr_type == "wifi":
            ssid = request.form.get("ssid", "").strip()
            wifi_pass = request.form.get("wifi_pass", "").strip()
            if ssid:
                payload = f"WIFI:S:{ssid};T:WPA;P:{wifi_pass};;"
                qr_subtitle = f"Wi-Fi Network: {ssid}"
            else:
                error_msg = "Kripya Wi-Fi Name (SSID) bharein!"

        elif qr_type == "image":
            if 'qr_image' in request.files:
                file = request.files['qr_image']
                if file and file.filename != '':
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    
                    host_url = request.host_url.rstrip('/')
                    image_url = host_url + url_for('static', filename=f'uploads/{filename}')
                    payload = image_url
                    qr_subtitle = f"Photo Link: {filename}"
                else:
                    error_msg = "Kripya ek image file select karein!"
            else:
                error_msg = "Koi image upload nahi mili!"

        else:
            user_data = request.form.get("data", "").strip()
            if user_data:
                payload = user_data
                qr_subtitle = "Custom Smart Link Payload"
            else:
                error_msg = "Kripya URL ya Text content bharein!"

        if payload and not error_msg:
            try:
                qr = qrcode.QRCode(
                    version=None,
                    error_correction=qrcode.constants.ERROR_CORRECT_H,
                    box_size=12,
                    border=3,
                )
                qr.add_data(payload)
                qr.make(fit=True)

                img = qr.make_image(
                    image_factory=StyledPilImage,
                    module_drawer=drawer_style,
                    fill_color=fill_color,
                    back_color=back_color
                ).convert("RGBA")

                if 'logo_image' in request.files:
                    logo_file = request.files['logo_image']
                    if logo_file and logo_file.filename != '':
                        logo = Image.open(logo_file.stream).convert("RGBA")
                        qr_w, qr_h = img.size
                        logo_size = int(qr_w * 0.20)
                        logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
                        logo_pos = ((qr_w - logo_size) // 2, (qr_h - logo_size) // 2)
                        img.paste(logo, logo_pos, mask=logo if logo.mode == 'RGBA' else None)

                img_io = io.BytesIO()
                img.save(img_io, "PNG")
                img_io.seek(0)
                qr_img_base64 = base64.b64encode(img_io.getvalue()).decode("utf-8")
                qr_generated = True

            except Exception as e:
                error_msg = f"Error: {str(e)}"

    return render_template(
        "index.html",
        user_data=user_data,
        ssid=ssid,
        wifi_pass=wifi_pass,
        fill_color=fill_color,
        back_color=back_color,
        qr_type=qr_type,
        qr_style=qr_style,
        qr_generated=qr_generated,
        qr_img_base64=qr_img_base64,
        qr_subtitle=qr_subtitle,
        error_msg=error_msg,
        frame_text=frame_text
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)