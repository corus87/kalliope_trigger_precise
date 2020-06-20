import logging
import os
import sys
from threading import Thread

from kalliope import Utils 

from cffi import FFI as _FFI

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from precisedecoder import HotwordDetector

class PreciseModelNotFound(Exception):
    pass

class MissingParameterException(Exception):
    pass

logging.basicConfig()
logger = logging.getLogger("kalliope")


class Precise(Thread):
 
    def __init__(self, **kwargs):
        super(Precise, self).__init__()
        self._ignore_stderr()
        # pause listening boolean
        self.interrupted = False        
        # callback function to call when hotword caught
        self.callback = kwargs.get('callback', None)

        if self.callback is None:
            raise MissingParameterException("Callback function is required with precise")
        
        # get the sensitivity if set by the user
        self.sensitivity = kwargs.get('sensitivity', 0.5)

        # get the pmdl file to load
        self.pb_file = kwargs.get('pb_file', None)
        
        if self.pb_file is None:
            raise MissingParameterException("Wake word file is required with precise")

        try:
            os.path.isfile(Utils.get_real_file_path(self.pb_file))
        except TypeError: 
            raise PreciseModelNotFound("Precise wake word file %s does not exist" % self.pb_file)
        
        self.detector = HotwordDetector(keyword=self.pb_file,
                                        sensitivity=self.sensitivity,
                                        detected_callback=self.callback)


    def run(self):
        """
        Start the precise thread and wait for a Kalliope trigger word
        :return:
        """
        # start precise loop forever
        self.detector.daemon = True
        self.detector.start()
        self.detector.join()

    def pause(self):
        """
        pause the precise main thread
        """
        logger.debug("Pausing precise process")
        self.detector.pause()

    def unpause(self):
        """
        unpause the precise main thread
        """
        logger.debug("Unpausing precise process")
        self.detector.unpause()

    @staticmethod
    def _ignore_stderr():
        """
        Try to forward PortAudio messages from stderr to /dev/null.
        """
        ffi = _FFI()
        ffi.cdef("""
            /* from stdio.h */
            extern FILE* fopen(const char* path, const char* mode);
            extern int fclose(FILE* fp);
            extern FILE* stderr;  /* GNU C library */
            extern FILE* __stderrp;  /* Mac OS X */
            """)
        stdio = ffi.dlopen(None)
        devnull = stdio.fopen(os.devnull.encode(), b'w')
        try:
            stdio.stderr = devnull
        except KeyError:
            try:
                stdio.__stderrp = devnull
            except KeyError:
                stdio.fclose(devnull)
