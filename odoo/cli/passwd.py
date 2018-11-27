#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------
# Copyright (c) Merchise Autrement [~º/~] and Contributors
# All rights reserved.
#
# This is free software; you can do what the LICENCE file allows you to.
#
from __future__ import (division as _py3_division,
                        print_function as _py3_print,
                        absolute_import as _py3_abs_import)


import sys
from . import Command

from passlib.context import CryptContext
crypt_context = CryptContext(schemes=['pbkdf2_sha512', 'plaintext'],
                             deprecated=['plaintext'])


class Passwd(Command):
    def run(self, argv):
        if not argv:
            print('Provide the password to hash', file=sys.stderr)
            exit(1)
        else:
            clear = argv[0]
            print(crypt_context.encrypt(clear))
