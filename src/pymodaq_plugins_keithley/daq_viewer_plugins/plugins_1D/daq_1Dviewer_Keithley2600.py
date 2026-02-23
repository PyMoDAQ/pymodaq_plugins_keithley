import numpy as np

from pymodaq_utils.utils import ThreadCommand
from pymodaq_data.data import DataToExport, Axis, Q_
from pymodaq_gui.parameter import Parameter

from pymodaq.control_modules.viewer_utility_classes import DAQ_Viewer_base, comon_parameters, main
from pymodaq.utils.data import DataFromPlugins

import pyvisa
from pymodaq_plugins_keithley.hardware.keithley2600.keithley2600_VISADriver import Keithley2600VISADriver, Keithley2600Channel, get_VISA_resources

import datetime
from qtpy.QtCore import QDateTime


# Helper functions
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
        _build_param("resource_name", "VISA resource", "list", "", limits=get_VISA_resources()),
        _build_param("channel", "Channel", "str", "A"),
        _build_param("startv", "Sweep start voltage", "float", 0, unit="V"),
        _build_param("stopv", "Sweep stop voltage", "float", 1, unit="V"),
        _build_param("stime", "Sweep stabilization time", "float", 1e-3, unit="s"),
        _build_param("npoints", "Sweep points", "int", 101),
        _build_param("ilimit", "Current limit", "float", 0.1, unit="A"),
        _build_param("autorange", "Autorange", "bool", True),
        _build_param("idle_pol_on", "Keep polarized after scan", "bool", False),
        _build_param("idle_pol_v", "Polarization voltage after scan", "float", 0, unit="V"),
        _build_param("meas_start", "Last measurement start time", "date_time",
                     QDateTime(datetime.datetime.now()), readonly=True),
        _build_param("meas_end", "Last measurement end time", "date_time",
                     QDateTime(datetime.datetime.now()), readonly=True),
        ]


    def ini_attributes(self):
        # Type declaration of the controller
        self.controller: Keithley2600VISADriver = None
        self.channel: Keithley2600Channel = None


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

        # No argument processing for now


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

        # Get initialization parameters
        resource_name = self.settings["resource_name"]
        channel = self.settings["channel"]
        autorange = self.settings["autorange"]

        # If stand-alone device, initialize controller object
        if self.is_master:

            # Initialize device
            self.controller = Keithley2600VISADriver(resource_name)
            initialized = True

        # If slave device, retrieve controller object
        else:
            self.controller = controller
            initialized = True

        # Initialize channel
        self.channel = self.controller.create_channel(channel_name=channel,
                                                      autorange=autorange)

        # Initialize viewers panel with the future type of data
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
        ilimit = self.settings["ilimit"]
        idle_pol_on = self.settings["idle_pol_on"]
        idle_pol_v = self.settings["idle_pol_v"]

        # Apply current limit
        self.channel.Ilimit = ilimit

        # Get timestamp before acquisition
        start_time = datetime.datetime.now()

        # Sweep and retrieve x and y axes
        x, y = self.channel.sweepV_measureI(startv, stopv, stime, npoints)

        # Get timestamp after acquisition and update timestamp parameters
        end_time = datetime.datetime.now()
        self.settings["meas_start"] = QDateTime(start_time)
        self.settings["meas_end"] = QDateTime(end_time)

        # Emit data to PyMoDAQ
        _emit_xy_data(self, x, y)

        # If "keep polarized after scan" is selected, apply selected voltage
        if idle_pol_on:
            self.channel.sourceV(idle_pol_v)


    def stop(self):
        """Stop the current grab hardware wise if necessary"""
        pass


if __name__ == '__main__':
    main(__file__)
