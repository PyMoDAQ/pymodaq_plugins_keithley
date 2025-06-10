import numpy as np
import pyvisa as visa
from pymodaq_plugins_keithley import config
from pymodaq.utils.logger import set_logger, get_module_name
logger = set_logger(get_module_name(__file__))


class Keithley27XXVISADriver:
    """VISA base class driver for Keithley 2700-2701-2750 drivers
    """

    # Modules specifications
    non_amp_module = {"MODULE01": False, "MODULE02": False}
    non_amp_modules_list = ['7701', '7703', '7706', '7707', '7708', '7709']
    automatic_cjc_modules_list = ['7700', '7706', '7708']

    # Channels & modes attributes
    model = ''
    channels_scan_list = ''
    modes_channels_dict = {'VOLT:DC': [],
                           'VOLT:AC': [],
                           'CURR:DC': [],
                           'CURR:AC': [],
                           'RES': [],
                           'FRES': [],
                           'FREQ': [],
                           'TEMP': []}
    sample_count_1 = False
    reading_scan_list = False
    current_mode = ''

    def __init__(self, rsrc_name):
        """Initialize KeithleyVISADriver class

        :param rsrc_name: VISA Resource name
        :type rsrc_name: string
        """
        self._instr = None
        self.rsrc_name = rsrc_name
        self.instr = ""
        self.configured_modules = {}

    def init_hardware(self, pyvisa_backend='@py'):
        """Initialize the selected VISA resource
        
        :param pyvisa_backend: Expects a pyvisa backend identifier or a path to the visa backend dll (ref. to pyvisa)
        :type pyvisa_backend: string
        """
        # Open connexion with instrument
        rm = visa.highlevel.ResourceManager(pyvisa_backend)
        logger.info("Resources detected by pyvisa: {}".format(rm.list_resources(query='?*')))
        try:
            self._instr = rm.open_resource(self.rsrc_name,
                                           write_termination="\n",
                                           read_termination="\n",
                                           )
            self._instr.timeout = 10000

            # Check if the selected resource match the loaded configuration
            model = self.get_idn()[32:36]
            try:
                assert model == self.model, model
            except AssertionError as err:
                logger.error("{}: Keithley {} used doesn't match the model in the configuration.".format(KeyError, err))
            if "27" not in model:
                logger.warning("Driver designed to use Keithley 27XX series, not {} model.".format(model))
            for instr in config["Keithley", self.model]:
                if type(config["Keithley", self.model, instr]) == dict:
                    if self.rsrc_name in config["Keithley", self.model, instr, "rsrc_name"]:
                        self.instr = instr
            logger.info("Instrument selected: {} ".format(config["Keithley", self.model, self.instr, "rsrc_name"]))
            logger.info("Keithley model : {}".format(config["Keithley", self.model, self.instr, "model_name"]))
            try:
                # Load the configuration matching the selected module
                cards = self.get_card().split(',')
                logger.info("card : {}".format(cards))
                try:
                    assert config["Keithley", self.model, self.instr, "MODULE01", "module_name"] == cards[0], cards[0]
                    self.configured_modules["MODULE01"] = cards[0]
                except KeyError as err:
                    logger.error("{}: configuration {} does not exist.".format(KeyError, err))
                except AssertionError as err:
                    logger.error("{}: Switching module {} does not match any configuration".format(
                        AssertionError, str(err)))
                try:
                    assert config["Keithley", self.model, self.instr, "MODULE02", "module_name"] == cards[1], cards[1]
                    self.configured_modules["MODULE02"] = cards[1]
                except KeyError as err:
                    logger.error("{}: configuration {} does not exist." .format(KeyError, err))
                except AssertionError as err:
                    logger.error("{}: Switching module {} does not match any configuration".format(
                        AssertionError, str(err)))
                logger.info("Configured modules : {}".format(self.configured_modules))
                try:
                    if config["Keithley", self.model, self.instr, 'MODULE01', 'module_name']\
                            in self.non_amp_modules_list:
                        self.non_amp_module["MODULE01"] = True
                    if config["Keithley", self.model, self.instr, 'MODULE02', 'module_name']\
                            in self.non_amp_modules_list:
                        self.non_amp_module["MODULE02"] = True
                except KeyError:
                    pass
                logger.info("Hardware initialized")
            except AttributeError:
                logger.error(AttributeError)
        except visa.errors.VisaIOError as err:
            logger.error(err)
        except Exception:
            logger.error(Exception)

    def configuration_sequence(self):
        """Configure each channel selected by the user

        Read the configuration file to get the channels used and their configuration,
        and send the keithley a sequence allowing to set up each channel.
        
        :raises TypeError: Channel section of configuration file not correctly defined, each channel should be a dict
        :raises ValueError: Channel not correctly defined, it should at least contain a key called "mode"
        """
        logger.info("       ********** CONFIGURATION SEQUENCE INITIALIZED **********")

        self.reset()
        self.clear_buffer()
        channels = ''

        # The following loop set up each channel in the config file
        for module in self.configured_modules:
            for key in config["Keithley", self.model, self.instr, module, "CHANNELS"].keys():

                # Handling user mistakes if the channels' configuration section is not correctly set up
                if not type(config["Keithley", self.model, self.instr, module, 'CHANNELS', key]) == dict:
                    logger.info("Channel {} not correctly defined, must be a dictionary" .format(key))
                    continue
                if not config["Keithley", self.model, self.instr, module, 'CHANNELS', key]:
                    continue
                if "mode" not in config["Keithley", self.model, self.instr, module, 'CHANNELS', key]:
                    logger.info("Channel {} not fully defined, 'mode' is missing" .format(key))
                    continue
                if config["Keithley", self.model, self.instr, module, 'CHANNELS', key, "mode"].upper()\
                        not in self.modes_channels_dict.keys():
                    logger.info("Channel {} not correctly defined, mode not recognized" .format(key))
                    continue

                # Channel mode
                mode = config["Keithley", self.model, self.instr, module, 'CHANNELS', key, "mode"].upper()
                self.modes_channels_dict[mode].append(int(key))
                channel = '(@' + key + ')'
                channels += key + ","
                cmd = "FUNC '" + mode + "'," + channel
                self._instr.write(cmd)

                # Config
                if 'range' in config["Keithley", self.model, self.instr, module, 'CHANNELS', key].keys():
                    rang = config["Keithley", self.model, self.instr, module, 'CHANNELS', key, "range"]
                    if 'autorange' in str(rang):
                        self._instr.write(mode + ':RANG:AUTO ')
                    else:
                        self._instr.write(mode + ':RANG ' + str(range))

                if 'resolution' in config["Keithley", self.model, self.instr, module, 'CHANNELS', key].keys():
                    resolution = config["Keithley", self.model, self.instr, module, 'CHANNELS', key, "resolution"]
                    self._instr.write(mode + ':DIG ' + str(resolution))

                if 'nplc' in config["Keithley", self.model, self.instr, module, 'CHANNELS', key].keys():
                    nplc = config["Keithley", self.model, self.instr, module, 'CHANNELS', key, "nplc"]
                    self._instr.write(mode + ':NPLC ' + str(nplc))

                if "TEMP" in mode:
                    trans = config["Keithley", self.model, self.instr, module, 'CHANNELS', key, "transducer"].upper()
                    if "TC" in trans:
                        tc_type = config["Keithley", self.model, self.instr, module, 'CHANNELS', key, "type"].upper()
                        ref_j = config["Keithley", self.model, self.instr, module, 'CHANNELS', key, "ref_junc"].upper()
                        self.mode_temp_tc(module, channel, trans, tc_type, ref_j)
                    elif "THER" in trans:
                        ther_type = config["Keithley", self.model, self.instr, module, 'CHANNELS', key, "type"].upper()
                        self.mode_temp_ther(channel, trans, ther_type)
                    elif "FRTD" in trans:
                        frtd_type = config["Keithley", self.model, self.instr, module, 'CHANNELS', key, "type"].upper()
                        self.mode_temp_frtd(channel, trans, frtd_type)

                # Console info
                logger.info("Channels {} \n {}"
                            .format(key, config["Keithley", self.model, self.instr, module, 'CHANNELS', key]))
                # Timeout update for long measurement modes such as voltage AC
                if "AC" in mode:
                    self._instr.timeout += 4000

                # Handling errors from Keithley
                current_error = self.get_error()
                try:
                    if current_error != '0,"No error"':
                        raise ValueError("The following error has been raised by the Keithley:\
                        %s => Please refer to the User Manual to correct it\n\
                        Note: To make sure channels are well configured in the .toml file,\
                        refer to section 15 'SCPI Reference Tables', Table 15-5" % current_error)
                except Exception as err:
                    logger.info("{}".format(err))
                    pass
        
        self.current_mode = 'scan_list'
        self.channels_scan_list = channels[:-1]
        logger.info("       ********** CONFIGURATION SEQUENCE SUCCESSFULLY ENDED **********")

    def clear_buffer(self):
        # Default: auto clear when scan start
        self._instr.write("TRAC:CLE")

    def clear_buffer_off(self):
        # Disable buffer auto clear
        self._instr.write("TRAC:CLE:AUTO OFF")

    def clear_buffer_on(self):
        # Disable buffer auto clear
        self._instr.write("TRAC:CLE:AUTO ON")

    def close(self):
        self._instr.write("ROUT:OPEN:ALL")
        self._instr.close()

    def data(self):
        """Get data from instrument

        Make the Keithley perform 3 actions: init, trigger, fetch. Then process the answer to return 3 variables:
        - The answer (string)
        - The measurement values (numpy array)
        - The timestamp of each measurement (numpy array)
        """
        if not self.sample_count_1:
            # Initiate scan
            self._instr.write("INIT")
            # Trigger scan
            self._instr.write("*TRG")
            # Get data (equivalent to TRAC:DATA? from buffer)
            str_answer = self.get_data()
        else:
            str_answer = self.get_data()
        # Split the instrument answer (MEASUREMENT,TIME,READING COUNT) to create a list
        list_split_answer = str_answer.split(",")

        # MEASUREMENT & TIME EXTRACTION
        list_measurements = list_split_answer[::3]
        str_measurements = ''
        list_times = list_split_answer[1::3]
        str_times = ''
        for j in range(len(list_measurements)):
            if not j == 0:
                str_measurements += ','
                str_times += ','
            for l1 in range(len(list_measurements[j])):
                test_carac = list_measurements[j][-(l1+1)]
                # Remove non-digit characters (units)
                if test_carac.isdigit():
                    if l1 == 0:
                        str_measurements += list_measurements[j]
                    else:
                        str_measurements += list_measurements[j][:-l1]
                    break
            for l2 in range(len(list_times[j])):
                test_carac = list_times[j][-(l2+1)]
                # Remove non-digit characters (units)
                if test_carac.isdigit():
                    if l2 == 0:
                        str_times += list_times[j]
                    else:
                        str_times += list_times[j][:-l2]
                    break

        # Split created string to access each value
        list_measurements_values = str_measurements.split(",")
        list_times_values = str_times.split(",")
        # Create numpy.array containing desired values (float type)
        array_measurements_values = np.array(list_measurements_values, dtype=float)
        if not self.sample_count_1:
            array_times_values = np.array(list_times_values, dtype=float)
        else:
            array_times_values = np.array([0], dtype=float)

        return str_answer, array_measurements_values, array_times_values

    def get_card(self):
        # Query switching module
        raise NotImplementedError

    def get_data(self):
        # Make a measurement
        raise NotImplementedError

    def get_error(self):
        # Ask the keithley to return the last current error
        raise NotImplementedError

    def get_idn(self):
        # Query identification
        raise NotImplementedError

    def init_cont_off(self):
        # Disable continuous initiation
        self._instr.write("INIT:CONT OFF")
        
    def init_cont_on(self):
        # Enable continuous initiation
        self._instr.write("INIT:CONT ON")

    def mode_temp_frtd(self, channel, transducer, frtd_type,):
        self._instr.write("TEMP:TRAN " + transducer + "," + channel)
        self._instr.write("TEMP:FRTD:TYPE " + frtd_type + "," + channel)

    def mode_temp_tc(self, module, channel, transducer, tc_type, ref_junc,):
        self._instr.write("TEMP:TRAN " + transducer + "," + channel)
        self._instr.write("TEMP:TC:TYPE " + tc_type + "," + channel)
        self._instr.write("TEMP:RJUN:RSEL " + ref_junc + "," + channel)
        if self.get_error() != '0,"No error"':
            logger.error("Modules {} only have automatic cjc, not {}"
                         .format(self.automatic_cjc_modules_list, self.configured_modules[module]))

    def mode_temp_ther(self, channel, transducer, ther_type,):
        self._instr.write("TEMP:TRAN " + transducer + "," + channel)
        self._instr.write("TEMP:THER:TYPE " + ther_type + "," + channel)
    
    def reset(self):
        # Clear measurement event register
        self._instr.write("*CLS")
        # One-shot measurement mode (Equivalent to INIT:COUNT OFF)
        self._instr.write("*RST")

    def set_mode(self, mode):
        """Define whether the Keithley will scan all the scan_list or only channels in the selected mode

        :param mode: Supported modes: 'SCAN_LIST', 'VDC', 'VAC', 'IDC', 'IAC', 'R2W', 'R4W', 'FREQ' and 'TEMP'
        :type mode: string
        """
        mode = mode.upper()
        
        # FRONT panel
        if "SCAN" not in mode:
            self.init_cont_on()
            self.sample_count_1 = True
            self.reading_scan_list = False
            self._instr.write("FUNC '" + mode + "'")

        # REAR panel
        else:
            self.clear_buffer()
            # Init continuous disabled
            self.init_cont_off()
            mode = mode[5:]
            self.current_mode = mode
            if 'SCAN_LIST' in mode:
                self.reading_scan_list = True
                self.sample_count_1 = False
                channels = '(@' + self.channels_scan_list + ')'
                # Set to perform 1 to INF scan(s)
                self._instr.write("TRIG:COUN 1")
                # Trigger immediately after previous scan end if IMM
                self._instr.write("TRIG:SOUR BUS")
                # Set to scan <n> channels
                samp_count = 1 + channels.count(',')
                self._instr.write("SAMP:COUN "+str(samp_count))
                # Disable scan if currently enabled
                self._instr.write("ROUT:SCAN:LSEL NONE")
                # Set scan list channels
                self._instr.write("ROUT:SCAN " + channels)
                # Start scan immediately when enabled and triggered
                self._instr.write("ROUT:SCAN:TSO IMM")
                # Enable scan
                self._instr.write("ROUT:SCAN:LSEL INT")

            else:
                self.reading_scan_list = False
                # Select channels in the channels list (config file) matching the requested mode
                channels = '(@' + str(self.modes_channels_dict[mode])[1:-1] + ')'
                # Set to perform 1 to INF scan(s)
                self._instr.write("TRIG:COUN 1")
                # Set to scan <n> channels
                samp_count = 1+channels.count(',')
                self._instr.write("SAMP:COUN "+str(samp_count))
                if samp_count == 1:
                    self.init_cont_on()
                    # Trigger definition
                    self._instr.write("TRIG:SOUR IMM")
                    # Disable scan if currently enabled
                    self._instr.write("ROUT:SCAN:LSEL NONE")
                    self._instr.write("ROUT:CLOS " + channels)
                    
                    self._instr.write("FUNC '" + mode + "'")
                    logger.info("rear sample count: {}".format(self.sample_count_1))
                    if not self.sample_count_1:
                        self.sample_count_1 = True
                    self.reading_scan_list = False
                else:
                    self.sample_count_1 = False
                    # Trigger definition
                    self._instr.write("TRIG:SOUR BUS")
                    # Disable scan if currently enabled
                    self._instr.write("ROUT:SCAN:LSEL NONE")
                    # Set scan list channels
                    self._instr.write("ROUT:SCAN " + channels)
                    # Start scan immediately when enabled and triggered
                    self._instr.write("ROUT:SCAN:TSO IMM")
                    # Enable scan
                    self._instr.write("ROUT:SCAN:LSEL INT")
                
            return channels
