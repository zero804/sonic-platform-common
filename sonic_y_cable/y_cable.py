#
# y_cable.py
#
#  definitions for implementing Y cable access and configurations
#   API's for Y cable functionality in SONiC

try:
    import struct
    from sonic_py_common import logger
    import sonic_platform.platform
except ImportError as e:
    # When build python3 xcvrd, it tries to do basic check which will import this file. However,
    # not all platform supports python3 API now, so it could cause an issue when importing 
    # sonic_platform.platform. We skip the ImportError here. This is safe because:
    #   1. If any python package is not available, there will be exception when use it
    #   2. Vendors know their platform API version, they are responsible to use correct python
    #   version when importing this file.
    pass

# definitions of the offset with width accommodated for values
# of MUX register specs of upper page 0x04 starting at 640
# info eeprom for Y Cable
Y_CABLE_IDENTFIER_LOWER_PAGE = 0
Y_CABLE_IDENTFIER_UPPER_PAGE = 128
Y_CABLE_DETERMINE_CABLE_READ_SIDE = 640
Y_CABLE_CHECK_LINK_ACTIVE = 641
Y_CABLE_SWITCH_MUX_DIRECTION = 642
Y_CABLE_MUX_DIRECTION = 644
Y_CABLE_ACTIVE_TOR_INDICATOR = 645
Y_CABLE_MANUAL_SWITCH_COUNT = 669

SYSLOG_IDENTIFIER = "sonic_y_cable"

# Global logger instance for helper functions and classes to log
helper_logger = logger.Logger(SYSLOG_IDENTIFIER)

# Global platform_chassis instance to call get_sfp required for read/write eeprom
platform_chassis = None

try:
    platform_chassis = sonic_platform.platform.Platform().get_chassis()
    helper_logger.log_info("chassis loaded {}".format(platform_chassis))
except Exception as e:
    helper_logger.log_warning("Failed to load chassis due to {}".format(repr(e)))


def hook_y_cable_simulator(target):
    """Decorator to add hook for calling y_cable_simulator_client.

    This decorator updates the y_cable driver functions to call hook functions defined in the y_cable_simulator_client
    module if importing the module is successful. If importing the y_cable_simulator_client module failed, just call
    the original y_cable driver functions defined in this module.

    Args:
        target (function): The y_cable driver function to be updated.
    """
    def wrapper(*args, **kwargs):
        try:
            import y_cable_simulator_client
            y_cable_func = getattr(y_cable_simulator_client, target.__name__, None)
            if y_cable_func and callable(y_cable_func):
                return y_cable_func(*args, **kwargs)
            else:
                return target(*args, **kwargs)
        except ImportError:
            return target(*args, **kwargs)
    wrapper.__name__ = target.__name__
    return wrapper


@hook_y_cable_simulator
def toggle_mux_to_torA(physical_port):
    """
    This API specifically does a hard switch toggle of the Y cable's MUX regardless of link state to
    TOR A. This means if the Y cable is actively routing, the "check_active_linked_tor_side(physical_port)"
    API will now return Tor A. It also implies that if the link is actively routing on this port, Y cable
    MUX will start forwarding packets from TOR A to NIC, and drop packets from TOR B to NIC
    regardless of previous forwarding state. This API basically writes to upper page 4 offset 130 the
    value of 0x2 and expects the MUX to toggle to TOR A. Bit 0 value 0 means TOR A.

    Register Specification at offset 130 is documented below

    Byte offset   bits     Name                    Description
    130           7-2      Reserved                Reserved
                  1        Hard vs. soft switch    0b0 - Switch only if a valid TOR link on target; 0b1 Switch to new target regardless of link status
                  0        Switch Target           Switch Target - 0b0 - TOR#1, 0b1 - TOR#2; default is TOR #1

    Args:
         physical_port:
             an Integer, the actual physical port connected to Y end of a Y cable which can toggle the MUX

    Returns:
        a Boolean, true if the toggle succeeded and false if it did not succeed.
    """

    buffer = bytearray([2])
    curr_offset = Y_CABLE_SWITCH_MUX_DIRECTION

    if platform_chassis is not None:
        result = platform_chassis.get_sfp(
            physical_port).write_eeprom(curr_offset, 1, buffer)
    else:
        helper_logger.log_error("platform_chassis is not loaded, failed to toggle mux to TOR A")
        return False

    return result


