import logging
import sys
import os

import openerp

from command import Command, main

import deploy
import scaffold
import server
import start
from . import celery  # noqa
