from flask import Flask, render_template, request, jsonify, json, redirect, url_for

from braid_group import BraidSignGroup
import logging, random, requests, pickle, base64, config

bsg = BraidSignGroup(9, 17, 5)
SERVER = "http://127.0.0.1:5080"

app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False


@app.route('/',  methods=['GET'])
def index():
    return render_template('public/client.html')

@app.route('/',  methods=['POST'])
def lab_enter():

    cert = json.loads(request.files['file'].read().decode())
    z = bsg.deserializeBraid(cert['key'])
    email = cert['email']

    x = bsg.deserializeBraid(config.x)
    y = z * x / z

    r = requests.post(f"{SERVER}/secret_knowledge", json={
        'action': 'open_key',
        'email': email,
        'y': bsg.serializeBraid(y)})
    a = bsg.deserializeBraid(r.json()['a'])
    b = z * a * x / z
    r = requests.post(f"{SERVER}/secret_knowledge", json={
        'action': 'b',
        'email': email,
        'b': bsg.serializeBraid(b)})
    r = int(r.json()['r'])
    c = z * a ** r * x / z
    r = requests.post(f"{SERVER}/secret_knowledge", json={
        'action': 'prove',
        'email': email,
        'c': bsg.serializeBraid(c)})
    result = r.json()['result']
    print(result)
    # if result:
    #     return "OK"
    # else: return "NOT OK"
    return redirect(url_for('index'))



if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
    app.run(port=5081)