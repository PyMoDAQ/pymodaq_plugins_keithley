import numpy as np

from pymodaq_utils.utils import ThreadCommand
from pymodaq_data.data import DataToExport, Axis, Q_
from pymodaq_gui.parameter import Parameter

from pymodaq.control_modules.viewer_utility_classes import DAQ_Viewer_base, comon_parameters, main
from pymodaq.utils.data import DataFromPlugins

import pyvisa
from pymodaq_plugins_keithley.hardware.keithley2600.keithley2600_VISADriver import Keithley2600VISADriver


# Helper functions
def _get_VISA_resources(pyvisa_backend="@py"):

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


def _build_param(name, title, type, value, limits=None, unit=None, **kwargs):
    params = {}
    params["name"] = name
    params["title"] = title
    params["type"] = type
    params["value"] = value
    if limits is not None:
        params["limits"] = limits
    if unit is not None:
        params["suffix"] = unit
        params["siPrefix"] = True
    for argn, argv in kwargs.items():
        params[argn] = argv
    return params


def _emit_xy_data(self, x, y):
    x_axis = Axis(data=x, label="Voltage", units="V", index=0)
    self.dte_signal.emit(DataToExport("Keithley2600",
                                      data=[DataFromPlugins(name="Keithley2600",
                                                            data=[y],
                                                            units="A",
                                                            dim="Data1D", labels=["I-V"],
                                                            axes=[x_axis])]))


class DAQ_1DViewer_Keithley2600(DAQ_Viewer_base):
    """ Instrument plugin class for a Keithley 2600 sourcemeter.
    
    Attributes:
    -----------
    controller: object
        The particular object that allow the communication with the hardware, in general a python wrapper around the
         hardware library.
         
    # TODO add your particular attributes here if any

    """
    params = comon_parameters+[
        _build_param("resource_name", "VISA resource", "list", "", limits=_get_VISA_resources()),
        _build_param("channel", "Channel", "str", "A"),
        _build_param("startv", "Sweep start voltage", "float", 0, unit="V"),
        _build_param("stopv", "Sweep stop voltage", "float", 1, unit="V"),
        _build_param("stime", "Sweep stabilization time", "float", 1e-3, unit="s"),
        _build_param("npoints", "Sweep points", "int", 101),
        _build_param("ilimit", "Current limit", "float", 0.1, unit="A"),
        _build_param("autorange", "Autorange", "bool", True)
        ]


    def ini_attributes(self):
        # Type declaration of the controller
        self.controller: Keithley2600VISADriver = None


    def commit_settings(self, param: Parameter):
        """Apply the consequences of a change of value in the detector settings

        Parameters
        ----------
        param: Parameter
            A given parameter (within detector_settings) whose value has been changed by the user
        """
        # Dispatch arguments
        name = param.name()
        val = param.value()
        unit = param.opts.get("suffix")
        qty = Q_(val, unit)

        # Current limit
        if name == "ilimit":
           self.controller.channel.current_limit = qty.to("A").m


    def ini_detector(self, controller=None):
        """Detector communication initialization

        Parameters
        ----------
        controller: (object)
            custom object of a PyMoDAQ plugin (Slave case). None if only one actuator/detector by controller
            (Master case)

        Returns
        -------
        info: str
        initialized: bool
            False if initialization failed otherwise True
        """

        # If stand-alone device, initialize controller object
        if self.is_master:

            # Get initialization parameters
            resource_name = self.settings["resource_name"]
            channel = self.settings["channel"]
            autorange = self.settings["autorange"]

            # Initialize device
            self.controller = Keithley2600VISADriver(resource_name,
                                                     channel_name=channel,
                                                     autorange=autorange)
            initialized = True

        # If slave device, retrieve controller object
        else:
            self.controller = controller
            initialized = True

        # Initialize viewers pannel with the future type of data
        mock_x = np.linspace(0, 1, 101)
        mock_y = np.zeros(101)
        _emit_xy_data(self, mock_x, mock_y)

        # Initialization successful
        info = "Keithey 2600 initialization finished."
        return info, initialized


    def close(self):
        """Terminate the communication protocol"""
        if self.is_master:
            self.controller.close()
            self.controller = None


    def grab_data(self, Naverage=1, **kwargs):
        """Start a grab from the detector

        Parameters
        ----------
        Naverage: int
            Number of hardware averaging (if hardware averaging is possible, self.hardware_averaging should be set to
            True in class preamble and you should code this implementation)
        kwargs: dict
            others optionals arguments
        """

        # Retrieve parameters
        startv = self.settings["startv"]
        stopv = self.settings["stopv"]
        stime = self.settings["stime"]
        npoints = self.settings["npoints"]

        # Sweep and retrieve x and y axes
        x, y = self.controller.channel.sweepV_measureI(startv, stopv, stime, npoints)

        # Emit data to PyMoDAQ
        _emit_xy_data(self, x, y)


    def stop(self):
        """Stop the current grab hardware wise if necessary"""
        pass


if __name__ == '__main__':
    main(__file__)
