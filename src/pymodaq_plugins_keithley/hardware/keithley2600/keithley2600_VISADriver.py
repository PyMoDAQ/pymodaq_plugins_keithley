import numpy as np
import pyvisa
from pymodaq_plugins_keithley import config
from pymodaq.utils.logger import set_logger, get_module_name
logger = set_logger(get_module_name(__file__))


def table_to_np(table):
    """Convert sequence of ASCII-encoded, comma-separated values to NumPy array."""
    split = table.split(", ")
    floats = [float(x) for x in split]
    array = np.array(floats)
    return array


class Keithley2600VISADriver:
    """VISA class driver for Keithley 2600 sourcemeters.

    Communication with the device is performed in text mode (TSP). Detailed instructions can be found in:
    https://download.tek.com/manual/2600BS-901-01_C_Aug_2016_2.pdf
    """


    def __init__(self, resource_name, channel_name="A", autorange=True, pyvisa_backend="@py"):
        """Initialize KeithleyVISADriver class.

        Parameters
        ----------
        resource_name: str
            VISA resource name. (ex: "USB0::1510::9782::1234567::0::INSTR")
        channel_name: str, optional
            Channel name. (default: "A")
        autorange: bool, optional
            Enable I and V autorange. (default: True)
        pyvisa_backend: str, optional
            pyvisa backend identifier or path to the visa backend dll (ref. to pyvisa)
            (default: "@py")
        """

        # Establish connection
        resourceman = pyvisa.ResourceManager(pyvisa_backend)
        self._instr = resourceman.open_resource(resource_name)

        # Create channel
        self.channel = Keithley2600Channel(self, channel_name, autorange)


    def close(self):
        """Terminate connection with the instrument."""
        self._instr.close()
        self._instr = None


    def _write(self, cmd):
        """Convenience methode to send a TSP command to the device."""
        self._instr.write(cmd)


    def _read(self):
        """Convenience methode to get response from the device."""
        return self._instr.read()


class Keithley2600Channel:
    """Class for handling a single channel on a Keithley 2600 sourcemeter."""

    def __init__(self, parent, channel, autorange):
        """Initialize class.

        Parameters
        ----------
        parent: Keithley2600
            Parent class.
        channel: str
            Identifier of the channel. (ex: "A")
        autorange: bool
            Enable I and V autorange.
        """

        # Initialize variables
        self.channel = channel
        self.smu = f"smu{channel.lower()}"
        self.parent = parent

        # Set autorange if enabled
        if autorange:
            self.autorange()


    def _write(self, cmd):
        """Convenience methode to send a TSP command to the device."""
        self.parent._write(cmd)


    def _read(self):
        """Convenience methode to get response from the device."""
        return self.parent._read()


    @property
    def current_limit(self):
        """Get current limit [A] of the channel.

        Returns
        -------
        current_limit: float
            Current limit [A] of the selected channel.
        """
        self._write(f"print({self.smu}.source.limiti)")
        limit = self._read()
        return float(limit)


    @current_limit.setter
    def current_limit(self, limit):
        """Set current limit [A] of the channel.

        Parameters
        ----------
        limit: float
            Current limit [A] to set.
        """
        limit = f"{limit:.6e}"
        self._write(f"{self.smu}.source.limiti = {limit}")


    def autorange(self):
        """Set current and voltage measurements to autorange."""
        self._write(f"{self.smu}.measure.autorangei = {self.smu}.AUTORANGE_ON")
        self._write(f"{self.smu}.measure.autorangev = {self.smu}.AUTORANGE_ON")


    def sweepV_measureI(self, startv=0, stopv=1, stime=1e-3, npoints=100):
        """Perform a linear voltage sweep and measure current. This version is called with arguments.

        Parameters
        ----------
        startv: float
            Starting voltage [V] of the sweep.
        stopv: float
            Stopping voltage [V] of the sweep.
        stime: float
            Stabilization time [s]. The device waits for this amount of time at each measurement
            step, once voltage has reached the setpoint. In practice, actual step time is longer
            than this value because of the time needed to reach the voltage setpoint.
        npoints: int
            Number of points to be acquired. Must be >2.

        Returns
        -------
        x: np.ndarray
            Voltage values [V].
        y: np.ndarray
            Current (intensity) values [A].
        """
        
        # Convert channel and step time
        startv = f"{startv:.6e}"
        stopv = f"{stopv:.6e}"
        stime = f"{stime:.6e}"
        npoints = str(npoints)

        # Send request to sweep
        self._write(f"SweepVLinMeasureI({self.smu}, {startv}, {stopv}, {stime}, {npoints})")
        self._write(f"print(status.measurement.buffer_available.{self.smu.upper()})")
        ret = self._read()
        if not int(float(ret)) == 2:
            raise ValueError(f"Return data {ret} != 2")

        # Retrieve applied voltages
        self._write(f"printbuffer(1, {npoints}, {self.smu}.nvbuffer1.sourcevalues)")
        x = table_to_np(self._read())

        # Retrieve measured currents
        self._write(f"printbuffer(1, {npoints}, {self.smu}.nvbuffer1.readings)")
        y = table_to_np(self._read())
        
        # Return x and y vectors
        return x, y