@hook_y_cable_simulator
def toggle_mux_to_torB(physical_port):
    """
    This API specifically does a hard switch toggle of the Y cable's MUX regardless of link state to
    TOR B. This means if the Y cable is actively routing, the "check_active_linked_tor_side(physical_port)"
    API will now return Tor B. It also implies that if the link is actively routing on this port, Y cable
    MUX will start forwarding packets from TOR B to NIC, and drop packets from TOR A to NIC
    regardless of previous forwarding state. API basically writes to upper page 4 offset 130 the value
    of 0x3 and expects the MUX to toggle to TOR B. Bit 0 value 1 means TOR B

    Register Specification at offset 130 is documented below

    Byte offset   bits      Name                   Description
    130           7-2       Reserved               Reserved
                  1         Hard vs. soft switch   0b0 - Switch only if a valid TOR link on target; 0b1 Switch to new target regardless of link status
                  0         Switch Target          Switch Target - 0b0 - TOR#1, 0b1 - TOR#2; default is TOR #1

    Args:
         physical_port:
             an Integer, the actual physical port connected to Y end of a Y cable which can toggle the MUX

    Returns:
        a Boolean, true if the toggle succeeded and false if it did not succeed.
    """

    buffer = bytearray([3])
    curr_offset = Y_CABLE_SWITCH_MUX_DIRECTION

    if platform_chassis is not None:
        result = platform_chassis.get_sfp(
            physical_port).write_eeprom(curr_offset, 1, buffer)
    else:
        helper_logger.log_error("platform_chassis is not loaded, failed to toggle mux to TOR B")
        return False

    return result


@hook_y_cable_simulator
def check_read_side(physical_port):
    """
    This API specifically checks which side of the Y cable the reads are actually getting performed
    from, either TOR A or TOR B or NIC and returns the value. API basically reads 1 byte at upper
    page 4 offset 128 and checks which side of the Y cable the read is being performed from.

    Register Specification of upper page 0x4 at offset 128 is documented below

    Byte offset   bits     Name                    Description
                  7-3      Reserved                Determine which side of the cable you are reading from - specifically to differentiate TOR #1 and TOR #2:
                                                   0b1 : Reading from indicated side, 0b0 not reading from that side.
                  2        TOR #1 Side
                  1        TOR #2 Side
                  0        NIC Side
    Args:
         physical_port:
             an Integer, the actual physical port connected to Y end of a Y cable which can which side reading the MUX from

    Returns:
        an Integer, 1 if reading the Y cable from TOR A side(TOR 1).
                  , 2 if reading the Y cable from TOR B side(TOR 2).
                  , 0 if reading the Y cable from NIC side.
                  , -1 if reading the Y cable API fails.
    """

    curr_offset = Y_CABLE_DETERMINE_CABLE_READ_SIDE

    if platform_chassis is not None:
        result = platform_chassis.get_sfp(
            physical_port).read_eeprom(curr_offset, 1)
    else:
        helper_logger.log_error("platform_chassis is not loaded, failed to check read side")
        return -1

    if result is not None:
        if isinstance(result, bytearray):
            if len(result) != 1:
                helper_logger.log_error("Error: for checking mux_cable read side, eeprom read returned a size {} not equal to 1 for port {}".format(
                    len(result), physical_port))
                return -1
        else:
            helper_logger.log_error("Error: for checking mux_cable read_side, eeprom read returned an instance value of type {} which is not a bytearray for port {}".format(
                type(result), physical_port))
            return -1
    else:
        helper_logger.log_error(
            "Error: for checking mux_cable read_side, eeprom read returned a None value for port {} which is not expected".format(physical_port))
        return -1

    regval_read = struct.unpack(">B", result)

    if ((regval_read[0] >> 2) & 0x01):
        helper_logger.log_info("Reading from TOR A")
        return 1
    elif ((regval_read[0] >> 1) & 0x01):
        helper_logger.log_info("Reading from TOR B")
        return 2
    elif (regval_read[0] & 0x01):
        helper_logger.log_info("Reading from NIC side")
        return 0
    else:
        helper_logger.log_error(
            "Error: unknown status for checking which side regval = {} ".format(result))

    return -1


