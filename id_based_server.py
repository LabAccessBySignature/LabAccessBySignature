from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from sage.all import *
from threading import Thread
from time import sleep
import traceback

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
    db.execute('select current_timestamp, email, result from auth where current_timestamp < datetime(timestamp,"+60 minutes");')
    last_elements = [{'time': r[0], 'email': r[1], 'result': r[2]} for r in db.fetchall()]
    db.execute('select count(distinct(email)) from auth where current_timestamp < datetime(timestamp,"+60 minutes") and result="True";')
    accessed_accounts = db.fetchone()[0]
    return render_template('public/id_based_server.html', last_elements=last_elements, accessed_accounts=accessed_accounts)

@app.route('/secret_knowledge',  methods=['POST'])
def secret_knowledge():
    db = sqlite3.connect('db.sqlite').cursor()
    j = request.json
    if j['action'] == 'init':
        email = j['email']
        a = bsg.deserializeBraid(j['a'])
        b = bsg.deserializeBraid(j['b'])

        init_session(email)
        session[email]['secret_knowledge']['a'] = a
        session[email]['secret_knowledge']['b'] = b

        r = random.randint(config.r['min'], config.r['max'])
        session[email]['secret_knowledge']['r'] = r
        return jsonify({'action': 'multiplier', 'r': str(r)})
    if j['action'] == 'prove':
        email = j['email']
        c = bsg.deserializeBraid(j['c'])
        a = session[email]['secret_knowledge']['a']
        b = session[email]['secret_knowledge']['b']
        r = session[email]['secret_knowledge']['r']
        db.execute('select open_key_x, open_key_y from credentials where email=?;', (email,))
        open_keys = db.fetchone()
        if open_keys is None:
            db.execute('insert into auth (email, result) values (?, ?)', (email, 'False'))
            db.connection.commit()
            socketio.emit('new_access_request', {'email': email, 'result': 'False'})
            return jsonify({'action': 'result', 'result': 'False'})
        x, y = open_keys
        x = bsg.deserializeBraid(x)
        y = bsg.deserializeBraid(y)

        result = (((c/b).is_conjugated(x**r)) and ((y**(-r)*c).is_conjugated(a)))
        if result:
            db.execute('insert into auth (email, result) values (?, ?)', (email, 'True'))
            db.connection.commit()
            db.execute('select count(distinct(email)) from auth where current_timestamp < datetime(timestamp,"+60 minutes") and result = "True";')
            accepted = int(db.fetchone()[0])
            db.execute('select value from params where key="threshold";')
            threshold = int(db.fetchone()[0])
            if accepted >= threshold:
                result = try_access()
        else:
            db.execute('insert into auth (email, result) values (?, ?)', (email, 'False'))
            db.connection.commit()
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
    db.connection.commit()
    return S

def init_master_key():
    mk = bsg.randLBElement()
    db = sqlite3.connect('db.sqlite').cursor()
    db.execute('insert or replace into params values (?, ?)', ('master_key', bsg.serializeBraid(mk)))
    db.connection.commit()
    return mk

def init_open_keys(mk, s):
    x = bsg.randLBElement()
    mks = mk**s
    y = mks * x / mks
    with open(f'certs/lab_cert.json', 'w') as c_f:
        json.dump({
            'open_key': {
                'x': bsg.serializeBraid(x),
                'y': bsg.serializeBraid(y)
            }}, c_f)


def create_polynomial(t, S):
    R, x = PolynomialRing(GF(config.p), 'x').objgen()
    f = R.random_element(t - 1)
    f = f - f % x + S
    return f

