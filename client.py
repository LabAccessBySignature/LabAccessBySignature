from flask import Flask, render_template, request, jsonify, json, redirect, url_for

from braid_group import BraidSignGroup
import logging, random, requests, pickle, base64, config

bsg = BraidSignGroup(9, 17, 5)
SERVER = "http://127.0.0.1:5080"

app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False


@app.route('/',  methods=['GET'])
def index():
    if 'result' in request.args:
        result = request.args['result'] == 'True'
    else:
        result = None
    return render_template('public/client.html', result=result)

@app.route('/',  methods=['POST'])
def lab_enter():

    cert = json.loads(request.files['file'].read().decode())
    z = bsg.deserializeBraid(cert['secrete_key'])
    x = bsg.deserializeBraid(cert['open_key']['x'])
    email = cert['email']

    a = bsg.randLBlElement()
    b = z * a / z

    resp = requests.post(f"{SERVER}/secret_knowledge", json={
        'action': 'init',
        'email': email,
        'a': bsg.serializeBraid(a),
        'b': bsg.serializeBraid(b)})
    r = int(resp.json()['r'])
    c = z * x ** r * a / z
    resp = requests.post(f"{SERVER}/secret_knowledge", json={
        'action': 'prove',
        'email': email,
        'c': bsg.serializeBraid(c)})
    result = resp.json()['result']

    return redirect(url_for('index', result=result))



if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
    app.run(port=5081)