#!/usr/bin/env python
import time
import os
import logging
import pyaudio
import sys

from threading import Thread

from kalliope import Utils
from kalliope.core.ConfigurationManager import SettingLoader

from precise_runner import PreciseRunner, ReadWriteStream, PreciseEngine

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig()
logger = logging.getLogger("kalliope")

TOP_DIR = os.path.dirname(os.path.abspath(__file__))
RESOURCE_FILE = os.path.join(TOP_DIR, "precise-engine/precise-engine")

class PreciseEngineNotFound(Exception):
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
                 detected_callback=None
                ):
                 
        super(HotwordDetector, self).__init__()
        sl = SettingLoader()
        self.settings = sl.settings
        self.paused_loop = False
        self.detected_callback = detected_callback
        self.sensitivity = sensitivity
        trigger_level = 3
        self.keyword = keyword
        self.found_keyword = False

        if not os.path.exists(RESOURCE_FILE):
            if self.downloadPreciseEngine():
                Utils.print_info("[Precise] Download complete")
            else:
                raise PreciseEngineNotFound("Error downloading precise engine, check your internet connection or try again later.")

        engine = PreciseEngine(RESOURCE_FILE, self.keyword)

        self.stream = ReadWriteStream()
        self.runner = PreciseRunner(engine,
                                    sensitivity=float(self.sensitivity),
                                    trigger_level=trigger_level,
                                    on_activation=self.activation
                                    )
        
        self.runner.start()
        self.pause()                                    # To avoid that precise starts detecting without beeing ready, we pause it right after start
        if self.settings.machine.startswith("arm"):     # Because importing tensorflow takes up to 10 seconds, we sleep a while
            Utils.print_info("Starting precise trigger")
            time.sleep(10)

    def run(self):
        logger.debug("detecting...")
        while True:
            if not self.paused_loop:
                data = self.stream.read()
                if len(data) > 0:
                    self.stream.write(data)

                if self.found_keyword:
                    self.pause()                          # We start pausing it here, to avoid double activations
                    message = "[Precise] Keyword detected"
                    Utils.print_info(message)
                    logger.debug(message)
                    self.detected_callback()

            time.sleep(0.01)
        logger.debug("finished")


    def activation(self):
        self.found_keyword = True

    def pause(self):
        self.runner.pause()
        self.paused_loop = True

    def unpause(self):
        self.runner.play()
        self.paused_loop = False
        self.found_keyword = False
    
    def downloadPreciseEngine(self):
        import json
        import requests
        import tarfile

        Utils.print_info("[Preicse] Precise engine not present, starting download now")
        url = "https://api.github.com/repos/MycroftAI/mycroft-precise/releases/latest"
        response = requests.get(url)
        if response.status_code == 200:
            download_url = None
            arch = self.settings.machine
            for asset in response.json()["assets"]:
                if arch in asset.get("name"):
                    if asset.get("name").startswith("precise-engine") and asset.get("name").endswith(".tar.gz"):
                        download_name = asset.get("name")
                        download_url = asset.get('browser_download_url')

            filepath = os.path.join(TOP_DIR, download_name)
            if download_url:
                Utils.print_info("[Precise] Downloading %s this can take a moment" % download_name)
                file = requests.get(download_url)
                if file.status_code == 200:
                    with open(filepath, 'wb') as f:
                        f.write(file.content)

                    with tarfile.open(filepath) as tar:
                        tar.extractall(path=TOP_DIR)
                    os.remove(filepath)
                    return True
        return False