def try_access():
    try:
        db = sqlite3.connect('db.sqlite').cursor()
        db.execute('''select
        c.email, secret_key
        from credentials c
        inner
        join(select
        distinct(email)
        from auth where
        current_timestamp < datetime(timestamp, "+60 minutes")) as a
        on
        a.email = c.email;''')
        emails, secrets = zip(*[(x[0], int(x[1])) for x in db.fetchall()])
        db.execute('select value from params where key = ?', ('secret',))
        S_real = db.fetchone()[0]
        db.execute('select value from params where key = ?', ('master_key',))
        mk = db.fetchone()[0]
        mk = bsg.deserializeBraid(mk)
        p = config.p
        hashes = [hash(e) % p if hash(e) % p != 0 else 1 for e in emails]
        points = list(zip(hashes, secrets))
        R, x = PolynomialRing(GF(p), 'x').objgen()
        f = R.lagrange_polynomial(points)
        S = f%x
        if S != int(S_real):
            return False

        sign_k = mk ** int(S)

        r = requests.get(f"{LAB_SERVER}/auth")
        msg = r.json()['msg']
        msg_h = bsg.hash1(msg)

        sign = bsg.serializeBraid(sign_k * msg_h / sign_k)
        resp = requests.post(f"{LAB_SERVER}/auth", json={'msg': msg, 'sign': sign, 'emails': emails})
        result = resp.json()['result'] == 'True'
        return result
    except:
        traceback.print_exc()
        return False

def generate_keys(emails_list):
    db = sqlite3.connect('db.sqlite').cursor()
    if ('.txt' in emails_list):
        with open(emails_list, 'r') as f:
            emails = [x[:-1] for x in f.readlines()]
    else:
        emails = emails_list.split()
    S = init_secret()
    mk = init_master_key()
    init_open_keys(mk, S)
    threshold = ceil(len(emails) * 0.6)
    db.execute('insert or replace into params values (?, ?)', ('threshold', str(threshold)))
    db.connection.commit()
    f = create_polynomial(threshold, S)
    for e in emails:
        p = config.p
        h = hash(e) % p if hash(e) % p != 0 else 1
        key = f(h)
        key_hash = bsg.hash1(str(key))
        x = bsg.randLBlElement()
        y = key_hash * x / key_hash
        key_hash = bsg.serializeBraid(key_hash)
        x = bsg.serializeBraid(x)
        y = bsg.serializeBraid(y)
        db.execute('delete from credentials where email == ?;', (e,))
        db.execute('insert or replace into credentials values (?, ?, ?, ?);', (e, str(int(key)), x, y))

        with open(f'certs/{e}.json', 'w') as c_f:
            json.dump({
                'email': e,
                'secrete_key': key_hash,
                'open_key': {
                    'x': x,
                    'y': y
                }
            }, c_f)
            
    db.connection.commit()

def revocation(emails_list):
    emails = emails_list.split()
    db = sqlite3.connect('db.sqlite').cursor()
    for e in emails:
        db.execute('delete from credentials where email == ?;', (e, ))
    db.execute("delete from auth;")
    db.connection.commit()
    db.execute('select distinct(email) from credentials;')
    new_emails_list = ' '.join([r[0] for r in db.fetchall()])
    generate_keys(new_emails_list)


def stat_info_reporter():
    db = sqlite3.connect('db.sqlite').cursor()
    while True:
        db.execute('select count(distinct(email)) from auth where current_timestamp < datetime(timestamp,"+60 minutes") and result = "True";')
        accessed_accounts = db.fetchone()[0]
        socketio.emit('accessed_accounts_number', {'accessed_accounts': accessed_accounts})
        sleep(0.5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--command", help="command")
    parser.add_argument("-e", "--emails", help="path to email list file / revocation list")
    args = parser.parse_args()

    if args.command == 'generate_keys':
        generate_keys(args.emails)
    elif args.command == 'revocation':
        revocation(args.emails)
    else:
        logging.basicConfig(level=logging.INFO,
            format='%(asctime)s %(levelname)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
        info_thread = Thread(None, stat_info_reporter, 'stat_info_reporter')
        info_thread.start()
        socketio.run(app, port=5080)
        info_thread.stop()