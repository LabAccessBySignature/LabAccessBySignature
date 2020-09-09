from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from sage.all import *
from threading import Thread
from time import sleep

from braid_group import BraidSignGroup
import logging, hashlib, random, argparse, requests
import config, json
CLIENT = "http://127.0.0.1:5080"
LAB_SERVER = "http://127.0.0.1:5082"

app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False
socketio = SocketIO(app)

import sqlite3
bsg = BraidSignGroup(config.braid['n'], config.braid['p'], config.braid['l'])

session = {}
def init_session(email):
    if email not in session:
        session[email] = {'secret_knowledge': {}}

@app.route('/',  methods=['GET'])
def index():
    db = sqlite3.connect('db.sqlite').cursor()
    db.execute('select current_timestamp, email from auth where current_timestamp < datetime(timestamp,"+60 minutes");')
    last_elements = [{'time': r[0], 'email': r[1]} for r in db.fetchall()]
    db.execute('select count(distinct(email)) from auth where current_timestamp < datetime(timestamp,"+60 minutes");')
    accessed_accounts = db.fetchone()[0]
    return render_template('public/id_based_server.html', last_elements=last_elements, accessed_accounts=accessed_accounts)

@app.route('/secret_knowledge',  methods=['POST'])
def secret_knowledge():
    db = sqlite3.connect('db.sqlite').cursor()
    j = request.json
    if j['action'] == 'open_key':
        email = j['email']
        x = bsg.deserializeBraid(config.x)
        y = bsg.deserializeBraid(j['y'])
        a = bsg.randLBElement()

        init_session(email)
        session[email]['secret_knowledge']['y'] = y
        session[email]['secret_knowledge']['a'] = a
        return jsonify({'action': 'multiplier', 'a': bsg.serializeBraid(a)})
    if j['action'] == 'b':
        email = j['email']
        b = bsg.deserializeBraid(j['b'])
        r = random.randint(0, 1)
        session[email]['secret_knowledge']['b'] = b
        session[email]['secret_knowledge']['r'] = r
        return jsonify({'action': 'random', 'r': str(r)})
    if j['action'] == 'prove':
        email = j['email']
        c = bsg.deserializeBraid(j['c'])
        b = session[email]['secret_knowledge']['b']
        r = session[email]['secret_knowledge']['r']
        y = session[email]['secret_knowledge']['y']
        db.execute('select secret from credentials where email=?;', (email,))
        z = bsg.hash1(str(db.fetchone()[0]))
        x = bsg.deserializeBraid(config.x)

        result = ((r == 0 and c == y) | (r == 1 and c == b)) and y == z * x / z
        if result:
            db.execute('insert into auth (email) values (?)', (email, ))
            db.connection.commit()
            db.execute('select count(distinct(email)) from auth where current_timestamp < datetime(timestamp,"+60 minutes");')
            if db.fetchone()[0] >= config.threshold:
                try_access()
        socketio.emit('new_access_request', {'email': email, 'result': result})

        return jsonify({'action': 'result', 'result': result})

def hash(s):
    m = hashlib.sha256()
    m.update(s.encode())
    m.digest()
    return int.from_bytes(m.digest(), "big")

def init_secret():
    S = random.randint(1, 19)
    db = sqlite3.connect('db.sqlite').cursor()
    db.execute('insert or replace into params values (?, ?)', ('secret', str(S)))

def init_master_key():
    mk = bsg.randLBElement()
    mk = bsg.serializeBraid(mk)
    db = sqlite3.connect('db.sqlite').cursor()
    db.execute('insert or replace into params values (?, ?)', ('master_key', str(mk)))

def create_polynomial(t):
    R, x = PolynomialRing(GF(config.p), 'x').objgen()
    f = R.random_element(t - 1)
    db = sqlite3.connect('db.sqlite').cursor()
    db.execute('select value from params where key = ?', ('secret',))
    S = int(db.fetchone()[0])
    f = f - f % x + S
    return f
from base64 import b64encode as b64
def try_access():
    db = sqlite3.connect('db.sqlite').cursor()
    db.execute('''select
    c.email, secret
    from credentials c
    inner
    join(select
    distinct(email)
    from auth where
    current_timestamp < datetime(timestamp, "+60 minutes")) as a
    on
    a.email = c.email;''')
    emails, secrets = zip(*[(x[0], x[1]) for x in db.fetchall()])
    db.execute('select value from params where key = ?', ('secret',))
    S_real = db.fetchone()[0]
    db.execute('select value from params where key = ?', ('master_key',))
    mk = db.fetchone()[0]
    mk = bsg.deserializeBraid(mk)
    p = config.p
    hashes = [hash(e) % p if hash(e) % p != 0 else 1 for e in emails]
    points = list(zip(hashes, secrets))
    print(points)
    R, x = PolynomialRing(GF(p), 'x').objgen()
    f = R.lagrange_polynomial(points)
    S = f%x
    print(f, S, S_real)
    assert(S == int(S_real))

    sign_k = mk ** int(S)

    r = requests.get(f"{LAB_SERVER}/auth")
    msg = r.json()['msg']
    msg_h = bsg.hash1(msg)
    print(msg_h)

    sign = bsg.serializeBraid(sign_k * msg_h / sign_k)
    requests.post(f"{LAB_SERVER}/auth", json={'msg': msg, 'sign': sign, 'emails': emails})

def generate_keys(emails_list_path):
    db = sqlite3.connect('db.sqlite').cursor()
    with open(emails_list_path, 'r') as f:
        emails = [x[:-1] for x in f.readlines()]
    init_secret()
    init_master_key()
    f = create_polynomial(ceil(len(emails) * 0.6))
    for e in emails:
        p = config.p
        h = hash(e) % p if hash(e) % p != 0 else 1
        key = f(h)
        db.execute('insert or replace into credentials values (?, ?)', (e, str(int(key))))

        with open(f'certs/{e}.json', 'w') as c_f:
            json.dump({
                'email': e,
                'key': bsg.serializeBraid(bsg.hash1(str(key)))
            }, c_f)
            
    db.connection.commit()

def stat_info_reporter():
    db = sqlite3.connect('db.sqlite').cursor()
    db = sqlite3.connect('db.sqlite').cursor()
    while True:
        db.execute('select count(distinct(email)) from auth where current_timestamp < datetime(timestamp,"+60 minutes");')
        accessed_accounts = db.fetchone()[0]
        socketio.emit('accessed_accounts_number', {'accessed_accounts': accessed_accounts})
        sleep(0.5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--command", help="command")
    parser.add_argument("-e", "--emails", help="path to email list file")
    args = parser.parse_args()

    if args.command == 'generate_keys':
        generate_keys(args.emails)
    else:
        logging.basicConfig(level=logging.INFO,
            format='%(asctime)s %(levelname)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
        info_thread = Thread(None, stat_info_reporter, 'stat_info_reporter')
        info_thread.start()
        socketio.run(app, port=5080)
        info_thread.stop()