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
        Dictionary with the macros {macro name : {pin name : direction <INPUT, OUTPUT, INOUT>}}

    Return:
    -------
    n/a
    """
    pinBlock = False # True if we are in a PIN block.
    macroBlock = False # True if we are in a MACRO block.

    with open(file, 'r') as f:
        lines = f.readlines()

    with alive_bar(len(lines)) as bar:
        for line in lines:
            bar()
            line = line.strip()
            if 'MACRO' in line:
                macroName = line.split()[1] # The name of the macro is the second word in the line 'MACRO ...'
                macros[macroName] = dict()
                macroBlock = True
            elif macroBlock:
                if 'PIN' in line:
                    pinName = line.split()[1] # The name of the pin is the second word in the line 'PIN ...'

                elif 'DIRECTION' in line:
                    direction = line.split()[1] # the direction of the pin is the second word in the line 'DIRECTION ...'
                    macros[macroName][pinName] = direction
                elif line == f"END {macroName}":
                    macroBlock = False


def parseDEF(defFile, instances, netInstances, instanceNets):
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
    instanceNets : dict
        {instance name : {pin name, net name}}

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
                    match = re.search('- ([^\s]+) ([^\s]+) \+', line)
                    if match:
                        instance = match.group(1)
                        stdCell = match.group(2)
                        instances[instance] = stdCell
                        instanceNets[instance] = dict() # Preparing entry to be populated when parsing nets

                    # match = re.search('- ([^\s]+) \+ NET', line)
                    # if match:


                    match = re.search('^NETS (\d+)', line)
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

                        if ('ROUTED' in line or ";" in line or 'PROPERTY' in line or 'SOURCE' in line
                            or '+ USE' in line or '+ WEIGHT' in line or 'NONDEFAULTRULE' in line):
                            inNetDetails = False
                            # We reached the end of the relevant part

                        else:
                            # We are still in the 'connectivity' part of the net details
                            # Those lines look like:
                            #  ( u_logic_Pdi2z4_reg CK ) ( u_logic_Wai2z4_reg CK ) ( u_logic_U2x2z4_reg CK )
                            # with one or more parenthesis blocks
                            lineContent = line.split(')')
                            for candidate in lineContent:
                                match = re.search('\( ([^\s]+) ([^\s]+) ', candidate)
                                if match:
                                    instance = match.group(1)
                                    pin = match.group(2)
                                    netInstances[netName].append([instance, pin])
                                    if instance == "PIN" and instance not in instanceNets:
                                        # If the instance actually is a pin, there is not an
                                        # entry in the dictionary yet.
                                        instanceNets[instance] = dict()
                                    instanceNets[instance][pin] = netName





        logger.info("Found {} components out of {} expected ({}%)".format(len(instances), expectedComponents, 100*(len(instances)/expectedComponents)))
        logger.info("Found {} nets out of {} expected ({}%)".format(len(nets), expectedNets, 100*(len(nets)/expectedNets)))

        # logger.debug("{}".format(netInstances))


def identifyBufferedNets(netInstances, buffCondition, instances, macros, instanceNets):
    """

    Parameters:
    -----------
    netInstances : dict
        {net name : [instance name, pin name]}
    buffCondition : str
        Starting string of instances name to remove
    instances : dict
        {instance name : stdCell name}
    macros : dict
        Dictionary with the macros {macro name : {pin name : direction <INPUT, OUTPUT, INOUT>}}
    instanceNets : dict
        {instance name : {pin name, net name}}

    Return:
    -------
    absorbingNets : dict
        {net name : [net names]}
        Key if the net absorbing the content of the nets in the array value

    """

    bufferedNets = set() # [net name]

    for netname in netInstances.keys():
        isBuffNet = False
        cells = netInstances[netname]
        for instance in cells:
            if instance[0].startswith(buffCondition):
                bufferedNets.add(netname)

    logger.info("Buffered nets: {}/{} ({}%)".format(len(bufferedNets), len(netInstances), len(bufferedNets)/len(netInstances)))

    absorbingNets = dict()  # {net name : [net names]}
                            # key is the absorbing net, values is a list of absorbed nets

    for buffNet in bufferedNets:
        cells = netInstances[buffNet]
        # logger.debug(f"buffNet: {buffNet}")
        for instance in cells:
            instanceName = instance[0]
            pinName = instance[1]
            # logger.debug(f"instanceName: {instanceName}")
            if instanceName == "PIN":
                # Net is connected to a PIN, not enough to conclude if the net is at the end or begining of the buffered path.
                continue
            macroPins = macros[instances[instanceName]]
            pinDir = macroPins[pinName]
            if (not instanceName.startswith(buffCondition) and
                pinDir == "OUTPUT"):
                # logger.info("Net {} is starting a buffer path.".format(buffNet))
                absorbingNets[buffNet] = list() # Empty list for now, will be populated with a list of nets to absorb later.

    for absorbingNet in absorbingNets.keys():
        absorbingNets[absorbingNet] = traceBufferPath(netInstances, buffCondition, instances, macros, absorbingNet, instanceNets)

    return absorbingNets


def traceBufferPath(netInstances, buffCondition, instances, macros, startingNet, instanceNets):
    """
    From a starting net with a buffer input, find the chain of nets that end up to
    one or several nets with only non-buffer cells.

    Parameters:
    -----------
    netInstances : dict
        {net name : [instance name, pin name]}
    macros : dict
        Dictionary with the macros {macro name : {pin name : direction <INPUT, OUTPUT, INOUT>}}
    instances : dict
        {instance name : stdCell name}
    instanceNets : dict
        {instance name : {pin name, net name}}

    Return:
    -------
    list()
        List of net names in the buffer path
    """

    fullPath = list() # List of net names constituing the buffer path
    for instance in netInstances[startingNet]:
        instanceName = instance[0]
        pinName = instance[1]
        if instanceName.startswith(buffCondition):
            bufferStdCell = instances[instanceName]
            pinDirection = macros[bufferStdCell][pinName]
            if pinDirection == "INPUT":
                # Net is an input for a buffer.
                # Need to find where is its output.
                # logger.debug("In net {}, buffer {} has input pin.".format(startingNet, instanceName))
                for pinName in instanceNets[instanceName].keys():
                    if macros[bufferStdCell][pinName] == "OUTPUT":
                        outputNet = instanceNets[instanceName][pinName]
                        # logger.debug("  Other side of buffer is net {}".format(outputNet))
                        fullPath.append(outputNet)
                        # logger.debug("  Jump into that one to see if there are other buffer.")
                        fullPath.extend(traceBufferPath(netInstances, buffCondition, instances, macros, outputNet, instanceNets))
    return fullPath



def deleteBuffers(defFile, macros, instances, netInstances, buffCondition, bufferedNets):
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
        Dictionary with the macros {macro name : {pin name : direction <INPUT, OUTPUT, INOUT>}}
    buffCondition : str
        Starting string of instances name to remove
    bufferedNets : dict
        {net name : [net names]}
        Key if the net absorbing the content of the nets in the array value

    Return:
    -------
    str
        String holding the new DEF file
    """

    inComponents = False
    inNets = False
    deletingComponent = False
    deletingNet = False
    newDEFStr = ""
    deletedBuffers = 0 # Count of deleted buffers
    deletedNets = 0 # Count of deleted nets
    componentsCount = 0 # Count of components as stated on the COMPONENTS xxx line in DEF file.
    netsCount = 0 # Count of nets as stated on the NETS xxx line in DEF file.

    ######################
    # New DEF file header
    newDEFStr += "# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
    newDEFStr += f"# DEF file devoid of buffer instances starting with '{buffCondition}'"
    newDEFStr += f"# This file was generated on {datetime.datetime.now().strftime('%Y-%m-%d %H-%M-%S')} with {os.path.basename(__file__)}"
    newDEFStr += f"# The original DEF file was located in {defFile}"
    newDEFStr += "# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"

    #######################################################################
    # Preprocessing buffered nets to list nets to delete when seeing them.
    netsToDelete = list()
    for bufferPath in bufferedNets.values():
        netsToDelete.extend(bufferPath)
    # logger.debug(netsToDelete)


    with open(defFile, 'r') as f:
        lines = f.readlines()

    with alive_bar(len(lines)) as bar:
        for line in lines:
            bar()
            # logger.debug("Analysing line:")
            # logger.debug(line)
            if not inComponents and not inNets:
                ##############################################
                # Try to see if we enter the COMPONENTS scope
                match = re.search('COMPONENTS (\d+)', line)
                if match:
                    inComponents = True
                    componentsCount = int(match.group(1)) # Get amount of components
                ########################################
                # Try to see if we enter the NETS scope
                else:
                    match = re.search('^NETS (\d+)', line)
                    if match:
                        # logger.debug("Entering nets")
                        netsCount = int(match.group(1))
                        inNets = True

            elif inComponents:
                if line.strip() == "END COMPONENTS":
                    inComponents = False
                    newDEFStr = newDEFStr.replace(f"COMPONENTS {componentsCount}", f"COMPONENTS {componentsCount-deletedBuffers}") # Replace amount of components
                    logger.info(f"Deleted {deletedBuffers} buffers out of {componentsCount} instances in COMPONENTS")
                # Typical line for components looks like:
                # - DFFSR_692 DFFSR + PLACED ( 40 50 ) FS 
                match = re.search('- ([^\s]+) ([^\s]+) \+', line)
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

            #####################################
            # In nets, merging the buffered ones
            elif inNets:

                ######################################
                # End of NETS scope, update the count
                if line.strip() == "END NETS":
                    inNets = False
                    newDEFStr = newDEFStr.replace(f"NETS {netsCount}", f"NETS {netsCount - deletedNets}") # Replace amount of nets
                    logger.info(f"Deleted {deletedNets} nets out of {netsCount}")
                match = re.search('- ([^\s\n]+)', line)
                if match:
                    netName = match.group(1)

                    if netName in netsToDelete:
                        ##############################################
                        # Net on a buffer path, but not at the start,
                        # Just delete it.
                        # logger.debug('{} is marked to be deleted, start skipping lines.'.format(netName))
                        deletingNet = True

                    elif netName in bufferedNets:
                        #########################################
                        # This is a buffered net path
                        # We will create a new one from scratch

                        # First, get a list of instance/pins from the source net,
                        # *except* the buffers, obviously

                        # logger.debug(f"{netName} is starting a buffered path.")
                        newNetInstances = list() # [ [instance, pin] ... ]
                        for instancePair in netInstances[netName]:
                            if not instancePair[0].startswith(buffCondition):
                                newNetInstances.append(instancePair)
                        for buffNet in bufferedNets[netName]:
                            for instancePair in netInstances[buffNet]:
                                if not instancePair[0].startswith(buffCondition):
                                    newNetInstances.append(instancePair)
                        newNetStr = f"- {netName}\n"
                        for pair in newNetInstances:
                            newNetStr += f"  ( {pair[0]} {pair[1]} )\n"
                        newNetStr += ";\n"
                        # logger.debug("Here is the new entry for the DEF file:")
                        # logger.debug(newNetStr)
                        newDEFStr += newNetStr

                        deletedNets += len(bufferedNets[netName])

                        deletingNet = True

                    else:
                        # Not a buffered net, continue copying the original DEF file
                        pass

                if deletingNet and ';' in line:
                    # logger.debug("Line is '{}', stop deleting".format(line))
                    deletingNet = False
                    continue

            if not deletingComponent and not deletingNet:
                # logger.debug(f"deletingComponent: {deletingComponent}, deletingNet: {deletingNet}, writing line '{line}'")
                newDEFStr += line
            # else:
            #     logger.debug(f"deletingComponent: {deletingComponent}, deletingNet: {deletingNet}, not writing line.")
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
    instanceNets = dict()   # {instance name : {pin name, net name}} 
                            # Allows to quicky find nets connected to a cell
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

    logger.info("Reading LEF file {}".format(lefFile))
    parse_lef(lefFile, macros)

    logger.info("Parsing DEF file...")
    parseDEF(defFile, instances, netInstances, instanceNets)

    logger.info("Identify buffered nets...")
    bufferedNets = identifyBufferedNets(netInstances, buffCondition, instances, macros, instanceNets)

    logger.info("Delete buffers from DEF file...")
    DEFStr = deleteBuffers(defFile, macros, instances, netInstances, buffCondition, bufferedNets)

    newDEFFilePath = os.sep.join([output_dir, f"{designName}_noBuffers.def"])
    logger.info(f"Write new DEF file to {newDEFFilePath}")
    with open(newDEFFilePath, 'w') as f:
        f.write(DEFStr)