@hook_y_cable_simulator
def check_mux_direction(physical_port):
    """
    This API specifically checks which side of the Y cable mux is currently point to
    and returns either TOR A or TOR B. API basically reads 1 byte at upper page 4 offset 132
    and checks which side the mux is pointing to


    Register Specification of upper page 0x4 at offset 133 is documented below

    Byte offset   bits     Name                           Description
    132           7-0      MUX Switch Status Register     0x00 : MUX pointing at TOR#2, 0x01 MUX pointing at TOR#1 regardless of connection status

    Args:
         physical_port:
             an Integer, the actual physical port connected to a Y cable

    Returns:
        an Integer, 1 if the mux is pointing to TOR A .
                  , 2 if the mux is pointing to TOR B.
                  , -1 if checking which side mux is pointing to API fails.
    """

    curr_offset = Y_CABLE_MUX_DIRECTION

    if platform_chassis is not None:
        result = platform_chassis.get_sfp(
            physical_port).read_eeprom(curr_offset, 1)
    else:
        helper_logger.log_error("platform_chassis is not loaded, failed to check Active Linked and routing TOR side")
        return -1

    if result is not None:
        if isinstance(result, bytearray):
            if len(result) != 1:
                helper_logger.log_error("Error: for checking mux_cable mux pointing side, eeprom read returned a size {} not equal to 1 for port {}".format(
                    len(result), physical_port))
                return -1
        else:
            helper_logger.log_error("Error: for checking mux_cable mux pointing side, eeprom read returned an instance value of type {} which is not a bytearray for port {}".format(
                type(result), physical_port))
            return -1
    else:
        helper_logger.log_error(
            "Error: for checking mux_cable mux pointing side, eeprom read returned a None value from eeprom read for port {} which is not expected".format(physical_port))
        return -1

    regval_read = struct.unpack(">B", result)

    if ((regval_read[0]) & 0x01):
        helper_logger.log_info("mux pointing to TOR A")
        return 1
    elif regval_read[0] == 0:
        helper_logger.log_info("mux pointing to TOR B")
        return 2
    else:
        helper_logger.log_error(
            "Error: unknown status for mux direction regval = {} ".format(result))
        return -1

    return -1


@hook_y_cable_simulator
def check_active_linked_tor_side(physical_port):
    """
    This API specifically checks which side of the Y cable is actively linked and routing
    and returns either TOR A or TOR B. API basically reads 1 byte at upper page 4 offset 133
    and checks which side is actively linked and routing.


    Register Specification of upper page 0x4 at offset 133 is documented below

    Byte offset   bits     Name                     Description
    133           7-0      TOR Active Indicator     0x00, no sides linked and routing frames, 0x01 TOR #1 linked and routing, 0x02, TOR #2 linked and routing

    Args:
         physical_port:
             an Integer, the actual physical port connected to a Y cable

    Returns:
        an Integer, 1 if TOR A is actively linked and routing(TOR 1).
                  , 2 if TOR B is actively linked and routing(TOR 2).
                  , 0 if nothing linked and actively routing
                  , -1 if checking which side linked for routing API fails.
    """

    curr_offset = Y_CABLE_ACTIVE_TOR_INDICATOR

    if platform_chassis is not None:
        result = platform_chassis.get_sfp(
            physical_port).read_eeprom(curr_offset, 1)
    else:
        helper_logger.log_error("platform_chassis is not loaded, failed to check Active Linked and routing TOR side")
        return -1

    if result is not None:
        if isinstance(result, bytearray):
            if len(result) != 1:
                helper_logger.log_error("Error: for checking mux_cable active linked side, eeprom read returned a size {} not equal to 1 for port {}".format(
                    len(result), physical_port))
                return -1
        else:
            helper_logger.log_error("Error: for checking mux_cable active linked side, eeprom read returned an instance value of type {} which is not a bytearray for port {}".format(
                type(result), physical_port))
            return -1
    else:
        helper_logger.log_error(
            "Error: for checking mux_cable active linked side, eeprom read returned a None value from eeprom read for port {} which is not expected".format(physical_port))
        return -1

    regval_read = struct.unpack(">B", result)

    if ((regval_read[0] >> 1) & 0x01):
        helper_logger.log_info("TOR B active linked and actively routing")
        return 2
    elif ((regval_read[0]) & 0x01):
        helper_logger.log_info("TOR A standby linked and actively routing")
        return 1
    elif regval_read[0] == 0:
        helper_logger.log_info("Nothing linked for routing")
        return 0
    else:
        helper_logger.log_error(
            "Error: unknown status for active TOR regval = {} ".format(result))
        return -1

    return -1


@hook_y_cable_simulator
def check_if_link_is_active_for_NIC(physical_port):
    """
    This API specifically checks if NIC side of the Y cable's link is active
    API basically reads 1 byte at upper page 4 offset 129 and checks if the link is active on NIC side

    Register Specification of upper page 0x4 at offset 129 is documented below

    Byte offset   bits     Name                   Description
    129           7-3      Reserved               Cable link status is for each end.  0b1 : Link up, 0b0 link not up.
                  2        TOR #1 Side
                  1        TOR #2 Side
                  0        NIC Side

    Args:
        physical_port:
             an Integer, the actual physical port connected to a Y cable

    Returns:
        a boolean, true if the link is active
                 , false if the link is not active
    """
    curr_offset = Y_CABLE_CHECK_LINK_ACTIVE

    if platform_chassis is not None:
        result = platform_chassis.get_sfp(
            physical_port).read_eeprom(curr_offset, 1)
    else:
        helper_logger.log_error("platform_chassis is not loaded, failed to check if link is Active on NIC side")
        return -1

    if result is not None:
        if isinstance(result, bytearray):
            if len(result) != 1:
                helper_logger.log_error("Error: for checking mux_cable link is active on NIC side, eeprom read returned a size {} not equal to 1 for port {}".format(
                    len(result), physical_port))
                return -1
        else:
            helper_logger.log_error("Error: for checking mux_cable link is active on NIC side, eeprom read returned an instance value of type {} which is not a bytearray for port {}".format(
                type(result), physical_port))
            return -1
    else:
        helper_logger.log_error(
            "Error: for checking mux_cable link is active on NIC side, eeprom read returned a None value from eeprom read for port {} which is not expected".format(physical_port))
        return -1

    regval_read = struct.unpack(">B", result)

    if (regval_read[0] & 0x01):
        helper_logger.log_info("NIC link is up")
        return True
    else:
        return False


