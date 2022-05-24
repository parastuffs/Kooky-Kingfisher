#!/usr/bin/env python3
"""
Usage:
    delete_buffers.py [-d <DEF_file>] [-v <Verilog_file>] [-l <LEF_file>]
    delete_buffers.py (--help|-h)

Options:
    -d <DEF_file>       Path to input DEF file
    -v <Verilog_file>   Path to input Verilog file
    -l <LEF_file>       Path to LEF file used for the design
    -h --help           Print this help

"""

import datetime
import os
from docopt import docopt
import logging, logging.config
from alive_progress import alive_bar
import re


def parseDEF(defFile):
    """
    Parse the DEF file to extract the components/nets relationships.

    Parameters:
    -----------
    defFile:str
        Path to DEF file.

    Return:
    -------
    n/a
    """
    with open(defFile, 'r') as f:
        lines = f.readlines()

    expectedComponents = -1 # Number of components as stated on the 'COMPONENTS xxx' line
    expectedNets = -1
    instances = dict() # {instance name : stdCell name}
    netInstances = dict() # {net name : [instance name, pin name]}
    inNetDetails = False
    nets = []

    logger.info("Parsing DEF file...")
    with alive_bar(len(lines)) as bar:
        for line in lines:
            bar()
            if expectedComponents == -1:
                # Typical line for components count look like:
                # COMPONENTS 10875 
                match = re.search('COMPONENTS (\d+)', line)
                if match:
                    expectedComponents = int(match.group(1))
                    logger.info("Expecting {} components".format(expectedComponents))

            # One we know the amount of components, it means we are entering the COMPONENTS part
            else:
                if expectedNets == -1:
                    # Typical line for components looks like:
                    # - DFFSR_692 DFFSR + PLACED ( 40 50 ) FS 
                    match = re.search('- ([^\s]+) ([^\s]+) \+ PLACED', line)
                    if match:
                        instance = match.group(1)
                        stdCell = match.group(2)
                        instances[instance] = stdCell

                    match = re.search('NETS (\d+)', line)
                    if match:
                        expectedNets = int(match.group(1))

                # Once we know the amount of nets, we get into the NETS block.
                # This is assuming that the nets are declared *after* the components.
                else:
                    # Once we reach the end of the nets description, quit the process.
                    if "END NETS" in line:
                        bar(len(lines)-bar.current()) # Jump the progress bar to the end
                        break
                    if not inNetDetails:
                        # Try to fetch a net name
                        match = re.search('- ([^\s\n]+)', line)
                        if match:
                            netName = match.group(1)
                            nets.append(netName)
                            netInstances[netName] = list() # Prepare entry in dictionary for later net details
                            inNetDetails = True
                    elif inNetDetails:
                        # We reached the end of the relevant part
                        if ('ROUTED' in line or ";" in line or 'PROPERTY' in line or 'SOURCE' in line
                            or '+ USE' in line or '+ WEIGHT' in line or 'NONDEFAULTRULE' in line):
                            inNetDetails = False
                        # We are still in the 'connectivity' part of the net details
                        # Those lines look like:
                        #  ( u_logic_Pdi2z4_reg CK ) ( u_logic_Wai2z4_reg CK ) ( u_logic_U2x2z4_reg CK )
                        # with one or more parenthesis blocks
                        else:
                            lineContent = line.split(')')
                            for candidate in lineContent:
                                match = re.search('\( ([^\s]+) ([^\s]+) ', candidate)
                                if match:
                                    instance = match.group(1)
                                    pin = match.group(2)
                                    netInstances[netName].append([instance, pin])





        logger.info("Found {} components out of {} expected ({}%)".format(len(instances), expectedComponents, 100*(len(instances)/expectedComponents)))
        logger.info("Found {} nets ou of {} expected ({}%)".format(len(nets), expectedNets, 100*(len(nets)/expectedNets)))

        # logger.debug("{}".format(netInstances))






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

    parseDEF(defFile)