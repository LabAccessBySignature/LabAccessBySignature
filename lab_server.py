from flask import Flask, render_template, request, jsonify

from braid_group import BraidSignGroup
import logging, datetime, random, string
import config

app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False

bsg = bsg = BraidSignGroup(config.braid['n'], config.braid['p'], config.braid['l'])
session = {}

def init_session(email):
    if email not in session:
        session[email] = {'secret_knowledge': {}}

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
        j = request.json
        sign = bsg.deserializeBraid(j['sign'])
        msg = j['msg']
        if sign.is_conjugated(bsg.hash1(msg)):
            session['last_open'] = datetime.datetime.now()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
    app.run(port=5082)