@hook_y_cable_simulator
def check_if_link_is_active_for_torA(physical_port):
    """
    This API specifically checks if TOR A side of the Y cable's link is active
    API basically reads 1 byte at upper page 4 offset 129 and checks if the link is active on NIC side

    Register Specification of upper page 0x4 at offset 129 is documented below

    Byte offset   bits     Name                    Description
    129           7-3      Reserved                Cable link status is for each end.  0b1 : Link up, 0b0 link not up.
                  2        TOR #1 Side
                  1        TOR #2 Side
                  0        NIC Side

    Args:
        physical_port:
             an Integer, the actual physical port connected to a Y cable

    Returns:
        a boolean, true if the link is active
                 , false if the link is not active
    """

    curr_offset = Y_CABLE_CHECK_LINK_ACTIVE

    if platform_chassis is not None:
        result = platform_chassis.get_sfp(
            physical_port).read_eeprom(curr_offset, 1)
    else:
        helper_logger.log_error("platform_chassis is not loaded, failed to check if link is Active on TOR A side")
        return -1

    if result is not None:
        if isinstance(result, bytearray):
            if len(result) != 1:
                helper_logger.log_error("Error: for checking mux_cable link is active on TOR A side, eeprom read returned a size {} not equal to 1 for port {}".format(
                    len(result), physical_port))
                return -1
        else:
            helper_logger.log_error("Error: for checking mux_cable link is active on TOR A side, eeprom read returned an instance value of type {} which is not a bytearray for port {}".format(
                type(result), physical_port))
            return -1
    else:
        helper_logger.log_error(
            "Error: for checking mux_cable link is active on TOR A side, eeprom read returned a None value from eeprom read for port {} which is not expected".format(physical_port))
        return -1

    regval_read = struct.unpack(">B", result)

    if ((regval_read[0] >> 2) & 0x01):
        helper_logger.log_info("TOR A link is up")
        return True
    else:
        return False


@hook_y_cable_simulator
def check_if_link_is_active_for_torB(physical_port):
    """
    This API specifically checks if TOR B side of the Y cable's link is active
    API basically reads 1 byte at upper page 4 offset 129 and checks if the link is active on NIC side

    Register Specification of upper page 0x4 at offset 129 is documented below

    Byte offset   bits    Name                  Description
    129           7-3     Reserved              Cable link status is for each end.  0b1 : Link up, 0b0 link not up.
                  2       TOR #1 Side
                  1       TOR #2 Side
                  0       NIC Side

    Args:
        physical_port:
             an Integer, the actual physical port connected to a Y cable

    Returns:
        a boolean, true if the link is active
                 , false if the link is not active
    """

    curr_offset = Y_CABLE_CHECK_LINK_ACTIVE

    if platform_chassis is not None:
        result = platform_chassis.get_sfp(
            physical_port).read_eeprom(curr_offset, 1)
    else:
        helper_logger.log_error("platform_chassis is not loaded, failed to check if link is Active on TOR B side")
        return -1

    if result is not None:
        if isinstance(result, bytearray):
            if len(result) != 1:
                helper_logger.log_error("Error: for checking mux_cable link is active on TOR B side, eeprom read returned a size {} not equal to 1 for port {}".format(
                    len(result), physical_port))
                return -1
        else:
            helper_logger.log_error("Error: for checking mux_cable link is active on TOR B side, eeprom read returned an instance value of type {} which is not a bytearray for port {}".format(
                type(result), physical_port))
            return -1
    else:
        helper_logger.log_error(
            "Error: for checking mux_cable link is active on TOR B side, eeprom read returned a None value from eeprom read for port {} which is not expected".format(physical_port))
        return -1

    regval_read = struct.unpack(">B", result)

    if ((regval_read[0] >> 1) & 0x01):
        helper_logger.log_info("TOR B link is up")
        return True
    else:
        return False
