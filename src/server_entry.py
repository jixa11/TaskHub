# -*- coding: utf-8 -*-
"""Console entry point for running TaskHub behind IIS/ARR."""
import sys

if '--server' not in sys.argv:
    sys.argv.append('--server')

from taskhub import main

if __name__ == '__main__':
    main()
