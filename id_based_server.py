from flask import Flask, render_template, request, jsonify
from sage.all import *

from braid_group import BraidSignGroup
import logging, hashlib, random, argparse, requests
import config
CLIENT = "http://127.0.0.1:5080"
LAB_SERVER = "http://127.0.0.1:5082"

app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False

import sqlite3
db = sqlite3.connect('db.sqlite').cursor()
bsg = BraidSignGroup(config.braid['n'], config.braid['p'], config.braid['l'])

session = {}
def init_session(email):
    if email not in session:
        session[email] = {'secret_knowledge': {}}

@app.route('/',  methods=['GET'])
def index():
    return render_template('public/server.html')

@app.route('/secret_knowledge',  methods=['POST'])
def secret_knowledge():
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
        result = (r == 0 and c == y) | (r == 1 and c == b)
        if result:
            db.execute('insert into auth (email) values (?)', (email, ))
            db.connection.commit()
            db.execute('select count(distinct(email)) from auth where current_timestamp < datetime(timestamp,"+60 minutes");')
            if db.fetchone()[0] >= config.threshold:
                try_access()

        return jsonify({'action': 'result', 'result': result})

def hash(s):
    m = hashlib.sha256()
    m.update(s.encode())
    m.digest()
    return int.from_bytes(m.digest(), "big")

def init_secret():
    S = random.randint(1, 19)
    db.execute('insert or replace into params values (?, ?)', ('secret', str(S)))

def init_master_key():
    mk = bsg.randLBElement()
    mk = bsg.serializeBraid(mk)
    db.execute('insert or replace into params values (?, ?)', ('master_key', str(mk)))

def create_polynomial(t):
    print('t = ', t)
    R, x = PolynomialRing(GF(config.p), 'x').objgen()
    f = R.random_element(t - 1)
    db.execute('select value from params where key = ?', ('secret',))
    S = int(db.fetchone()[0])
    print(S)
    f = f - f % x + S
    return f
from base64 import b64encode as b64
def try_access():
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
    with open(emails_list_path, 'r') as f:
        emails = [x[:-1] for x in f.readlines()]
    init_secret()
    init_master_key()
    f = create_polynomial(ceil(len(emails) * 0.6))
    print(f)
    for e in emails:
        p = config.p
        h = hash(e) % p if hash(e) % p != 0 else 1
        key = f(h)
        print(h, key)
        db.execute('insert or replace into credentials values (?, ?)', (e, str(int(key))))
    db.connection.commit()

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
        app.run(port=5080)