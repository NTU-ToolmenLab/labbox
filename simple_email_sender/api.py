from flask import Flask, request, jsonify, abort
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os


# setup
app = Flask(__name__)
app.secret_key = "super secret string"  # Change this!
email_host = os.environ.get("EMAIL_HOST")
email_port = int(os.environ.get("EMAIL_PORT"))
admin_email = os.environ.get("ADMIN_EMAIL")
admin_password = os.environ.get("ADMIN_PASSWORD")


@app.errorhandler(Exception)
def AllError(error):
    """
    Catch all error here.

    This function will call if the error cannot handle by my code.

    Returns
    -------
    json
        The status code will be 500.
        There will have a key named "status" and its value is 500.
        The message will show why this happened.
    """
    message = {
        'status': 500,
        'message': "Internal Error: " + str(error)
    }
    app.logger.warning("Error: " + str(error))
    resp = jsonify(message)
    resp.status_code = 500
    return resp


def Ok(data={}):
    """
    Handle all return data here.

    Returns
    -------
    json
        The status code will be 200.
        There will have a "status" key and its value is 200.
        All the return data will in "data" key.
    """
    return jsonify({
        'status': 200,
        'message': "OK",
        'data': data
    })


@app.route("/")
def checkHealth():
    """
    Always return OK while alive
    """
    return Ok()


@app.route("/mail", methods=["POST"])
def webSendMail():
    """ Check before sending mail """
    if not email_host:
        abort(400, "Not setting mail host")

    data = dict(request.get_json())
    app.logger.debug(data)
    if not data.get('title') or not data.get('address') or not data.get('text'):
        abort(400, "Error post data")
    return sendMail(data)


def sendMail(data):
    """ Format the mail and send it """
    # init
    # prepare for mail
    msg = MIMEMultipart()
    msg['From']    = admin_email
    msg['To']      = data['address']
    msg['CC']      = admin_email
    msg['Subject'] = data['title']
    msg.attach(MIMEText(data['text']))
    app.logger.debug("[Email] send " + str(msg))

    # send
    try:
        s = smtplib.SMTP(host=email_host, port=email_port)
        s.starttls()
        s.login(admin_email, admin_password)
        s.send_message(msg)
    except smtplib.SMTPException as e:
        app.logger.error("[Email] send Error" + e)
        abort(400, "Send email error")

    app.logger.debug("[Email] Send successed." + data['address'])
    return Ok()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5870)  # , debug=True)
