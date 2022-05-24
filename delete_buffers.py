#!/usr/bin/env python3
"""
Usage:
    delete_buffers.py [-d <DEF_file>] [-v <Verilog_file>] [-l <LEF_file>] [--buff=<BUFFER_START>]
    delete_buffers.py (--help|-h)

Options:
    -d <DEF_file>           Path to input DEF file
    -v <Verilog_file>       Path to input Verilog file
    -l <LEF_file>           Path to LEF file used for the design
    --buff=<BUFFER_START>   Starting characters of the buffer instance name to delete
    -h --help               Print this help

"""

import datetime
import os
from docopt import docopt
import logging, logging.config
from alive_progress import alive_bar
import re



def parse_lef(file, macros):
    """
    Parse lef file to extract the macros name and pin direction.

    Parameters:
    -----------
    file : str
        Path to LEF file
    macros : dict
        Dictionary with the macros {macro name : [pin name, direction <INPUT, OUTPUT, INOUT>]}

    Return:
    -------
    n/a
    """
    pinBlock = False # True if we are in a PIN block.
    macroBlock = False # True if we are in a MACRO block.

    logger.info("Reading LEF file {}".format(file))

    with open(file, 'r') as f:
        lines = f.readlines()

    with alive_bar(len(lines)) as bar:
        for line in lines:
            bar()
            line = line.strip()
            if 'MACRO' in line:
                macroName = line.split()[1] # The name of the macro is the second word in the line 'MACRO ...'
                macros[macroName] = list()
                macroBlock = True
            elif macroBlock:
                if 'PIN' in line:
                    pinName = line.split()[1] # The name of the pin is the second word in the line 'PIN ...'

                elif 'DIRECTION' in line:
                    direction = line.split()[1] # the direction of the pin is the second word in the line 'DIRECTION ...'
                    macros[macroName].append([pinName, direction])
                elif line == f"END {macroName}":
                    macroBlock = False
                    logger.debug("Leaving macro block")


def parseDEF(defFile, instances, netInstances):
    """
    Parse the DEF file to extract the components/nets relationships.

    Parameters:
    -----------
    defFile : str
        Path to DEF file.
    instances : dict
        {instance name : stdCell name}
    netInstances : dict
        {net name : [instance name, pin name]}

    Return:
    -------
    n/a
    """
    with open(defFile, 'r') as f:
        lines = f.readlines()

    expectedComponents = -1 # Number of components as stated on the 'COMPONENTS xxx' line
    expectedNets = -1
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


def deleteBuffers(defFile, macros, instances, netInstances, buffCondition):
    """
    Delete buffer paths from DEF file.

    Parameters:
    -----------
    defFile : str
        Path to DEF file.
    instances : dict
        {instance name : stdCell name}
    netInstances : dict
        {net name : [instance name, pin name]}
    macros : dict
        Dictionary with the macros {macro name : [pin name, direction <INPUT, OUTPUT, INOUT>]}
    buffCondition : str
        Starting string of instances name to remove

    Return:
    -------
    str
        String holding the new DEF file
    """

    inComponents = False
    deletingComponent = False
    newDEFStr = ""
    deletedBuffers = 0 # Count of deleted buffers
    components = 0 # Count of components as stated on the COMPONENTS xxx line in DEF file.

    with open(defFile, 'r') as f:
        lines = f.readlines()

    with alive_bar(len(lines)) as bar:
        for line in lines:
            bar()
            if not inComponents:
                match = re.search('COMPONENTS (\d+)', line)
                if match:
                    inComponents = True
                    components = int(match.group(1)) # Get amount of components
            elif inComponents:
                if line.strip() == "END COMPONENTS":
                    inComponents = False
                    newDEFStr = newDEFStr.replace(f"COMPONENTS {components}", f"COMPONENTS {components-deletedBuffers}") # Replace amount of components
                    logger.info(f"Deleted {deletedBuffers} buffers out of {components} instances in COMPONENTS")
                # Typical line for components looks like:
                # - DFFSR_692 DFFSR + PLACED ( 40 50 ) FS 
                match = re.search('- ([^\s]+) ([^\s]+) \+ PLACED', line)
                if match:
                    instance = match.group(1)
                    stdCell = match.group(2)
                    if instance.startswith(buffCondition):
                        # logger.info("We should delete {}".format(instance))
                        deletingComponent = True
                        deletedBuffers += 1
                if deletingComponent and ';' in line:
                    deletingComponent = False
                    continue
            if not deletingComponent:
                newDEFStr += line
    return newDEFStr







if __name__ == "__main__":

    args = docopt(__doc__)

    designName = ""
    defFile = None
    verilogFile = None
    lefFile = None
    macros = dict() # {macro name : [pin name, direction <INPUT, OUTPUT, INOUT>]}
    instances = dict() # {instance name : stdCell name}
    netInstances = dict() # {net name : [instance name, pin name]}
    buffCondition = "FE"


    ################
    # CLI arguments
    ################
    if args["-d"]:
        defFile = args["-d"]
        designName = defFile.split(os.sep)[-1].replace('.def', '')
    if args["-v"]:
        verilogFile = args["-v"]
    if args["-l"]:
        lefFile = args["-l"]
    if args["--buff"]:
        buffCondition = args["--buff"]

    ######################################
    # Create the directory for the output
    ######################################
    rootDir = os.getcwd()
    output_dir = os.sep.join([rootDir, "{}_{}".format(datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), designName)])
    try:
        os.makedirs(output_dir)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

    #########################
    # Log file configuration
    #########################
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

    logger.debug(args)

    parse_lef(lefFile, macros)

    parseDEF(defFile, instances, netInstances)

    DEFStr = deleteBuffers(defFile, macros, instances, netInstances, buffCondition)
    with open(os.sep.join([output_dir, f"{designName}_noBuffers.def"]), 'w') as f:
        f.write(DEFStr)