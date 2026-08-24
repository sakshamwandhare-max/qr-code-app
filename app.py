from flask import Flask, render_template, request, send_file
import qrcode
import io

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def home():
    qr_image = None

    if request.method == "POST":
        text = request.form.get("text", "").strip()

        if text:
            qr = qrcode.QRCode(
                version=1,
                box_size=10,
                border=4
            )

            qr.add_data(text)
            qr.make(fit=True)

            img = qr.make_image(
                fill_color="black",
                back_color="white"
            )

            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)

            qr_image = buffer.getvalue()

            # Store temporarily for download
            app.config["QR_IMAGE"] = qr_image

    return render_template("index.html", qr_image=qr_image)


@app.route("/download")
def download():
    qr_image = app.config.get("QR_IMAGE")

    if not qr_image:
        return "Generate a QR code first."

    buffer = io.BytesIO(qr_image)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="image/png",
        as_attachment=True,
        download_name="qr_code.png"
    )


if __name__ == "__main__":
    app.run(debug=True)
