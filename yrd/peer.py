from .arg import arg, wrap_errors
from . import xcjdns as cjdns
from . import cjdns as cj
from . import utils
from .const import YRD_INBOUND, YRD_OUTBOUND, CJDROUTE_CONF, CJDROUTE_BIN
import socket
import json
import sys
import os


@arg('name', help='name of the peer')
@arg('password', nargs='?', help='Set peering password')
@arg('-l', '--live', help='Don\'t write to disk')
@arg('-s', '--silent', help='ignore already added error')
@wrap_errors([socket.error, IOError])
def auth(name, password, live=False, silent=False):
    'add a password for inbound connections'

    if '/' in name:
        yield 'nope'
        exit(1)

    path = os.path.join(YRD_INBOUND, name)
    if os.path.exists(path):
        with open(path) as f:
            password = json.load(f)['password']
    else:
        if not password:
            password = utils.generate_key(31)

        info = {
            'name': name,
            'password': password
        }

        if not live:
            with open(path, 'w') as f:
                f.write(json.dumps(info))

    conf = utils.load_conf(CJDROUTE_CONF, CJDROUTE_BIN)
    c = cj.connect('127.0.0.1', 11234, conf['admin']['password'])
    resp = c.AuthorizedPasswords_add(user=name, password=password)
    try:
        utils.raise_on_error(resp)
    except:
        if not silent:
            raise
    c.disconnect()

    publicKey = conf['publicKey']
    port = conf['interfaces']['UDPInterface'][0]['bind'].split(':')[1]

    yield utils.to_credstr(utils.get_ip(), port, publicKey, password)


@arg('name', help='the peers name')
@arg('source', nargs='?', help='read from file')
@arg('-l', '--live', help='Don\'t write to disk')
@wrap_errors([IOError])
def add(name, source, live=False):
    'add an outbound connection'
    if '/' in name:
        yield 'nope'
        exit(1)

    conf = utils.load_conf(CJDROUTE_CONF, CJDROUTE_BIN)
    c = cj.connect('127.0.0.1', 11234, conf['admin']['password'])

    path = os.path.join(YRD_OUTBOUND, name)
    source = source or path

    out = not live and open(path, 'w')
    source = sys.stdin if source == '-' else open(source)
    for auth in source:
        auth = auth.strip()

        if not auth:
            continue

        if out:
            print(auth, file=out)

        for addr, args in json.loads('{' + auth + '}').items():
            addr = utils.dns_resolve(addr)
            resp = c.UDPInterface_beginConnection(address=addr,
                                                  publicKey=args['publicKey'],
                                                  password=args['password'],
                                                  interfaceNumber=0)
            utils.raise_on_error(resp)
    c.disconnect()


@wrap_errors([IOError])
def ls():
    'list passwords for inbound connections'
    conf = utils.load_conf(CJDROUTE_CONF, CJDROUTE_BIN)
    c = cjdns.connect(password=conf['admin']['password'])
    for user in c.listPasswords()['users']:
        yield user
    c.disconnect()


@wrap_errors([IOError])
def rm(user):
    'unpeer a node'
    if '/' in user:
        yield 'nope'
        exit(1)

    for path in [YRD_INBOUND, YRD_OUTBOUND]:
        path = os.path.join(path, user)
        if os.path.exists(path):
            os.unlink(path)
            yield 'deleted %r' % path

    conf = utils.load_conf(CJDROUTE_CONF, CJDROUTE_BIN)
    c = cjdns.connect(password=conf['admin']['password'])
    c.removePassword(user)
    c.disconnect()


cmd = [auth, add, ls, rm]
