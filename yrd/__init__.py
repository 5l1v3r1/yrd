from .arg import ArghParser, dispatch
from . import start
from . import core
from . import peer


parser = ArghParser(description='cjdns swiss army knife')
parser.add_commands(start.cmd + core.cmd)
parser.add_commands(peer.cmd, namespace='peer', title='ctrl peers')


def main():
    try:
        dispatch(parser)
    except KeyboardInterrupt as e:
        pass


if __name__ == '__main__':
    main()
