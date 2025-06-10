import pyvisa as visa
from pymodaq_plugins_keithley import config
from pymodaq_plugins_keithley.hardware.keithley27XX.keithley27XX_VISADriver import Keithley27XXVISADriver
from pymodaq.utils.logger import set_logger, get_module_name
logger = set_logger(get_module_name(__file__))


class Keithley2750VISADriver(Keithley27XXVISADriver):
    """VISA class driver for the Keithley 2750 Multimeter/Switch System

    This class relies on pyvisa module to communicate with the instrument via VISA protocol.
    Please refer to the instrument reference manual available at:
    https://download.tek.com/manual/2750-900-01%28F-Aug2011%29%28User%29.pdf
    """
    # List the Keithley instruments the user has configured from the .toml configuration file
    model = "2750"
    list_instruments = {}
    for instr in config["Keithley", model].keys():
        if "INSTRUMENT" in instr:
            list_instruments[instr] = config["Keithley", model, instr, "rsrc_name"]
    logger.info("Configured instruments: {}".format(list(list_instruments.items())))

    def get_card(self):
        # Query switching module
        return self._instr.query("*OPT?")[1:-1]

    def get_data(self):
        # Make a measurement
        return self._instr.query("FETCH?")[1:-1]

    def get_error(self):
        # Ask the keithley to return the last current error
        return self._instr.query("SYST:ERR?")[1:-1]

    def get_idn(self):
        # Query identification
        return self._instr.query("*IDN?")[1:-1]


if __name__ == "__main__":
    try:
        print("In main")

        # You can use this main section for:
        # - Testing connexion and communication with your instrument
        # - Testing new methods in developer mode

        RM = visa.ResourceManager("@py")
        print("list resources", RM.list_resources())

        # K2750 Instance of KeithleyVISADriver class (replace ASRL1::INSTR by the name of your resource)
        k2750 = Keithley2750VISADriver("ASRL1::INSTR")
        k2750.init_hardware()
        print("IDN?")
        print(k2750.get_idn())
        k2750.reset()
        k2750.configuration_sequence()

        # Daq_viewer simulation first run
        for i in range(10):
            print(k2750.data())
        print(k2750.data())

        k2750.clear_buffer()
        k2750.close()

        print("Out")

    except Exception as e:
        print("Exception ({}): {}".format(type(e), str(e)))
