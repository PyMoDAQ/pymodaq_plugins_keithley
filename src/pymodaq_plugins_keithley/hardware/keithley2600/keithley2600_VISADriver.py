import numpy as np
import pyvisa
from pymodaq_plugins_keithley import config
from pymodaq.utils.logger import set_logger, get_module_name
logger = set_logger(get_module_name(__file__))


# Helper functions
def get_VISA_resources(pyvisa_backend="@py"):

    # Get list of VISA resources
    resourceman = pyvisa.ResourceManager(pyvisa_backend)
    resources = list(resourceman.list_resources())

    # Move the first USB connection to the top
    for i, val in enumerate(resources):
        if val.startswith("USB0"):
            resources.remove(val)
            resources.insert(0, val)
            break

    # Return list of resources
    return resources


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


    def __init__(self, resource_name, pyvisa_backend="@py"):
        """Initialize KeithleyVISADriver class.

        Parameters
        ----------
        resource_name: str
            VISA resource name. (ex: "USB0::1510::9782::1234567::0::INSTR")
        pyvisa_backend: str, optional
            pyvisa backend identifier or path to the visa backend dll (ref. to pyvisa)
            (default: "@py")
        """
        resourceman = pyvisa.ResourceManager(pyvisa_backend)
        self._instr = resourceman.open_resource(resource_name)


    def close(self):
        """Terminate connection with the instrument."""
        self._instr.close()
        self._instr = None


    def create_channel(self, channel_name="A", autorange=True):
        """Create an object for driving an SMU channel connected to this device.

        Parameters
        ----------
        channel_name: str, optional
            Channel name. (default: "A")
        autorange: bool, optional
            Enable I and V autorange. (default: True)
        """
        return Keithley2600Channel(self, channel_name, autorange)


    def _write(self, cmd):
        """Convenience methode to send a TSP command to the device."""
        self._instr.write(cmd)


    def _read(self):
        """Convenience methode to get response from the device."""
        return self._instr.read()


class Keithley2600Channel:
    """Class for handling a single SMU channel on a Keithley 2600 sourcemeter."""

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
    def Ilimit(self):
        """Get current limit [A] of the channel.

        Returns
        -------
        ilimit: float
            Current limit [A] of the selected channel.
        """
        self._write(f"print({self.smu}.source.limiti)")
        ilimit = self._read()
        return float(ilimit)


    @Ilimit.setter
    def Ilimit(self, ilimit):
        """Set current limit [A] of the channel.

        Parameters
        ----------
        ilimit: float
            Current limit [A] to set.
        """
        ilimit = f"{ilimit:.6e}"
        self._write(f"{self.smu}.source.limiti = {ilimit}")


    @property
    def Vlimit(self):
        """Get voltage limit [A] of the channel.

        Returns
        -------
        vlimit: float
            Voltage limit [A] of the selected channel.
        """
        self._write(f"print({self.smu}.source.limitv)")
        vlimit = self._read()
        return float(vlimit)


    @Vlimit.setter
    def Vlimit(self, vlimit):
        """Set voltage limit [A] of the channel.

        Parameters
        ----------
        vlimit: float
            Voltage limit [A] to set.
        """
        vlimit = f"{vlimit:.6e}"
        self._write(f"{self.smu}.source.limitv = {vlimit}")


    def autorange(self):
        """Set current and voltage measurements to autorange."""
        self._write(f"{self.smu}.measure.autorangei = {self.smu}.AUTORANGE_ON")
        self._write(f"{self.smu}.measure.autorangev = {self.smu}.AUTORANGE_ON")


    def measureI(self):
        """Measure current [A]."""
        self._write(f"print({self.smu}.measure.i())")
        meas = self._read()
        return float(meas)


    def measureV(self):
        """Measure voltage [V]."""
        self._write(f"print({self.smu}.measure.v())")
        meas = self._read()
        return float(meas)


    def measureIV(self):
        """Measure simultaneously current [A] and voltage [V]."""
        self._write(f"print({self.smu}.measure.iv())")
        ret = self._read()
        i, v = ret.split()
        return float(i), float(v)


    def off(self, highz=False):
        """Switch off channel output.

        Parameters
        ----------
        highz: bool, optional
            Set output to high impedance mode in addition to switching off.
            (default: False)
        """
        offmode = 2 if highz else 0
        self._write(f"{self.smu}.source.output = {offmode}")


    def sourceI(self, isetpoint):
        """Set channel output to constant current with the specified setpoint.

        Parameters
        ----------
        isetpoint: float
            Current [A] to set.
        """
        isetpoint = f"{isetpoint:.6e}"
        self._write(f"{self.smu}.source.func = 0")
        self._write(f"{self.smu}.source.output = 1")
        self._write(f"{self.smu}.source.leveli = {isetpoint}")


    def sourceV(self, vsetpoint):
        """Set channel output to constant voltage with the specified setpoint.

        Parameters
        ----------
        vsetpoint: float
            Voltage [V] to set.
        """
        vsetpoint = f"{vsetpoint:.6e}"
        self._write(f"{self.smu}.source.func = 1")
        self._write(f"{self.smu}.source.output = 1")
        self._write(f"{self.smu}.source.levelv = {vsetpoint}")


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
