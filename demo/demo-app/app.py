"""Intentionally vulnerable demo application for the SentinelX walkthrough.

This file exists only to give the scanner realistic findings. Never deploy it.
"""

import os
import pickle
import subprocess

from flask import Flask, request

app = Flask(__name__)


@app.route("/lookup")
def lookup():
    user_id = request.args.get("id", "")
    query = "SELECT * FROM users WHERE id = '%s'" % user_id
    cursor = db.cursor()
    cursor.execute(query)
    return str(cursor.fetchall())


@app.route("/run")
def run_command():
    target = request.args.get("host", "")
    os.system("ping -c 1 " + target)
    subprocess.run(target, shell=True)
    return "ok"


@app.route("/restore", methods=["POST"])
def restore():
    state = pickle.loads(request.data)
    expression = request.args.get("expr", "1 + 1")
    return str(eval(expression))


if __name__ == "__main__":
    app.run(debug=True)
