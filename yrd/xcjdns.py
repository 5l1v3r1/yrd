from .cjdns.bencode import bencode, bdecode
from . import cjdns
from hashlib import sha512, sha256
import socket
import os

BUFFER_SIZE = 69632


class Cjdroute(object):
    def __init__(self, ip='127.0.0.1', port=11234, password=''):
        self.password = password

        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.connect((ip, port))
        self.s.settimeout(7)

        if not self.ping():
            raise Exception('Not a cjdns socket? (%s:%d)' % (ip, port))

    def disconnect(self):
        self.s.close()

    def recv(self):
        res = bdecode(self.s.recv(BUFFER_SIZE))
        if 'error' in res and res['error'] != 'none':
            raise Exception(repr(res))
        if os.getenv('YRD_DEBUG'):
            print(repr(res))  # DEBUG SWITCH
        return res

    def _send(self, **kwargs):
        self.s.send(bencode(kwargs).encode('ascii'))

    def send(self, **kwargs):
        if self.password:
            self._send(q='cookie')
            cookie = self.recv()['cookie']

            kwargs['hash'] = sha256((self.password + cookie).encode('ascii')).hexdigest()
            kwargs['cookie'] = cookie

            kwargs['aq'] = kwargs['q']
            kwargs['q'] = 'auth'
            kwargs['hash'] = sha256(bencode(kwargs).encode('ascii')).hexdigest()

        if os.getenv('YRD_DEBUG'):
            print(repr(kwargs))  # DEBUG SWITCH

        self._send(**kwargs)

    def poll(self, **kwargs):
        if 'args' not in kwargs:
            kwargs['args'] = {}
        kwargs['args']['page'] = 0

        while True:
            self.send(**kwargs)
            resp = self.recv()

            yield resp

            if 'more' not in resp:
                break

            kwargs['args']['page'] += 1

    def ping(self):
        self.send(q='ping')
        resp = self.recv()
        return 'q' in resp and resp['q'] == 'pong'

    def nodeForAddr(self, ip=None):
        q = dict(q='NodeStore_nodeForAddr')
        if ip:
            q['ip'] = ip
        self.send(**q)
        return self.recv()

    def dumpTable(self):
        for page in self.poll(q='NodeStore_dumpTable'):
            for route in page['routingTable']:
                yield route

    def sessionStats(self):
        for page in self.poll(q='SessionManager_getHandles'):
            for handle in page['handles']:
                self.send(q='SessionManager_sessionStats', args={
                    'handle': handle
                })
                yield self.recv()

    def search(self, addr, count=-1):
        self.send(q='SearchRunner_search',
                  args={'ipv6': addr, 'maxRequests': count})

        while True:
            x = self.recv()
            if 'complete' in x:
                break
            yield x

    def genericPing(self, q, path, timeout=5000):
        self.send(q=q, args={'path': path, 'timeout': timeout})
        return self.recv()

    def routerPing(self, *args, **kwargs):
        return self.genericPing('RouterModule_pingNode', *args, **kwargs)

    def switchPing(self, *args, **kwargs):
        return self.genericPing('SwitchPinger_ping', *args, **kwargs)

    def nextHop(self, target, lastNode):
        self.send(q='RouterModule_nextHop',
                  args={'target': target, 'nodeToQuery': lastNode})
        return self.recv()

    def getLink(self, target, num):
        self.send(q='NodeStore_getLink', args={'parent': target,
                                               'linkNum': num})
        return self.recv()

    def addPassword(self, name, password):
        self.send(q='AuthorizedPasswords_add',
                  args={'user': str(name), 'password': str(password)})

    def listPasswords(self):
        self.send(q='AuthorizedPasswords_list')
        return self.recv()

    def removePassword(self, user):
        self.send(q='AuthorizedPasswords_remove', args={'user': user})
        return self.recv()

    def udpBeginConnection(self, addr, pk, password):
        self.send(q='UDPInterface_beginConnection', args={'password': password,
                  'publicKey': pk, 'address': addr})
        return self.recv()

    def peerStats(self):
        for page in self.poll(q='InterfaceController_peerStats'):
            for i, args in page.items():
                if i == 'peers':
                    for peer in args:
                        yield Peer(**peer)


class Peer(object):
    def __init__(self, **kwargs):
        if 'ip' not in kwargs:
            if 'publicKey' in kwargs:
                kwargs['ip'] = pk2ipv6(kwargs['publicKey'])
            elif 'addr' in kwargs:
                kwargs['ip'] = addr2ip(kwargs['addr'])

        if 'path' not in kwargs and 'addr' in kwargs:
            kwargs['path'] = kwargs['addr'][4:23]

        if 'version' not in kwargs and 'addr' in kwargs:
            kwargs['version'] = kwargs['addr'][1:3]

        for x, y in kwargs.items():
            setattr(self, x, y)


def connect(ip='127.0.0.1', port=11234, password=''):
    return Cjdroute(ip, port, password)


# see util/Base32.h
def Base32_decode(input):
    output = bytearray(len(input))
    numForAscii = [
        99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99,
        99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99,
        99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99,
        0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 99, 99, 99, 99, 99, 99,
        99, 99, 10, 11, 12, 99, 13, 14, 15, 99, 16, 17, 18, 19, 20, 99,
        21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 99, 99, 99, 99, 99,
        99, 99, 10, 11, 12, 99, 13, 14, 15, 99, 16, 17, 18, 19, 20, 99,
        21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 99, 99, 99, 99, 99,
    ]

    outputIndex = 0
    inputIndex = 0
    nextByte = 0
    bits = 0

    while inputIndex < len(input):
        o = ord(input[inputIndex])
        if o & 0x80:
            raise ValueError
        b = numForAscii[o]
        inputIndex += 1
        if b > 31:
            raise ValueError("bad character " + input[inputIndex])

        nextByte |= b << bits
        bits += 5

        if bits >= 8:
            output[outputIndex] = nextByte & 0xff
            outputIndex += 1
            bits -= 8
            nextByte >>= 8

    if bits >= 5 or nextByte:
        raise ValueError("bits is %d and nextByte is %d" % (bits, nextByte))

    return buffer(output, 0, outputIndex)


def addr2ip(addr):
    return pk2ipv6(addr.split('.', 5)[-1])


pk2ipv6 = cjdns.PublicToIp6


def collect_from_address(addr):
    addrs = {}
    parts = len(addr.split('.'))

    if parts == 7:
        addrs['path'] = addr
    elif parts == 2:
        addrs['key'] = addr
    elif parts == 1:
        addrs['ip'] = addr
    else:
        raise ValueError('weird input')

    if 'path' in addrs and 'key' not in addrs:
        addrs['key'] = addrs['path'].split('.', 5)[-1]

    if 'key' in addrs and 'ip' not in addrs:
        addrs['ip'] = pk2ipv6(addrs['key'])

    return addrs
