from flask import Flask, render_template, request, jsonify

from braid_group import BraidSignGroup
import logging, datetime, random, string
import config, json, traceback

app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False

bsg = BraidSignGroup(config.braid['n'], config.braid['p'], config.braid['l'])
session = {}

@app.route('/',  methods=['GET'])
def index():
    open = session['last_open'] + datetime.timedelta(minutes = 10) > datetime.datetime.now()
    return render_template('public/server.html', open=open)

@app.route('/auth',  methods=['GET', 'POST'])
def verify():
    if request.method == 'GET':
        msg = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
        return jsonify({'msg': msg})
    else:
        try:
            j = request.json
            sign = bsg.deserializeBraid(j['sign'])
            msg = j['msg']
            msg_hash = bsg.hash1(msg)
            with open('certs/lab_cert.json') as f:
                cert = json.load(f)
            x = bsg.deserializeBraid(cert['open_key']['x'])
            y = bsg.deserializeBraid(cert['open_key']['y'])
            if sign.is_conjugated(msg_hash) and (y * sign).is_conjugated(x * msg_hash):
                session['last_open'] = datetime.datetime.now()
                return jsonify({'result': 'True'})
            else:
                return jsonify({'result': 'False'})
        except:
            traceback.print_exc()
            return jsonify({'result': 'False'})



if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
    session['last_open'] = datetime.datetime.now() - datetime.timedelta(days = 365)
    app.run(port=5082)