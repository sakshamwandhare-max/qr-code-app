from flask import Flask, render_template, request, send_file
import qrcode
import io
import base64

app = Flask(__name__)


@app.template_filter("b64encode")
def b64encode_filter(data):
    return base64.b64encode(data).decode("utf-8")


@app.route("/", methods=["GET", "POST"])
def home():
    qr_image = None
    entered_text = ""

    if request.method == "POST":
        entered_text = request.form.get("text", "").strip()

        if entered_text:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10,
                border=4
            )

            qr.add_data(entered_text)
            qr.make(fit=True)

            image = qr.make_image(
                fill_color="black",
                back_color="white"
            )

            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            buffer.seek(0)

            qr_image = buffer.getvalue()

            app.config["QR_IMAGE"] = qr_image

    return render_template(
        "index.html",
        qr_image=qr_image,
        entered_text=entered_text
    )


@app.route("/download")
def download():
    qr_image = app.config.get("QR_IMAGE")

    if not qr_image:
        return "Generate a QR code first.", 400

    buffer = io.BytesIO(qr_image)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="image/png",
        as_attachment=True,
        download_name="qr_code.png"
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000
    )
