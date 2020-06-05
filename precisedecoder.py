#!/usr/bin/env python
import time
import os
import logging
import pyaudio
import sys

from threading import Thread
from contextlib import contextmanager
from ctypes import *
from kalliope import Utils
from precise_runner import PreciseRunner, ReadWriteStream, PreciseEngine

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig()
logger = logging.getLogger("kalliope")

TOP_DIR = os.path.dirname(os.path.abspath(__file__))
RESOURCE_FILE = os.path.join(TOP_DIR, "precise-engine/precise-engine")


def py_error_handler(filename, line, function, err, fmt):
    pass

ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)
c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)

@contextmanager
def no_alsa_error():
    try:
        asound = cdll.LoadLibrary('libasound.so')
        asound.snd_lib_error_set_handler(c_error_handler)
        yield
        asound.snd_lib_error_set_handler(None)
    except:
        yield
        pass

class HotwordDetector(Thread):
    """
    Precise decoder to detect whether a keyword specified by `decoder_model`
    exists in a microphone input stream.

    :param decoder_model: decoder model file path, a string or a list of strings
    :param sensitivity: decoder sensitivity, a float of a list of floats.
                              The bigger the value, the more senstive the
                              decoder. If an empty list is provided, then the
                              default sensitivity in the model will be used.
    """
    def __init__(self,
                 keyword=None,
                 sensitivity=None,
                 detected_callback=None,
                 interrupt_check=lambda: False
                 ):
                 
        super(HotwordDetector, self).__init__()
        self.kill_received = False
        self.paused = False
        self.detected_callback = detected_callback
        self.interrupt_check = interrupt_check
        self.sensitivity = sensitivity
        trigger_level = 3
        self.keyword = keyword

        self.found_keyword = False

        engine = PreciseEngine(RESOURCE_FILE, self.keyword)

        with no_alsa_error():
            self.audio = pyaudio.PyAudio()

        self.stream_in = self.audio.open(
            input=True, output=False,
            format=self.audio.get_format_from_width(2),
            channels=1,
            rate=16000,
            frames_per_buffer=1024)

        self.stream = ReadWriteStream()
        self.runner = PreciseRunner(engine,
                                    stream=self.stream_in,
                                    sensitivity=float(self.sensitivity),
                                    trigger_level=trigger_level,
                                    on_activation=self.activation
                                    )

    def run(self):
        logger.debug("detecting...")
        self.runner.start()
        while not self.kill_received:
            if not self.paused:
                if self.interrupt_check():
                    logger.debug("detect voice break")
                    break
                
                data = self.stream.read()
                if len(data) > 0:
                    self.stream.write(data)

                if self.found_keyword:
                    self.runner.stop()
                    message = "Keyword detected"
                    Utils.print_info(message)
                    logger.debug(message)
                    self.detected_callback()

            time.sleep(0.1)

        logger.debug("finished.")

    def activation(self):
        self.found_keyword = True

    def terminate(self):
        """
        Terminate audio stream. Users cannot call start() again to detect.
        :return: None
        """
        self.stream_in.stop_stream()
        self.stream_in.close()
        self.audio.terminate()
