"""
PyMoDAQ Viewer0D plugin — Keithley 6517B Electrometer
RS-232 via pyvisa-py (no NI-VISA required).
"""

import numpy as np
import time

from pymodaq.control_modules.viewer_utility_classes import DAQ_Viewer_base, comon_parameters
from pymodaq.utils.data import DataToExport, DataFromPlugins

UNITS = {'current': 'A', 'voltage': 'V', 'resistance': 'Ohm', 'charge': 'C'}
_OVERFLOW = 9.9e36


class DAQ_0DViewer_Keithley6517B(DAQ_Viewer_base):
    """Viewer0D for the Keithley 6517B via RS-232."""

    params = comon_parameters + [
        {'title': 'Communication', 'name': 'comms', 'type': 'group', 'children': [
            {'title': 'Serial port',  'name': 'port',     'type': 'str',  'value': '/dev/ttyUSB0'},
            {'title': 'Baud rate',   'name': 'baud_rate', 'type': 'list',
             'limits': [9600, 19200, 38400, 57600, 115200], 'value': 19200},
            {'title': 'Timeout (ms)', 'name': 'timeout',  'type': 'int',  'value': 5000},
        ]},
        {'title': 'Measurement', 'name': 'meas', 'type': 'group', 'children': [
            {'title': 'Function',   'name': 'function',  'type': 'list',
             'limits': ['current', 'voltage', 'resistance', 'charge'], 'value': 'current'},
            {'title': 'Auto range', 'name': 'auto_range','type': 'bool',  'value': True},
            {'title': 'NPLC',       'name': 'nplc',      'type': 'float', 'value': 1.0,
             'min': 0.01, 'max': 10.0, 'step': 0.1},
        ]},
    ]

    def ini_attributes(self):
        self.controller = None

    def ini_detector(self, controller=None):
        from pymeasure.instruments.keithley import Keithley6517B
        info, initialized = "", False
        try:
            if self.is_master:
                self.controller = Keithley6517B(
                    f"ASRL{self.settings['comms', 'port']}::INSTR",
                    baud_rate=self.settings['comms', 'baud_rate'],
                    timeout=self.settings['comms', 'timeout'],
                    write_termination='\r',
                    read_termination='\r',
                )
                self.controller.reset()
                self.controller.write(':SYST:ZCH OFF')  # ← disable Zero Check
                self._configure_function()
                info = self.controller.id
            else:
                self.controller = controller
                info = "slave"
            initialized = True
        except Exception as exc:
            info = f"Init error: {exc}"

        self.dte_signal_temp.emit(DataToExport('K6517B', data=[
            DataFromPlugins(name='Keithley 6517B',
                            data=[np.array([0.0])],
                            dim='Data0D',
                            labels=[self._label()],
                            units=self._unit())
        ]))
        return info, initialized

    def grab_data(self, Naverage=1, **kwargs):
        try:
            vals = [self._read_value() for _ in range(max(1, Naverage))]
            self.dte_signal.emit(DataToExport('K6517B', data=[
                DataFromPlugins(name='Keithley 6517B',
                                data=[np.array([float(np.mean(vals))])],
                                dim='Data0D',
                                labels=[self._label()],
                                units=self._unit())
            ]))
        except Exception as exc:
            self.emit_status_message(str(exc))

    def stop(self):
        pass

    def commit_settings(self, param):
        if param.parent().name() == 'meas':
            self._configure_function()

    def close(self):
        if self.controller is not None:
            try:
                self.controller.shutdown()
            except Exception:
                pass
            self.controller = None

    # ── helpers ──────────────────────────────────────────────────────────

    def _configure_function(self):
        func = self.settings['meas', 'function']
        nplc = self.settings['meas', 'nplc']
        auto = self.settings['meas', 'auto_range']

        # Minimal response format: only the reading value, no timestamp or RDNG#
        self.controller.write(':FORM:ELEM READ')

        # Trigger layer: arm and trigger immediately, run continuously
        self.controller.write(':ARM:SOUR IMM')
        self.controller.write(':ARM:COUN 1')
        self.controller.write(':TRIG:SOUR IMM')
        self.controller.write(':TRIG:DEL 0')
        self.controller.write(':INIT:CONT ON')

        if func == 'current':
            self.controller.measure_current(nplc=nplc, auto_range=auto)
            if auto:
                # Auto-range once: take a throwaway reading to let the instrument
                # settle on the right range, then lock it
                time.sleep(0.5)
                self.controller.ask(':READ?')  # triggers range selection
                time.sleep(0.5)
                self.controller.write(':SENS:CURR:RANG:AUTO OFF')  # lock range
        elif func == 'voltage':
            self.controller.measure_voltage(nplc=nplc, auto_range=auto)
            if auto:
                time.sleep(0.5)
                self.controller.ask(':READ?')
                time.sleep(0.5)
                self.controller.write(':SENS:VOLT:RANG:AUTO OFF')
        elif func == 'resistance':
            self.controller.measure_resistance(nplc=nplc, auto_range=auto)
            if auto:
                time.sleep(0.5)
                self.controller.ask(':READ?')
                time.sleep(0.5)
                self.controller.write(':SENS:RES:RANG:AUTO OFF')
        elif func == 'charge':
            self.controller.write(':SENS:FUNC "CHAR"')
            self.controller.write(f':SENS:CHAR:RANG:AUTO {"ON" if auto else "OFF"}')
        time.sleep(0.3)  # ← let the instrument settle after reconfiguration

    def _read_value(self) -> float:
        func = self.settings['meas', 'function']
        if func == 'charge':
            raw = self.controller.ask(':FETC?')
            val = float(raw.strip())
        else:
            # PyMeasure properties internally call :READ?; bypass them and use :FETC?
            raw = self.controller.ask(':FETC?')
            val = float(raw.strip())

        return float('nan') if abs(val) > _OVERFLOW else val

    def _label(self): return self.settings['meas', 'function'].capitalize()
    def _unit(self):  return UNITS.get(self.settings['meas', 'function'], '')