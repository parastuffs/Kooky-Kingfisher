#!/usr/bin/env python3
"""
Usage:
    delete_buffers.py [-d <DEF_file>] [-v <Verilog_file>]
    delete_buffers.py (--help|-h)

Options:
    -d <DEF_file>       Path to input DEF file
    -v <Verilog_file>   Path to input Verilog file
    -h --help           Print this help

"""

import datetime
import os
from docopt import docopt
import logging, logging.config
import sys
from alive_progress import alive_bar

if __name__ == "__main__":

    args = docopt(__doc__)

    designName = ""
    defFile = None
    verilogFile = None

    if args["-d"]:
        defFile = args["-d"]
        designName = defFile.split(os.sep)[-1].replace('.def', '')
    if args["-v"]:
        verilogFile = args["-v"]


    # Create the directory for the output.
    rootDir = os.getcwd()
    output_dir = os.sep.join([rootDir, "{}_{}".format(datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), designName)])

    try:
        os.makedirs(output_dir)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

    # Load base config from conf file.
    logging.config.fileConfig('log.conf')
    # Load logger from config
    logger = logging.getLogger('default')
    # Create new file handler
    fh = logging.FileHandler(os.path.join(output_dir, 'delete_buffers_' + datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + '.log'))
    # Set a format for the file handler
    fh.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))
    # Add the handler to the logger
    logger.addHandler(fh)

    logger.info("Let's go")